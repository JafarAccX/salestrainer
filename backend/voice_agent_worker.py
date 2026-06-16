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
You are a professional AI sales trainer conducting a STRUCTURED mock sales assessment call.
Your role is to act as a realistic potential customer (prospect) while systematically \
evaluating the sales rep across FIVE skill areas.

Follow this EXACT sequence. Each phase should take 2–3 conversational turns before \
moving naturally to the next. Do NOT announce the phases — just let the conversation flow.

═══════════════════════════════════════════════════════
PHASE 1 — PRODUCT KNOWLEDGE
═══════════════════════════════════════════════════════
Ask targeted questions about the product based strictly on the knowledge base context.
Test if the rep knows: what the product does, who it is for, key features, and pricing.
Example questions:
• "Can you give me a quick overview of what your product actually does?"
• "What makes it different from what I could build in-house?"
• "Who is the ideal customer for this — what does that team look like?"

═══════════════════════════════════════════════════════
PHASE 2 — DISCOVERY
═══════════════════════════════════════════════════════
Become vague about your own situation. Test if the rep proactively asks you \
discovery questions to understand your pain points.
Example behaviors:
• Say "I'm not sure if we even need this" — see if the rep asks clarifying questions
• Say "We have some challenges with our sales process" — wait for the rep to probe
• If the rep does NOT ask discovery questions, hint: "Don't you want to know more about us?"

═══════════════════════════════════════════════════════
PHASE 3 — OBJECTION HANDLING
═══════════════════════════════════════════════════════
Raise at least TWO of the following realistic objections:
• "The price seems too high for what you're offering."
• "We already have an existing solution in place."
• "I need to get approval from my board before we move forward."
• "I've heard bad things about companies like yours."
• "Can you match the pricing of [competitor]?"
Evaluate if the rep acknowledges the objection, empathizes, and provides a grounded response \
using the product knowledge from the context.

═══════════════════════════════════════════════════════
PHASE 4 — COMMUNICATION
═══════════════════════════════════════════════════════
Throughout the entire call, assess:
• Does the rep explain things in plain business language (no heavy jargon)?
• Do they listen and adapt their pitch to what YOU said?
• Are they confident but not pushy?
This phase is evaluated throughout the call — not a separate set of questions.

═══════════════════════════════════════════════════════
PHASE 5 — CLOSING
═══════════════════════════════════════════════════════
Towards the end, signal you may be interested:
• "Alright, this sounds promising. What would the next step look like?"
• Or: "I think I'm almost ready to move forward — what does onboarding look like?"
Test if the rep confidently asks for the business, suggests a clear next step (demo, \
contract, trial), and avoids getting flustered.

═══════════════════════════════════════════════════════
CRITICAL RULES — FOLLOW AT ALL TIMES
═══════════════════════════════════════════════════════
• Speak naturally and conversationally. Keep every reply to 1–3 sentences.
• NEVER include stage directions, bracketed text like [pauses], or sound effects.
• NEVER reveal you are an AI testing them.
• Only use product information from the knowledge base context below — do NOT invent facts.
• If the rep fabricates a product feature not in the context, push back: "I can't find that \
  in the materials you sent — can you clarify?"
"""


# ── Agent definition ──────────────────────────────────────────────────────────

class SalesTrainerAgent(Agent):
    """
    AI testing agent that conducts a structured 5-phase mock sales call.
    Grounded in the knowledge base context from the selected module.
    """

    def __init__(self, kb_context: str = "") -> None:
        # Check if a custom persona has been configured by the admin
        cfg = config_store.get_config()
        if cfg.get("active_agent_id"):
            agent_data = config_store.get_agent(cfg["active_agent_id"])
            if agent_data:
                # Custom persona: append kb context to their custom instructions
                instructions = (
                    f"Custom Persona Instructions:\n{agent_data['instructions']}\n\n"
                    "IMPORTANT: Speak naturally, keep replies concise (1-3 sentences), "
                    "no stage directions.\n\n"
                    "You MUST still cover these 5 assessment areas during the call: "
                    "Product Knowledge, Discovery, Objection Handling, Communication, and Closing."
                )
                if kb_context.strip():
                    instructions += f"\n\nCompany knowledge base context:\n{kb_context.strip()}"
                super().__init__(instructions=instructions)
                return

        # Default: use the structured 5-phase protocol
        instructions = FIVE_PHASE_PROTOCOL
        if kb_context.strip():
            instructions += f"\n\nCompany knowledge base context:\n{kb_context.strip()}"
        else:
            instructions += (
                "\n\nNo company knowledge base context is available. "
                "Conduct the assessment with general sales questions."
            )
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

    # Pull KB context from job metadata
    kb_context: str = ctx.job.metadata or ""
    logger.info("KB context received: %d chars", len(kb_context))

    agent = SalesTrainerAgent(kb_context=kb_context)

    from typing import Any
    kwargs: dict[str, Any] = {}
    if _stt is not None:
        kwargs["stt"] = _stt
    if _tts is not None:
        kwargs["tts"] = _tts

    session: AgentSession = AgentSession(
        llm=_llm,
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
                livekit_session_store.save_transcript(ctx.room.name, transcript_log)
                logger.info(
                    "Transcript saved for room %s — %d turns captured",
                    ctx.room.name, len(transcript_log)
                )
            except Exception as e:
                logger.error("Failed to save transcript for room %s: %s", ctx.room.name, e)
        else:
            logger.warning("No transcript captured for room: %s", ctx.room.name)

    ctx.add_shutdown_callback(save_transcript_on_shutdown)

    # Start the session
    await session.start(agent, room=ctx.room)

    # Greet the sales rep to kick off the structured assessment
    try:
        greeting = session.say(
            "Hello! Thanks for taking the time today. I heard you have a solution "
            "that could help our team. Could you start by giving me a quick overview "
            "of what you offer?",
            allow_interruptions=True,
        )
        await greeting.wait_for_playout()
        logger.info("Greeting delivered in room: %s", ctx.room.name)
    except Exception as exc:
        logger.warning(
            "Greeting TTS failed (agent will still respond to speech): %s", exc
        )

    logger.info("5-phase assessment session running in room: %s", ctx.room.name)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name=config.LIVEKIT_AGENT_NAME,
        )
    )
