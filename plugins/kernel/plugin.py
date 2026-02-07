from __future__ import annotations

from typing import Any, Dict, List

from core.plugin_manifest import get_hive_metadata
from loguru import logger


class Plugin:
    def __init__(self, hub: Any = None, manifest: Dict[str, Any] | None = None):
        self.hub = hub
        self.manifest = manifest or {}
        hive_meta = get_hive_metadata(self.manifest)
        self.hive = str(hive_meta.get("hive") or "merlin").lower()
        self.name = f"{self.hive}.kernel"

    def commands(self) -> Dict[str, Any]:
        return {
            f"{self.hive}.hive.status": self.hive_status,
            f"{self.hive}.hive.plugins": self.hive_plugins,
        }

    def hive_status(self) -> Dict[str, Any]:
        plugins = self._collect_plugins()
        return {
            "ok": True,
            "hive": self.hive,
            "plugin_count": len(plugins),
            "plugins": plugins,
        }

    def hive_plugins(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "hive": self.hive,
            "plugins": self._collect_plugins(),
        }

    def _collect_plugins(self) -> List[str]:
        if not self.hub or not hasattr(self.hub, "hives"):
            return []
        grouped = self.hub.hives
        metas = grouped.get(self.hive, [])
        return sorted([meta.name for meta in metas])
