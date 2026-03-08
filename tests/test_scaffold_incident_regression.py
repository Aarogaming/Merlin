from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "scaffold_incident_regression.py"
)


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        check=False,
        text=True,
        capture_output=True,
    )


def test_scaffold_incident_regression_creates_fixture_and_test(tmp_path: Path):
    fixture_dir = tmp_path / "fixtures" / "incidents"
    tests_dir = tmp_path / "tests"

    result = _run(
        "--incident-id",
        "INC-2026-02-22-001",
        "--operation-name",
        "merlin.command.execute",
        "--error-code",
        "COMMAND_EXECUTION_FAILED",
        "--summary",
        "Command path returned transient execution failure.",
        "--fixture-dir",
        str(fixture_dir),
        "--tests-dir",
        str(tests_dir),
    )

    assert result.returncode == 0
    fixture_path = fixture_dir / "inc_2026_02_22_001.incident_regression.scaffold.json"
    test_path = tests_dir / "test_incident_regression_inc_2026_02_22_001.py"
    assert fixture_path.exists()
    assert test_path.exists()

    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert payload["schema_name"] == "AAS.IncidentRegressionScaffold"
    assert payload["incident"]["incident_id"] == "INC-2026-02-22-001"
    assert payload["incident"]["operation_name"] == "merlin.command.execute"
    assert payload["regression_plan"]["expected_error_code"] == "COMMAND_EXECUTION_FAILED"

    generated_test = test_path.read_text(encoding="utf-8")
    assert "pytest.mark.skip" in generated_test
    assert "INC-2026-02-22-001" in generated_test


def test_scaffold_incident_regression_refuses_overwrite_without_force(tmp_path: Path):
    fixture_dir = tmp_path / "fixtures" / "incidents"
    tests_dir = tmp_path / "tests"
    base_args = (
        "--incident-id",
        "INC-2026-02-22-002",
        "--operation-name",
        "assistant.tools.execute",
        "--error-code",
        "TOOL_EXECUTION_ERROR",
        "--fixture-dir",
        str(fixture_dir),
        "--tests-dir",
        str(tests_dir),
    )

    first = _run(*base_args)
    second = _run(*base_args)

    assert first.returncode == 0
    assert second.returncode == 1
    assert "refusing to overwrite existing file without --force" in second.stdout


def test_scaffold_incident_regression_dry_run_does_not_write_files(tmp_path: Path):
    fixture_dir = tmp_path / "fixtures" / "incidents"
    tests_dir = tmp_path / "tests"

    result = _run(
        "--incident-id",
        "INC-2026-02-22-003",
        "--operation-name",
        "merlin.plugins.execute",
        "--error-code",
        "PLUGIN_EXECUTION_ERROR",
        "--fixture-dir",
        str(fixture_dir),
        "--tests-dir",
        str(tests_dir),
        "--dry-run",
    )

    assert result.returncode == 0
    assert "[dry-run] fixture_path=" in result.stdout
    assert "[dry-run] test_path=" in result.stdout
    assert not fixture_dir.exists()
    assert not tests_dir.exists()
