from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from core.integrations.maelstrom_ipc import MaelstromIpcClient


def _parse_timestamp(value: str | None) -> datetime:
    if not value:
        return datetime.min
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.min


def _iter_event_files(paths: List[str]) -> Iterable[Path]:
    for raw in paths:
        path = Path(raw)
        if path.is_file():
            yield path
        elif path.is_dir():
            yield from sorted(path.glob("*.jsonl"))


def _load_events(paths: List[str], session_id: str | None) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for file_path in _iter_event_files(paths):
        for line in file_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("schema") != "MerlinSessionEvent":
                continue
            if session_id and event.get("session_id") != session_id:
                continue
            events.append(event)
    events.sort(key=lambda item: _parse_timestamp(item.get("timestamp")))
    return events


def _write_dataset(events: List[Dict[str, Any]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=True) + "\n")


def _write_summary(events: List[Dict[str, Any]], output: Optional[Path]) -> Dict[str, Any]:
    summary = {
        "count": len(events),
        "event_types": dict(Counter(event.get("event_type") for event in events)),
    }
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(summary, indent=2, ensure_ascii=True), encoding="utf-8")
    return summary


def _emit_ipc(events: List[Dict[str, Any]], ipc_root: str) -> None:
    client = MaelstromIpcClient(ipc_root)
    for event in events:
        client.send_event_envelope(
            event_type="merlin.session_event",
            payload=event,
            correlation_id=event.get("session_id"),
        )


class Plugin:
    def __init__(self, hub: Any = None, manifest: Dict[str, Any] | None = None):
        self.hub = hub
        self.manifest = manifest or {}

    def commands(self) -> Dict[str, Any]:
        return {
            "merlin.session.build": self.build,
        }

    def build(
        self,
        events_dir: Optional[List[str]] = None,
        output: str = "artifacts/merlin/datasets/merlin_events.jsonl",
        summary: Optional[str] = None,
        session_id: Optional[str] = None,
        emit_ipc: bool = False,
        ipc_root: str = "artifacts/ipc",
    ) -> Dict[str, Any]:
        paths = events_dir or []
        events = _load_events(paths, session_id)
        if not events:
            return {"ok": False, "error": "No MerlinSessionEvent entries found."}

        output_path = Path(output)
        _write_dataset(events, output_path)
        summary_path = Path(summary) if summary else None
        summary_payload = _write_summary(events, summary_path)

        if emit_ipc:
            _emit_ipc(events, ipc_root)

        return {
            "ok": True,
            "count": len(events),
            "output": str(output_path),
            "summary": summary_payload,
            "summary_path": str(summary_path) if summary_path else None,
        }
