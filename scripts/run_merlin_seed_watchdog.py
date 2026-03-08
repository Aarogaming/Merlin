#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from merlin_seed_access import build_seed_access


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run Merlin seed watchdog ticks in a loop and optionally apply control actions."
        )
    )
    parser.add_argument(
        "--workspace-root",
        default=None,
        help="Workspace root containing seed artifacts/guild/scripts.",
    )
    parser.add_argument("--status-file", default=None, help="Override status file path.")
    parser.add_argument(
        "--merged-jsonl",
        default=None,
        help="Override merged JSONL dataset path.",
    )
    parser.add_argument(
        "--merged-parquet",
        default=None,
        help="Override merged parquet dataset path.",
    )
    parser.add_argument("--log-file", default=None, help="Override runtime log path.")
    parser.add_argument(
        "--stale-after-seconds",
        type=float,
        default=3600.0,
        help="Seconds before status is treated as stale.",
    )
    apply_group = parser.add_mutually_exclusive_group()
    apply_group.add_argument(
        "--apply",
        dest="apply",
        action="store_true",
        help="Apply recommended control actions when policy allows.",
    )
    apply_group.add_argument(
        "--no-apply",
        dest="apply",
        action="store_false",
        help="Preview-only mode (default).",
    )
    parser.set_defaults(apply=False)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force control action when watchdog applies start/restart.",
    )
    parser.add_argument(
        "--dry-run-control",
        action="store_true",
        help="When --apply is set, execute control in dry-run mode.",
    )
    live_group = parser.add_mutually_exclusive_group()
    live_group.add_argument(
        "--allow-live-automation",
        dest="allow_live_automation",
        action="store_true",
        help="Force allow_live_automation=true policy override.",
    )
    live_group.add_argument(
        "--no-live-automation",
        dest="allow_live_automation",
        action="store_false",
        help="Force allow_live_automation=false policy override.",
    )
    parser.set_defaults(allow_live_automation=None)
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=60.0,
        help="Sleep interval between iterations when max-iterations > 1.",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=1,
        help="Number of watchdog ticks to execute (0 means continuous).",
    )
    heartbeat_group = parser.add_mutually_exclusive_group()
    heartbeat_group.add_argument(
        "--emit-heartbeat",
        dest="emit_heartbeat",
        action="store_true",
        help="Emit a seed heartbeat event each iteration (default).",
    )
    heartbeat_group.add_argument(
        "--no-heartbeat",
        dest="emit_heartbeat",
        action="store_false",
        help="Skip heartbeat emission for this run.",
    )
    parser.set_defaults(emit_heartbeat=True)
    parser.add_argument(
        "--heartbeat-file",
        default=None,
        help="Override heartbeat JSONL output path.",
    )
    parser.add_argument(
        "--append-jsonl",
        default=None,
        help="Optional JSONL path to append each tick payload.",
    )
    parser.add_argument(
        "--output-json",
        default=None,
        help="Report output path (default under artifacts/diagnostics).",
    )
    return parser


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def main() -> int:
    args = _build_parser().parse_args()
    raw_max_iterations = int(args.max_iterations)
    if raw_max_iterations < 0:
        raw_max_iterations = 1
    infinite_mode = raw_max_iterations == 0
    max_iterations = raw_max_iterations
    interval_seconds = max(0.0, float(args.interval_seconds))
    stale_after_seconds = max(1.0, float(args.stale_after_seconds))

    access = build_seed_access(workspace_root=args.workspace_root)
    tick_records: list[dict[str, Any]] = []

    iteration = 0
    while True:
        iteration += 1
        watchdog_payload = access.watchdog(
            status_file=args.status_file,
            merged_jsonl=args.merged_jsonl,
            merged_parquet=args.merged_parquet,
            log_file=args.log_file,
            allow_live_automation=args.allow_live_automation,
            stale_after_seconds=stale_after_seconds,
            apply=bool(args.apply),
            force=bool(args.force),
            dry_run_control=bool(args.dry_run_control),
        )

        heartbeat_payload = None
        if args.emit_heartbeat:
            heartbeat_payload = access.heartbeat(
                status_file=args.status_file,
                merged_jsonl=args.merged_jsonl,
                merged_parquet=args.merged_parquet,
                log_file=args.log_file,
                allow_live_automation=args.allow_live_automation,
                stale_after_seconds=stale_after_seconds,
                heartbeat_file=args.heartbeat_file,
                write_event=True,
            )

        record = {
            "iteration": iteration,
            "watchdog": watchdog_payload,
            "heartbeat": heartbeat_payload,
            "tick_at": _utc_now_iso(),
        }
        tick_records.append(record)

        if args.append_jsonl:
            _append_jsonl(Path(args.append_jsonl), record)

        if not infinite_mode and iteration >= max_iterations:
            break
        if interval_seconds > 0:
            time.sleep(interval_seconds)

    outcomes = [
        str(
            (
                tick.get("watchdog", {})
                .get("decision", {})
                .get("outcome_status", "unknown")
            )
        ).strip()
        for tick in tick_records
    ]
    summary = {
        "total_ticks": len(tick_records),
        "noop": outcomes.count("noop"),
        "preview": outcomes.count("preview"),
        "executed": outcomes.count("executed"),
        "blocked": outcomes.count("blocked"),
        "error": outcomes.count("error"),
    }

    report = {
        "schema_name": "AAS.Merlin.SeedWatchdogLoopResult",
        "schema_version": "1.0.0",
        "workspace_root": str(access.workspace_root),
        "generated_at": _utc_now_iso(),
        "mode": {
            "apply": bool(args.apply),
            "force": bool(args.force),
            "dry_run_control": bool(args.dry_run_control),
            "emit_heartbeat": bool(args.emit_heartbeat),
            "infinite_mode": infinite_mode,
            "max_iterations": max_iterations,
            "interval_seconds": interval_seconds,
        },
        "summary": summary,
        "ticks": tick_records,
    }

    output_path = (
        Path(args.output_json)
        if args.output_json
        else (
            Path("artifacts")
            / "diagnostics"
            / f"seed_watchdog_loop_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"Saved seed watchdog report: {output_path}")
    print(json.dumps(summary, indent=2))

    if summary["error"] > 0:
        return 2
    if bool(args.apply) and summary["blocked"] > 0:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
