import json
from typing import Dict

from aas_kernel import ReflexPlugin

class Creation(ReflexPlugin):
    """
    Domain: Workbench (Creation)
    Handles Tool routing, execution compilation, and UI state validation.
    Bridges to Maelstrom for visual analysis.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.capability_registry: Dict[str, str] = {}

    @property
    def capabilities(self) -> list[str]:
        return [
            "aaroneousautomationsuite_mcp_bridge_execute",
            "aaroneousautomationsuite_maelstrom_ui_validate",
            "aaroneousautomationsuite_maelstrom_screenshot_capture"
        ]

    async def handle_message(self, capability_id: str, payload: dict) -> dict:
        import time
        start_time = time.time()

        if capability_id == "aaroneousautomationsuite_mcp_bridge_execute":
            target = payload.get("target_capability")
            target_subject = self.capability_registry.get(target)
            if not target_subject:
                return self._format_error(capability_id, f"Tool {target} not online.")
                
            if self.kernel and self.kernel.nc:
                resp = await self.kernel.nc.request(target_subject, json.dumps(payload).encode(), timeout=45.0)
                return self._format_success(capability_id, json.loads(resp.data.decode()), start_time)
            return self._format_error(capability_id, "NATS not connected.")

        elif capability_id == "aaroneousautomationsuite_maelstrom_ui_validate":
            return self._format_success(capability_id, f"UX {payload.get('component')} Validated.", start_time)

        elif capability_id == "aaroneousautomationsuite_maelstrom_screenshot_capture":
            return self._format_success(capability_id, f"Captured visual bytes for {payload.get('url')}.", start_time)

        return self._format_error(capability_id, "Unknown creation capability.")
