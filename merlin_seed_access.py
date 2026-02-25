from __future__ import annotations

import json
import os
import shlex
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

POLICY_ALLOWED = "allowed"
POLICY_STUBBED = "stubbed"

DEFAULT_STATUS_FILE = "artifacts/merlin_seed_status.json"
DEFAULT_MERGED_JSONL = "guild/data/merlin_distill_merged.jsonl"
DEFAULT_MERGED_PARQUET = "guild/data/merlin_distill_merged.parquet"
DEFAULT_LOG_FILE = "logs/merlin_seed_task.log"
DEFAULT_PROMPT_SET = "scripts/eval/prompts_guild.json"
DEFAULT_SEED_TARGET = 50000
DEFAULT_SEED_INCREMENT = 500
DEFAULT_SEED_REPEAT = 13
DEFAULT_SEED_ETA_WINDOW = 5
DEFAULT_SEED_SLEEP = 0.1
DEFAULT_SEED_DELAY = 1.0
DEFAULT_SEED_CPU_MAX = 85.0
DEFAULT_SEED_MEM_MAX = 85.0
DEFAULT_SEED_RESOURCE_WAIT = 5.0
DEFAULT_LOG_TAIL_LINES = 40
MAX_LOG_TAIL_LINES = 400

DEFAULT_PROCESS_MATCH_TOKENS: tuple[str, ...] = (
    "run_merlin_seed_until_enhanced.py",
    "run_merlin_seed_until.py",
    "run_merlin_seed_batches.py",
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return value != 0
    normalized = str(value).strip().lower()
    if not normalized:
        return default
    return normalized in {"1", "true", "yes", "on", "enabled", "allow", "allowed"}


def _safe_int(value: Any, *, default: int, minimum: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed < minimum:
        return minimum
    return parsed


def _safe_float(value: Any, *, default: float, minimum: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if parsed < minimum:
        return minimum
    return parsed


def _status_age_seconds(updated_at: Any) -> float | None:
    if not isinstance(updated_at, str) or not updated_at.strip():
        return None
    try:
        parsed = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    delta = _utc_now() - parsed.astimezone(timezone.utc)
    return max(0.0, round(delta.total_seconds(), 3))


def _mtime_iso(path: Path) -> str | None:
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    return (
        datetime.fromtimestamp(mtime, tz=timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _count_non_empty_lines(path: Path) -> int:
    if not path.exists():
        return 0
    count = 0
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.strip():
                count += 1
    return count


def _tail_file_lines(path: Path, *, max_lines: int) -> list[str]:
    if not path.exists() or max_lines <= 0:
        return []
    lines: list[str] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            lines.append(line.rstrip("\n"))
    if len(lines) <= max_lines:
        return lines
    return lines[-max_lines:]


def _looks_like_seed_workspace(root: Path) -> bool:
    markers = (
        root / "scripts" / "run_merlin_seed_until.py",
        root / "scripts" / "run_merlin_seed_until_enhanced.py",
        root / "guild" / "data" / "merlin_distill_merged.jsonl",
        root / "artifacts" / "merlin_seed_status.json",
    )
    return any(marker.exists() for marker in markers)


def resolve_seed_workspace_root(raw_root: str | Path | None = None) -> Path:
    candidates: list[Path] = []

    if raw_root is not None and str(raw_root).strip():
        candidates.append(Path(raw_root))

    env_root = os.getenv("MERLIN_SEED_WORKSPACE_ROOT")
    if env_root and env_root.strip():
        candidates.append(Path(env_root))

    module_root = Path(__file__).resolve().parent
    candidates.extend(
        [
            Path.cwd(),
            Path.cwd().parent,
            module_root,
            module_root.parent,
        ]
    )

    resolved: list[Path] = []
    for candidate in candidates:
        try:
            path = candidate.resolve()
        except OSError:
            continue
        if path not in resolved:
            resolved.append(path)

    for candidate in resolved:
        if _looks_like_seed_workspace(candidate):
            return candidate

    if resolved:
        return resolved[0]
    return Path.cwd().resolve()


def evaluate_seed_live_policy(
    allow_live_override: bool | None = None,
) -> dict[str, Any]:
    allow_live_default = _parse_bool(
        os.getenv("ALLOW_LIVE_AUTOMATION"),
        default=True,
    )
    allow_live_effective = (
        allow_live_default if allow_live_override is None else bool(allow_live_override)
    )
    decision = POLICY_ALLOWED if allow_live_effective else POLICY_STUBBED
    reason = (
        "live automation is enabled"
        if decision == POLICY_ALLOWED
        else "live automation disabled (ALLOW_LIVE_AUTOMATION=false)"
    )
    return {
        "decision": decision,
        "allow_live_automation": allow_live_effective,
        "allow_live_automation_default": allow_live_default,
        "reason": reason,
    }


class MerlinSeedAccess:
    def __init__(self, workspace_root: str | Path | None = None):
        self.workspace_root = resolve_seed_workspace_root(workspace_root)

    def _resolve_path(self, value: str | None, default_relative: str) -> Path:
        raw = str(value).strip() if isinstance(value, str) else ""
        if raw:
            candidate = Path(raw)
            if candidate.is_absolute():
                return candidate.resolve()
            return (self.workspace_root / candidate).resolve()
        return (self.workspace_root / default_relative).resolve()

    def _path_for_command(self, path: Path) -> str:
        try:
            relative = path.relative_to(self.workspace_root)
            return str(relative)
        except ValueError:
            return str(path)

    def _resolve_seed_script(self) -> Path:
        candidates = (
            self.workspace_root / "scripts" / "run_merlin_seed_until_enhanced.py",
            self.workspace_root / "scripts" / "run_merlin_seed_until.py",
        )
        for candidate in candidates:
            if candidate.exists():
                return candidate
        raise FileNotFoundError("Seed runner script not found under scripts/")

    def _resolve_python_executable(self) -> str:
        candidates = (
            self.workspace_root / ".venv" / "bin" / "python",
            self.workspace_root / ".venv" / "Scripts" / "python.exe",
        )
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        if sys.executable:
            return sys.executable
        return "python"

    def _list_processes(self, *, match_tokens: tuple[str, ...]) -> list[dict[str, Any]]:
        tokens = tuple(token.lower() for token in match_tokens if token)
        if not tokens:
            return []

        try:
            result = subprocess.run(
                ["ps", "-eo", "pid=,args="],
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError:
            return []

        matches: list[dict[str, Any]] = []
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            parts = stripped.split(maxsplit=1)
            if len(parts) != 2:
                continue
            pid_text, command = parts
            try:
                pid = int(pid_text)
            except ValueError:
                continue

            normalized_command = command.strip().lower()
            if not normalized_command:
                continue
            if all(token not in normalized_command for token in tokens):
                continue
            if "ps -eo pid=,args=" in normalized_command:
                continue

            matches.append({"pid": pid, "command": command.strip()})

        return matches

    def _resolve_common_paths(
        self,
        *,
        status_file: str | None,
        merged_jsonl: str | None,
        merged_parquet: str | None,
        log_file: str | None,
    ) -> dict[str, Path]:
        return {
            "status_file": self._resolve_path(status_file, DEFAULT_STATUS_FILE),
            "merged_jsonl": self._resolve_path(merged_jsonl, DEFAULT_MERGED_JSONL),
            "merged_parquet": self._resolve_path(merged_parquet, DEFAULT_MERGED_PARQUET),
            "log_file": self._resolve_path(log_file, DEFAULT_LOG_FILE),
        }

    def status(
        self,
        *,
        status_file: str | None = None,
        merged_jsonl: str | None = None,
        merged_parquet: str | None = None,
        log_file: str | None = None,
        include_log_tail: bool = True,
        tail_lines: int = DEFAULT_LOG_TAIL_LINES,
        allow_live_automation: bool | None = None,
        match_tokens: tuple[str, ...] = DEFAULT_PROCESS_MATCH_TOKENS,
    ) -> dict[str, Any]:
        paths = self._resolve_common_paths(
            status_file=status_file,
            merged_jsonl=merged_jsonl,
            merged_parquet=merged_parquet,
            log_file=log_file,
        )
        policy = evaluate_seed_live_policy(allow_live_automation)

        status_payload: dict[str, Any] | None = None
        status_read_error: str | None = None
        if paths["status_file"].exists():
            try:
                parsed = json.loads(paths["status_file"].read_text(encoding="utf-8"))
                if isinstance(parsed, dict):
                    status_payload = parsed
                else:
                    status_read_error = "status file root is not an object"
            except (OSError, ValueError) as exc:
                status_read_error = str(exc)

        dataset_count = _count_non_empty_lines(paths["merged_jsonl"])
        process_rows = self._list_processes(match_tokens=match_tokens)

        safe_tail_lines = _safe_int(
            tail_lines,
            default=DEFAULT_LOG_TAIL_LINES,
            minimum=1,
        )
        safe_tail_lines = min(safe_tail_lines, MAX_LOG_TAIL_LINES)

        status_age_seconds = None
        if isinstance(status_payload, dict):
            status_age_seconds = _status_age_seconds(status_payload.get("updated_at"))

        response: dict[str, Any] = {
            "schema_name": "AAS.Merlin.SeedStatus",
            "schema_version": "1.0.0",
            "workspace_root": str(self.workspace_root),
            "policy": policy,
            "paths": {
                "status_file": str(paths["status_file"]),
                "merged_jsonl": str(paths["merged_jsonl"]),
                "merged_parquet": str(paths["merged_parquet"]),
                "log_file": str(paths["log_file"]),
            },
            "status_file": {
                "exists": paths["status_file"].exists(),
                "mtime_utc": _mtime_iso(paths["status_file"]),
                "status_age_seconds": status_age_seconds,
                "stale": (
                    isinstance(status_age_seconds, float)
                    and status_age_seconds > 3600
                ),
                "read_error": status_read_error,
            },
            "status": status_payload,
            "dataset": {
                "exists": paths["merged_jsonl"].exists(),
                "line_count": dataset_count,
                "mtime_utc": _mtime_iso(paths["merged_jsonl"]),
            },
            "process": {
                "active": bool(process_rows),
                "count": len(process_rows),
                "rows": process_rows,
            },
            "updated_at": _utc_now_iso(),
        }

        if include_log_tail:
            response["log_tail"] = {
                "lines": _tail_file_lines(paths["log_file"], max_lines=safe_tail_lines),
                "line_limit": safe_tail_lines,
                "mtime_utc": _mtime_iso(paths["log_file"]),
            }

        return response

    def _stop_processes(self, *, match_tokens: tuple[str, ...]) -> dict[str, Any]:
        before = self._list_processes(match_tokens=match_tokens)
        target_pids = [int(row["pid"]) for row in before]
        if not target_pids:
            return {
                "before_count": 0,
                "terminated": [],
                "killed": [],
                "errors": [],
                "remaining": [],
            }

        terminated: list[int] = []
        errors: list[str] = []

        for pid in target_pids:
            try:
                os.kill(pid, signal.SIGTERM)
                terminated.append(pid)
            except ProcessLookupError:
                continue
            except OSError as exc:
                errors.append(f"pid {pid}: {exc}")

        time.sleep(0.35)
        remaining_rows = self._list_processes(match_tokens=match_tokens)
        remaining = [row for row in remaining_rows if int(row["pid"]) in target_pids]

        killed: list[int] = []
        for row in remaining:
            pid = int(row["pid"])
            try:
                os.kill(pid, signal.SIGKILL)
                killed.append(pid)
            except ProcessLookupError:
                continue
            except OSError as exc:
                errors.append(f"pid {pid}: {exc}")

        if killed:
            time.sleep(0.2)
            remaining_rows = self._list_processes(match_tokens=match_tokens)
            remaining = [row for row in remaining_rows if int(row["pid"]) in target_pids]

        return {
            "before_count": len(before),
            "terminated": terminated,
            "killed": killed,
            "errors": errors,
            "remaining": remaining,
        }

    def _start_process(
        self,
        *,
        status_file: Path,
        merged_jsonl: Path,
        merged_parquet: Path,
        log_file: Path,
        endpoint: str,
        prompt_set: str,
        target: int,
        increment: int,
        repeat: int,
        eta_window: int,
        sleep_seconds: float,
        delay_seconds: float,
        resource_aware: bool,
        cpu_max: float,
        mem_max: float,
        resource_wait: float,
        notify_on_complete: bool,
        teachers: str | None,
        config: str | None,
        command_override: list[str] | None = None,
    ) -> dict[str, Any]:
        command = (
            list(command_override)
            if isinstance(command_override, list) and command_override
            else self._build_start_command(
                status_file=status_file,
                merged_jsonl=merged_jsonl,
                merged_parquet=merged_parquet,
                endpoint=endpoint,
                prompt_set=prompt_set,
                target=target,
                increment=increment,
                repeat=repeat,
                eta_window=eta_window,
                sleep_seconds=sleep_seconds,
                delay_seconds=delay_seconds,
                resource_aware=resource_aware,
                cpu_max=cpu_max,
                mem_max=mem_max,
                resource_wait=resource_wait,
                notify_on_complete=notify_on_complete,
                teachers=teachers,
                config=config,
            )
        )

        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("a", encoding="utf-8") as log_handle:
            log_handle.write(
                f"[{_utc_now_iso()}] merlin.seed.control start: {shlex.join(command)}\n"
            )
            log_handle.flush()
            process = subprocess.Popen(
                command,
                cwd=str(self.workspace_root),
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )

        return {
            "pid": int(process.pid),
            "command": command,
        }

    def _build_start_command(
        self,
        *,
        status_file: Path,
        merged_jsonl: Path,
        merged_parquet: Path,
        endpoint: str,
        prompt_set: str,
        target: int,
        increment: int,
        repeat: int,
        eta_window: int,
        sleep_seconds: float,
        delay_seconds: float,
        resource_aware: bool,
        cpu_max: float,
        mem_max: float,
        resource_wait: float,
        notify_on_complete: bool,
        teachers: str | None,
        config: str | None,
    ) -> list[str]:
        script_path = self._resolve_seed_script()
        python_exe = self._resolve_python_executable()

        command: list[str] = [
            python_exe,
            str(script_path),
            "--endpoint",
            endpoint,
            "--prompt-set",
            prompt_set,
            "--target",
            str(target),
            "--increment",
            str(increment),
            "--repeat",
            str(repeat),
            "--eta-window",
            str(eta_window),
            "--sleep",
            str(sleep_seconds),
            "--delay",
            str(delay_seconds),
            "--status-file",
            self._path_for_command(status_file),
            "--merged-jsonl",
            self._path_for_command(merged_jsonl),
            "--merged-parquet",
            self._path_for_command(merged_parquet),
        ]

        if teachers:
            command.extend(["--teachers", teachers])
        if config:
            command.extend(["--config", config])
        if resource_aware:
            command.extend(
                [
                    "--resource-aware",
                    "--cpu-max",
                    str(cpu_max),
                    "--mem-max",
                    str(mem_max),
                    "--resource-wait",
                    str(resource_wait),
                ]
            )
        if notify_on_complete:
            command.append("--notify-on-complete")
        return command

    def control(
        self,
        *,
        action: str,
        allow_live_automation: bool | None = None,
        dry_run: bool = False,
        force: bool = False,
        status_file: str | None = None,
        merged_jsonl: str | None = None,
        merged_parquet: str | None = None,
        log_file: str | None = None,
        endpoint: str = "http://127.0.0.1:1234",
        prompt_set: str = DEFAULT_PROMPT_SET,
        target: int = DEFAULT_SEED_TARGET,
        increment: int = DEFAULT_SEED_INCREMENT,
        repeat: int = DEFAULT_SEED_REPEAT,
        eta_window: int = DEFAULT_SEED_ETA_WINDOW,
        sleep_seconds: float = DEFAULT_SEED_SLEEP,
        delay_seconds: float = DEFAULT_SEED_DELAY,
        resource_aware: bool = True,
        cpu_max: float = DEFAULT_SEED_CPU_MAX,
        mem_max: float = DEFAULT_SEED_MEM_MAX,
        resource_wait: float = DEFAULT_SEED_RESOURCE_WAIT,
        notify_on_complete: bool = False,
        teachers: str | None = None,
        config: str | None = None,
        match_tokens: tuple[str, ...] = DEFAULT_PROCESS_MATCH_TOKENS,
    ) -> dict[str, Any]:
        normalized_action = str(action or "").strip().lower()
        if normalized_action not in {"start", "stop", "restart"}:
            raise ValueError("action must be one of: start, stop, restart")

        policy = evaluate_seed_live_policy(allow_live_automation)
        if policy["decision"] != POLICY_ALLOWED:
            return {
                "schema_name": "AAS.Merlin.SeedControl",
                "schema_version": "1.0.0",
                "action": normalized_action,
                "decision": policy["decision"],
                "status": "blocked",
                "message": policy["reason"],
                "policy": policy,
                "workspace_root": str(self.workspace_root),
                "updated_at": _utc_now_iso(),
            }

        paths = self._resolve_common_paths(
            status_file=status_file,
            merged_jsonl=merged_jsonl,
            merged_parquet=merged_parquet,
            log_file=log_file,
        )
        current = self._list_processes(match_tokens=match_tokens)

        result: dict[str, Any] = {
            "schema_name": "AAS.Merlin.SeedControl",
            "schema_version": "1.0.0",
            "action": normalized_action,
            "decision": POLICY_ALLOWED,
            "dry_run": bool(dry_run),
            "policy": policy,
            "workspace_root": str(self.workspace_root),
            "paths": {
                "status_file": str(paths["status_file"]),
                "merged_jsonl": str(paths["merged_jsonl"]),
                "merged_parquet": str(paths["merged_parquet"]),
                "log_file": str(paths["log_file"]),
            },
        }

        normalized_endpoint = str(endpoint).strip() or "http://127.0.0.1:1234"
        normalized_prompt_set = str(prompt_set).strip() or DEFAULT_PROMPT_SET
        normalized_target = _safe_int(target, default=DEFAULT_SEED_TARGET, minimum=1)
        normalized_increment = _safe_int(
            increment, default=DEFAULT_SEED_INCREMENT, minimum=1
        )
        normalized_repeat = _safe_int(repeat, default=DEFAULT_SEED_REPEAT, minimum=1)
        normalized_eta_window = _safe_int(
            eta_window, default=DEFAULT_SEED_ETA_WINDOW, minimum=1
        )
        normalized_sleep_seconds = _safe_float(
            sleep_seconds, default=DEFAULT_SEED_SLEEP, minimum=0.0
        )
        normalized_delay_seconds = _safe_float(
            delay_seconds, default=DEFAULT_SEED_DELAY, minimum=0.0
        )
        normalized_resource_aware = bool(resource_aware)
        normalized_cpu_max = _safe_float(
            cpu_max, default=DEFAULT_SEED_CPU_MAX, minimum=1.0
        )
        normalized_mem_max = _safe_float(
            mem_max, default=DEFAULT_SEED_MEM_MAX, minimum=1.0
        )
        normalized_resource_wait = _safe_float(
            resource_wait, default=DEFAULT_SEED_RESOURCE_WAIT, minimum=0.1
        )
        normalized_notify_on_complete = bool(notify_on_complete)
        normalized_teachers = (
            str(teachers).strip()
            if isinstance(teachers, str) and teachers.strip()
            else None
        )
        normalized_config = (
            str(config).strip() if isinstance(config, str) and config.strip() else None
        )

        if normalized_action == "stop":
            if dry_run:
                result.update(
                    {
                        "status": "preview",
                        "message": (
                            "Dry-run preview only; no processes were stopped"
                        ),
                        "preview": {
                            "would_stop_count": len(current),
                            "rows": current,
                        },
                    }
                )
                result["status_snapshot"] = self.status(
                    status_file=status_file,
                    merged_jsonl=merged_jsonl,
                    merged_parquet=merged_parquet,
                    log_file=log_file,
                    include_log_tail=False,
                    allow_live_automation=allow_live_automation,
                    match_tokens=match_tokens,
                )
                result["updated_at"] = _utc_now_iso()
                return result

            stopped = self._stop_processes(match_tokens=match_tokens)
            result.update(
                {
                    "status": "stopped" if stopped["before_count"] > 0 else "already_stopped",
                    "message": (
                        "Seed worker processes stopped"
                        if stopped["before_count"] > 0
                        else "No active seed worker processes"
                    ),
                    "process": stopped,
                }
            )
            result["status_snapshot"] = self.status(
                status_file=status_file,
                merged_jsonl=merged_jsonl,
                merged_parquet=merged_parquet,
                log_file=log_file,
                include_log_tail=False,
                allow_live_automation=allow_live_automation,
                match_tokens=match_tokens,
            )
            result["updated_at"] = _utc_now_iso()
            return result

        should_launch = not (normalized_action in {"start", "restart"} and current and not force)
        should_stop = normalized_action == "restart" or (
            normalized_action == "start" and current and force
        )
        preview_command = self._build_start_command(
            status_file=paths["status_file"],
            merged_jsonl=paths["merged_jsonl"],
            merged_parquet=paths["merged_parquet"],
            endpoint=normalized_endpoint,
            prompt_set=normalized_prompt_set,
            target=normalized_target,
            increment=normalized_increment,
            repeat=normalized_repeat,
            eta_window=normalized_eta_window,
            sleep_seconds=normalized_sleep_seconds,
            delay_seconds=normalized_delay_seconds,
            resource_aware=normalized_resource_aware,
            cpu_max=normalized_cpu_max,
            mem_max=normalized_mem_max,
            resource_wait=normalized_resource_wait,
            notify_on_complete=normalized_notify_on_complete,
            teachers=normalized_teachers,
            config=normalized_config,
        )

        if dry_run:
            result.update(
                {
                    "status": "preview",
                    "message": (
                        "Dry-run preview only; no process started"
                        if should_launch
                        else "Dry-run preview: worker already running (force=true required to relaunch)"
                    ),
                    "preview": {
                        "active_before_count": len(current),
                        "active_before_rows": current,
                        "force": bool(force),
                        "would_launch": bool(should_launch),
                        "would_stop_count": len(current) if should_stop else 0,
                        "command": shlex.join(preview_command),
                    },
                }
            )
            result["status_snapshot"] = self.status(
                status_file=status_file,
                merged_jsonl=merged_jsonl,
                merged_parquet=merged_parquet,
                log_file=log_file,
                include_log_tail=False,
                allow_live_automation=allow_live_automation,
                match_tokens=match_tokens,
            )
            result["updated_at"] = _utc_now_iso()
            return result

        if normalized_action in {"start", "restart"} and current and not force:
            result.update(
                {
                    "status": "already_running",
                    "message": "Seed worker already running (set force=true to restart)",
                    "process": {
                        "before_count": len(current),
                        "rows": current,
                    },
                }
            )
            result["status_snapshot"] = self.status(
                status_file=status_file,
                merged_jsonl=merged_jsonl,
                merged_parquet=merged_parquet,
                log_file=log_file,
                include_log_tail=False,
                allow_live_automation=allow_live_automation,
                match_tokens=match_tokens,
            )
            result["updated_at"] = _utc_now_iso()
            return result

        stop_details: dict[str, Any] | None = None
        if normalized_action == "restart" or (normalized_action == "start" and current and force):
            stop_details = self._stop_processes(match_tokens=match_tokens)

        start_details = self._start_process(
            status_file=paths["status_file"],
            merged_jsonl=paths["merged_jsonl"],
            merged_parquet=paths["merged_parquet"],
            log_file=paths["log_file"],
            endpoint=normalized_endpoint,
            prompt_set=normalized_prompt_set,
            target=normalized_target,
            increment=normalized_increment,
            repeat=normalized_repeat,
            eta_window=normalized_eta_window,
            sleep_seconds=normalized_sleep_seconds,
            delay_seconds=normalized_delay_seconds,
            resource_aware=normalized_resource_aware,
            cpu_max=normalized_cpu_max,
            mem_max=normalized_mem_max,
            resource_wait=normalized_resource_wait,
            notify_on_complete=normalized_notify_on_complete,
            teachers=normalized_teachers,
            config=normalized_config,
            command_override=preview_command,
        )

        result.update(
            {
                "status": "started" if normalized_action == "start" else "restarted",
                "message": (
                    "Seed worker process started"
                    if normalized_action == "start"
                    else "Seed worker process restarted"
                ),
                "start": {
                    "pid": start_details["pid"],
                    "command": shlex.join(start_details["command"]),
                },
            }
        )
        if stop_details is not None:
            result["stop"] = stop_details

        result["status_snapshot"] = self.status(
            status_file=status_file,
            merged_jsonl=merged_jsonl,
            merged_parquet=merged_parquet,
            log_file=log_file,
            include_log_tail=False,
            allow_live_automation=allow_live_automation,
            match_tokens=match_tokens,
        )
        result["updated_at"] = _utc_now_iso()
        return result


def build_seed_access(workspace_root: str | Path | None = None) -> MerlinSeedAccess:
    return MerlinSeedAccess(workspace_root=workspace_root)
