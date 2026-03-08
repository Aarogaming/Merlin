import fnmatch
import hashlib
import json
import logging
import os
import pathlib
from datetime import datetime
from pathlib import Path
import merlin_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

RESOURCE_TYPES = {
    "audio": [".mp3", ".wav", ".ogg", ".flac"],
    "scripts": [
        ".py",
        ".ps1",
        ".bat",
        ".sh",
        ".js",
        ".ts",
        ".rb",
        ".pl",
        ".cmd",
        ".kt",
    ],
    "executables": [".exe", ".msi", ".app", ".jar"],
    "docs": [".md", ".txt", ".pdf", ".docx"],
}

CONFIG_PATH = Path(__file__).with_name("merlin_resource_config.json")
DEFAULT_CONFIG = {
    "resource_index_path": "merlin_resource_index.json",
    "resource_hash_cache_path": "merlin_resource_hash_cache.json",
    "scan_root": merlin_settings.DEV_LIBRARY_PATH,
    "exclude_dirs": [".git", ".venv", "__pycache__", "node_modules", "dist", "build"],
    "exclude_globs": ["*.tmp", "*.log"],
    "max_file_size_mb": 50,
}


def load_config() -> dict:
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            return {**DEFAULT_CONFIG, **json.load(f)}
    return DEFAULT_CONFIG.copy()


def _hash_file_sha256(file_path: Path, chunk_size: int = 1024 * 1024) -> str:
    hasher = hashlib.sha256()
    with file_path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def _load_hash_cache(cache_path: Path) -> dict[str, dict]:
    if not cache_path.exists():
        return {}
    try:
        with cache_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_hash_cache(cache_path: Path, cache: dict[str, dict]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with cache_path.open("w", encoding="utf-8") as handle:
        json.dump(cache, handle, indent=2, sort_keys=True)


def _hash_from_cache_or_compute(
    *,
    file_path: Path,
    relative_path: str,
    stat_result: os.stat_result,
    prior_cache: dict[str, dict],
    next_cache: dict[str, dict],
) -> str:
    prior_entry = prior_cache.get(relative_path)
    size = int(stat_result.st_size)
    mtime_ns = int(getattr(stat_result, "st_mtime_ns", int(stat_result.st_mtime * 1e9)))
    if (
        isinstance(prior_entry, dict)
        and int(prior_entry.get("size", -1)) == size
        and int(prior_entry.get("mtime_ns", -1)) == mtime_ns
        and isinstance(prior_entry.get("sha256"), str)
        and prior_entry.get("sha256")
    ):
        sha256 = prior_entry["sha256"]
    else:
        sha256 = _hash_file_sha256(file_path)

    next_cache[relative_path] = {
        "size": size,
        "mtime_ns": mtime_ns,
        "sha256": sha256,
    }
    return sha256


def index_file(file_path):
    """Indexes or updates a single file in the library."""
    config = load_config()
    index_path = Path(CONFIG_PATH.parent / config["resource_index_path"])
    hash_cache_path = Path(
        CONFIG_PATH.parent / config.get("resource_hash_cache_path", "merlin_resource_hash_cache.json")
    )
    prior_hash_cache = _load_hash_cache(hash_cache_path)
    next_hash_cache = dict(prior_hash_cache)

    if index_path.exists():
        with open(index_path, "r", encoding="utf-8") as f:
            index = json.load(f)
    else:
        index = {key: [] for key in RESOURCE_TYPES}

    ext = pathlib.Path(file_path).suffix.lower()
    for rtype, exts in RESOURCE_TYPES.items():
        if ext in exts:
            stat = os.stat(file_path)
            rel_path = os.path.relpath(file_path, config["scan_root"])
            sha256 = _hash_from_cache_or_compute(
                file_path=Path(file_path),
                relative_path=rel_path,
                stat_result=stat,
                prior_cache=prior_hash_cache,
                next_cache=next_hash_cache,
            )

            # Remove existing entry if it exists
            index[rtype] = [item for item in index[rtype] if item["path"] != rel_path]

            index[rtype].append(
                {
                    "path": rel_path,
                    "type": ext[1:],
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "sha256": sha256,
                }
            )
            break

    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)
    _save_hash_cache(hash_cache_path, next_hash_cache)
    logger.info(f"Updated index for: {file_path}")


def search_library(query):
    """Searches the indexed library for a query string."""
    config = load_config()
    index_path = Path(CONFIG_PATH.parent / config["resource_index_path"])
    if not index_path.exists():
        return []

    with open(index_path, "r") as f:
        index = json.load(f)

    results = []
    for rtype, files in index.items():
        for f in files:
            if query.lower() in f["path"].lower():
                results.append(f)
    return results


def scan_resources(root_dir):
    resources = {key: [] for key in RESOURCE_TYPES}
    config = load_config()
    hash_cache_path = Path(
        CONFIG_PATH.parent / config.get("resource_hash_cache_path", "merlin_resource_hash_cache.json")
    )
    prior_hash_cache = _load_hash_cache(hash_cache_path)
    next_hash_cache: dict[str, dict] = {}
    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [d for d in dirnames if d not in config["exclude_dirs"]]
        for filename in filenames:
            if any(fnmatch.fnmatch(filename, pattern) for pattern in config["exclude_globs"]):
                continue
            ext = pathlib.Path(filename).suffix.lower()
            for rtype, exts in RESOURCE_TYPES.items():
                if ext in exts:
                    fpath = os.path.join(dirpath, filename)
                    stat = os.stat(fpath)
                    rel_path = os.path.relpath(fpath, root_dir)
                    sha256 = _hash_from_cache_or_compute(
                        file_path=Path(fpath),
                        relative_path=rel_path,
                        stat_result=stat,
                        prior_cache=prior_hash_cache,
                        next_cache=next_hash_cache,
                    )
                    resources[rtype].append(
                        {
                            "path": rel_path,
                            "type": ext[1:],
                            "size": stat.st_size,
                            "modified": datetime.fromtimestamp(
                                stat.st_mtime
                            ).isoformat(),
                            "sha256": sha256,
                        }
                    )
                    break
    _save_hash_cache(hash_cache_path, next_hash_cache)
    return resources


if __name__ == "__main__":
    config = load_config()
    res = scan_resources(config["scan_root"])
    with open(CONFIG_PATH.parent / config["resource_index_path"], "w") as f:
        json.dump(res, f, indent=2)
