import json
from typing import List, Dict, Any
from merlin_plugin_manager import PluginManager
from merlin_logger import merlin_logger
from manager_health_protocol import (
    HealthCheckResult,
    HealthStatus,
    LifecycleState,
    LifecycleStateMixin,
    StatusPayloadBuilder,
)


class MerlinToolManager(LifecycleStateMixin):
    def __init__(self):
        LifecycleStateMixin.__init__(self)
        self._transition_state(LifecycleState.STARTING)
        self.plugin_manager = PluginManager()
        self.plugin_manager.load_plugins()
        self._transition_state(LifecycleState.RUNNING)

    def get_status(self) -> Dict:
        """Return standardised status payload."""
        return (
            StatusPayloadBuilder("MerlinToolManager")
            .with_lifecycle_state(self._lifecycle_state)
            .with_health_status(
                HealthStatus.HEALTHY if self.is_running() else HealthStatus.DEGRADED
            )
            .with_metrics({
                "plugins_available": len(self.plugin_manager.plugins),
            })
            .build()
        )

    def health_check(self) -> HealthCheckResult:
        """Return a named-check health report."""
        is_running = self.is_running()
        plugin_manager_ok = self.plugin_manager is not None
        all_ok = is_running and plugin_manager_ok
        return HealthCheckResult(
            status=HealthStatus.HEALTHY if all_ok else HealthStatus.DEGRADED,
            is_healthy=all_ok,
            message="MerlinToolManager is operational" if all_ok else "One or more checks failed",
            checks={
                "lifecycle_running": is_running,
                "plugin_manager_ready": plugin_manager_ok,
            },
        )

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
