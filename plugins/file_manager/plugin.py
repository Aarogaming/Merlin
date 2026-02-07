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
    import merlin_file_manager as file_manager
except Exception as exc:  # pragma: no cover - import guard
    file_manager = None
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
            "merlin.file.list": self.list_files,
            "merlin.file.delete": self.delete_file,
            "merlin.file.move": self.move_file,
            "merlin.file.open": self.open_file,
        }

    def list_files(self, path: str = ".") -> Dict[str, Any]:
        if file_manager is None:
            return {
                "ok": False,
                "error": f"merlin_file_manager import failed: {_IMPORT_ERROR}",
            }
        result = file_manager.list_files(path)
        if isinstance(result, dict) and result.get("error"):
            return {"ok": False, "error": result["error"]}
        return {"ok": True, "items": result}

    def delete_file(self, path: str) -> Dict[str, Any]:
        if file_manager is None:
            return {
                "ok": False,
                "error": f"merlin_file_manager import failed: {_IMPORT_ERROR}",
            }
        result = file_manager.delete_file(path)
        if isinstance(result, dict) and result.get("error"):
            return {"ok": False, "error": result["error"]}
        return {"ok": True, "status": "deleted"}

    def move_file(self, src: str, dst: str) -> Dict[str, Any]:
        if file_manager is None:
            return {
                "ok": False,
                "error": f"merlin_file_manager import failed: {_IMPORT_ERROR}",
            }
        result = file_manager.move_file(src, dst)
        if isinstance(result, dict) and result.get("error"):
            return {"ok": False, "error": result["error"]}
        return {"ok": True, "status": "moved"}

    def open_file(self, path: str) -> Dict[str, Any]:
        if file_manager is None:
            return {
                "ok": False,
                "error": f"merlin_file_manager import failed: {_IMPORT_ERROR}",
            }
        try:
            result = file_manager.open_file(path)
        except Exception as exc:
            logger.warning(f"Open file failed: {exc}")
            return {"ok": False, "error": str(exc)}
        if isinstance(result, dict) and result.get("error"):
            return {"ok": False, "error": result["error"]}
        return {"ok": True, "status": "opened"}
