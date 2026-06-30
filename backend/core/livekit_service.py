"""
LiveKit Service
===============
Handles room creation, JWT token generation, and explicit agent dispatch
for mock sales call sessions.    
The FastAPI server (main.py) calls create_mock_call_session() when the
user clicks "Start Mock Call".  It creates a LiveKit room, generates a
participant token for the browser, and dispatches a job to the running
voice_agent_worker.py process via the LiveKit Explicit Dispatch API.
The worker receives the job, reads the KB context from job.metadata,
and starts the SalesTrainerAgent inside the room.
"""
import uuid
from datetime import datetime, timezone
import json
import logging
from typing import Any

from config import config
from core.livekit_session_store import livekit_session_store
from core.rag_engine import rag_engine
from core.document_store import document_store

logger = logging.getLogger(__name__)


class LiveKitService:
    def __init__(self) -> None:
        self._last_dispatched = {
            "round": 1,
            "module_id": "ALL",
            "course_id": None,
        }

    def get_last_dispatched(self) -> dict:
        return self._last_dispatched

    async def create_mock_call_session(
        self, sales_rep_id: str, module_id: str | None = None, round_num: int = 2,
        course_id: str | None = None,
    ) -> dict[str, Any]:
        room_name = f"mock-call-{uuid.uuid4()}"
        participant_identity = sales_rep_id or f"sales-rep-{uuid.uuid4()}"

        # ── 1. Retrieve RAG knowledge base context ────────────────────────────
        kb_context = ""
        if module_id:
            kb_context = await rag_engine.retrieve_context(
                "sales discovery objections product value implementation trust",
                top_k=8,
                module_id=module_id,
                rerank=False,
            )
        if module_id and not kb_context.strip():
            raise ValueError(
                "Knowledge base module has no indexed content for the mock call."
            )

        # Resolve the module display name for the agent prompt
        module_name = ""
        if module_id:
            module = document_store.get_module(module_id)
            if module:
                module_name = module.get("name", "")

        # Resolve the agent behaviour for this call. Resolution order:
        #   1. The COURSE's configured agent_id (per-course persona).
        #   2. The global active_agent_id (legacy default).
        # If neither resolves to a real agent, the voice worker falls back to
        # the built-in prospect prompt.
        agent_instructions = ""
        agent_llm_settings: dict[str, Any] = {}
        try:
            from core.config_store import config_store
            from core.agent_store import agent_store
            from core.course_store import course_store

            resolved_agent_id: str | None = None
            if round_num == 2:
                if course_id:
                    course = course_store.get_course(course_id)
                    if course:
                        # 1a. Native embedded Course persona
                        if course.get("custom_agent_instructions") or course.get("custom_objections"):
                            base_inst = course.get("custom_agent_instructions", "")
                            objs = course.get("custom_objections") or []
                            obj_str = "\n".join([f"- {o}" for o in objs])
                            agent_instructions = (
                                f"Custom Persona Instructions:\n{base_inst}\n\n"
                                f"Objections to raise natively:\n{obj_str}\n\n"
                                "IMPORTANT: Speak naturally, keep replies concise (1-3 sentences), "
                                "no stage directions. Stay in character as the prospect — never coach the rep."
                            )
                            if module_name.strip():
                                agent_instructions += f"\n\nProduct/Course being evaluated:\n{module_name.strip()}"
                            if kb_context.strip():
                                agent_instructions += f"\n\nKnowledge base context:\n{kb_context.strip()}"
                        
                        # 1b. Linked Agent Persona
                        if not agent_instructions and course.get("agent_id"):
                            resolved_agent_id = course["agent_id"]

                # 2. Global active agent fallback
                if not agent_instructions and not resolved_agent_id:
                    # If "All Courses" mode, try the all_courses_agent_id fallback
                    cfg = config_store.get_config()
                    if module_id == "ALL" and cfg.get("all_courses_agent_id"):
                        resolved_agent_id = cfg["all_courses_agent_id"]
                    elif cfg.get("active_agent_id"):
                        resolved_agent_id = cfg["active_agent_id"]

                if not agent_instructions and resolved_agent_id:
                    agent_cfg = agent_store.get_agent(resolved_agent_id)
                    if agent_cfg and agent_cfg.get("tier3_round2_enabled", True):
                        agent_instructions = agent_store.build_instructions(
                            agent_cfg, kb_context=kb_context, module_name=module_name
                        )
                        agent_llm_settings = agent_cfg.get("llm_settings") or {}
        except Exception as exc:
            logger.warning("Agent behaviour resolution failed (non-fatal): %s", exc)

        # Build structured metadata. KB context is NOT included (too large for
        # LiveKit metadata limits). The worker fetches it via HTTP instead.
        job_metadata = json.dumps({
            "round": round_num,
            "course_id": course_id or "",
            "module_id": module_id or "",
            "module_name": module_name,
            "agent_instructions": agent_instructions,
            "agent_llm_settings": agent_llm_settings,
        })

        # ── 2. Build participant JWT (for the browser / frontend) ─────────────
        participant_token = self._build_participant_token(
            room_name, participant_identity
        )

        # ── 3. LiveKit server interaction (room + agent dispatch) ─────────────
        agent_dispatched = False
        if config.LIVEKIT_URL and config.LIVEKIT_API_KEY and config.LIVEKIT_API_SECRET:
            try:
                from livekit import api

                http_url = (
                    config.LIVEKIT_URL.replace("wss://", "https://")
                    .replace("ws://", "http://")
                )
                lkapi = api.LiveKitAPI(
                    http_url, config.LIVEKIT_API_KEY, config.LIVEKIT_API_SECRET
                )

                # Create the room first
                await lkapi.room.create_room(
                    api.CreateRoomRequest(name=room_name)
                )

                # Dispatch a job to the voice_agent_worker.py process.
                # The KB context is passed via job metadata so the worker
                # can build a personalised SalesTrainerAgent without hitting
                # the database again.
                await lkapi.agent_dispatch.create_dispatch(
                    api.CreateAgentDispatchRequest(
                        agent_name=config.LIVEKIT_AGENT_NAME,
                        room=room_name,
                        metadata=job_metadata,  # JSON: round, module_name, kb_context
                    )
                )
                await lkapi.aclose()
                agent_dispatched = True
                logger.info(
                    "Room '%s' created and agent '%s' dispatched.",
                    room_name, config.LIVEKIT_AGENT_NAME,
                )

            except Exception as exc:
                logger.error("Error during room/dispatch setup: %s", exc)

        # Store last dispatched session info for fallback query
        self._last_dispatched = {
            "round": round_num,
            "module_id": module_id or "ALL",
            "course_id": course_id,
        }

        # ── 4. Build the connection link for the frontend ─────────────────────
        # Include url + token as query params so the LiveKit playground
        # auto-connects without the user needing to paste credentials.
        playground_base = (
            config.LIVEKIT_PLAYGROUND_URL or "https://agents-playground.livekit.io/"
        ).rstrip("/")
        connection_link = playground_base
        if participant_token and config.LIVEKIT_URL:
            connection_link = (
                f"{playground_base}?"
                f"url={config.LIVEKIT_URL}&token={participant_token}"
            )

        # ── 5. Persist session record ─────────────────────────────────────────
        session_record: dict[str, Any] = {
            "session_id": str(uuid.uuid4()),
            "room_name": room_name,
            "participant_identity": participant_identity,
            "course_id": course_id,
            "module_id": module_id,
            "module_name": module_name,
            "round": round_num,
            "sales_rep_id": sales_rep_id,
            "kb_context": kb_context,
            "voice_pipeline": {
                "transport": "livekit",
                "stt": config.VOICE_STT_PROVIDER,
                "llm": config.MODEL_NAME,
                "tts": config.VOICE_TTS_PROVIDER,
            },
            "agent_dispatched": agent_dispatched,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        livekit_session_store.save(session_record)

        # ── 6. Return response to FastAPI ─────────────────────────────────────
        frontend_message = (
            "Agent dispatched. Open the connection link to join the call."
            if agent_dispatched
            else (
                "LiveKit credentials are configured but agent dispatch failed. "
                "Open the connection link, then ensure voice_agent_worker.py is running."
            )
        )
        if not config.LIVEKIT_URL:
            frontend_message = (
                "LiveKit is not configured. Set LIVEKIT_URL, LIVEKIT_API_KEY, "
                "and LIVEKIT_API_SECRET in backend/.env, then start voice_agent_worker.py."
            )

        return {
            "session_id": session_record["session_id"],
            "room_name": room_name,
            "participant_identity": participant_identity,
            "course_id": course_id,
            "module_id": module_id,
            "livekit_url": config.LIVEKIT_URL,
            "participant_token": participant_token,
            "agent_name": config.LIVEKIT_AGENT_NAME,
            "agent_dispatched": agent_dispatched,
            "module_id": module_id,
            "voice_pipeline": session_record["voice_pipeline"],
            "created_at": session_record["created_at"],
            "frontend_message": frontend_message,
            "connection_link": connection_link,
        }

    # ── Token helpers ─────────────────────────────────────────────────────────

    def _build_participant_token(self, room_name: str, identity: str) -> str | None:
        """Generates a JWT for a human participant (the sales rep in the browser)."""
        if not config.LIVEKIT_API_KEY or not config.LIVEKIT_API_SECRET:
            return None
        try:
            from livekit import api

            token = (
                api.AccessToken(config.LIVEKIT_API_KEY, config.LIVEKIT_API_SECRET)
                .with_identity(identity)
                .with_name(identity)
                .with_grants(
                    api.VideoGrants(
                        room_join=True,
                        room=room_name,
                        can_publish=True,
                        can_subscribe=True,
                        can_publish_data=True,
                    )
                )
            )
            return token.to_jwt()
        except Exception as exc:
            logger.error("Error creating participant token: %s", exc)
            return None


livekit_service = LiveKitService()
