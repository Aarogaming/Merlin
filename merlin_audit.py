import json
import os
from datetime import datetime
from typing import Any
from merlin_logger import log_with_context

AUDIT_LOG_FILE = "logs/audit.json"


def build_request_audit_metadata(
    route: str,
    decision_version: str,
    request_id: str | None,
    operation_name: str | None = None,
) -> dict:
    metadata = {
        "request_id": request_id,
        "route": route,
        "decision_version": decision_version,
    }
    if operation_name:
        metadata["operation_name"] = operation_name
    return metadata


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
    context_details = dict(details)
    context_details.pop("request_id", None)
    log_with_context(
        "INFO",
        f"AUDIT: {action} by {user}",
        request_id=request_id,
        **context_details,
    )

    # Also save to dedicated audit file
    try:
        if not os.path.exists("logs"):
            os.makedirs("logs")

        with open(AUDIT_LOG_FILE, "a") as f:
            f.write(json.dumps(event) + "\n")
    except Exception as e:
        print(f"Failed to write audit log: {e}")


def log_read_only_rejection(
    *,
    component: str,
    operation: str,
    details: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        "component": component,
        "operation": operation,
        "reason": "read_only_mode",
    }
    if details:
        payload.update(details)
    log_audit_event(
        action="read_only_rejection",
        details=payload,
        user=component,
        request_id=request_id,
    )


def get_audit_logs(limit: int = 100):
    if not os.path.exists(AUDIT_LOG_FILE):
        return []

    try:
        with open(AUDIT_LOG_FILE, "r") as f:
            lines = f.readlines()
            return [json.loads(line) for line in lines[-limit:]]
    except Exception:
        return []
