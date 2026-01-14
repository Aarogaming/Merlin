import fnmatch
import json
import logging
import os
import pathlib
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

RESOURCE_TYPES = {
    "audio": [".mp3", ".wav", ".ogg", ".flac"],
    "scripts": [".py", ".ps1", ".bat", ".sh", ".js", ".ts", ".rb", ".pl", ".cmd", ".kt"],
    "executables": [".exe", ".msi", ".app", ".jar"],
    "docs": [".md", ".txt", ".pdf", ".docx"],
}

CONFIG_PATH = Path(__file__).with_name("merlin_resource_config.json")
DEFAULT_CONFIG = {
    "resource_index_path": "merlin_resource_index.json",
    "scan_root": "D:/Dev library/AaroneousAutomationSuite",
    "exclude_dirs": [".git", ".venv", "__pycache__", "node_modules", "dist", "build"],
    "exclude_globs": ["*.tmp", "*.log"],
    "max_file_size_mb": 50,
}

def load_config() -> dict:
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            return {**DEFAULT_CONFIG, **json.load(f)}
    return DEFAULT_CONFIG.copy()

def index_file(file_path):
    """Indexes or updates a single file in the library."""
    config = load_config()
    index_path = Path(CONFIG_PATH.parent / config["resource_index_path"])

    if index_path.exists():
        with open(index_path, 'r') as f:
            index = json.load(f)
    else:
        index = {key: [] for key in RESOURCE_TYPES}

    ext = pathlib.Path(file_path).suffix.lower()
    for rtype, exts in RESOURCE_TYPES.items():
        if ext in exts:
            stat = os.stat(file_path)
            rel_path = os.path.relpath(file_path, config["scan_root"])

            # Remove existing entry if it exists
            index[rtype] = [item for item in index[rtype] if item["path"] != rel_path]

            index[rtype].append({
                "path": rel_path,
                "type": ext[1:],
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
            break

    with open(index_path, 'w') as f:
        json.dump(index, f, indent=2)
    logger.info(f"Updated index for: {file_path}")

def search_library(query):
    """Searches the indexed library for a query string."""
    config = load_config()
    index_path = Path(CONFIG_PATH.parent / config["resource_index_path"])
    if not index_path.exists():
        return []

    with open(index_path, 'r') as f:
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
    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [d for d in dirnames if d not in config["exclude_dirs"]]
        for filename in filenames:
            ext = pathlib.Path(filename).suffix.lower()
            for rtype, exts in RESOURCE_TYPES.items():
                if ext in exts:
                    fpath = os.path.join(dirpath, filename)
                    stat = os.stat(fpath)
                    resources[rtype].append({
                        "path": os.path.relpath(fpath, root_dir),
                        "type": ext[1:],
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    })
    return resources

if __name__ == "__main__":
    config = load_config()
    res = scan_resources(config["scan_root"])
    with open(CONFIG_PATH.parent / config["resource_index_path"], 'w') as f:
        json.dump(res, f, indent=2)
