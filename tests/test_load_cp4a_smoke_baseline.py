from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "load_cp4a_smoke_baseline.py"
)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _run_load(*args: str) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(SCRIPT_PATH), *args]
    return subprocess.run(command, check=False, text=True, capture_output=True)


def _valid_baseline() -> dict:
    return {
        "planner_expected_tests": 45,
        "schema_expected_tests": 48,
        "planner_min_tests": 1,
        "schema_min_tests": 1,
        "sync_expected_summary": "contract schemas are in sync",
    }


def test_load_cp4a_smoke_baseline_values_output(tmp_path: Path):
    baseline_path = tmp_path / "baseline.json"
    _write_json(baseline_path, _valid_baseline())

    result = _run_load("--baseline", str(baseline_path))

    assert result.returncode == 0
    assert result.stdout.splitlines() == [
        "45",
        "48",
        "1",
        "1",
        "contract schemas are in sync",
    ]


def test_load_cp4a_smoke_baseline_fails_on_invalid_types(tmp_path: Path):
    baseline_path = tmp_path / "baseline.json"
    payload = _valid_baseline()
    payload["planner_expected_tests"] = "forty-five"  # type: ignore[assignment]
    _write_json(baseline_path, payload)

    result = _run_load("--baseline", str(baseline_path))

    assert result.returncode == 1
    assert "baseline field 'planner_expected_tests' must be an integer" in result.stderr


def test_load_cp4a_smoke_baseline_fails_on_min_greater_than_expected(tmp_path: Path):
    baseline_path = tmp_path / "baseline.json"
    payload = _valid_baseline()
    payload["planner_min_tests"] = 99
    _write_json(baseline_path, payload)

    result = _run_load("--baseline", str(baseline_path))

    assert result.returncode == 1
    assert "planner_min_tests cannot exceed planner_expected_tests" in result.stderr
