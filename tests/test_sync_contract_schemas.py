from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "sync_contract_schemas.py"
)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _run_sync(*args: str) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(SCRIPT_PATH), *args]
    return subprocess.run(command, check=False, text=True, capture_output=True)


def _standalone_schema() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://aas.local/contracts/assistant.chat.routing-metadata.v1.schema.json",
        "title": "Assistant Chat Routing Metadata v1",
        "description": "test schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["field_a"],
        "properties": {"field_a": {"type": "string"}},
    }


def _normalized_schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["field_a"],
        "properties": {"field_a": {"type": "string"}},
    }


def _envelope_schema(embedded: dict | None = None) -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://aas.local/contracts/aas.operation-envelope.v1.schema.json",
        "type": "object",
        "$defs": {
            "assistant_chat_routing_metadata": (
                embedded if embedded is not None else _normalized_schema()
            )
        },
    }


def test_sync_check_passes_when_schemas_are_in_sync(tmp_path: Path):
    standalone_path = tmp_path / "standalone.json"
    envelope_path = tmp_path / "envelope.json"
    _write_json(standalone_path, _standalone_schema())
    _write_json(envelope_path, _envelope_schema())

    result = _run_sync(
        "--check",
        "--standalone-path",
        str(standalone_path),
        "--envelope-path",
        str(envelope_path),
    )

    assert result.returncode == 0
    assert "contract schemas are in sync" in result.stdout


def test_sync_check_fails_on_schema_drift(tmp_path: Path):
    standalone_path = tmp_path / "standalone.json"
    envelope_path = tmp_path / "envelope.json"
    _write_json(standalone_path, _standalone_schema())
    _write_json(envelope_path, _envelope_schema({"type": "object", "properties": {}}))

    result = _run_sync(
        "--check",
        "--standalone-path",
        str(standalone_path),
        "--envelope-path",
        str(envelope_path),
    )

    assert result.returncode == 1
    assert "contract schema drift detected" in result.stdout


def test_sync_write_repairs_embedded_schema(tmp_path: Path):
    standalone_path = tmp_path / "standalone.json"
    envelope_path = tmp_path / "envelope.json"
    _write_json(standalone_path, _standalone_schema())
    _write_json(envelope_path, _envelope_schema({"type": "object", "properties": {}}))

    write_result = _run_sync(
        "--write",
        "--standalone-path",
        str(standalone_path),
        "--envelope-path",
        str(envelope_path),
    )
    check_result = _run_sync(
        "--check",
        "--standalone-path",
        str(standalone_path),
        "--envelope-path",
        str(envelope_path),
    )

    assert write_result.returncode == 0
    assert "updated" in write_result.stdout
    assert check_result.returncode == 0

    updated_envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
    assert (
        updated_envelope["$defs"]["assistant_chat_routing_metadata"]
        == _normalized_schema()
    )


def test_sync_precommit_mode_passes_when_in_sync(tmp_path: Path):
    standalone_path = tmp_path / "standalone.json"
    envelope_path = tmp_path / "envelope.json"
    _write_json(standalone_path, _standalone_schema())
    _write_json(envelope_path, _envelope_schema())

    result = _run_sync(
        "--precommit",
        "--standalone-path",
        str(standalone_path),
        "--envelope-path",
        str(envelope_path),
    )

    assert result.returncode == 0
    assert "contract-schema-sync: PASS" in result.stdout


def test_sync_precommit_mode_fails_when_out_of_sync(tmp_path: Path):
    standalone_path = tmp_path / "standalone.json"
    envelope_path = tmp_path / "envelope.json"
    _write_json(standalone_path, _standalone_schema())
    _write_json(envelope_path, _envelope_schema({"type": "object", "properties": {}}))

    result = _run_sync(
        "--precommit",
        "--standalone-path",
        str(standalone_path),
        "--envelope-path",
        str(envelope_path),
    )

    assert result.returncode == 1
    assert "contract-schema-sync: FAIL" in result.stdout
