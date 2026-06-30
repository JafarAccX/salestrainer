"""
LiveKit Voice Agent Worker
==========================
This is a SEPARATE process from the FastAPI server.
It registers with the LiveKit server as an agent worker and
handles dispatched voice call jobs using the JobContext pattern.

Run this in a second terminal ALONGSIDE main.py:
    python voice_agent_worker.py start

Environment variables required (read from backend/.env automatically):
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

# Ensure the backend directory is on sys.path when run from any working dir
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from livekit.agents import (
    Agent,
    AgentSession,
    AutoSubscribe,
    JobContext,
    WorkerOptions,
    cli,
)
from livekit.plugins import anthropic, cartesia, elevenlabs, silero

from config import config
from core.config_store import config_store
from core.livekit_session_store import livekit_session_store
from core import prompts
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ── Plugin registration (MUST happen on the main thread at import time) ───────
_llm = anthropic.LLM(model=config.MODEL_NAME)

_stt: elevenlabs.STT | None = None
if config.ELEVENLABS_API_KEY:
    _stt = elevenlabs.STT(api_key=config.ELEVENLABS_API_KEY)
else:
    logger.warning("ELEVENLABS_API_KEY not set — STT will be unavailable.")

_tts: cartesia.TTS | None = None
_cartesia_api_key = getattr(config, 'CARTESIA_API_KEY', None)
if _cartesia_api_key:
    _tts = cartesia.TTS(
        api_key=_cartesia_api_key,
        model="sonic-3",
        voice="f786b574-daa5-4673-aa0c-cbe3e8534c02",
        language="en",
    )
else:
    logger.warning(
        "CARTESIA_API_KEY not set — TTS will be unavailable. "
        "Get a free key at https://cartesia.ai and add to backend/.env"
    )

_vad = silero.VAD.load()


# ── Five-Phase Testing Protocol ───────────────────────────────────────────────

FIVE_PHASE_PROTOCOL = """\
You are a realistic potential customer (prospect) on a sales call. You are secretly \
evaluating the sales rep across five skill areas while acting as a natural, somewhat \
skeptical buyer.

INTERNAL STATE TRACKING:
- You have an internal phase counter starting at Phase 1.
- Advance to the next phase after 2-3 exchanges OR when the rep has clearly demonstrated \
  (or failed at) the current skill.
- TRANSITION SIGNALS: Use natural bridging lines to shift topics. Examples:
  "Okay, that makes sense. So let me ask you..." (Phase 1→2)
  "Right, but here's my concern..." (Phase 2→3)
  "Alright, I appreciate that. So where do we go from here?" (Phase 3→5)

═══════════════════════════════════════════════════════
PHASE 1 — PRODUCT KNOWLEDGE (2-3 turns)
═══════════════════════════════════════════════════════
You are an interested but uninformed buyer. Ask about:
• What the product does in simple terms
• Who it's built for
• What makes it different from alternatives
GROUNDING: You know the product info from the KB below. If the rep says something NOT \
in the KB, challenge them: "Hmm, I don't see that mentioned anywhere — where did you get that?"

═══════════════════════════════════════════════════════
PHASE 2 — DISCOVERY (2-3 turns)
═══════════════════════════════════════════════════════
Become deliberately vague. Give incomplete answers. Test if the rep ASKS you questions.
• "We have some issues with [relevant pain point from KB], but I'm not sure this is the fix."
• "My team is small, I don't know if we're the right fit."
If the rep just pitches without asking about YOUR situation, after 2 turns say: \
"You haven't really asked about our specific situation though."

═══════════════════════════════════════════════════════
PHASE 3 — OBJECTION HANDLING (2-3 turns)
═══════════════════════════════════════════════════════
Raise exactly TWO objections, one at a time. Choose from:
• Price: "Honestly, this sounds expensive for what it is."
• Competition: "We've been looking at [competitor category] too — why should I pick you?"
• Authority: "I'd need to run this by my VP. What would you tell them?"
• Trust: "How do I know this will actually work for us?"
Wait for a response to the first before raising the second.

═══════════════════════════════════════════════════════
PHASE 4 — COMMUNICATION (assessed throughout)
═══════════════════════════════════════════════════════
Not a separate phase with turns. Continuously note:
• Is the rep listening and adapting?
• Plain language vs jargon?
• Confident without being pushy?

═══════════════════════════════════════════════════════
PHASE 5 — CLOSING (1-2 turns)
═══════════════════════════════════════════════════════
Signal buying intent: "Alright, I'm fairly convinced. What happens next?"
Test if the rep proposes a concrete next step with a timeline.
After their close attempt, wrap up naturally: "Great, let me think on it. Thanks for your time."

