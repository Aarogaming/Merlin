#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import xml.etree.ElementTree as ET


def _parse_non_negative_int(raw: str | None) -> int:
    if raw is None:
        return 0
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 0
    return max(0, value)


def _collect_suites(root: ET.Element) -> list[ET.Element]:
    if root.tag == "testsuite":
        return [root]
    if root.tag == "testsuites":
        suites = list(root.findall("testsuite"))
        if suites:
            return suites
        # Some emitters may attach totals directly to testsuites.
        return [root]
    return [root]


def _summarize_junit(path: Path) -> dict[str, int]:
    tree = ET.parse(path)
    root = tree.getroot()
    suites = _collect_suites(root)

    tests = 0
    failures = 0
    errors = 0
    skipped = 0

    for suite in suites:
        tests += _parse_non_negative_int(suite.attrib.get("tests"))
        failures += _parse_non_negative_int(suite.attrib.get("failures"))
        errors += _parse_non_negative_int(suite.attrib.get("errors"))
        skipped += _parse_non_negative_int(suite.attrib.get("skipped"))

    return {
        "tests": tests,
        "failures": failures,
        "errors": errors,
        "skipped": skipped,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify JUnit totals for smoke/CI gating."
    )
    parser.add_argument("--junit", required=True, help="Path to JUnit XML file.")
    parser.add_argument("--label", default="junit", help="Label for output.")
    parser.add_argument(
        "--min-tests",
        type=int,
        default=1,
        help="Minimum number of tests expected in the JUnit file.",
    )
    parser.add_argument(
        "--expect-tests",
        type=int,
        default=None,
        help="Exact number of tests expected in the JUnit file.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    junit_path = Path(args.junit)

    if not junit_path.exists():
        print(f"{args.label}: junit file missing: {junit_path}")
        return 1

    summary = _summarize_junit(junit_path)
    tests = summary["tests"]
    failures = summary["failures"]
    errors = summary["errors"]
    skipped = summary["skipped"]

    print(
        f"{args.label}: tests={tests} failures={failures} errors={errors} skipped={skipped}"
    )

    if tests < args.min_tests:
        print(f"{args.label}: expected at least {args.min_tests} tests, got {tests}")
        return 1

    if args.expect_tests is not None and tests != args.expect_tests:
        print(f"{args.label}: expected exactly {args.expect_tests} tests, got {tests}")
        return 1

    if failures > 0 or errors > 0:
        print(f"{args.label}: failures/errors detected")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
