#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Sequence

DEFAULT_BASELINE_PATH = Path("docs/research/CP4A_SMOKE_BASELINE_2026-02-15.json")

PLANNER_TEST_PATHS: tuple[str, ...] = (
    "tests/test_merlin_parallel_llm.py",
    "tests/test_merlin_streaming_llm.py",
    "tests/test_merlin_adaptive_llm.py",
    "tests/test_merlin_routing_contract.py",
)

SCHEMA_TEST_PATHS: tuple[str, ...] = (
    "tests/test_contract_schemas.py",
    "tests/test_merlin_routing_contract.py",
    "tests/test_export_cp4a_smoke_evidence.py",
    "tests/test_verify_cp4a_smoke_evidence_schema.py",
    "tests/test_sync_contract_schemas.py",
    "tests/test_verify_junit_totals.py",
    "tests/test_verify_routing_taxonomy_sync.py",
    "tests/test_verify_smoke_log_signatures.py",
)


def _parse_collected_tests(output: str) -> int:
    matches = list(
        re.finditer(r"(\d+)\s+tests?\s+collected", output, flags=re.IGNORECASE)
    )
    if not matches:
        raise ValueError(
            "unable to parse pytest --collect-only output for collected tests"
        )
    return int(matches[-1].group(1))


def _collect_tests_count(*, python_bin: str, test_paths: Sequence[str]) -> int:
    command = [
        python_bin,
        "-m",
        "pytest",
        "--collect-only",
        "-q",
        *test_paths,
    ]
    result = subprocess.run(
        command,
        check=False,
        text=True,
        capture_output=True,
    )
    output = f"{result.stdout}\n{result.stderr}"
    if result.returncode != 0:
        raise RuntimeError(
            "pytest --collect-only failed "
            f"(returncode={result.returncode}): {output[-1200:].strip()}"
        )
    return _parse_collected_tests(output)


def _load_baseline(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("baseline root must be an object")
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify CP4A smoke baseline expected test counts against collected tests."
    )
    parser.add_argument(
        "--baseline",
        default=str(DEFAULT_BASELINE_PATH),
        help="Path to CP4A smoke baseline JSON.",
    )
    parser.add_argument(
        "--python-bin",
        default=sys.executable,
        help="Python executable used to run pytest --collect-only.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Rewrite baseline expected test totals to current collected counts.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    baseline_path = Path(args.baseline)
    if not baseline_path.exists():
        print(f"baseline file not found: {baseline_path}", file=sys.stderr)
        return 1

    try:
        planner_tests = _collect_tests_count(
            python_bin=args.python_bin,
            test_paths=PLANNER_TEST_PATHS,
        )
        schema_tests = _collect_tests_count(
            python_bin=args.python_bin,
            test_paths=SCHEMA_TEST_PATHS,
        )
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    try:
        baseline = _load_baseline(baseline_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"planner_collected_tests={planner_tests}")
    print(f"schema_collected_tests={schema_tests}")

    if args.write:
        baseline["planner_expected_tests"] = planner_tests
        baseline["schema_expected_tests"] = schema_tests
        baseline_path.write_text(
            json.dumps(baseline, indent=2) + "\n", encoding="utf-8"
        )
        print(f"updated baseline: {baseline_path}")
        return 0

    planner_expected = baseline.get("planner_expected_tests")
    schema_expected = baseline.get("schema_expected_tests")

    mismatches: list[str] = []
    if planner_expected != planner_tests:
        mismatches.append(
            "planner_expected_tests mismatch: "
            f"baseline={planner_expected} collected={planner_tests}"
        )
    if schema_expected != schema_tests:
        mismatches.append(
            "schema_expected_tests mismatch: "
            f"baseline={schema_expected} collected={schema_tests}"
        )

    if mismatches:
        print("cp4a smoke baseline drift detected:")
        for line in mismatches:
            print(f"- {line}")
        print(
            "run `python scripts/verify_cp4a_smoke_baseline_counts.py --write` "
            "to refresh baseline expected totals"
        )
        return 1

    print("cp4a smoke baseline counts match collected test totals")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
