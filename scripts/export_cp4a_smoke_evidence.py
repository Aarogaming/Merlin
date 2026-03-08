#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
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
        description=(
            "Export machine-readable CP4-A smoke evidence using JUnit totals and"
            " required smoke log signatures."
        )
    )
    parser.add_argument(
        "--planner-junit", required=True, help="Planner JUnit XML path."
    )
    parser.add_argument("--schema-junit", required=True, help="Schema JUnit XML path.")
    parser.add_argument("--smoke-log", required=True, help="Smoke log path.")
    parser.add_argument("--output", required=True, help="Output evidence JSON path.")
    parser.add_argument(
        "--sync-summary",
        default="contract schemas are in sync",
        help="Required sync signature to check in smoke log.",
    )
    parser.add_argument(
        "--taxonomy-summary",
        default="routing taxonomy is in sync",
        help="Required taxonomy signature to check in smoke log.",
    )
    parser.add_argument(
        "--smoke-signature-summary",
        default="smoke log signatures verified",
        help="Required smoke signature verifier summary in smoke log.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()

    planner_junit = Path(args.planner_junit)
    schema_junit = Path(args.schema_junit)
    smoke_log = Path(args.smoke_log)
    output_path = Path(args.output)

    if not planner_junit.exists():
        print(f"planner junit file missing: {planner_junit}")
        return 1
    if not schema_junit.exists():
        print(f"schema junit file missing: {schema_junit}")
        return 1
    if not smoke_log.exists():
        print(f"smoke log file missing: {smoke_log}")
        return 1

    planner = _summarize_junit(planner_junit)
    schema = _summarize_junit(schema_junit)
    smoke_log_text = smoke_log.read_text(encoding="utf-8")

    sync_found = args.sync_summary in smoke_log_text
    taxonomy_found = args.taxonomy_summary in smoke_log_text
    smoke_signature_found = args.smoke_signature_summary in smoke_log_text
    junit_clean = (
        planner["failures"] == 0
        and planner["errors"] == 0
        and schema["failures"] == 0
        and schema["errors"] == 0
    )

    status = "pass"
    if (
        not sync_found
        or not taxonomy_found
        or not smoke_signature_found
        or not junit_clean
    ):
        status = "fail"

    payload = {
        "artifact_schema": "cp4a-smoke-evidence.v1",
        "status": status,
        "planner": planner,
        "schema": schema,
        "log_signatures": {
            "sync_summary_found": sync_found,
            "taxonomy_summary_found": taxonomy_found,
            "smoke_signature_summary_found": smoke_signature_found,
        },
        "inputs": {
            "planner_junit": str(planner_junit),
            "schema_junit": str(schema_junit),
            "smoke_log": str(smoke_log),
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(f"wrote {output_path}")
    print(f"cp4a smoke evidence status: {status}")
    if status != "pass":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
