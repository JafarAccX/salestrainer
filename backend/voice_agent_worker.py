"""
LiveKit Voice Agent Worker
==========================
Separate process from the FastAPI server. Registers with LiveKit as an
agent worker and handles dispatched voice call jobs.

Run alongside main.py:
    python voice_agent_worker.py start

Required environment variables (read from backend/.env):
    LIVEKIT_URL        - wss://your-project.livekit.cloud
    LIVEKIT_API_KEY    - APIxxxxxxxx
    LIVEKIT_API_SECRET - your-secret
    LIVEKIT_AGENT_NAME - sales-trainer-agent  (must match FastAPI .env)
    ANTHROPIC_API_KEY  - sk-ant-...
    ELEVENLABS_API_KEY - sk_...
    CARTESIA_API_KEY   - your-cartesia-key
"""
import logging
import sys
import os
import json

# Ensure the backend directory is on sys.path when run from any working dir
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import aiohttp
from livekit.agents import (
    Agent,
    AgentSession,
    AutoSubscribe,
    JobContext,
    WorkerOptions,
    cli,
)
# from livekit.plugins import anthropic, cartesia, deepgram, silero
from livekit.plugins import groq, cartesia, deepgram, silero, elevenlabs

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
# Enable DEBUG only for relevant modules; silence HTTP noise
logging.getLogger("livekit.agents").setLevel(logging.DEBUG)
logging.getLogger("livekit.plugins.deepgram").setLevel(logging.DEBUG)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)

from config import config
from core.config_store import config_store
from core.livekit_session_store import livekit_session_store
from core import prompts
from core.rag_engine import rag_engine

# Pre-warm embedding models to prevent blocking the event loop on first use
logger.info("Pre-warming RAG embedding model...")
try:
    _ = rag_engine.embeddings
    logger.info("RAG embedding model pre-warmed successfully.")
except Exception as e:
    logger.warning("Failed to pre-warm RAG embedding model: %s", e)


# OPTIMIZED VAD for better latency and turn-handling (runs locally on CPU, no event loop requirement)
_vad = silero.VAD.load(
    min_silence_duration=0.35,  # Reduced from 0.5 to 0.35 for quicker turnaround response times
    min_speech_duration=0.08,
    activation_threshold=0.35
)


# ── Agent definition ──────────────────────────────────────────────────────────

class SalesTrainerAgent(Agent):
    """
    Voice agent for Tier 3 mock calls.

    Round 1 → AI acts as the counsellor running a live demonstration call.
    Round 2 → AI acts as a realistic prospect; the learner is the counsellor.
    A custom admin persona (if configured) overrides both for Round 2.
    """

    def __init__(
        self,
        kb_context: str = "",
        module_name: str = "",
        round_num: int = 2,
    ) -> None:
        instructions = self._build_instructions(kb_context, module_name, round_num)
        super().__init__(instructions=instructions)

    @staticmethod
    def _build_instructions(kb_context: str, module_name: str, round_num: int) -> str:
        """Return the system prompt for this agent based on round and config."""
        if round_num == 1:
            return prompts.tier3_round1_counsellor(kb_context, module_name)

        # Round 2: prefer a custom admin persona if one is active.
        cfg = config_store.get_config()
        active_agent_id = cfg.get("active_agent_id")
        if active_agent_id:
            agent_data = config_store.get_agent(active_agent_id)
            if agent_data:
                parts = [
                    "Custom Persona Instructions:",
                    agent_data["instructions"],
                    "",
                    "IMPORTANT: Speak naturally, keep replies concise (1-3 sentences), "
                    "no stage directions. Stay in character as the prospect — never coach the rep.",
                ]
                if module_name.strip():
                    parts += ["", f"Product/Course being evaluated:\n{module_name.strip()}"]
                if kb_context.strip():
                    parts += ["", f"Knowledge base context:\n{kb_context.strip()}"]
                return "\n".join(parts)

        return prompts.tier3_round2_prospect(kb_context, module_name)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_job_metadata(raw: str) -> dict:
    """
    Parse job metadata JSON into a normalised dict.
    Falls back to treating the raw string as kb_context for legacy dispatches.
    """
    defaults: dict = {
        "round_num": 2,
        "module_name": "",
        "module_id": "",
        "kb_context": "",
        "agent_instructions": "",
        "agent_llm_settings": {},
    }
    if not raw or not raw.strip():
        return defaults

    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        # Legacy: bare string is treated as kb_context.
        return {**defaults, "kb_context": raw}

    if not isinstance(parsed, dict):
        return {**defaults, "kb_context": raw}

    try:
        round_num = int(parsed.get("round", 2))
    except (TypeError, ValueError):
        round_num = 2

    llm_settings = parsed.get("agent_llm_settings") or {}
    if not isinstance(llm_settings, dict):
        llm_settings = {}

    return {
        "round_num": round_num,
        "module_name": parsed.get("module_name") or "",
        "module_id": parsed.get("module_id") or "",
        "kb_context": parsed.get("kb_context") or "",
        "agent_instructions": parsed.get("agent_instructions") or "",
        "agent_llm_settings": llm_settings,
    }


