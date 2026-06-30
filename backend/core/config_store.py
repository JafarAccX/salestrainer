import json
from pathlib import Path
from typing import Any

from config import config
from core.atomic_json import atomic_read, atomic_write

class ConfigStore:
    def __init__(self):
        self.file_path = Path(config.KB_STORE_DIR) / "admin_config.json"
        if not self.file_path.exists():
            self._write({
                "active_module_id": None,
                "active_agent_id": None,
                "timer_minutes": 2,
                "agents": []
            })

    def get_config(self) -> dict[str, Any]:
        try:
            data = atomic_read(self.file_path)
            return data if isinstance(data, dict) else {"active_module_id": None, "active_agent_id": None, "timer_minutes": 2, "agents": []}
        except Exception:
            return {"active_module_id": None, "active_agent_id": None, "timer_minutes": 2, "agents": []}

    def update_config(
        self,
        active_module_id: str | None = None,
        active_agent_id: str | None = None,
        timer_minutes: int | None = None,
        all_courses_passing_score: float | None = None,
        all_courses_agent_id: str | None = None,
    ) -> dict[str, Any]:
        curr = self.get_config()
        if active_module_id is not None:
            curr["active_module_id"] = active_module_id
        if active_agent_id is not None:
            curr["active_agent_id"] = active_agent_id
        if timer_minutes is not None:
            curr["timer_minutes"] = timer_minutes
        if all_courses_passing_score is not None:
            curr["all_courses_passing_score"] = all_courses_passing_score
        if all_courses_agent_id is not None:
            curr["all_courses_agent_id"] = all_courses_agent_id
        self._write(curr)
        return curr

    def list_agents(self) -> list[dict[str, str]]:
        curr = self.get_config()
        return curr.get("agents", [])

    def create_agent(self, agent_id: str, name: str, instructions: str) -> dict[str, str]:
        curr = self.get_config()
        if "agents" not in curr:
            curr["agents"] = []
        
        agent = {"id": agent_id, "name": name, "instructions": instructions}
        curr["agents"].append(agent)
        self._write(curr)
        return agent

    def delete_agent(self, agent_id: str) -> bool:
        curr = self.get_config()
        if "agents" not in curr:
            return False
            
        initial_len = len(curr["agents"])
        curr["agents"] = [a for a in curr["agents"] if a.get("id") != agent_id]
        if len(curr["agents"]) < initial_len:
            self._write(curr)
            return True
        return False

    def get_agent(self, agent_id: str) -> dict[str, str] | None:
        curr = self.get_config()
        for a in curr.get("agents", []):
            if a.get("id") == agent_id:
                return a
        return None

    def _write(self, data: dict[str, Any]):
        atomic_write(self.file_path, data)

config_store = ConfigStore()
