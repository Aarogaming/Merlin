# Merlin: The Librarian's Watcher (debounced + backpressure-aware)
from __future__ import annotations

import os
import time
from collections import deque

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
except ModuleNotFoundError:

    class FileSystemEventHandler:  # pragma: no cover - lightweight fallback
        pass

    class Observer:  # pragma: no cover - lightweight fallback
        def schedule(self, *args, **kwargs):
            return None

        def start(self):
            return None

        def stop(self):
            return None

        def join(self):
            return None

from merlin_api_server import global_context  # To update cross-platform context
from merlin_code_reviewer import code_reviewer
from merlin_logger import merlin_logger
from merlin_resource_indexer import index_file
import merlin_settings

DEFAULT_WATCH_DEBOUNCE_SECONDS = 1.5
DEFAULT_WATCH_MAX_PENDING_EVENTS = 256
DEFAULT_WATCH_PROCESS_INTERVAL_SECONDS = 0.25


def _coerce_positive_float(value: str | None, default: float) -> float:
    if value is None:
        return default
    try:
        parsed = float(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _coerce_positive_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


class DevLibraryHandler(FileSystemEventHandler):
    def __init__(
        self,
        *,
        debounce_seconds: float | None = None,
        max_pending_events: int | None = None,
    ):
        super().__init__()
        self.debounce_seconds = (
            DEFAULT_WATCH_DEBOUNCE_SECONDS
            if debounce_seconds is None
            else max(0.01, float(debounce_seconds))
        )
        self.max_pending_events = (
            DEFAULT_WATCH_MAX_PENDING_EVENTS
            if max_pending_events is None
            else max(1, int(max_pending_events))
        )
        self._pending_paths: deque[str] = deque()
        self._last_enqueued_at: dict[str, float] = {}
        self.dropped_event_count = 0

    def on_modified(self, event):
        if event.is_directory:
            return
        if not event.src_path.endswith((".py", ".kt")):
            return

        path = event.src_path
        now = time.monotonic()
        last_enqueued = self._last_enqueued_at.get(path)
        if last_enqueued is not None and (now - last_enqueued) < self.debounce_seconds:
            return

        if len(self._pending_paths) >= self.max_pending_events:
            self._pending_paths.popleft()
            self.dropped_event_count += 1

        self._pending_paths.append(path)
        self._last_enqueued_at[path] = now

    def process_pending(self, max_items: int = 8) -> int:
        processed = 0
        allowed = max(1, int(max_items))
        while self._pending_paths and processed < allowed:
            path = self._pending_paths.popleft()
            self.process_change(path)
            processed += 1
        return processed

    def process_change(self, path):
        # 1. Automatic Code Review
        review = code_reviewer.review_file(path)

        # 2. Incremental resource index update for changed file.
        try:
            index_file(path)
        except Exception as exc:
            merlin_logger.warning(f"Watcher index update skipped for {path}: {exc}")

        # 3. Update Universal Context for the Creator
        filename = os.path.basename(path)
        global_context.update(
            {
                "current_task": f"Reviewed {filename}",
                "last_review": {
                    "file": filename,
                    "summary": review[:200] + "...",  # Truncated for context sync
                },
                "watcher_backpressure": {
                    "pending": len(self._pending_paths),
                    "dropped": self.dropped_event_count,
                },
            }
        )

        merlin_logger.info(
            f"Merlin: I've reviewed your changes in {filename}. Check your dashboard."
        )


def start_watcher(path_to_watch=merlin_settings.DEV_LIBRARY_PATH):
    debounce_seconds = _coerce_positive_float(
        os.getenv("MERLIN_WATCH_DEBOUNCE_SECONDS"),
        DEFAULT_WATCH_DEBOUNCE_SECONDS,
    )
    max_pending_events = _coerce_positive_int(
        os.getenv("MERLIN_WATCH_MAX_PENDING_EVENTS"),
        DEFAULT_WATCH_MAX_PENDING_EVENTS,
    )
    process_interval = _coerce_positive_float(
        os.getenv("MERLIN_WATCH_PROCESS_INTERVAL_SECONDS"),
        DEFAULT_WATCH_PROCESS_INTERVAL_SECONDS,
    )

    event_handler = DevLibraryHandler(
        debounce_seconds=debounce_seconds,
        max_pending_events=max_pending_events,
    )
    observer = Observer()
    observer.schedule(event_handler, path_to_watch, recursive=True)
    observer.start()
    merlin_logger.info(
        f"Merlin Watcher active on: {path_to_watch} "
        f"(debounce={debounce_seconds}s, max_pending={max_pending_events})"
    )
    try:
        while True:
            event_handler.process_pending()
            time.sleep(process_interval)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    start_watcher()
