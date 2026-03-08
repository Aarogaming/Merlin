#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BenchmarkCommand:
    command_id: str
    command: list[str]
    description: str
    critical: bool = False


DEFAULT_COMMAND_PACK: tuple[BenchmarkCommand, ...] = (
    BenchmarkCommand(
        command_id="python_version",
        command=[sys.executable, "--version"],
        description="Capture interpreter version used for benchmark snapshots.",
        critical=True,
    ),
    BenchmarkCommand(
        command_id="llm_local_snapshot",
        command=[
            sys.executable,
            "merlin_benchmark.py",
            "--iterations",
            "1",
            "--output-json",
            "artifacts/benchmarks/llm_local_snapshot.json",
        ],
        description="Run one local LLM benchmark iteration and store JSON snapshot.",
        critical=False,
    ),
    BenchmarkCommand(
        command_id="voice_dataset_snapshot",
        command=[
            sys.executable,
            "merlin_voice_benchmark.py",
            "--engines",
            "pyttsx3",
            "--runs",
            "1",
            "--output-dir",
            "artifacts/benchmarks/voice",
        ],
        description="Run voice benchmark snapshot with catalog-backed dataset metadata.",
        critical=False,
    ),
    BenchmarkCommand(
        command_id="operation_conformance_plan",
        command=[
            sys.executable,
            "scripts/run_operation_conformance_suite.py",
            "--dry-run",
        ],
        description="Capture conformance suite command plan for reproducibility.",
        critical=True,
    ),
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run standardized Merlin benchmark command pack."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not execute commands; emit plan only (default).",
    )
    mode.add_argument(
        "--execute",
        action="store_true",
        help="Execute selected commands and capture outcomes.",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="Run only selected command IDs (repeatable).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail when any selected command fails (default fails only critical commands).",
    )
    parser.add_argument(
        "--output-json",
        default=None,
        help="Optional output path for command-pack report JSON.",
    )
    return parser


def _select_commands(only_ids: list[str]) -> list[BenchmarkCommand]:
    if not only_ids:
        return list(DEFAULT_COMMAND_PACK)

    selected = []
    wanted = {item.strip() for item in only_ids if item.strip()}
    for command in DEFAULT_COMMAND_PACK:
        if command.command_id in wanted:
            selected.append(command)
    return selected


def _render_command(command: list[str]) -> str:
    return " ".join(shlex.quote(token) for token in command)


def _run_command(command: BenchmarkCommand) -> dict[str, Any]:
    completed = subprocess.run(
        command.command,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "command_id": command.command_id,
        "description": command.description,
        "critical": command.critical,
        "executed": True,
        "command": command.command,
        "command_str": _render_command(command.command),
        "returncode": completed.returncode,
        "ok": completed.returncode == 0,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
    }


def main() -> int:
    args = _build_parser().parse_args()
    execute = bool(args.execute)
    selected = _select_commands(args.only)
    if not selected:
        print("No benchmark commands selected.")
        return 1

    results: list[dict[str, Any]] = []
    if execute:
        for command in selected:
            results.append(_run_command(command))
    else:
        for command in selected:
            results.append(
                {
                    "command_id": command.command_id,
                    "description": command.description,
                    "critical": command.critical,
                    "executed": False,
                    "command": command.command,
                    "command_str": _render_command(command.command),
                    "returncode": None,
                    "ok": None,
                }
            )

    failed = [item for item in results if item.get("executed") and not item.get("ok")]
    failed_critical = [item for item in failed if item.get("critical")]

    report = {
        "schema_name": "AAS.BenchmarkCommandPackResult",
        "schema_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "execute" if execute else "dry_run",
        "selected_command_ids": [item.command_id for item in selected],
        "summary": {
            "total": len(results),
            "executed": sum(1 for item in results if item.get("executed")),
            "failed": len(failed),
            "failed_critical": len(failed_critical),
        },
        "results": results,
    }

    output_path = (
        Path(args.output_json)
        if args.output_json
        else (
            Path("artifacts")
            / "benchmarks"
            / f"benchmark_command_pack_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"Saved benchmark command pack report: {output_path}")
    print(json.dumps(report["summary"], indent=2))

    if not execute:
        return 0
    if args.strict and failed:
        return 1
    if failed_critical:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