def _extract_speech_text(ev: object) -> str | None:
    """Pull transcript text from a speech event regardless of attribute name."""
    for attr in ("user_transcript", "agent_transcript", "transcript", "message", "text"):
        value = getattr(ev, attr, None)
        if value and str(value).strip():
            return str(value).strip()
    return None


async def _fetch_kb_context(module_id: str) -> str:
    """Retrieve RAG context for a module; returns empty string on failure."""
    try:
        from core.rag_engine import rag_engine as _rag
        ctx = await _rag.retrieve_context(
            "sales discovery objections product value", top_k=8, module_id=module_id, rerank=False
        )
        logger.info(
            "KB context fetched from local RAG for module %s: %d chars",
            module_id, len(ctx),
        )
        return ctx
    except Exception as exc:
        logger.warning("Failed to fetch KB context for module %s: %s", module_id, exc)
        return ""


async def _save_transcript(room_name: str, transcript_log: list[dict]) -> None:
    """
    Persist the transcript via HTTP callback, with a direct-write fallback.
    Uses aiohttp so we never block the event loop.
    """
    if not transcript_log:
        logger.warning("No transcript captured for room: %s", room_name)
        return

    api_url = f"http://localhost:8000/api/sessions/{room_name}/transcript"
    try:
        async with aiohttp.ClientSession() as http:
            async with http.post(
                api_url,
                json={"transcript": transcript_log},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                resp.raise_for_status()
        logger.info(
            "Transcript saved via HTTP for room %s — %d turns",
            room_name, len(transcript_log),
        )
        return
    except Exception as exc:
        logger.error("HTTP transcript callback failed for room %s: %s", room_name, exc)

    # Fallback: write directly to the session store.
    try:
        livekit_session_store.save_transcript(room_name, transcript_log)
        logger.info("Transcript saved via direct fallback for room %s", room_name)
    except Exception as exc:
        logger.error("Fallback transcript save also failed for room %s: %s", room_name, exc)


# ── Job entrypoint ────────────────────────────────────────────────────────────

async def entrypoint(ctx: JobContext) -> None:
    """
    Called by the LiveKit worker runtime for every dispatched job.

    Flow:
    1. Connect to the LiveKit room (audio only).
    2. Parse KB context / round info from job metadata.
    3. Build the appropriate SalesTrainerAgent.
    4. Start the AgentSession and deliver an opening greeting.
    5. Capture the transcript via session events.
    6. On shutdown, persist the transcript for admin review.
    """
    logger.info("Agent job received -- room: %s", ctx.room.name)

    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    # Log all participants and their track states
    logger.info("Connected to room: %s, participants: %d", ctx.room.name, len(ctx.room.remote_participants))
    for pid, p in ctx.room.remote_participants.items():
        logger.info("  Participant: %s (identity=%s), tracks: %d", pid, p.identity, len(p.track_publications))
        for tid, t in p.track_publications.items():
            logger.info("    Track: %s, kind=%s, source=%s, subscribed=%s, muted=%s",
                       tid, t.kind, t.source, t.subscribed, t.muted)

    # Wait for the human participant to connect
    logger.info("Waiting for participant to join...")
    try:
        participant = await ctx.wait_for_participant()
        logger.info("Participant joined: identity=%s, sid=%s", participant.identity, participant.sid)
        logger.info("  Participant tracks: %d", len(participant.track_publications))
        for tid, t in participant.track_publications.items():
            logger.info("    Track: %s, kind=%s, source=%s, subscribed=%s, muted=%s",
                       tid, t.kind, t.source, t.subscribed, t.muted)
    except Exception as exc:
        logger.error("Error waiting for participant: %s", exc)
        
    # --- Parse metadata ---
    meta = _parse_job_metadata(ctx.job.metadata or "")
    round_num = meta["round_num"]
    module_name = meta["module_name"]
    module_id = meta["module_id"]
    kb_context = meta["kb_context"]
    agent_instructions = meta["agent_instructions"]
    agent_llm_settings = meta["agent_llm_settings"]

    # Fallback to backend singleton if room is a console room or metadata is empty
    is_console = ctx.room.name.startswith("console-") or not (ctx.job.metadata or "").strip()
    if is_console:
        logger.info("Console room detected — querying backend fallback for last dispatched config.")
        try:
            async with aiohttp.ClientSession() as http:
                async with http.get("http://localhost:8000/api/sessions/last-dispatched", timeout=aiohttp.ClientTimeout(total=4)) as resp:
                    if resp.status == 200:
                        fallback_data = await resp.json()
                        logger.info("Successfully loaded fallback config: %s", fallback_data)
                        round_num = int(fallback_data.get("round", 1))
                        module_id = fallback_data.get("module_id") or "ALL"
                        
                        # Resolve module name
                        if module_id and module_id != "ALL":
                            try:
                                from core.document_store import document_store as _doc_store
                                module = _doc_store.get_module(module_id)
                                if module:
                                    module_name = module.get("name", "")
                            except Exception:
                                pass
        except Exception as exc:
            logger.warning("Backend fallback query failed: %s", exc)

    # Fetch KB via RAG if not already embedded in metadata.
    if not kb_context and module_id and not agent_instructions:
        kb_context = await _fetch_kb_context(module_id)

    logger.info(
        "Job metadata — round: %s, module: %r, KB: %d chars, admin agent: %s",
        round_num,
        module_name or "(none)",
        len(kb_context),
        "yes" if agent_instructions else "no",
    )

    # --- Build agent ---
    if agent_instructions.strip():
        agent: Agent = Agent(instructions=agent_instructions)
    else:
        agent = SalesTrainerAgent(
            kb_context=kb_context,
            module_name=module_name,
            round_num=round_num,
        )

    # ORIGINAL ANTHROPIC LLM SETUP (Commented out)
    # --------------------------------------------
    # job_llm = anthropic.LLM(model=config.MODEL_NAME, caching="ephemeral")
    # raw_temp = agent_llm_settings.get("temperature")
    # if raw_temp is not None:
    #     try:
    #         job_llm = anthropic.LLM(model=config.MODEL_NAME, temperature=float(raw_temp), caching="ephemeral")
    #     except (TypeError, ValueError) as exc:
    #         logger.warning("Ignoring invalid temperature setting %r: %s", raw_temp, exc)

    # NEW GROQ LLM SETUP
    # ------------------
    groq_api_key = config.GROQ_API_KEY or os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        logger.error("GROQ_API_KEY is not set in config or environment variables!")
    job_llm = groq.LLM(
        model="llama-3.3-70b-versatile",
        api_key=groq_api_key,
    )
    raw_temp = agent_llm_settings.get("temperature")
    if raw_temp is not None:
        try:
            job_llm = groq.LLM(
                model="llama-3.3-70b-versatile",
                api_key=groq_api_key,
                temperature=float(raw_temp),
            )
        except (TypeError, ValueError) as exc:
            logger.warning("Ignoring invalid temperature setting %r: %s", raw_temp, exc)

    job_stt = None
    if config.DEEPGRAM_API_KEY:
        job_stt = deepgram.STT(
            api_key=config.DEEPGRAM_API_KEY,
            model="nova-3",
            language="en",
        )
        logger.info("Using Deepgram STT (nova-3)")
    else:
        logger.warning("DEEPGRAM_API_KEY not set — STT unavailable.")

    job_tts = None
    tts_provider = getattr(config, "VOICE_TTS_PROVIDER", "cartesia").lower()
    _cartesia_api_key = getattr(config, "CARTESIA_API_KEY", None)
    _elevenlabs_api_key = getattr(config, "ELEVENLABS_API_KEY", None)

    if tts_provider == "elevenlabs" and _elevenlabs_api_key:
        logger.info("Using ElevenLabs TTS")
        job_tts = elevenlabs.TTS(
            api_key=_elevenlabs_api_key,
        )
    elif _cartesia_api_key:
        logger.info("Using Cartesia TTS")
        job_tts = cartesia.TTS(
            api_key=_cartesia_api_key,
            model="sonic-3",
            voice="f786b574-daa5-4673-aa0c-cbe3e8534c02",
            language="en",
        )
    elif _elevenlabs_api_key:
        logger.info("Cartesia not configured or unavailable, falling back to ElevenLabs TTS")
        job_tts = elevenlabs.TTS(
            api_key=_elevenlabs_api_key,
        )
    else:
        logger.warning("No TTS provider API keys configured. TTS will be unavailable.")

    # --- Session ---
    # OPTIMIZED Session configuration for snappier responses and interruptibility
    session: AgentSession = AgentSession(
        llm=job_llm,
        vad=_vad,
        allow_interruptions=True,
        min_endpointing_delay=0.5,
        **({"stt": job_stt} if job_stt is not None else {}),
        **({"tts": job_tts} if job_tts is not None else {}),
    )

    # --- Transcript capture ---
    transcript_log: list[dict] = []

    @session.on("conversation_item_added")
    def on_conversation_item(ev: object) -> None:
        item = getattr(ev, "item", None)
        if not item or not hasattr(item, "role") or not hasattr(item, "text_content"):
            return
        role_str = str(item.role).lower()
        role = "Rep" if "user" in role_str or "rep" in role_str else "Agent"
        text = item.text_content
        if text and text.strip() and text != "<system>":
            # Avoid duplicate logs for identical speaker-text pairs
            if not transcript_log or transcript_log[-1]["text"] != text.strip() or transcript_log[-1]["role"] != role:
                transcript_log.append({"role": role, "text": text.strip()})
                logger.debug("%s said: %s", role, text.strip())

    # --- Shutdown callback ---
    async def save_transcript_on_shutdown() -> None:
        # Fallback: pull from session.history if no events fired.
        history = getattr(session, "history", getattr(session, "_chat_ctx", None))
        if not transcript_log and history:
            logger.info("Falling back to history for transcript capture.")
            messages = history.messages() if callable(history.messages) else getattr(history, "messages", [])
            for msg in messages:
                role_str = str(msg.role).lower()
                role = "Rep" if "user" in role_str or "rep" in role_str else "Agent"
                text = msg.text_content
                if text and text.strip() and text != "<system>":
                    transcript_log.append({"role": role, "text": text.strip()})

        await _save_transcript(ctx.room.name, transcript_log)

    ctx.add_shutdown_callback(save_transcript_on_shutdown)

    # --- Start session ---
    await session.start(agent, room=ctx.room)

    # Round 1 → AI is the counsellor; open with a natural sales opener.
    # Round 2 → AI is the prospect; give a brief, guarded greeting.
    greeting_text = (
        "Hi there! Thanks so much for taking my call today. I'm reaching out "
        "because I help teams like yours get better results, and I'd love to ask "
        "you just a couple of quick questions to see if we're a fit. Is now an okay time?"
        if round_num == 1
        else "Hello? Sure, I have a few minutes. What's this about?"
    )

    try:
        greeting = session.say(greeting_text, allow_interruptions=True)
        await greeting.wait_for_playout()
        logger.info("Round %s greeting delivered — room: %s", round_num, ctx.room.name)
    except Exception as exc:
        logger.warning(
            "Greeting TTS failed (agent will still respond to speech): %s", exc
        )

    logger.info("Round %s mock call session running — room: %s", round_num, ctx.room.name)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name=config.LIVEKIT_AGENT_NAME,
        )
    )
