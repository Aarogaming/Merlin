from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional

from core.plugin_manifest import get_hive_metadata
from loguru import logger

MERLIN_ROOT = Path(__file__).resolve().parents[2]
if str(MERLIN_ROOT) not in sys.path:
    sys.path.insert(0, str(MERLIN_ROOT))

try:
    from merlin_voice_curate_local import DEFAULT_SOURCES_FILE, update_sources
except Exception as exc:  # pragma: no cover - import guard
    DEFAULT_SOURCES_FILE = MERLIN_ROOT / "merlin_voice_sources.json"
    update_sources = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


def _maybe_path(value: str | Path | None) -> Optional[Path]:
    if not value:
        return None
    return Path(value)


class Plugin:
    def __init__(self, hub: Any = None, manifest: Dict[str, Any] | None = None):
        self.hub = hub
        self.manifest = manifest or {}
        hive_meta = get_hive_metadata(self.manifest)
        self.hive = str(hive_meta.get("hive") or "merlin").lower()

    def commands(self) -> Dict[str, Any]:
        return {
            "merlin.voice.curate_local": self.curate_local,
        }

    def curate_local(
        self,
        ljspeech: str = "",
        vctk: str = "",
        libritts: str = "",
        sources_file: str = "",
    ) -> Dict[str, Any]:
        if update_sources is None:
            return {
                "ok": False,
                "error": f"merlin_voice_curate_local import failed: {_IMPORT_ERROR}",
            }

        sources_path = Path(sources_file) if sources_file else Path(DEFAULT_SOURCES_FILE)
        if not sources_path.exists():
            return {
                "ok": False,
                "error": f"Sources file not found: {sources_path}",
            }

        ljspeech_root = _maybe_path(ljspeech)
        vctk_root = _maybe_path(vctk)
        libritts_root = _maybe_path(libritts)

        try:
            payload = update_sources(sources_path, ljspeech_root, vctk_root, libritts_root)
        except Exception as exc:
            logger.warning(f"Voice curate failed: {exc}")
            return {"ok": False, "error": str(exc)}

        sources = payload.get("sources", []) if isinstance(payload, dict) else []
        return {
            "ok": True,
            "sources_file": str(sources_path),
            "source_count": len(sources),
            "sources": sources,
        }
