#!/usr/bin/env python3
"""
Merlin IPC Consumer - Integrates Merlin with AAS IPC system.
Consumes messages from AAS outbox and processes them.
"""

import json
import os
import shutil
import time
from pathlib import Path

# AAS IPC paths (relative to AAS root)
AAS_ROOT = Path(__file__).parent.parent  # Assuming Merlin is in AAS/Merlin
IPC_BASE = AAS_ROOT / "artifacts" / "ipc"
COMMANDS_OUTBOX = IPC_BASE / "commands" / "outbox"
COMMANDS_PROCESSING = IPC_BASE / "commands" / "processing" / "merlin"
COMMANDS_ARCHIVE = IPC_BASE / "commands" / "archive" / "merlin"
COMMANDS_DEADLETTER = IPC_BASE / "commands" / "deadletter"

def ensure_dirs():
    """Ensure IPC directories exist."""
    for d in [COMMANDS_PROCESSING, COMMANDS_ARCHIVE]:
        d.mkdir(parents=True, exist_ok=True)

def claim_message():
    """Atomically claim a message from outbox."""
    for msg_file in COMMANDS_OUTBOX.glob("*.json"):
        processing_file = COMMANDS_PROCESSING / msg_file.name
        try:
            msg_file.rename(processing_file)
            return processing_file
        except FileExistsError:
            continue  # Another consumer got it
    return None

def process_message(msg_file):
    """Process a claimed message."""
    try:
        with open(msg_file, 'r') as f:
            msg = json.load(f)

        print(f"Merlin processing: {msg.get('schemaName')} - {len(msg.get('commands', []))} commands")

        # Simulate processing (replace with real Merlin logic)
        for cmd in msg.get('commands', []):
            cmd_type = cmd.get('type')
            if cmd_type == 'delay':
                delay = cmd.get('delayMs', 1000) / 1000
                print(f"  Delaying {delay}s...")
                time.sleep(delay)
            else:
                print(f"  Unknown command: {cmd_type}")

        # Archive on success
        archive_file = COMMANDS_ARCHIVE / msg_file.name
        shutil.move(str(msg_file), str(archive_file))
        print(f"Archived: {archive_file}")

    except Exception as e:
        # Deadletter on failure
        error_file = COMMANDS_DEADLETTER / f"{msg_file.name}.error.txt"
        deadletter_file = COMMANDS_DEADLETTER / msg_file.name
        try:
            shutil.move(str(msg_file), str(deadletter_file))
            with open(error_file, 'w') as f:
                f.write(str(e))
            print(f"Deadlettered: {deadletter_file}")
        except Exception:
            print(f"Failed to deadletter: {e}")

def main():
    ensure_dirs()
    print("Merlin IPC Consumer started. Monitoring commands...")

    while True:
        msg_file = claim_message()
        if msg_file:
            process_message(msg_file)
        else:
            time.sleep(1)  # Poll every second

if __name__ == "__main__":
    main()
