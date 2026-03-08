from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "verify_cp4a_smoke_evidence_schema.py"
)
SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "contracts"
    / "cp4a.smoke-evidence.v1.schema.json"
)


def _run_verify(*args: str) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(SCRIPT_PATH), *args]
    return subprocess.run(command, check=False, text=True, capture_output=True)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _valid_evidence() -> dict:
    return {
        "artifact_schema": "cp4a-smoke-evidence.v1",
        "status": "pass",
        "planner": {"tests": 45, "failures": 0, "errors": 0, "skipped": 0},
        "schema": {"tests": 44, "failures": 0, "errors": 0, "skipped": 0},
        "log_signatures": {
            "sync_summary_found": True,
            "taxonomy_summary_found": True,
            "smoke_signature_summary_found": True,
        },
        "inputs": {
            "planner_junit": "artifacts/planner-fallback-junit.xml",
            "schema_junit": "artifacts/cp4a-schema-junit.xml",
            "smoke_log": "artifacts/planner-fallback.log",
        },
    }


def test_verify_cp4a_smoke_evidence_schema_passes_for_valid_evidence(tmp_path: Path):
    evidence_path = tmp_path / "evidence.json"
    _write_json(evidence_path, _valid_evidence())

    result = _run_verify(
        "--schema-path",
        str(SCHEMA_PATH),
        "--evidence",
        str(evidence_path),
    )

    assert result.returncode == 0
    assert "cp4a smoke evidence schema verified" in result.stdout


def test_verify_cp4a_smoke_evidence_schema_fails_when_required_field_missing(
    tmp_path: Path,
):
    evidence_path = tmp_path / "evidence.json"
    evidence = _valid_evidence()
    evidence.pop("inputs")
    _write_json(evidence_path, evidence)

    result = _run_verify(
        "--schema-path",
        str(SCHEMA_PATH),
        "--evidence",
        str(evidence_path),
    )

    assert result.returncode == 1
    assert "cp4a smoke evidence schema validation failed:" in result.stdout
    assert "is a required property" in result.stdout


def test_verify_cp4a_smoke_evidence_schema_fails_when_pass_status_has_failures(
    tmp_path: Path,
):
    evidence_path = tmp_path / "evidence.json"
    evidence = _valid_evidence()
    evidence["planner"]["failures"] = 1
    _write_json(evidence_path, evidence)

    result = _run_verify(
        "--schema-path",
        str(SCHEMA_PATH),
        "--evidence",
        str(evidence_path),
    )

    assert result.returncode == 1
    assert "cp4a smoke evidence schema validation failed:" in result.stdout
    assert "planner.failures" in result.stdout
