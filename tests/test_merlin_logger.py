import json
import logging

from merlin_logger import JsonFormatter


def _record(message: str) -> logging.LogRecord:
    return logging.LogRecord(
        name="merlin",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )


def test_json_formatter_includes_extra_fields():
    formatter = JsonFormatter()
    record = _record("hello")
    record.request_id = "req-123"
    record.event = "http_access"
    record.status_code = 200

    payload = json.loads(formatter.format(record))

    assert payload["message"] == "hello"
    assert payload["request_id"] == "req-123"
    assert payload["event"] == "http_access"
    assert payload["status_code"] == 200


def test_json_formatter_stringifies_non_serializable_extra_fields():
    formatter = JsonFormatter()
    record = _record("hello")
    record.payload = {"data": object()}

    payload = json.loads(formatter.format(record))

    assert isinstance(payload["payload"], str)
    assert "object at" in payload["payload"]
