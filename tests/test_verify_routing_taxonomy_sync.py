from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "verify_routing_taxonomy_sync.py"
)
SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "contracts"
    / "assistant.chat.routing-metadata.v1.schema.json"
)


def _run_verify(*args: str) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(SCRIPT_PATH), *args]
    return subprocess.run(command, check=False, text=True, capture_output=True)


def _load_schema() -> dict:
    with SCHEMA_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_schema(path: Path, schema: dict) -> None:
    path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")


def test_verify_routing_taxonomy_sync_passes_with_repo_schema():
    result = _run_verify()

    assert result.returncode == 0
    assert "routing taxonomy is in sync" in result.stdout


def test_verify_routing_taxonomy_sync_fails_when_reason_code_enum_drifts(
    tmp_path: Path,
):
    schema = _load_schema()
    enum_values = schema["properties"]["fallback_reason_code"]["enum"]
    schema["properties"]["fallback_reason_code"]["enum"] = [
        value for value in enum_values if value != "dms_timeout"
    ]
    schema_path = tmp_path / "schema.json"
    _write_schema(schema_path, schema)

    result = _run_verify("--schema-path", str(schema_path))

    assert result.returncode == 1
    assert "fallback_reason_code enum mismatch" in result.stdout


def test_verify_routing_taxonomy_sync_fails_when_retryable_partition_drifts(
    tmp_path: Path,
):
    schema = _load_schema()
    for rule in schema["allOf"]:
        reason_code = (
            rule.get("if", {}).get("properties", {}).get("fallback_reason_code")
        )
        retryable = rule.get("then", {}).get("properties", {}).get("fallback_retryable")
        if reason_code and retryable and retryable.get("const") is True:
            enum_values = reason_code.get("enum", [])
            if "dms_timeout" in enum_values:
                enum_values.remove("dms_timeout")
                break

    schema_path = tmp_path / "schema.json"
    _write_schema(schema_path, schema)

    result = _run_verify("--schema-path", str(schema_path))

    assert result.returncode == 1
    assert "retryable(true) partition mismatch" in result.stdout
