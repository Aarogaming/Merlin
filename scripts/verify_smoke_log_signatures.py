#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify smoke log signatures and required artifact files for planner"
            " fallback smoke runs."
        )
    )
    parser.add_argument("--log", required=True, help="Path to smoke log file.")
    parser.add_argument(
        "--expect-summary",
        action="append",
        default=[],
        help="Required log summary signature (repeatable).",
    )
    parser.add_argument(
        "--require-file",
        action="append",
        default=[],
        help="Required non-empty artifact path (repeatable).",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    log_path = Path(args.log)

    errors: list[str] = []
    if not log_path.exists():
        errors.append(f"log file missing: {log_path}")
        log_text = ""
    else:
        log_text = log_path.read_text(encoding="utf-8")

    for summary in args.expect_summary:
        if summary not in log_text:
            errors.append(f"missing summary signature: {summary}")

    for raw_path in args.require_file:
        artifact_path = Path(raw_path)
        if not artifact_path.exists():
            errors.append(f"required artifact missing: {artifact_path}")
            continue
        if artifact_path.stat().st_size <= 0:
            errors.append(f"required artifact is empty: {artifact_path}")

    if errors:
        print("smoke log signature check failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("smoke log signatures verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
