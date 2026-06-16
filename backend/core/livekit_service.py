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
from typing import Any

from config import config
from core.livekit_session_store import livekit_session_store
from core.rag_engine import rag_engine


class LiveKitService:
    async def create_mock_call_session(
        self, sales_rep_id: str, module_id: str | None = None
    ) -> dict[str, Any]:
        room_name = f"mock-call-{uuid.uuid4()}"
        participant_identity = sales_rep_id or f"sales-rep-{uuid.uuid4()}"

        # ── 1. Retrieve RAG knowledge base context ────────────────────────────
        kb_context = ""
        if module_id:
            kb_context = rag_engine.retrieve_context(
                "sales discovery objections product value implementation trust",
                top_k=8,
                module_id=module_id,
            )
        if module_id and not kb_context.strip():
            raise ValueError(
                "Knowledge base module has no indexed content for the mock call."
            )

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
                        metadata=kb_context,  # passed to ctx.job.metadata
                    )
                )
                await lkapi.aclose()
                agent_dispatched = True
                print(
                    f"[LiveKitService] Room '{room_name}' created and agent "
                    f"'{config.LIVEKIT_AGENT_NAME}' dispatched successfully."
                )

            except Exception as exc:
                print(
                    f"[LiveKitService] Error during room/dispatch setup: {exc}"
                )

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
            "module_id": module_id,
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
            "livekit_url": config.LIVEKIT_URL,
            "participant_token": participant_token,
            "agent_name": config.LIVEKIT_AGENT_NAME,
            "agent_dispatched": agent_dispatched,
            "module_id": module_id,
            "voice_pipeline": session_record["voice_pipeline"],
            "created_at": session_record["created_at"],
            "frontend_message": frontend_message,
            "connection_link": connection_link,
            "kb_context": kb_context,
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
            print(f"[LiveKitService] Error creating participant token: {exc}")
            return None


livekit_service = LiveKitService()
