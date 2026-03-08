from __future__ import annotations

import types

from merlin_watcher import DevLibraryHandler


def _event(path: str, is_directory: bool = False):
    return types.SimpleNamespace(src_path=path, is_directory=is_directory)


def test_on_modified_debounces_repeated_file_changes():
    handler = DevLibraryHandler(debounce_seconds=5.0, max_pending_events=8)
    event = _event("/tmp/example.py")

    handler.on_modified(event)
    handler.on_modified(event)

    assert list(handler._pending_paths) == ["/tmp/example.py"]


def test_on_modified_applies_backpressure_by_dropping_oldest():
    handler = DevLibraryHandler(debounce_seconds=0.01, max_pending_events=2)

    handler.on_modified(_event("/tmp/one.py"))
    handler.on_modified(_event("/tmp/two.py"))
    handler.on_modified(_event("/tmp/three.py"))

    assert list(handler._pending_paths) == ["/tmp/two.py", "/tmp/three.py"]
    assert handler.dropped_event_count == 1


def test_process_pending_limits_batch_size(monkeypatch):
    handler = DevLibraryHandler(debounce_seconds=0.01, max_pending_events=8)
    processed_paths: list[str] = []

    monkeypatch.setattr(
        handler,
        "process_change",
        lambda path: processed_paths.append(path),
    )

    handler.on_modified(_event("/tmp/one.py"))
    handler.on_modified(_event("/tmp/two.py"))

    processed = handler.process_pending(max_items=1)

    assert processed == 1
    assert processed_paths == ["/tmp/one.py"]
    assert list(handler._pending_paths) == ["/tmp/two.py"]
