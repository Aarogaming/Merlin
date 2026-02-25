from __future__ import annotations

from pathlib import Path
from typing import Any

from merlin_discovery_engine import build_engine


class Plugin:
    def __init__(self, hub: Any = None, manifest: dict[str, Any] | None = None):
        self.hub = hub
        self.manifest = manifest or {}
        self.workspace_root = Path(__file__).resolve().parents[2]

    def commands(self) -> dict[str, Any]:
        return {
            "merlin.discovery.run": self.run,
            "merlin.discovery.queue.status": self.queue_status,
            "merlin.discovery.queue.drain": self.queue_drain,
            "merlin.discovery.queue.purge_deadletter": self.queue_purge_deadletter,
            "merlin.discovery.queue.pause": self.queue_pause,
            "merlin.discovery.queue.resume": self.queue_resume,
            "merlin.knowledge.search": self.knowledge_search,
        }

    def get_info(self) -> dict[str, Any]:
        return {
            "name": "discovery_engine",
            "description": "Policy-gated offline-first discovery pipeline",
            "version": "0.1.0",
            "category": "pipeline",
        }

    def _engine(
        self, *, workspace_root: str | Path | None = None, merlin_mode: str = "local"
    ):
        root = Path(workspace_root).resolve() if workspace_root else self.workspace_root
        return build_engine(workspace_root=root, merlin_mode=merlin_mode)

    def run(self, **kwargs: Any) -> dict[str, Any]:
        workspace_root = kwargs.pop("workspace_root", None)
        merlin_mode = kwargs.pop("merlin_mode", "local")
        engine = self._engine(workspace_root=workspace_root, merlin_mode=merlin_mode)
        return engine.run(**kwargs)

    def queue_status(self, **kwargs: Any) -> dict[str, Any]:
        workspace_root = kwargs.pop("workspace_root", None)
        merlin_mode = kwargs.pop("merlin_mode", "local")
        out = kwargs.pop("out", None)
        engine = self._engine(workspace_root=workspace_root, merlin_mode=merlin_mode)
        return engine.queue_status(out=out)

    def queue_drain(self, **kwargs: Any) -> dict[str, Any]:
        workspace_root = kwargs.pop("workspace_root", None)
        merlin_mode = kwargs.pop("merlin_mode", "local")
        out = kwargs.pop("out", None)
        run_id = kwargs.pop("run_id", None)
        engine = self._engine(workspace_root=workspace_root, merlin_mode=merlin_mode)
        return engine.queue_drain(out=out, run_id=run_id)

    def queue_purge_deadletter(self, **kwargs: Any) -> dict[str, Any]:
        workspace_root = kwargs.pop("workspace_root", None)
        merlin_mode = kwargs.pop("merlin_mode", "local")
        out = kwargs.pop("out", None)
        engine = self._engine(workspace_root=workspace_root, merlin_mode=merlin_mode)
        return engine.queue_purge_deadletter(out=out)

    def queue_pause(self, **kwargs: Any) -> dict[str, Any]:
        workspace_root = kwargs.pop("workspace_root", None)
        merlin_mode = kwargs.pop("merlin_mode", "local")
        out = kwargs.pop("out", None)
        engine = self._engine(workspace_root=workspace_root, merlin_mode=merlin_mode)
        return engine.queue_pause(out=out)

    def queue_resume(self, **kwargs: Any) -> dict[str, Any]:
        workspace_root = kwargs.pop("workspace_root", None)
        merlin_mode = kwargs.pop("merlin_mode", "local")
        out = kwargs.pop("out", None)
        engine = self._engine(workspace_root=workspace_root, merlin_mode=merlin_mode)
        return engine.queue_resume(out=out)

    def knowledge_search(self, **kwargs: Any) -> dict[str, Any]:
        workspace_root = kwargs.pop("workspace_root", None)
        merlin_mode = kwargs.pop("merlin_mode", "local")
        query = kwargs.pop("query", "")
        out = kwargs.pop("out", None)
        limit = kwargs.pop("limit", 20)
        tag = kwargs.pop("tag", None)
        engine = self._engine(workspace_root=workspace_root, merlin_mode=merlin_mode)
        return engine.knowledge_search(
            query=query,
            out=out,
            limit=limit,
            tag=tag,
        )

    def execute(self, action: str = "run", **kwargs: Any) -> dict[str, Any]:
        normalized = str(action or "run").strip().lower()
        if normalized in {"run", "discovery.run"}:
            return self.run(**kwargs)
        if normalized in {"queue.status", "discovery.queue.status"}:
            return self.queue_status(**kwargs)
        if normalized in {"queue.drain", "discovery.queue.drain"}:
            return self.queue_drain(**kwargs)
        if normalized in {
            "queue.purge-deadletter",
            "queue.purge_deadletter",
            "discovery.queue.purge_deadletter",
        }:
            return self.queue_purge_deadletter(**kwargs)
        if normalized in {"queue.pause", "discovery.queue.pause"}:
            return self.queue_pause(**kwargs)
        if normalized in {"queue.resume", "discovery.queue.resume"}:
            return self.queue_resume(**kwargs)
        if normalized in {"knowledge.search", "discovery.knowledge.search"}:
            return self.knowledge_search(**kwargs)
        return {
            "ok": False,
            "error": (
                "unsupported discovery action '"
                + normalized
                + "' (supported: run, queue.status, queue.drain, queue.purge_deadletter, queue.pause, queue.resume, knowledge.search)"
            ),
        }
