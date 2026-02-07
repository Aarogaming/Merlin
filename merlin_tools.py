import json
from typing import List, Dict, Any
from merlin_plugin_manager import PluginManager
from merlin_logger import merlin_logger


class MerlinToolManager:
    def __init__(self):
        self.plugin_manager = PluginManager()
        self.plugin_manager.load_plugins()

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        tools = []
        for name, info in self.plugin_manager.list_plugin_info().items():
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": info["description"],
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "args": {"type": "array", "items": {"type": "string"}},
                                "kwargs": {"type": "object"},
                            },
                        },
                    },
                }
            )
        return tools

    def call_tool(
        self, name: str, args: list | None = None, kwargs: dict | None = None
    ) -> Any:
        merlin_logger.info(f"Calling tool: {name} with args={args}, kwargs={kwargs}")
        return self.plugin_manager.execute_plugin(name, *(args or []), **(kwargs or {}))


tool_manager = MerlinToolManager()
