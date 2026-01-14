# Merlin: The Librarian's Watcher (Updated with Wisdom)
import time
import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from merlin_logger import merlin_logger
from merlin_code_reviewer import code_reviewer
from merlin_api_server import global_context # To update cross-platform context

class DevLibraryHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.is_directory: return
        if event.src_path.endswith(('.py', '.kt')):
            merlin_logger.info(f"Librarian noticed change: {event.src_path}")
            self.process_change(event.src_path)

    def process_change(self, path):
        # 1. Automatic Code Review
        review = code_reviewer.review_file(path)

        # 2. Update Universal Context for the Creator
        filename = os.path.basename(path)
        global_context.update({
            "current_task": f"Reviewed {filename}",
            "last_review": {
                "file": filename,
                "summary": review[:200] + "..." # Truncated for context sync
            }
        })

        merlin_logger.info(f"Merlin: I've reviewed your changes in {filename}. Check your dashboard.")

def start_watcher(path_to_watch="D:/Dev library/AaroneousAutomationSuite"):
    event_handler = DevLibraryHandler()
    observer = Observer()
    observer.schedule(event_handler, path_to_watch, recursive=True)
    observer.start()
    merlin_logger.info(f"Merlin Watcher active on: {path_to_watch}")
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt: observer.stop()
    observer.join()

if __name__ == "__main__":
    start_watcher()
