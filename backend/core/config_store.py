import json
from pathlib import Path
from typing import Any

from config import config

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
            with self.file_path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"active_module_id": None, "active_agent_id": None, "timer_minutes": 2, "agents": []}

    def update_config(self, active_module_id: str | None = None, active_agent_id: str | None = None, timer_minutes: int | None = None) -> dict[str, Any]:
        curr = self.get_config()
        if active_module_id is not None:
            curr["active_module_id"] = active_module_id
        if active_agent_id is not None:
            curr["active_agent_id"] = active_agent_id
        if timer_minutes is not None:
            curr["timer_minutes"] = timer_minutes
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
        with self.file_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

config_store = ConfigStore()
