from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "verify_cp4a_smoke_baseline_counts.py"
)
SPEC = importlib.util.spec_from_file_location(
    "verify_cp4a_smoke_baseline_counts_module",
    SCRIPT_PATH,
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _baseline_payload(planner_expected_tests: int, schema_expected_tests: int) -> dict:
    return {
        "planner_expected_tests": planner_expected_tests,
        "schema_expected_tests": schema_expected_tests,
        "planner_min_tests": 1,
        "schema_min_tests": 1,
        "sync_expected_summary": "contract schemas are in sync",
    }


def test_parse_collected_tests_uses_last_summary_line():
    output = "\n".join(
        [
            "12 tests collected in 0.10s",
            "warning line",
            "149 tests collected in 1.12s",
        ]
    )
    assert MODULE._parse_collected_tests(output) == 149


def test_verify_cp4a_smoke_baseline_counts_passes_when_counts_match(
    monkeypatch, tmp_path: Path
):
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps(_baseline_payload(149, 104), indent=2) + "\n",
        encoding="utf-8",
    )

    def _fake_collect_tests_count(*, python_bin, test_paths):
        if tuple(test_paths) == MODULE.PLANNER_TEST_PATHS:
            return 149
        if tuple(test_paths) == MODULE.SCHEMA_TEST_PATHS:
            return 104
        raise AssertionError(f"unexpected test paths: {test_paths}")

    monkeypatch.setattr(MODULE, "_collect_tests_count", _fake_collect_tests_count)
    monkeypatch.setattr(
        MODULE.sys,
        "argv",
        [
            "verify_cp4a_smoke_baseline_counts.py",
            "--baseline",
            str(baseline_path),
        ],
    )

    assert MODULE.main() == 0


def test_verify_cp4a_smoke_baseline_counts_fails_on_drift(monkeypatch, tmp_path: Path):
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps(_baseline_payload(149, 104), indent=2) + "\n",
        encoding="utf-8",
    )

    def _fake_collect_tests_count(*, python_bin, test_paths):
        if tuple(test_paths) == MODULE.PLANNER_TEST_PATHS:
            return 150
        if tuple(test_paths) == MODULE.SCHEMA_TEST_PATHS:
            return 104
        raise AssertionError(f"unexpected test paths: {test_paths}")

    monkeypatch.setattr(MODULE, "_collect_tests_count", _fake_collect_tests_count)
    monkeypatch.setattr(
        MODULE.sys,
        "argv",
        [
            "verify_cp4a_smoke_baseline_counts.py",
            "--baseline",
            str(baseline_path),
        ],
    )

    assert MODULE.main() == 1


def test_verify_cp4a_smoke_baseline_counts_write_updates_expected_totals(
    monkeypatch, tmp_path: Path
):
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps(_baseline_payload(45, 48), indent=2) + "\n",
        encoding="utf-8",
    )

    def _fake_collect_tests_count(*, python_bin, test_paths):
        if tuple(test_paths) == MODULE.PLANNER_TEST_PATHS:
            return 149
        if tuple(test_paths) == MODULE.SCHEMA_TEST_PATHS:
            return 104
        raise AssertionError(f"unexpected test paths: {test_paths}")

    monkeypatch.setattr(MODULE, "_collect_tests_count", _fake_collect_tests_count)
    monkeypatch.setattr(
        MODULE.sys,
        "argv",
        [
            "verify_cp4a_smoke_baseline_counts.py",
            "--baseline",
            str(baseline_path),
            "--write",
        ],
    )

    assert MODULE.main() == 0
    updated = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert updated["planner_expected_tests"] == 149
    assert updated["schema_expected_tests"] == 104
