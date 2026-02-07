#!/usr/bin/env python3
"""
Merlin IPC Producer - Sends messages to AAS IPC system.
Example: Send a GameStateSnapshot after processing.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

# AAS IPC paths
AAS_ROOT = Path(__file__).parent.parent
IPC_BASE = AAS_ROOT / "artifacts" / "ipc"
SNAPSHOTS_INBOX = IPC_BASE / "snapshots" / "inbox"


def send_snapshot(resolution="1920x1080", gold=100):
    """Send a game state snapshot to AAS."""
    snapshot = {
        "schemaName": "GameStateSnapshot",
        "schemaVersion": "1.0.0",
        "capturedUtc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "resolution": resolution,
        "gold": gold,
    }

    # Write to temp file then rename atomically
    temp_file = SNAPSHOTS_INBOX / f"{uuid.uuid4()}.tmp"
    final_file = (
        SNAPSHOTS_INBOX
        / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_merlin_snapshot.json"
    )

    SNAPSHOTS_INBOX.mkdir(parents=True, exist_ok=True)

    with open(temp_file, "w") as f:
        json.dump(snapshot, f, indent=2)

    temp_file.rename(final_file)
    print(f"Merlin sent snapshot: {final_file}")


if __name__ == "__main__":
    send_snapshot()
