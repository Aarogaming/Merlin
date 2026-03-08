#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

DEFAULT_TARGETS = [
    "tests/test_operation_expected_responses.py",
    "tests/test_operation_error_responses.py",
    "tests/test_operation_error_dynamic_responses.py",
    "tests/test_operation_error_specific_responses.py",
]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run Merlin operation endpoint conformance suites against contract fixtures."
        )
    )
    parser.add_argument(
        "--target",
        action="append",
        default=None,
        help=(
            "Specific pytest target to run. "
            "If omitted, the default operation conformance suite is used."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the pytest command without executing it.",
    )
    parser.add_argument(
        "--pytest-args",
        default="-q -s",
        help="Additional pytest arguments string (default: '-q -s').",
    )
    return parser


def _command_for_targets(targets: list[str], pytest_args: str) -> list[str]:
    command = [sys.executable, "-m", "pytest"]
    if pytest_args.strip():
        command.extend(pytest_args.strip().split())
    command.extend(targets)
    return command


def main() -> int:
    args = _build_parser().parse_args()
    targets = args.target if args.target else list(DEFAULT_TARGETS)
    command = _command_for_targets(targets, args.pytest_args)

    print("operation-conformance command:")
    print(" ".join(command))

    if args.dry_run:
        return 0

    result = subprocess.run(command, check=False)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