═══════════════════════════════════════════════════════
ABSOLUTE RULES
═══════════════════════════════════════════════════════
• 1-2 sentences per reply. Never more than 3 sentences. Sound human.
• NO stage directions, [brackets], asterisks, or meta-commentary.
• NEVER reveal you are AI or that you are testing them.
• ONLY reference product facts from the knowledge base context below.
• If the rep invents features not in the context, push back naturally.
• If the rep asks YOU a discovery question, answer honestly based on a plausible persona \
  (mid-size company, 20-50 employees, some budget flexibility).
• End the call naturally after Phase 5 — do not loop back.
"""


# ── Agent definition ──────────────────────────────────────────────────────────

class SalesTrainerAgent(Agent):
    """
    Voice agent for Tier 3 mock calls.

    Round 1 → AI acts as the Counsellor running a live demonstration call.
    Round 2 → AI acts as a realistic Prospect; the learner is the counsellor.
    A custom admin persona (if configured) overrides both for Round 2.
    """

    def __init__(self, kb_context: str = "", module_name: str = "", round_num: int = 2) -> None:
        # Round 1: AI demonstrates the perfect sales call (no custom persona)
        if round_num == 1:
            instructions = prompts.tier3_round1_counsellor(kb_context, module_name)
            super().__init__(instructions=instructions)
            return

        # Round 2: check for a custom admin persona first
        cfg = config_store.get_config()
        if cfg.get("active_agent_id"):
            agent_data = config_store.get_agent(cfg["active_agent_id"])
            if agent_data:
                instructions = (
                    f"Custom Persona Instructions:\n{agent_data['instructions']}\n\n"
                    "IMPORTANT: Speak naturally, keep replies concise (1-3 sentences), "
                    "no stage directions. Stay in character as the prospect — never coach the rep."
                )
                if module_name.strip():
                    instructions += f"\n\nProduct/Course being evaluated:\n{module_name.strip()}"
                if kb_context.strip():
                    instructions += f"\n\nKnowledge base context:\n{kb_context.strip()}"
                super().__init__(instructions=instructions)
                return

        # Round 2 default: realistic prospect
        instructions = prompts.tier3_round2_prospect(kb_context, module_name)
        super().__init__(instructions=instructions)


# ── Job entrypoint ────────────────────────────────────────────────────────────

async def entrypoint(ctx: JobContext) -> None:
    """
    Called by the LiveKit worker runtime for every dispatched job.

    Flow:
    1. Connect to the LiveKit room (audio only).
    2. Read KB context from job metadata (set by FastAPI at dispatch time).
    3. Create the 5-phase SalesTrainerAgent.
    4. Start the session — agent listens and conducts the structured assessment.
    5. Capture the conversation transcript in real-time.
    6. On shutdown, save the transcript to the session store for admin review.
    """
    logger.info("Agent job received – room: %s", ctx.room.name)

    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    # Pull job metadata. New format is JSON {round, module_name, kb_context,
    # agent_instructions, agent_llm_settings}; fall back to treating the raw
    # string as kb_context for older dispatches.
    raw_metadata: str = ctx.job.metadata or ""
    round_num = 2
    module_name = ""
    module_id = ""
    kb_context = ""
    agent_instructions = ""
    agent_llm_settings: dict = {}
    try:
        parsed = json.loads(raw_metadata) if raw_metadata.strip() else {}
        if isinstance(parsed, dict):
            round_num = int(parsed.get("round", 2))
            module_name = parsed.get("module_name", "") or ""
            module_id = parsed.get("module_id", "") or ""
            agent_instructions = parsed.get("agent_instructions", "") or ""
            agent_llm_settings = parsed.get("agent_llm_settings") or {}
        else:
            kb_context = raw_metadata
    except (json.JSONDecodeError, ValueError, TypeError):
        kb_context = raw_metadata

    # Fetch KB context from the local RAG engine (avoids LiveKit metadata size limits).
    if not kb_context and module_id and not agent_instructions:
        try:
            from core.rag_engine import rag_engine as _rag
            kb_context = _rag.retrieve_context(
                "sales discovery objections product value", top_k=8, module_id=module_id
            )
            logger.info("KB context fetched from local RAG for module %s: %d chars", module_id, len(kb_context))
        except Exception as e:
            logger.warning("Failed to fetch KB context for module %s: %s", module_id, e)

    logger.info(
        "Job metadata parsed — round: %s, module: %s, KB: %d chars, admin agent: %s",
        round_num, module_name or "(none)", len(kb_context),
        "yes" if agent_instructions else "no",
    )

    # If the admin configured a behaviour for this agent, use its compiled
    # instructions directly; otherwise fall back to the default round prompts.
    if agent_instructions.strip():
        agent = Agent(instructions=agent_instructions)
    else:
        agent = SalesTrainerAgent(
            kb_context=kb_context, module_name=module_name, round_num=round_num
        )

    # Apply admin LLM sampling settings (temperature) for this job if provided.
    job_llm = _llm
    try:
        temp = agent_llm_settings.get("temperature") if agent_llm_settings else None
        if temp is not None:
            job_llm = anthropic.LLM(model=config.MODEL_NAME, temperature=float(temp))
    except Exception as exc:
        logger.warning("Could not apply admin LLM settings: %s", exc)

    from typing import Any
    kwargs: dict[str, Any] = {}
    if _stt is not None:
        kwargs["stt"] = _stt
    if _tts is not None:
        kwargs["tts"] = _tts

    session: AgentSession = AgentSession(
        llm=job_llm,
        vad=_vad,
        **kwargs
    )

    # ── Transcript capture ────────────────────────────────────────────────────
    transcript_log: list[dict] = []

    # Hook into session events for real-time transcript capture
    try:
        @session.on("user_speech_committed")
        def on_user_speech(ev: Any) -> None:
            text = (
                getattr(ev, 'user_transcript', None)
                or getattr(ev, 'transcript', None)
                or getattr(ev, 'text', None)
            )
            if text and str(text).strip():
                transcript_log.append({"role": "Rep", "text": str(text).strip()})
                logger.debug("Rep said: %s", text)
    except Exception as e:
        logger.warning("Could not hook user_speech_committed: %s", e)

    try:
        @session.on("agent_speech_committed")
        def on_agent_speech(ev: Any) -> None:
            text = (
                getattr(ev, 'agent_transcript', None)
                or getattr(ev, 'transcript', None)
                or getattr(ev, 'message', None)
                or getattr(ev, 'text', None)
            )
            if text and str(text).strip():
                transcript_log.append({"role": "Agent", "text": str(text).strip()})
                logger.debug("Agent said: %s", text)
    except Exception as e:
        logger.warning("Could not hook agent_speech_committed: %s", e)

    # ── Shutdown callback: save transcript ────────────────────────────────────
    async def save_transcript_on_shutdown() -> None:
        """
        Saves the captured voice call transcript to the session store.
        Falls back to reading from session.chat_ctx if event-based capture failed.
        """
        try:
            # Fallback: try to pull from the session's chat context if no events fired
            if not transcript_log and hasattr(session, 'chat_ctx') and session.chat_ctx:
                logger.info("Falling back to chat_ctx for transcript capture")
                for msg in session.chat_ctx.messages:
                    role_str = str(msg.role).lower()
                    role = "Rep" if role_str == "user" else "Agent"
                    content = msg.content if isinstance(msg.content, str) else str(msg.content)
                    if content.strip() and content != "<system>":
                        transcript_log.append({"role": role, "text": content.strip()})
        except Exception as e:
            logger.warning("Failed to extract chat_ctx transcript: %s", e)

        if transcript_log:
            try:
                import requests
                api_url = f"http://localhost:8000/api/sessions/{ctx.room.name}/transcript"
                resp = requests.post(api_url, json={"transcript": transcript_log}, timeout=10)
                resp.raise_for_status()
                logger.info(
                    "Transcript saved via HTTP callback for room %s — %d turns",
                    ctx.room.name, len(transcript_log)
                )
            except Exception as e:
                logger.error("HTTP transcript callback failed for room %s: %s", ctx.room.name, e)
                # Fallback: direct write if HTTP fails
                try:
                    livekit_session_store.save_transcript(ctx.room.name, transcript_log)
                    logger.info("Transcript saved via direct fallback for room %s", ctx.room.name)
                except Exception as fe:
                    logger.error("Fallback transcript save also failed: %s", fe)
        else:
            logger.warning("No transcript captured for room: %s", ctx.room.name)

    ctx.add_shutdown_callback(save_transcript_on_shutdown)

    # Start the session
    await session.start(agent, room=ctx.room)

    # Round-aware kickoff:
    #  • Round 1: AI is the counsellor — begin the demonstration call immediately.
    #  • Round 2: AI is the prospect — give a short, guarded greeting and wait.
    if round_num == 1:
        greeting_text = (
            "Hi there! Thanks so much for taking my call today. I'm reaching out "
            "because I help teams like yours get better results, and I'd love to ask "
            "you just a couple of quick questions to see if we're a fit. Is now an okay time?"
        )
    else:
        greeting_text = (
            "Hello? Sure, I have a few minutes. What's this about?"
        )

    try:
        greeting = session.say(greeting_text, allow_interruptions=True)
        await greeting.wait_for_playout()
        logger.info("Round %s greeting delivered in room: %s", round_num, ctx.room.name)
    except Exception as exc:
        logger.warning(
            "Greeting TTS failed (agent will still respond to speech): %s", exc
        )

    logger.info("Round %s mock call session running in room: %s", round_num, ctx.room.name)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name=config.LIVEKIT_AGENT_NAME,
        )
    )
