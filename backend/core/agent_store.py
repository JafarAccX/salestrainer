"""
Agent Store
===========
Admin-configurable AI agent personas (PRD §3.2). Each agent defines a prospect
persona, difficulty, the objections it raises, LLM sampling settings, and
conversation rules. `build_instructions()` compiles all of this into a single
voice-agent prompt used in Tier 3 Round 2.

Difficulty presets (easy/medium/hard) auto-fill behaviour; "custom" lets the
admin write raw instructions directly. File-based to match the app.
"""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import config


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Difficulty presets (PRD §3.2.3) ───────────────────────────────────────────
DIFFICULTY_PRESETS: dict[str, dict[str, Any]] = {
    "easy": {
        "description": "Friendly prospect, raises 1 objection, opens up after 1 good question.",
        "num_objections": 1,
        "warmup_threshold": 1,
        "behaviour": (
            "You are a FRIENDLY, open prospect. You are genuinely interested and easy to "
            "talk to. Raise only ONE objection during the call, and accept a reasonable "
            "answer gracefully. Warm up quickly after the rep asks even one good question."
        ),
    },
    "medium": {
        "description": "Neutral prospect, raises 2 objections, needs 2 good answers to warm up.",
        "num_objections": 2,
        "warmup_threshold": 2,
        "behaviour": (
            "You are a NEUTRAL, professional prospect. Raise TWO objections during the call, "
            "one at a time. You need at least two good discovery questions or solid answers "
            "before you warm up and show real interest."
        ),
    },
    "hard": {
        "description": "Guarded prospect, raises 3 objections, pushes back on everything.",
        "num_objections": 3,
        "warmup_threshold": 3,
        "behaviour": (
            "You are a GUARDED, skeptical prospect who has been burned before. Raise THREE "
            "objections and push back firmly on weak answers. You will NOT warm up unless the "
            "rep handles your objections with specific, knowledge-base-backed proof. Be "
            "demanding but fair."
        ),
    },
}

AVAILABLE_OBJECTIONS = ["budget", "timing", "competitor", "trust", "roi", "security"]

OBJECTION_LINES = {
    "budget": "Honestly, we've already spent our budget for this quarter.",
    "timing": "We're in the middle of a big project right now — maybe in a few months?",
    "competitor": "We tried something similar last year and it didn't work out. What makes yours different?",
    "trust": "How do I know this will actually work for a team like ours?",
    "roi": "I'm not convinced the return justifies the cost. Can you prove the ROI?",
    "security": "What about data security and compliance? That's a big concern for us.",
}


def default_llm_settings() -> dict[str, Any]:
    return {"temperature": 0.7, "max_tokens": 512}


def default_conversation_rules() -> dict[str, Any]:
    return {
        "max_turns_before_decision": 12,
        "allow_hints": False,
        "auto_end_on_poor_performance": True,
        "poor_performance_threshold": 3,
    }


def default_prospect_profile() -> dict[str, Any]:
    return {
        "role": "Operations Manager",
        "company_size": "200-500 employees",
        "pain_points": [],
        "objections": ["budget", "timing"],
        "warmup_threshold": 2,
    }


