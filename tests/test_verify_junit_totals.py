from __future__ import annotations

import subprocess
import sys
from pathlib import Path

VERIFY_SCRIPT = (
    Path(__file__).resolve().parents[1] / "scripts" / "verify_junit_totals.py"
)


def _write_junit(
    path: Path, tests: int, failures: int = 0, errors: int = 0, skipped: int = 0
) -> None:
    path.write_text(
        (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            f'<testsuites><testsuite name="suite" tests="{tests}" '
            f'failures="{failures}" errors="{errors}" skipped="{skipped}"/></testsuites>\n'
        ),
        encoding="utf-8",
    )


def _run_verify(*args: str) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(VERIFY_SCRIPT), *args]
    return subprocess.run(command, check=False, text=True, capture_output=True)


def test_verify_junit_totals_passes_with_valid_counts(tmp_path: Path):
    junit_path = tmp_path / "valid.xml"
    _write_junit(junit_path, tests=3, failures=0, errors=0, skipped=1)

    result = _run_verify(
        "--junit",
        str(junit_path),
        "--label",
        "schema",
        "--min-tests",
        "1",
    )

    assert result.returncode == 0
    assert "schema: tests=3 failures=0 errors=0 skipped=1" in result.stdout


def test_verify_junit_totals_fails_on_failures(tmp_path: Path):
    junit_path = tmp_path / "failing.xml"
    _write_junit(junit_path, tests=3, failures=1, errors=0)

    result = _run_verify("--junit", str(junit_path), "--label", "planner")

    assert result.returncode == 1
    assert "planner: failures/errors detected" in result.stdout


def test_verify_junit_totals_fails_when_expected_count_mismatch(tmp_path: Path):
    junit_path = tmp_path / "mismatch.xml"
    _write_junit(junit_path, tests=3, failures=0, errors=0)

    result = _run_verify(
        "--junit",
        str(junit_path),
        "--label",
        "planner",
        "--expect-tests",
        "5",
    )

    assert result.returncode == 1
    assert "planner: expected exactly 5 tests, got 3" in result.stdout
