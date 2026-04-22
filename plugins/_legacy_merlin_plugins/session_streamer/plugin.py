from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from core.integrations.maelstrom_ipc import MaelstromIpcClient

DEFAULT_EVENT_DIRS = [
    "artifacts/merlin/events",
    "artifacts/local_agent/logs",
]


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


def _load_state(state_path: Optional[Path]) -> Dict[str, int]:
    if not state_path or not state_path.exists():
        return {}
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    offsets: Dict[str, int] = {}
    for key, value in data.items():
        try:
            offsets[str(key)] = int(value)
        except (TypeError, ValueError):
            continue
    return offsets


def _write_state(state_path: Optional[Path], offsets: Dict[str, int]) -> None:
    if not state_path:
        return
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(offsets, indent=2), encoding="utf-8")


def _read_new_lines(path: Path, offset: int) -> Tuple[int, List[str]]:
    if not path.exists():
        return offset, []
    try:
        size = path.stat().st_size
    except OSError:
        return offset, []
    if offset > size:
        offset = 0
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        handle.seek(offset)
        chunk = handle.read()
        new_offset = handle.tell()
    if not chunk:
        return new_offset, []
    return new_offset, chunk.splitlines()


def _should_emit(event: Dict[str, Any], session_id: Optional[str]) -> bool:
    if event.get("schema") != "MerlinSessionEvent":
        return False
    if session_id and event.get("session_id") != session_id:
        return False
    return True


def _emit_event(client: MaelstromIpcClient, event: Dict[str, Any]) -> None:
    client.send_event_envelope(
        event_type="merlin.session_event",
        payload=event,
        source_service="merlin",
        source_component="session_streamer",
        correlation_id=event.get("session_id"),
        plugin="merlin_session_streamer",
    )


class Plugin:
    def __init__(self, hub: Any = None, manifest: Dict[str, Any] | None = None):
        self.hub = hub
        self.manifest = manifest or {}

    def commands(self) -> Dict[str, Any]:
        return {
            "merlin.session.stream": self.stream,
        }

    def stream(
        self,
        events_dir: Optional[List[str]] = None,
        ipc_root: str = "artifacts/ipc",
        state_file: str = "artifacts/merlin/datasets/merlin_stream_state.json",
        no_state: bool = False,
        session_id: Optional[str] = None,
        poll_sec: float = 1.0,
        from_start: bool = False,
        once: bool = True,
        max_cycles: int = 1,
    ) -> Dict[str, Any]:
        event_paths = events_dir or []
        if not event_paths:
            for default_path in DEFAULT_EVENT_DIRS:
                if Path(default_path).exists():
                    event_paths.append(default_path)
        if not event_paths:
            return {"ok": False, "error": "No event directories found."}

        state_path = None if no_state else Path(state_file)
        offsets = {} if from_start else _load_state(state_path)

        client = MaelstromIpcClient(ipc_root)
        emitted = 0
        errors = 0

        def _init_offsets(file_paths: List[Path]) -> None:
            for file_path in file_paths:
                key = str(file_path)
                if key in offsets:
                    continue
                if from_start:
                    offsets[key] = 0
                else:
                    try:
                        offsets[key] = file_path.stat().st_size
                    except OSError:
                        offsets[key] = 0

        cycles = 0
        while True:
            files = list(_iter_event_files(event_paths))
            _init_offsets(files)

            for file_path in files:
                key = str(file_path)
                offset = offsets.get(key, 0)
                new_offset, lines = _read_new_lines(file_path, offset)
                offsets[key] = new_offset
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not _should_emit(event, session_id):
                        continue
                    try:
                        _emit_event(client, event)
                        emitted += 1
                    except Exception:
                        errors += 1

            _write_state(state_path, offsets)

            cycles += 1
            if once or (max_cycles and cycles >= max_cycles):
                break
            time.sleep(max(0.1, poll_sec))

        return {
            "ok": True,
            "emitted": emitted,
            "errors": errors,
            "cycles": cycles,
        }
