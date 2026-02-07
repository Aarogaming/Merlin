from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

from core.plugin_manifest import get_hive_metadata
from loguru import logger

MERLIN_ROOT = Path(__file__).resolve().parents[2]
if str(MERLIN_ROOT) not in sys.path:
    sys.path.insert(0, str(MERLIN_ROOT))

try:
    import merlin_doctor as doctor
except Exception as exc:  # pragma: no cover - import guard
    doctor = None
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
            "merlin.doctor.run": self.run_doctor,
        }

    def run_doctor(self) -> Dict[str, Any]:
        if doctor is None:
            return {
                "ok": False,
                "error": f"merlin_doctor import failed: {_IMPORT_ERROR}",
            }

        checks = [
            ("Python Version", doctor.check_python_version),
            ("Dependencies", doctor.check_dependencies),
            ("Environment File", doctor.check_env_file),
            ("Directory Structure", doctor.check_directories),
            ("API Connectivity", doctor.check_api_connectivity),
        ]

        results: List[Dict[str, Any]] = []
        all_passed = True
        for name, fn in checks:
            try:
                passed, message = fn()
            except Exception as exc:
                passed = False
                message = str(exc)
            results.append({"name": name, "ok": bool(passed), "message": message})
            if not passed:
                all_passed = False

        return {
            "ok": all_passed,
            "checks": results,
        }
