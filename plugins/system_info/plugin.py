from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

from core.plugin_manifest import get_hive_metadata
from loguru import logger

MERLIN_ROOT = Path(__file__).resolve().parents[2]
if str(MERLIN_ROOT) not in sys.path:
    sys.path.insert(0, str(MERLIN_ROOT))

try:
    from merlin_system_info import get_system_info
except Exception as exc:  # pragma: no cover - import guard
    get_system_info = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


class Plugin:
    def __init__(self, hub: Any = None, manifest: Dict[str, Any] | None = None):
        self.hub = hub
        self.manifest = manifest or {}
        hive_meta = get_hive_metadata(self.manifest)
        self.hive = str(hive_meta.get("hive") or "merlin").lower()

    def commands(self) -> Dict[str, Any]:
        return {
            "merlin.system.info": self.system_info,
        }

    def system_info(self) -> Dict[str, Any]:
        if get_system_info is None:
            return {
                "ok": False,
                "error": f"merlin_system_info import failed: {_IMPORT_ERROR}",
            }
        try:
            info = get_system_info()
        except Exception as exc:
            logger.warning(f"System info failed: {exc}")
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "info": info}
