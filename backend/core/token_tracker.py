"""
Token Tracker
=============
Logs LLM token usage per session and estimates cost. Implements a SOFT limit:
when a session reaches 90% of its allowance (i.e. only 10% remaining), the
tracker flags `limit_warning` so the UI/evaluation can tell the trainee they
are near the cap. Usage is never hard-blocked — the session continues and the
admin dashboard surfaces the overage.

File-based to match the rest of the app (kb_store/token_usage.json).
"""
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import config


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# Default cost rates (USD). Override via token policy later if needed.
DEFAULT_LLM_COST_PER_1K_USD = 0.003   # blended input+output estimate
DEFAULT_PER_SESSION_TOKEN_LIMIT = 50000
WARN_AT_PERCENT = 90                  # soft warning when 90% used (10% remaining)


class TokenTracker:
    def __init__(self):
        self.path = Path(config.KB_STORE_DIR) / "token_usage.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        if not self.path.exists():
            self._write([])

    def record(
        self,
        session_id: str | None,
        input_tokens: int,
        output_tokens: int,
        course_id: str | None = None,
        user_id: str | None = None,
        per_session_limit: int = DEFAULT_PER_SESSION_TOKEN_LIMIT,
        cost_per_1k_usd: float = DEFAULT_LLM_COST_PER_1K_USD,
    ) -> dict[str, Any]:
        """
        Append a usage log entry and return the running session status,
        including whether the soft 90% warning has been triggered.
        """
        total_tokens = int(input_tokens) + int(output_tokens)
        cost = round((total_tokens / 1000.0) * cost_per_1k_usd, 6)
        sid = session_id or "anonymous"

        with self._lock:
            logs = self._read()
            logs.append({
                "session_id": sid,
                "course_id": course_id,
                "user_id": user_id,
                "input_tokens": int(input_tokens),
                "output_tokens": int(output_tokens),
                "total_tokens": total_tokens,
                "estimated_cost_usd": cost,
                "date": _today(),
                "created_at": _now(),
            })
            self._write(logs)

            session_total = sum(
                e["total_tokens"] for e in logs if e["session_id"] == sid
            )

        used_percent = round((session_total / per_session_limit) * 100, 1) if per_session_limit else 0.0
        remaining = max(per_session_limit - session_total, 0)
        limit_warning = used_percent >= WARN_AT_PERCENT

        return {
            "session_id": sid,
            "session_total_tokens": session_total,
            "per_session_limit": per_session_limit,
            "used_percent": used_percent,
            "remaining_tokens": remaining,
            "limit_warning": limit_warning,
            "warn_at_percent": WARN_AT_PERCENT,
            "last_call_tokens": total_tokens,
            "last_call_cost_usd": cost,
        }

    # ── Aggregations for the admin dashboard ─────────────────────────────────
    def summary(self) -> dict[str, Any]:
        logs = self._read()
        today = _today()
        today_logs = [e for e in logs if e.get("date") == today]
        return {
            "total_tokens_all_time": sum(e["total_tokens"] for e in logs),
            "total_cost_all_time_usd": round(sum(e["estimated_cost_usd"] for e in logs), 4),
            "tokens_today": sum(e["total_tokens"] for e in today_logs),
            "cost_today_usd": round(sum(e["estimated_cost_usd"] for e in today_logs), 4),
            "total_calls": len(logs),
        }

    def by_session(self) -> list[dict[str, Any]]:
        logs = self._read()
        grouped: dict[str, dict[str, Any]] = {}
        for e in logs:
            sid = e["session_id"]
            g = grouped.setdefault(sid, {
                "session_id": sid,
                "course_id": e.get("course_id"),
                "user_id": e.get("user_id"),
                "total_tokens": 0,
                "estimated_cost_usd": 0.0,
                "calls": 0,
            })
            g["total_tokens"] += e["total_tokens"]
            g["estimated_cost_usd"] = round(g["estimated_cost_usd"] + e["estimated_cost_usd"], 6)
            g["calls"] += 1
        return list(grouped.values())

    def by_course(self) -> list[dict[str, Any]]:
        logs = self._read()
        grouped: dict[str, dict[str, Any]] = {}
        for e in logs:
            cid = e.get("course_id") or "unassigned"
            g = grouped.setdefault(cid, {
                "course_id": cid,
                "total_tokens": 0,
                "estimated_cost_usd": 0.0,
                "calls": 0,
            })
            g["total_tokens"] += e["total_tokens"]
            g["estimated_cost_usd"] = round(g["estimated_cost_usd"] + e["estimated_cost_usd"], 6)
            g["calls"] += 1
        return list(grouped.values())

    # ── IO ────────────────────────────────────────────────────────────────────
    def _read(self) -> list[dict[str, Any]]:
        from core.atomic_json import atomic_read
        return atomic_read(self.path)

    def _write(self, logs: list[dict[str, Any]]) -> None:
        from core.atomic_json import atomic_write
        atomic_write(self.path, logs)


token_tracker = TokenTracker()
