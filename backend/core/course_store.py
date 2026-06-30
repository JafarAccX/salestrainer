"""
Course Store
============
JSON-backed CRUD for training Courses. Each course links a KB module, an AI
agent persona, and a per-tier configuration (Tier 1 chat, Tier 2 deep-dive,
Tier 3 voice rounds). Single-tenant, file-based to match the rest of the app.
"""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import config


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_tier_config() -> dict[str, Any]:
    """Sensible defaults matching the PRD §3.5 tier config."""
    return {
        "tier1": {
            "enabled": True,
            "mode": "both",                 # chat_only | reading_only | both
            "max_messages": 25,
            "passing_score": None,          # learning-only, no score
            "requires_approval_to_advance": False,
        },
        "tier2": {
            "enabled": True,
            "min_exchanges_before_advance": 5,
            "max_messages": 30,
            "passing_score": None,
            "requires_approval_to_advance": False,
        },
        "tier3": {
            "enabled": True,
            "round1_enabled": True,         # AI counsellor demo
            "round2_enabled": True,         # user pitches, AI is prospect
            "timer_minutes": 10,
            "max_attempts": 3,
            "passing_score": 7.0,
            "auto_fail_on_hallucination": True,
            "requires_approval_to_pass": True,
        },
    }


class CourseStore:
    def __init__(self):
        self.path = Path(config.KB_STORE_DIR) / "courses.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write([])

    # ── CRUD ──────────────────────────────────────────────────────────────────
    def list_courses(self) -> list[dict[str, Any]]:
        return self._read()

    def get_course(self, course_id: str) -> dict[str, Any] | None:
        return next((c for c in self._read() if c["id"] == course_id), None)

    def create_course(
        self,
        name: str,
        description: str = "",
        kb_module_id: str | None = None,
        agent_id: str | None = None,
        target_audience: str = "",
        passing_score: float = 7.0,
    ) -> dict[str, Any]:
        courses = self._read()
        course = {
            "id": str(uuid.uuid4()),
            "name": name,
            "description": description,
            "status": "draft",              # draft | active | archived
            "kb_module_id": kb_module_id,
            "agent_id": agent_id,
            "target_audience": target_audience,
            "passing_score": passing_score,
            "tier_sequence": ["tier1", "tier2", "tier3"],
            "tier_config": default_tier_config(),
            "approval_required": True,
            "assigned_users": [],
            "created_at": _now(),
            "updated_at": _now(),
        }
        courses.append(course)
        self._write(courses)
        return course

    def update_course(self, course_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        courses = self._read()
        for course in courses:
            if course["id"] == course_id:
                # Only allow known mutable fields
                allowed = {
                    "name", "description", "status", "kb_module_id", "agent_id",
                    "target_audience", "passing_score", "tier_sequence",
                    "tier_config", "approval_required", "assigned_users",
                }
                for key, value in updates.items():
                    if key in allowed and value is not None:
                        course[key] = value
                course["updated_at"] = _now()
                self._write(courses)
                return course
        return None

    def set_status(self, course_id: str, status: str) -> dict[str, Any] | None:
        return self.update_course(course_id, {"status": status})

    def delete_course(self, course_id: str) -> dict[str, Any] | None:
        courses = self._read()
        course = next((c for c in courses if c["id"] == course_id), None)
        if not course:
            return None
        self._write([c for c in courses if c["id"] != course_id])
        return course

    def duplicate_course(self, course_id: str) -> dict[str, Any] | None:
        original = self.get_course(course_id)
        if not original:
            return None
        courses = self._read()
        clone = dict(original)
        clone["id"] = str(uuid.uuid4())
        clone["name"] = f"{original['name']} (Copy)"
        clone["status"] = "draft"
        clone["created_at"] = _now()
        clone["updated_at"] = _now()
        courses.append(clone)
        self._write(courses)
        return clone

    # ── Enrollment ──────────────────────────────────────────────────────────────
    def enroll_user(self, course_id: str, user_id: str) -> dict[str, Any] | None:
        course = self.get_course(course_id)
        if not course:
            return None
        users = set(course.get("assigned_users", []))
        users.add(user_id)
        return self.update_course(course_id, {"assigned_users": list(users)})

    def unenroll_user(self, course_id: str, user_id: str) -> dict[str, Any] | None:
        course = self.get_course(course_id)
        if not course:
            return None
        users = [u for u in course.get("assigned_users", []) if u != user_id]
        return self.update_course(course_id, {"assigned_users": users})

    # ── IO ────────────────────────────────────────────────────────────────────
    def _read(self) -> list[dict[str, Any]]:
        from core.atomic_json import atomic_read
        return atomic_read(self.path)

    def _write(self, courses: list[dict[str, Any]]) -> None:
        from core.atomic_json import atomic_write
        atomic_write(self.path, courses)


course_store = CourseStore()