class AgentStore:
    def __init__(self):
        self.path = Path(config.KB_STORE_DIR) / "agents.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write([])

    # ── CRUD ──────────────────────────────────────────────────────────────────
    def list_agents(self) -> list[dict[str, Any]]:
        return self._read()

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        return next((a for a in self._read() if a["id"] == agent_id), None)

    def create_agent(self, data: dict[str, Any]) -> dict[str, Any]:
        agents = self._read()
        difficulty = data.get("difficulty", "medium")
        agent = {
            "id": str(uuid.uuid4()),
            "name": data.get("name", "Untitled Agent"),
            "description": data.get("description", ""),
            "difficulty": difficulty,
            "base_instructions": data.get("base_instructions", ""),  # used when difficulty == custom
            "prospect_profile": data.get("prospect_profile") or default_prospect_profile(),
            "llm_settings": data.get("llm_settings") or default_llm_settings(),
            "conversation_rules": data.get("conversation_rules") or default_conversation_rules(),
            "tier3_round1_enabled": data.get("tier3_round1_enabled", True),
            "tier3_round2_enabled": data.get("tier3_round2_enabled", True),
            "status": data.get("status", "draft"),
            "created_at": _now(),
            "updated_at": _now(),
        }
        agents.append(agent)
        self._write(agents)
        return agent

    def update_agent(self, agent_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        agents = self._read()
        allowed = {
            "name", "description", "difficulty", "base_instructions",
            "prospect_profile", "llm_settings", "conversation_rules",
            "tier3_round1_enabled", "tier3_round2_enabled", "status",
        }
        for agent in agents:
            if agent["id"] == agent_id:
                for key, value in updates.items():
                    if key in allowed and value is not None:
                        agent[key] = value
                agent["updated_at"] = _now()
                self._write(agents)
                return agent
        return None

    def delete_agent(self, agent_id: str) -> dict[str, Any] | None:
        agents = self._read()
        agent = next((a for a in agents if a["id"] == agent_id), None)
        if not agent:
            return None
        self._write([a for a in agents if a["id"] != agent_id])
        return agent

    # ── Instruction compilation ────────────────────────────────────────────────
    def build_instructions(self, agent: dict[str, Any], kb_context: str = "", module_name: str = "") -> str:
        """
        Compiles a full Tier 3 Round 2 prospect prompt from the agent config.
        Custom difficulty uses base_instructions verbatim; presets are assembled
        from the persona profile + difficulty behaviour + chosen objections.
        """
        difficulty = agent.get("difficulty", "medium")
        profile = agent.get("prospect_profile") or {}

        if difficulty == "custom" and agent.get("base_instructions", "").strip():
            parts = [agent["base_instructions"].strip()]
        else:
            preset = DIFFICULTY_PRESETS.get(difficulty, DIFFICULTY_PRESETS["medium"])
            role = profile.get("role", "decision-maker")
            company_size = profile.get("company_size", "a mid-sized company")
            pains = profile.get("pain_points") or []
            objections = profile.get("objections") or preset_default_objections(preset)

            lines = [
                "You are a realistic sales prospect on a mock sales training call. A sales "
                "trainee will call you and practice their pitch. Help them grow by being a "
                "believable, challenging-but-fair prospect.",
                "",
                f"YOUR PERSONA: You are a {role} at {company_size}.",
            ]
            if pains:
                lines.append("Your current pain points: " + ", ".join(pains) + ".")
            lines += ["", "DIFFICULTY & BEHAVIOUR:", preset["behaviour"], ""]

            obj_lines = [
                f"  • {OBJECTION_LINES.get(o, o)}" for o in objections if o in OBJECTION_LINES
            ]
            if obj_lines:
                lines.append(
                    f"RAISE THESE OBJECTIONS (one at a time, up to {preset['num_objections']}):"
                )
                lines.extend(obj_lines)
                lines.append("")

            lines += [
                "STRICT RULES:",
                "- Stay fully in character as the prospect. Never coach the rep during the call.",
                "- Keep each reply to 1-3 sentences. Sound human, no stage directions.",
                "- Base product knowledge ONLY on what the rep tells you and the context below.",
                "- If the rep handles your objections well, warm up and show genuine interest.",
                "- If the rep is poor, end the call politely without committing.",
            ]
            parts = ["\n".join(lines)]

        if module_name.strip():
            parts.append(f"Product/Course being evaluated:\n{module_name.strip()}")
        if kb_context.strip():
            parts.append(
                "Knowledge base context (what you, as prospect, vaguely know from marketing):\n"
                + kb_context.strip()
            )
        return "\n\n".join(parts)

    # ── IO ────────────────────────────────────────────────────────────────────
    def _read(self) -> list[dict[str, Any]]:
        from core.atomic_json import atomic_read
        return atomic_read(self.path)

    def _write(self, agents: list[dict[str, Any]]) -> None:
        from core.atomic_json import atomic_write
        atomic_write(self.path, agents)


def preset_default_objections(preset: dict[str, Any]) -> list[str]:
    """Pick the first N objections for a preset if the profile didn't specify any."""
    n = preset.get("num_objections", 2)
    return AVAILABLE_OBJECTIONS[:n]


agent_store = AgentStore()
