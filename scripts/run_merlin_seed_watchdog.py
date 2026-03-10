#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
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


def _pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _acquire_lock(lock_path: Path) -> int | None:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_data = {
        "pid": os.getpid(),
        "started_at": _utc_now_iso(),
    }
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(str(lock_path), flags)
    except FileExistsError:
        try:
            existing = json.loads(lock_path.read_text(encoding="utf-8"))
            existing_pid = int(existing.get("pid", 0))
        except Exception:
            existing_pid = 0
        if existing_pid and _pid_running(existing_pid):
            print(
                f"Watchdog lock active at {lock_path} (pid={existing_pid}); exiting duplicate instance."
            )
            return None
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass
        fd = os.open(str(lock_path), flags)

    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(lock_data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return fd


def _release_lock(fd: int | None, lock_path: Path) -> None:
    if fd is None:
        return
    try:
        os.close(fd)
    except OSError:
        pass
    try:
        lock_path.unlink()
    except FileNotFoundError:
        pass


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
    if args.output_json:
        output_path = Path(args.output_json)
        if not output_path.is_absolute():
            output_path = access.workspace_root / output_path
        lock_path = output_path.with_suffix(".lock")
    else:
        lock_path = (
            access.workspace_root
            / "artifacts"
            / "diagnostics"
            / "merlin_seed_watchdog_runtime.lock"
        )
    lock_fd = _acquire_lock(lock_path)
    if lock_fd is None:
        return 0

    tick_records: list[dict[str, Any]] = []

    try:
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
    finally:
        _release_lock(lock_fd, lock_path)

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
            access.workspace_root
            / "artifacts"
            / "diagnostics"
            / f"seed_watchdog_loop_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
    )
    if not output_path.is_absolute():
        output_path = access.workspace_root / output_path
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
