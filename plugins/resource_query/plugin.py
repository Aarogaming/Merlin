from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from core.plugin_manifest import get_hive_metadata
from loguru import logger


class Plugin:
    def __init__(self, hub: Any = None, manifest: Dict[str, Any] | None = None):
        self.hub = hub
        self.manifest = manifest or {}
        hive_meta = get_hive_metadata(self.manifest)
        self.hive = str(hive_meta.get("hive") or "merlin").lower()

    def commands(self) -> Dict[str, Any]:
        return {
            "merlin.resource.search": self.search,
        }

    def search(
        self,
        index: str = "merlin_resource_index.json",
        rtype: str = "",
        search: str = "",
        limit: int = 25,
    ) -> Dict[str, Any]:
        path = Path(index)
        if not path.exists():
            logger.warning(f"Resource index not found: {path}")
            return {"ok": False, "error": f"Index not found: {path}"}

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            return {"ok": False, "error": f"Failed to read index: {exc}"}

        candidates: List[Dict[str, Any]] = []
        if rtype:
            candidates = data.get(rtype, []) if isinstance(data, dict) else []
        else:
            if isinstance(data, dict):
                for items in data.values():
                    if isinstance(items, list):
                        candidates.extend(items)

        results = candidates
        if search:
            needle = search.lower()
            results = [item for item in candidates if needle in str(item.get("path", "")).lower()]

        sliced = results[: max(1, int(limit))]
        return {
            "ok": True,
            "count": len(results),
            "results": sliced,
        }
