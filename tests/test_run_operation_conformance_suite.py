from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[1] / "scripts" / "run_operation_conformance_suite.py"
)


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def test_dry_run_uses_default_targets():
    result = _run("--dry-run")

    assert result.returncode == 0
    assert "operation-conformance command:" in result.stdout
    assert "tests/test_operation_expected_responses.py" in result.stdout
    assert "tests/test_operation_error_responses.py" in result.stdout
    assert "tests/test_operation_error_dynamic_responses.py" in result.stdout
    assert "tests/test_operation_error_specific_responses.py" in result.stdout


def test_dry_run_supports_custom_targets():
    result = _run(
        "--dry-run",
        "--target",
        "tests/test_operation_expected_responses.py",
        "--pytest-args=-q",
    )

    assert result.returncode == 0
    assert " -m pytest -q tests/test_operation_expected_responses.py" in result.stdout
    assert "tests/test_operation_error_responses.py" not in result.stdout
