import json
from pathlib import Path
from typing import Any

from config import config


class LiveKitSessionStore:
    def __init__(self):
        self.path = Path(config.KB_STORE_DIR) / "livekit_sessions.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write([])

    def save(self, session: dict[str, Any]) -> None:
        sessions = self._read()
        sessions = [item for item in sessions if item.get("room_name") != session.get("room_name")]
        sessions.append(session)
        self._write(sessions)

    def save_transcript(self, room_name: str, transcript: list[dict]) -> None:
        """
        Appends the voice call transcript to an existing session record.
        Called by voice_agent_worker.py after the call ends.

        Args:
            room_name: The LiveKit room name used to look up the session.
            transcript: List of turn dicts, e.g. [{"role": "Rep", "text": "..."}]
        """
        sessions = self._read()
        updated = False
        for session in sessions:
            if session.get("room_name") == room_name:
                session["voice_transcript"] = transcript
                updated = True
                break
        if not updated:
            # If session record doesn't exist yet, create a minimal stub
            sessions.append({
                "room_name": room_name,
                "voice_transcript": transcript,
            })
        self._write(sessions)

    def get_transcript(self, room_name: str) -> list[dict] | None:
        """
        Returns the voice transcript for a session, or None if not yet captured.
        """
        session = self.get_by_room_name(room_name)
        if session:
            return session.get("voice_transcript")
        return None

    def list_sessions(self) -> list[dict[str, Any]]:
        """Returns all sessions, ordered newest-first."""
        return list(reversed(self._read()))

    def get_by_room_name(self, room_name: str) -> dict[str, Any] | None:
        return next((item for item in self._read() if item.get("room_name") == room_name), None)

    def delete_by_room_name(self, room_name: str) -> None:
        sessions = [item for item in self._read() if item.get("room_name") != room_name]
        self._write(sessions)

    def _read(self) -> list[dict[str, Any]]:
        with self.path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def _write(self, sessions: list[dict[str, Any]]) -> None:
        with self.path.open("w", encoding="utf-8") as file:
            json.dump(sessions, file, indent=2)


livekit_session_store = LiveKitSessionStore()
