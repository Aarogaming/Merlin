#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class PathCheck:
    category: str
    label: str
    path: Path
    required: bool = True


PATH_CHECKS: tuple[PathCheck, ...] = (
    PathCheck(
        category="contracts",
        label="operation envelope schema",
        path=ROOT_DIR / "contracts" / "aas.operation-envelope.v1.schema.json",
    ),
    PathCheck(
        category="contracts",
        label="routing metadata schema",
        path=ROOT_DIR / "contracts" / "assistant.chat.routing-metadata.v1.schema.json",
    ),
    PathCheck(
        category="protocol_docs",
        label="operation envelope protocol doc",
        path=ROOT_DIR / "docs" / "protocols" / "operation-envelope-v1.md",
    ),
    PathCheck(
        category="protocol_docs",
        label="capability protocol doc",
        path=ROOT_DIR / "docs" / "protocols" / "repo-capabilities-merlin-v1.md",
    ),
    PathCheck(
        category="tests",
        label="contract schema tests",
        path=ROOT_DIR / "tests" / "test_contract_schemas.py",
    ),
    PathCheck(
        category="tests",
        label="operation expected response tests",
        path=ROOT_DIR / "tests" / "test_operation_expected_responses.py",
    ),
)


def _latest_release_checklist_report() -> Path | None:
    release_dir = ROOT_DIR / "artifacts" / "release"
    if not release_dir.exists():
        return None
    reports = sorted(
        release_dir.glob("release_checklist_*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return reports[0] if reports else None


def _run_optional_checks(checklist_output_path: Path) -> list[dict[str, Any]]:
    maturity_report_path = checklist_output_path.parent / (
        f"maturity_evaluator_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    maturity_command = [
        sys.executable,
        "scripts/evaluate_maturity_promotion.py",
        "--output-json",
        str(maturity_report_path),
    ]
    latest_release_report = _latest_release_checklist_report()
    if latest_release_report:
        maturity_command.extend(
            ["--release-checklist-report", str(latest_release_report)]
        )
    smoke_report = ROOT_DIR / "artifacts" / "cp4a-smoke-evidence.json"
    if smoke_report.is_file():
        maturity_command.extend(["--smoke-evidence-report", str(smoke_report)])

    commands = [
        [sys.executable, "scripts/sync_contract_schemas.py", "--precommit"],
        [sys.executable, "-m", "pytest", "-q", "-s", "tests/test_sync_contract_schemas.py"],
        maturity_command,
    ]
    results: list[dict[str, Any]] = []
    env = os.environ.copy()
    stubs = "/tmp/merlin_test_stubs"
    if Path(stubs).exists():
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{stubs}:{existing}" if existing else stubs

    for command in commands:
        completed = subprocess.run(
            command,
            cwd=ROOT_DIR,
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )
        results.append(
            {
                "command": command,
                "ok": completed.returncode == 0,
                "returncode": completed.returncode,
                "stdout": completed.stdout[-2000:],
                "stderr": completed.stderr[-2000:],
            }
        )
    return results


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Merlin release checklist for contracts/artifacts/tests readiness."
    )
    parser.add_argument(
        "--run-commands",
        action="store_true",
        help="Run optional command validations in addition to path checks.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any checklist item fails.",
    )
    parser.add_argument(
        "--output-json",
        default=None,
        help="Optional output path for checklist JSON report.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    output_path = (
        Path(args.output_json)
        if args.output_json
        else (
            ROOT_DIR
            / "artifacts"
            / "release"
            / f"release_checklist_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    checks: list[dict[str, Any]] = []

    for item in PATH_CHECKS:
        exists = item.path.exists()
        checks.append(
            {
                "type": "path",
                "category": item.category,
                "label": item.label,
                "path": str(item.path.relative_to(ROOT_DIR)),
                "required": item.required,
                "ok": exists or not item.required,
                "details": "present" if exists else "missing",
            }
        )

    command_results: list[dict[str, Any]] = []
    if args.run_commands:
        command_results = _run_optional_checks(output_path)
        for result in command_results:
            checks.append(
                {
                    "type": "command",
                    "category": "validation_commands",
                    "label": " ".join(result["command"]),
                    "required": True,
                    "ok": bool(result["ok"]),
                    "details": f"returncode={result['returncode']}",
                }
            )

    failed_required = [item for item in checks if item.get("required") and not item.get("ok")]
    report = {
        "schema_name": "AAS.ReleaseChecklistReport",
        "schema_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root_dir": str(ROOT_DIR),
        "run_commands": bool(args.run_commands),
        "summary": {
            "total_checks": len(checks),
            "failed_required": len(failed_required),
            "ok": len(failed_required) == 0,
        },
        "checks": checks,
        "command_results": command_results,
    }

    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"Saved release checklist report: {output_path}")
    print(json.dumps(report["summary"], indent=2))

    if args.strict and failed_required:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
