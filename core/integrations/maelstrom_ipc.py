from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class MaelstromIpcClient:
    """Local filesystem-backed IPC shim for standalone Merlin runtime."""

    def __init__(self, ipc_root: str | Path = "artifacts/ipc"):
        self.ipc_root = Path(ipc_root)
        self.ipc_root.mkdir(parents=True, exist_ok=True)
        self._stream_path = self.ipc_root / "maelstrom_events.jsonl"

    def send_event_envelope(
        self,
        *,
        event_type: str,
        payload: dict[str, Any],
        source_service: str = "merlin",
        source_component: str = "plugin",
        correlation_id: str | None = None,
        plugin: str | None = None,
    ) -> dict[str, Any]:
        envelope = {
            "schema_name": "AAS.MerlinIpcEnvelope",
            "schema_version": "1.0.0",
            "captured_utc": datetime.now(timezone.utc).isoformat(),
            "event_type": str(event_type or "").strip(),
            "source_service": str(source_service or "").strip() or "merlin",
            "source_component": str(source_component or "").strip() or "plugin",
            "correlation_id": str(correlation_id or "").strip() or None,
            "plugin": str(plugin or "").strip() or None,
            "payload": payload if isinstance(payload, dict) else {"value": payload},
        }
        with self._stream_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(envelope, sort_keys=True) + "\n")
        return envelope
