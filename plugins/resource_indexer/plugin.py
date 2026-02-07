from __future__ import annotations

import fnmatch
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from core.plugin_manifest import get_hive_metadata
from loguru import logger

MERLIN_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = MERLIN_ROOT.parent
if str(MERLIN_ROOT) not in sys.path:
    sys.path.insert(0, str(MERLIN_ROOT))

try:
    from merlin_resource_indexer import RESOURCE_TYPES, load_config
except Exception as exc:  # pragma: no cover - import guard
    RESOURCE_TYPES = {
        "audio": [".mp3", ".wav", ".ogg", ".flac"],
        "scripts": [".py", ".ps1", ".bat", ".sh", ".js", ".ts", ".rb", ".pl", ".cmd", ".kt"],
        "executables": [".exe", ".msi", ".app", ".jar"],
        "docs": [".md", ".txt", ".pdf", ".docx"],
    }
    load_config = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


def _resolve_path(base: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else base / path


def _coerce_list(value: Optional[Iterable[str]]) -> List[str]:
    if not value:
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _should_exclude_file(filename: str, exclude_globs: List[str]) -> bool:
    for pattern in exclude_globs:
        if fnmatch.fnmatch(filename, pattern):
            return True
    return False


def _scan_resources(
    root_dir: Path,
    *,
    exclude_dirs: List[str],
    exclude_globs: List[str],
    max_bytes: Optional[int],
) -> Dict[str, List[Dict[str, Any]]]:
    resources: Dict[str, List[Dict[str, Any]]] = {key: [] for key in RESOURCE_TYPES}

    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
        for filename in filenames:
            if _should_exclude_file(filename, exclude_globs):
                continue
            ext = Path(filename).suffix.lower()
            if not ext:
                continue
            for rtype, exts in RESOURCE_TYPES.items():
                if ext in exts:
                    fpath = Path(dirpath) / filename
                    try:
                        stat = fpath.stat()
                    except OSError:
                        continue
                    if max_bytes is not None and stat.st_size > max_bytes:
                        continue
                    resources[rtype].append(
                        {
                            "path": os.path.relpath(fpath, root_dir),
                            "type": ext[1:],
                            "size": stat.st_size,
                            "modified": datetime.fromtimestamp(
                                stat.st_mtime
                            ).isoformat(),
                        }
                    )
                    break
    return resources


class Plugin:
    def __init__(self, hub: Any = None, manifest: Dict[str, Any] | None = None):
        self.hub = hub
        self.manifest = manifest or {}
        hive_meta = get_hive_metadata(self.manifest)
        self.hive = str(hive_meta.get("hive") or "merlin").lower()

    def commands(self) -> Dict[str, Any]:
        return {
            "merlin.resource.index": self.index_resources,
        }

    def index_resources(
        self,
        scan_root: str = "",
        output_path: str = "",
        exclude_dirs: Optional[Iterable[str]] = None,
        exclude_globs: Optional[Iterable[str]] = None,
        max_file_size_mb: Optional[int] = None,
    ) -> Dict[str, Any]:
        if load_config is None:
            return {
                "ok": False,
                "error": f"merlin_resource_indexer import failed: {_IMPORT_ERROR}",
            }

        config = load_config() if load_config else {}
        config_scan = str(config.get("scan_root", ""))
        scan_root_path = Path(scan_root) if scan_root else Path(config_scan) if config_scan else REPO_ROOT
        if not scan_root_path.exists():
            scan_root_path = REPO_ROOT

        output_value = output_path or str(config.get("resource_index_path", "merlin_resource_index.json"))
        index_path = _resolve_path(REPO_ROOT, output_value)

        exclude_dirs_list = _coerce_list(exclude_dirs) or _coerce_list(config.get("exclude_dirs"))
        exclude_globs_list = _coerce_list(exclude_globs) or _coerce_list(config.get("exclude_globs"))

        max_bytes = None
        if max_file_size_mb is None:
            cfg_mb = config.get("max_file_size_mb")
            if isinstance(cfg_mb, (int, float)):
                max_bytes = int(cfg_mb * 1024 * 1024)
        else:
            max_bytes = int(max_file_size_mb) * 1024 * 1024

        try:
            resources = _scan_resources(
                scan_root_path,
                exclude_dirs=exclude_dirs_list,
                exclude_globs=exclude_globs_list,
                max_bytes=max_bytes,
            )
            index_path.parent.mkdir(parents=True, exist_ok=True)
            index_path.write_text(json.dumps(resources, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning(f"Resource indexing failed: {exc}")
            return {"ok": False, "error": str(exc)}

        counts = {key: len(items) for key, items in resources.items()}
        return {
            "ok": True,
            "scan_root": str(scan_root_path),
            "index_path": str(index_path),
            "counts": counts,
        }
