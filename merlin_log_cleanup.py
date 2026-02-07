# Merlin Log Cleanup Script
# Deletes chat history files older than 90 days to save space

import os
import time
from pathlib import Path

CHAT_HISTORY_DIR = Path("merlin_chat_history")
DAYS_TO_KEEP = 90
now = time.time()

if not CHAT_HISTORY_DIR.exists():
    print("No chat history directory found.")
    exit(0)

for file in CHAT_HISTORY_DIR.glob("*.json"):
    mtime = file.stat().st_mtime
    age_days = (now - mtime) / 86400
    if age_days > DAYS_TO_KEEP:
        print(f"Deleting old chat file: {file} ({int(age_days)} days old)")
        file.unlink()
