# Merlin Plugin: Tool Registry
from pathlib import Path
from typing import Any

from merlin_plugin_manager import PluginManager


class MerlinToolsPlugin:
    def __init__(self):
        self.name = "tools"
        self.description = "List and invoke Merlin plugins as tools."
        self.version = "1.0.0"
        self.author = "AAS"
        self._plugin_dir = Path(__file__).resolve().parent

    def _manager(self) -> PluginManager:
        manager = PluginManager(plugin_dir=str(self._plugin_dir))
        manager.load_plugins()
        # Avoid recursive self reference in tool listings.
        manager.plugins.pop(self.name, None)
        return manager

    def get_info(self):
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
        }

    def execute(self, action: str, **kwargs: Any):
        if not action:
            return {"error": "action_required", "actions": ["list", "call"]}
        action = str(action).strip().lower()
        manager = self._manager()
        if action == "list":
            return {"tools": manager.list_plugin_info()}
        if action == "call":
            name = kwargs.get("name")
            if not name:
                return {"error": "name_required"}
            args = kwargs.get("args") or []
            call_kwargs = kwargs.get("kwargs") or {}
            return manager.execute_plugin(str(name), *args, **call_kwargs)
        return {"error": "unsupported_action", "action": action}


def get_plugin():
    return MerlinToolsPlugin()
