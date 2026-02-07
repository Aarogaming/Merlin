# Merlin Plugin: Resource Indexer
from pathlib import Path
from typing import Any

from merlin_resource_indexer import (
    index_file,
    load_config,
    scan_resources,
    search_library,
)


class MerlinResourceIndexerPlugin:
    def __init__(self):
        self.name = "resource_indexer"
        self.description = "Scan, index, and search Merlin's resource library."
        self.version = "1.0.0"
        self.author = "AAS"

    def get_info(self):
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
        }

    def execute(self, action: str, **kwargs: Any):
        if not action:
            return {"error": "action_required", "actions": ["scan", "search", "index"]}
        action = str(action).strip().lower()
        if action == "scan":
            root = kwargs.get("root") or load_config().get("scan_root")
            if not root:
                return {"error": "root_required"}
            resources = scan_resources(str(root))
            return {"root": str(root), "resources": resources}
        if action == "search":
            query = kwargs.get("query")
            if not query:
                return {"error": "query_required"}
            results = search_library(str(query))
            return {"query": query, "results": results}
        if action == "index":
            path = kwargs.get("path")
            if not path:
                return {"error": "path_required"}
            try:
                index_file(str(Path(path)))
            except Exception as exc:
                return {"error": "index_failed", "detail": str(exc)}
            return {"ok": True, "path": str(path)}
        return {"error": "unsupported_action", "action": action}


def get_plugin():
    return MerlinResourceIndexerPlugin()
