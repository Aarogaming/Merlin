#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

FIELD_ORDER = (
    "planner_expected_tests",
    "schema_expected_tests",
    "planner_min_tests",
    "schema_min_tests",
    "sync_expected_summary",
)


def _require_int(payload: dict, key: str, minimum: int) -> int:
    value = payload.get(key)
    if not isinstance(value, int):
        raise ValueError(f"baseline field '{key}' must be an integer")
    if value < minimum:
        raise ValueError(f"baseline field '{key}' must be >= {minimum}")
    return value


def _require_string(payload: dict, key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"baseline field '{key}' must be a string")
    if not value.strip():
        raise ValueError(f"baseline field '{key}' must be non-empty")
    return value


def load_baseline(path: Path) -> dict[str, int | str]:
    if not path.exists():
        raise FileNotFoundError(f"baseline file not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict):
        raise ValueError("baseline root must be an object")

    normalized = {
        "planner_expected_tests": _require_int(payload, "planner_expected_tests", 1),
        "schema_expected_tests": _require_int(payload, "schema_expected_tests", 1),
        "planner_min_tests": _require_int(payload, "planner_min_tests", 1),
        "schema_min_tests": _require_int(payload, "schema_min_tests", 1),
        "sync_expected_summary": _require_string(payload, "sync_expected_summary"),
    }

    if normalized["planner_min_tests"] > normalized["planner_expected_tests"]:
        raise ValueError(
            "baseline planner_min_tests cannot exceed planner_expected_tests"
        )
    if normalized["schema_min_tests"] > normalized["schema_expected_tests"]:
        raise ValueError(
            "baseline schema_min_tests cannot exceed schema_expected_tests"
        )

    return normalized


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Load and validate CP4-A smoke baseline fields."
    )
    parser.add_argument(
        "--baseline",
        required=True,
        help="Path to CP4-A smoke baseline JSON.",
    )
    parser.add_argument(
        "--format",
        choices=("values", "json"),
        default="values",
        help="Output format. 'values' emits deterministic line order.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()

    try:
        baseline = load_baseline(Path(args.baseline))
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps(baseline, sort_keys=True))
        return 0

    for key in FIELD_ORDER:
        print(baseline[key])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
