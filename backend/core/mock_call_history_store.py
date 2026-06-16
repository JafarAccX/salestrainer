from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import config


class MockCallHistoryStore:
    def __init__(self):
        self.path = Path(config.KB_STORE_DIR) / "mock_call_history.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write([])

    def add(self, record: dict[str, Any]) -> dict[str, Any]:
        records = self._read()
        stored = {
            "id": record.get("id") or self._timestamp_id(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            **record,
        }
        records.append(stored)
        self._write(records)
        return stored

    def list(self, module_id: str | None = None, session_id: str | None = None) -> list[dict[str, Any]]:
        records = self._read()
        if module_id is not None:
            records = [item for item in records if item.get("module_id") == module_id]
        if session_id is not None:
            records = [item for item in records if item.get("session_id") == session_id]
        return records

    def _read(self) -> list[dict[str, Any]]:
        with self.path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def _write(self, records: list[dict[str, Any]]) -> None:
        with self.path.open("w", encoding="utf-8") as file:
            json.dump(records, file, indent=2)

    def _timestamp_id(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")


mock_call_history_store = MockCallHistoryStore()
