import json
import os
from datetime import datetime
from merlin_logger import log_with_context

AUDIT_LOG_FILE = "logs/audit.json"


def log_audit_event(
    action: str, details: dict, user: str = "system", request_id: str | None = None
):
    event = {
        "timestamp": datetime.now().isoformat(),
        "user": user,
        "action": action,
        "details": details,
        "request_id": request_id,
    }

    # Log to structured logger
    log_with_context(
        "INFO", f"AUDIT: {action} by {user}", request_id=request_id, **details
    )

    # Also save to dedicated audit file
    try:
        if not os.path.exists("logs"):
            os.makedirs("logs")

        with open(AUDIT_LOG_FILE, "a") as f:
            f.write(json.dumps(event) + "\n")
    except Exception as e:
        print(f"Failed to write audit log: {e}")


def get_audit_logs(limit: int = 100):
    if not os.path.exists(AUDIT_LOG_FILE):
        return []

    try:
        with open(AUDIT_LOG_FILE, "r") as f:
            lines = f.readlines()
            return [json.loads(line) for line in lines[-limit:]]
    except Exception:
        return []
