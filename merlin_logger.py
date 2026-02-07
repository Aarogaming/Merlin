import logging
import json
import os
from datetime import datetime
from typing import Any, Dict
from pathlib import Path


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "funcName": record.funcName,
            "line": record.lineno,
        }

        # Add extra fields if present (like request_id)
        if hasattr(record, "request_id"):
            log_data["request_id"] = getattr(record, "request_id")

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


def setup_merlin_logger(log_dir: str = "logs", log_file: str = "merlin.json"):
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    logger = logging.getLogger("merlin")
    logger.setLevel(logging.INFO)

    # File handler (JSON)
    file_handler = logging.FileHandler(os.path.join(log_dir, log_file))
    file_handler.setFormatter(JsonFormatter())
    logger.addHandler(file_handler)

    # Console handler (Standard)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    logger.addHandler(console_handler)

    return logger


merlin_logger = setup_merlin_logger()


def get_recent_logs(lines: int = 100) -> list:
    log_path = Path("logs/merlin.json")
    if not log_path.exists():
        return []

    with open(log_path, "r") as f:
        all_lines = f.readlines()
        return [json.loads(line) for line in all_lines[-lines:]]


# Context-aware logging helper
def log_with_context(level: str, message: str, request_id: str | None = None, **kwargs):
    extra = {"request_id": request_id} if request_id else {}
    extra.update(kwargs)

    if level.upper() == "INFO":
        merlin_logger.info(message, extra=extra)
    elif level.upper() == "WARNING":
        merlin_logger.warning(message, extra=extra)
    elif level.upper() == "ERROR":
        merlin_logger.error(message, extra=extra)
    elif level.upper() == "DEBUG":
        merlin_logger.debug(message, extra=extra)
