from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "export_cp4a_smoke_evidence.py"
)


def _write_junit(
    path: Path, *, tests: int, failures: int = 0, errors: int = 0, skipped: int = 0
) -> None:
    path.write_text(
        (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            f'<testsuites><testsuite name="suite" tests="{tests}" '
            f'failures="{failures}" errors="{errors}" skipped="{skipped}"/></testsuites>\n'
        ),
        encoding="utf-8",
    )


def _run_export(*args: str) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(SCRIPT_PATH), *args]
    return subprocess.run(command, check=False, text=True, capture_output=True)


def test_export_cp4a_smoke_evidence_passes_with_valid_inputs(tmp_path: Path):
    planner_junit = tmp_path / "planner.xml"
    schema_junit = tmp_path / "schema.xml"
    smoke_log = tmp_path / "smoke.log"
    output = tmp_path / "evidence.json"

    _write_junit(planner_junit, tests=45)
    _write_junit(schema_junit, tests=41)
    smoke_log.write_text(
        "\n".join(
            [
                "contract schemas are in sync",
                "routing taxonomy is in sync",
                "smoke log signatures verified",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = _run_export(
        "--planner-junit",
        str(planner_junit),
        "--schema-junit",
        str(schema_junit),
        "--smoke-log",
        str(smoke_log),
        "--output",
        str(output),
    )

    assert result.returncode == 0
    assert "cp4a smoke evidence status: pass" in result.stdout
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "pass"
    assert payload["planner"]["tests"] == 45
    assert payload["schema"]["tests"] == 41
    assert payload["log_signatures"]["sync_summary_found"] is True
    assert payload["log_signatures"]["taxonomy_summary_found"] is True
    assert payload["log_signatures"]["smoke_signature_summary_found"] is True


def test_export_cp4a_smoke_evidence_fails_when_required_signature_missing(
    tmp_path: Path,
):
    planner_junit = tmp_path / "planner.xml"
    schema_junit = tmp_path / "schema.xml"
    smoke_log = tmp_path / "smoke.log"
    output = tmp_path / "evidence.json"

    _write_junit(planner_junit, tests=45)
    _write_junit(schema_junit, tests=41)
    smoke_log.write_text(
        "\n".join(
            [
                "contract schemas are in sync",
                "routing taxonomy is in sync",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = _run_export(
        "--planner-junit",
        str(planner_junit),
        "--schema-junit",
        str(schema_junit),
        "--smoke-log",
        str(smoke_log),
        "--output",
        str(output),
    )

    assert result.returncode == 1
    assert "cp4a smoke evidence status: fail" in result.stdout
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "fail"
    assert payload["log_signatures"]["smoke_signature_summary_found"] is False


def test_export_cp4a_smoke_evidence_is_timing_insensitive_for_totals(tmp_path: Path):
    planner_junit = tmp_path / "planner.xml"
    schema_junit = tmp_path / "schema.xml"
    smoke_log = tmp_path / "smoke.log"
    output = tmp_path / "evidence.json"

    _write_junit(planner_junit, tests=45)
    _write_junit(schema_junit, tests=41)
    smoke_log.write_text(
        "\n".join(
            [
                "45 passed in 0.01s",
                "41 passed in 99.99s",
                "contract schemas are in sync",
                "routing taxonomy is in sync",
                "smoke log signatures verified",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = _run_export(
        "--planner-junit",
        str(planner_junit),
        "--schema-junit",
        str(schema_junit),
        "--smoke-log",
        str(smoke_log),
        "--output",
        str(output),
    )

    assert result.returncode == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["planner"]["tests"] == 45
    assert payload["schema"]["tests"] == 41
