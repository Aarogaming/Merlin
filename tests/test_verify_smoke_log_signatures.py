from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "verify_smoke_log_signatures.py"
)


def _run_verify(*args: str) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(SCRIPT_PATH), *args]
    return subprocess.run(command, check=False, text=True, capture_output=True)


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_verify_smoke_log_signatures_passes_with_required_signatures_and_artifacts(
    tmp_path: Path,
):
    log_path = tmp_path / "smoke.log"
    planner_junit = tmp_path / "planner.xml"
    schema_junit = tmp_path / "schema.xml"

    _write(log_path, "contract schemas are in sync\nrouting taxonomy is in sync\n")
    _write(planner_junit, "<testsuites/>")
    _write(schema_junit, "<testsuites/>")

    result = _run_verify(
        "--log",
        str(log_path),
        "--expect-summary",
        "contract schemas are in sync",
        "--expect-summary",
        "routing taxonomy is in sync",
        "--require-file",
        str(planner_junit),
        "--require-file",
        str(schema_junit),
    )

    assert result.returncode == 0
    assert "smoke log signatures verified" in result.stdout


def test_verify_smoke_log_signatures_fails_when_summary_signature_is_missing(
    tmp_path: Path,
):
    log_path = tmp_path / "smoke.log"
    planner_junit = tmp_path / "planner.xml"
    schema_junit = tmp_path / "schema.xml"

    _write(log_path, "contract schemas are in sync\n")
    _write(planner_junit, "<testsuites/>")
    _write(schema_junit, "<testsuites/>")

    result = _run_verify(
        "--log",
        str(log_path),
        "--expect-summary",
        "contract schemas are in sync",
        "--expect-summary",
        "routing taxonomy is in sync",
        "--require-file",
        str(planner_junit),
        "--require-file",
        str(schema_junit),
    )

    assert result.returncode == 1
    assert "missing summary signature: routing taxonomy is in sync" in result.stdout


def test_verify_smoke_log_signatures_fails_when_required_artifact_is_empty(
    tmp_path: Path,
):
    log_path = tmp_path / "smoke.log"
    planner_junit = tmp_path / "planner.xml"
    schema_junit = tmp_path / "schema.xml"

    _write(log_path, "contract schemas are in sync\nrouting taxonomy is in sync\n")
    _write(planner_junit, "<testsuites/>")
    _write(schema_junit, "")

    result = _run_verify(
        "--log",
        str(log_path),
        "--expect-summary",
        "contract schemas are in sync",
        "--expect-summary",
        "routing taxonomy is in sync",
        "--require-file",
        str(planner_junit),
        "--require-file",
        str(schema_junit),
    )

    assert result.returncode == 1
    assert f"required artifact is empty: {schema_junit}" in result.stdout
