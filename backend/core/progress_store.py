"""
Progress Store
==============
Tracks each learner's progress through a course's sequential steps:

    tier1  →  tier2  →  tier3  →  evaluation  →  (admin approval)

A step unlocks only when the previous one is marked complete. The final
evaluation is submitted by the learner but must be APPROVED by an admin before
the learner is certified.

Keyed by (sales_rep_id, course_id). File-based (kb_store/progress.json).
"""
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import config


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Ordered steps. Each unlocks when the prior is complete.
STEP_ORDER = ["tier1", "tier2", "tier3", "evaluation"]


def _blank_progress(rep_id: str, course_id: str) -> dict[str, Any]:
    return {
        "sales_rep_id": rep_id,
        "course_id": course_id,
        "steps": {s: {"status": "locked"} for s in STEP_ORDER},
        # approval of the final evaluation: none | pending | approved | rejected
        "approval_status": "none",
        "approval_note": "",
        "certified": False,
        "created_at": _now(),
        "updated_at": _now(),
    }


class ProgressStore:
    def __init__(self):
        self.path = Path(config.KB_STORE_DIR) / "progress.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        if not self.path.exists():
            self._write([])

    def _key(self, rep_id: str, course_id: str) -> tuple[str, str]:
        return (rep_id or "anon", course_id or "default")

    def get(self, rep_id: str, course_id: str) -> dict[str, Any]:
        rep_id, course_id = self._key(rep_id, course_id)
        records = self._read()
        rec = next(
            (r for r in records if r["sales_rep_id"] == rep_id and r["course_id"] == course_id),
            None,
        )
        if not rec:
            rec = _blank_progress(rep_id, course_id)
            # Tier 1 is always unlocked at the start.
            rec["steps"]["tier1"]["status"] = "unlocked"
            records.append(rec)
            self._write(records)
        else:
            rec = self._recompute_locks(rec)
        return rec

    def complete_step(self, rep_id: str, course_id: str, step: str) -> dict[str, Any] | None:
        if step not in STEP_ORDER:
            return None
        with self._lock:
            rep_id, course_id = self._key(rep_id, course_id)
            records = self._read()
            rec = next(
                (r for r in records if r["sales_rep_id"] == rep_id and r["course_id"] == course_id),
                None,
            )
            if not rec:
                rec = _blank_progress(rep_id, course_id)
                rec["steps"]["tier1"]["status"] = "unlocked"
                records.append(rec)

            # Can only complete a step that is unlocked or already complete.
            if rec["steps"][step]["status"] == "locked":
                return self._recompute_locks(rec)  # ignore out-of-order completion

            rec["steps"][step]["status"] = "completed"
            rec["steps"][step]["completed_at"] = _now()

            # Submitting the evaluation puts it into pending admin approval.
            if step == "evaluation" and rec["approval_status"] in ("none", "rejected"):
                rec["approval_status"] = "pending"

            rec["updated_at"] = _now()
            rec = self._recompute_locks(rec)
            self._save_record(records, rec)
            return rec

    def set_approval(self, rep_id: str, course_id: str, decision: str, note: str = "") -> dict[str, Any] | None:
        """decision: 'approved' | 'rejected'. Approved → certified."""
        with self._lock:
            rep_id, course_id = self._key(rep_id, course_id)
            records = self._read()
            rec = next(
                (r for r in records if r["sales_rep_id"] == rep_id and r["course_id"] == course_id),
                None,
            )
            if not rec:
                return None
            rec["approval_status"] = decision
            rec["approval_note"] = note
            rec["certified"] = decision == "approved"
            if decision == "rejected":
                # Send the evaluation back so the learner can retry.
                rec["steps"]["evaluation"]["status"] = "unlocked"
            rec["updated_at"] = _now()
            rec = self._recompute_locks(rec)
            self._save_record(records, rec)
            return rec

    def list_pending_approvals(self) -> list[dict[str, Any]]:
        return [r for r in self._read() if r.get("approval_status") == "pending"]

    def list_all(self) -> list[dict[str, Any]]:
        return self._read()

    # ── Internal ────────────────────────────────────────────────────────────────
    def _recompute_locks(self, rec: dict[str, Any]) -> dict[str, Any]:
        """Unlock the next step after each completed one; keep later steps locked."""
        prev_done = True  # tier1 has no predecessor
        for step in STEP_ORDER:
            status = rec["steps"][step]["status"]
            if status == "completed":
                prev_done = True
                continue
            if prev_done:
                if status == "locked":
                    rec["steps"][step]["status"] = "unlocked"
            else:
                rec["steps"][step]["status"] = "locked"
            prev_done = False
        return rec

    def _save_record(self, records: list[dict[str, Any]], rec: dict[str, Any]) -> None:
        for i, r in enumerate(records):
            if r["sales_rep_id"] == rec["sales_rep_id"] and r["course_id"] == rec["course_id"]:
                records[i] = rec
                break
        else:
            records.append(rec)
        self._write(records)

    def _read(self) -> list[dict[str, Any]]:
        from core.atomic_json import atomic_read
        return atomic_read(self.path)

    def _write(self, records: list[dict[str, Any]]) -> None:
        from core.atomic_json import atomic_write
        atomic_write(self.path, records)


progress_store = ProgressStore()
