from __future__ import annotations

import json
import os
import shlex
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

POLICY_ALLOWED = "allowed"
POLICY_STUBBED = "stubbed"

DEFAULT_STATUS_FILE = "artifacts/merlin_seed_status.json"
DEFAULT_MERGED_JSONL = "guild/data/merlin_distill_merged.jsonl"
DEFAULT_MERGED_PARQUET = "guild/data/merlin_distill_merged.parquet"
DEFAULT_LOG_FILE = "logs/merlin_seed_task.log"
DEFAULT_HEARTBEAT_FILE = "artifacts/diagnostics/merlin_seed_health_heartbeat.jsonl"
DEFAULT_WATCHDOG_RUNTIME_LOG_FILE = "logs/merlin_seed_watchdog_runtime.log"
DEFAULT_WATCHDOG_RUNTIME_APPEND_JSONL = (
    "artifacts/diagnostics/merlin_seed_watchdog_runtime_ticks.jsonl"
)
DEFAULT_WATCHDOG_RUNTIME_OUTPUT_JSON = (
    "artifacts/diagnostics/merlin_seed_watchdog_runtime_latest.json"
)
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
DEFAULT_STATUS_STALE_SECONDS = 3600
WATCHDOG_ACTIONS: tuple[str, ...] = ("none", "start", "restart", "stop")

DEFAULT_PROCESS_MATCH_TOKENS: tuple[str, ...] = (
    "run_merlin_seed_until_enhanced.py",
    "run_merlin_seed_until.py",
    "run_merlin_seed_batches.py",
)
DEFAULT_WATCHDOG_RUNTIME_MATCH_TOKENS: tuple[str, ...] = (
    "run_merlin_seed_watchdog.py",
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


def _path_age_seconds(path: Path) -> float | None:
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    parsed = datetime.fromtimestamp(mtime, tz=timezone.utc)
    delta = _utc_now() - parsed
    return max(0.0, round(delta.total_seconds(), 3))


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


def _read_last_jsonl_object(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    lines = _tail_file_lines(path, max_lines=25)
    for line in reversed(lines):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            parsed = json.loads(stripped)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _looks_like_seed_workspace(root: Path) -> bool:
    markers = (
        root / "scripts" / "run_merlin_seed_until.py",
        root / "scripts" / "run_merlin_seed_until_enhanced.py",
        root / "guild" / "data" / "merlin_distill_merged.jsonl",
        root / "artifacts" / "merlin_seed_status.json",
    )
    return any(marker.exists() for marker in markers)


def _seed_workspace_score(root: Path) -> tuple[int, float]:
    status_file = root / DEFAULT_STATUS_FILE
    merged_jsonl = root / DEFAULT_MERGED_JSONL
    merged_parquet = root / DEFAULT_MERGED_PARQUET
    script_primary = root / "scripts" / "run_merlin_seed_until_enhanced.py"
    script_fallback = root / "scripts" / "run_merlin_seed_until.py"

    score = 0
    if status_file.exists():
        score += 8
    if merged_jsonl.exists():
        score += 4
    if merged_parquet.exists():
        score += 2
    if script_primary.exists():
        score += 2
    if script_fallback.exists():
        score += 1

    mtime = 0.0
    if status_file.exists():
        try:
            mtime = status_file.stat().st_mtime
        except OSError:
            mtime = 0.0
    return score, mtime


def _read_nested_mapping_value(payload: dict[str, Any], path: str) -> Any:
    cursor: Any = payload
    for segment in path.split("."):
        if not isinstance(cursor, dict) or segment not in cursor:
            return None
        cursor = cursor[segment]
    return cursor


def _coerce_non_negative_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        parsed = float(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = float(text.replace(",", ""))
        except ValueError:
            return None
    else:
        return None
    if parsed < 0:
        return None
    return parsed


def _extract_progress_number(
    payload: dict[str, Any], paths: tuple[str, ...]
) -> float | None:
    for path in paths:
        raw = _read_nested_mapping_value(payload, path)
        parsed = _coerce_non_negative_float(raw)
        if parsed is not None:
            return parsed
    return None


def _derive_seed_progress(
    status_payload: dict[str, Any] | None, *, dataset_count: int
) -> dict[str, Any]:
    payload = status_payload if isinstance(status_payload, dict) else {}

    target_guess = _extract_progress_number(
        payload,
        (
            "target",
            "target_total",
            "target_rounds",
            "progress.target",
            "progress.target_total",
        ),
    )
    target_rounds = (
        int(target_guess) if target_guess and target_guess > 0 else DEFAULT_SEED_TARGET
    )

    status_completed_guess = _extract_progress_number(
        payload,
        (
            "current_total",
            "rounds_completed",
            "completed_rounds",
            "generated_total",
            "progress.current_total",
            "progress.rounds_completed",
            "progress.completed_rounds",
        ),
    )
    status_completed = (
        int(status_completed_guess) if status_completed_guess is not None else 0
    )
    dataset_completed = max(0, int(dataset_count))
    completed_rounds = max(status_completed, dataset_completed)

    source = "none"
    if status_completed > 0 and dataset_completed > 0:
        source = "status_or_dataset_max"
    elif status_completed > 0:
        source = "status"
    elif dataset_completed > 0:
        source = "dataset"

    remaining_rounds = max(target_rounds - completed_rounds, 0)
    completion_ratio = (
        round(completed_rounds / target_rounds, 6) if target_rounds > 0 else 0.0
    )
    completion_percent = round(completion_ratio * 100.0, 2)

    eta_seconds = _extract_progress_number(
        payload, ("eta_seconds", "progress.eta_seconds")
    )
    throughput_per_min = _extract_progress_number(
        payload,
        (
            "throughput_per_min",
            "throughput_per_min_rolling",
            "progress.throughput_per_min",
        ),
    )

    return {
        "target_rounds": target_rounds,
        "completed_rounds": completed_rounds,
        "remaining_rounds": remaining_rounds,
        "completion_ratio": completion_ratio,
        "completion_percent": completion_percent,
        "source": source,
        "eta_seconds": None if eta_seconds is None else round(float(eta_seconds), 3),
        "throughput_per_min": (
            None if throughput_per_min is None else round(float(throughput_per_min), 3)
        ),
    }


def _build_seed_guidance(
    *,
    policy: dict[str, Any],
    progress: dict[str, Any],
    process_rows: list[dict[str, Any]],
    status_age_seconds: float | None,
) -> dict[str, Any]:
    recommendations: list[dict[str, str]] = []
    active = bool(process_rows)
    decision = str(policy.get("decision", "")).strip().lower()
    complete = (
        int(progress.get("target_rounds", 0)) > 0
        and int(progress.get("remaining_rounds", 0)) <= 0
    )
    stale = isinstance(status_age_seconds, float) and status_age_seconds > float(
        DEFAULT_STATUS_STALE_SECONDS
    )
    throughput = progress.get("throughput_per_min")
    stalled = isinstance(throughput, (int, float)) and throughput <= 0

    state = "healthy"
    if decision != POLICY_ALLOWED:
        state = "blocked"
        recommendations.append(
            {
                "id": "enable_live_automation",
                "severity": "high",
                "message": "Seed control is blocked by policy while live automation is disabled.",
                "action": "Set ALLOW_LIVE_AUTOMATION=true or pass allow_live_automation=true for merlin.seed.control.",
            }
        )
    elif complete:
        state = "complete"
        if active:
            recommendations.append(
                {
                    "id": "stop_worker",
                    "severity": "low",
                    "message": "Target rounds are complete and a worker still appears active.",
                    "action": "Run merlin.seed.control with action=stop to free resources.",
                }
            )
    else:
        if not active:
            state = "attention"
            recommendations.append(
                {
                    "id": "start_worker",
                    "severity": "high",
                    "message": "No active seed worker is running before target completion.",
                    "action": "Run merlin.seed.control with action=start and allow_live_automation=true.",
                }
            )
        if stale:
            state = "attention"
            recommendations.append(
                {
                    "id": "stale_status",
                    "severity": "medium",
                    "message": "Seed status has not been updated recently.",
                    "action": "Inspect logs and consider merlin.seed.control action=restart if the worker is stuck.",
                }
            )
        if active and stalled:
            state = "attention"
            recommendations.append(
                {
                    "id": "throughput_stalled",
                    "severity": "medium",
                    "message": "Reported throughput is zero while a worker appears active.",
                    "action": "Reduce --repeat, verify endpoint health, then restart seed control if needed.",
                }
            )

    next_action = "observe"
    if decision != POLICY_ALLOWED:
        next_action = "unblock_policy"
    elif complete:
        next_action = "stop" if active else "observe"
    elif not active:
        next_action = "start"
    elif stale or stalled:
        next_action = "restart"

    return {
        "schema_name": "AAS.Merlin.SeedGuidance",
        "schema_version": "1.0.0",
        "state": state,
        "next_action": next_action,
        "recommendations": recommendations,
    }


def _seed_health_severity(state: str) -> str:
    normalized = str(state or "").strip().lower()
    if normalized in {"healthy", "complete"}:
        return "ok"
    if normalized == "attention":
        return "warn"
    return "critical"


def _recommended_control_action(next_action: str, *, policy_decision: str) -> str:
    if policy_decision != POLICY_ALLOWED:
        return "none"
    normalized = str(next_action or "").strip().lower()
    if normalized in {"start", "restart", "stop"}:
        return normalized
    return "none"


def _normalized_seed_heartbeat_event(
    *,
    workspace_root: Path,
    health_payload: dict[str, Any],
    heartbeat_file: str | None,
    persisted: bool,
) -> dict[str, Any]:
    return {
        "schema_name": "AAS.Merlin.SeedHealthHeartbeat",
        "schema_version": "1.0.0",
        "event_id": f"hb_{uuid.uuid4().hex}",
        "event_type": "merlin.seed.health.heartbeat",
        "workspace_root": str(workspace_root),
        "state": str(health_payload.get("state", "attention")),
        "severity": str(health_payload.get("severity", "warn")),
        "policy_decision": str(health_payload.get("policy_decision", POLICY_STUBBED)),
        "next_action": str(health_payload.get("next_action", "observe")),
        "recommended_control_action": str(
            health_payload.get("recommended_control_action", "none")
        ),
        "checks": health_payload.get("checks", {}),
        "progress": health_payload.get("progress", {}),
        "worker": health_payload.get("worker", {}),
        "staleness": health_payload.get("staleness", {}),
        "health_snapshot": health_payload,
        "heartbeat_file": heartbeat_file,
        "persisted": persisted,
        "emitted_at": _utc_now_iso(),
    }


def resolve_seed_workspace_root(raw_root: str | Path | None = None) -> Path:
    candidates: list[Path] = []

    explicit_candidates: list[Path] = []
    if raw_root is not None and str(raw_root).strip():
        path = Path(raw_root)
        explicit_candidates.append(path)
        candidates.append(path)

    env_root = os.getenv("MERLIN_SEED_WORKSPACE_ROOT")
    if env_root and env_root.strip():
        path = Path(env_root)
        explicit_candidates.append(path)
        candidates.append(path)

    module_root = Path(__file__).resolve().parent
    runtime_candidates = [Path.cwd(), Path.cwd().parent]
    module_candidates = [module_root, module_root.parent]
    candidates.extend(runtime_candidates + module_candidates)

    resolved: list[Path] = []
    for candidate in candidates:
        try:
            path = candidate.resolve()
        except OSError:
            continue
        if path not in resolved:
            resolved.append(path)

    explicit_resolved: list[Path] = []
    for candidate in explicit_candidates:
        try:
            path = Path(candidate).resolve()
        except OSError:
            continue
        if path not in explicit_resolved:
            explicit_resolved.append(path)

    for candidate in explicit_resolved:
        score, _ = _seed_workspace_score(candidate)
        if score > 0:
            return candidate

    def _best_scored(candidates_to_rank: list[Path]) -> Path | None:
        best_candidate: Path | None = None
        best_score = -1
        best_mtime = -1.0
        for candidate in candidates_to_rank:
            score, mtime = _seed_workspace_score(candidate)
            if score <= 0:
                continue
            if score > best_score or (score == best_score and mtime > best_mtime):
                best_candidate = candidate
                best_score = score
                best_mtime = mtime
        return best_candidate

    runtime_resolved = [
        candidate
        for candidate in resolved
        if candidate in {p.resolve() for p in runtime_candidates}
    ]
    module_resolved = [
        candidate
        for candidate in resolved
        if candidate in {p.resolve() for p in module_candidates}
    ]

    runtime_best = _best_scored(runtime_resolved)
    if runtime_best is not None:
        return runtime_best

    module_best = _best_scored(module_resolved)
    if module_best is not None:
        return module_best

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

    def _resolve_watchdog_script(self) -> Path:
        module_root = Path(__file__).resolve().parent
        candidates = (
            self.workspace_root / "scripts" / "run_merlin_seed_watchdog.py",
            module_root / "scripts" / "run_merlin_seed_watchdog.py",
        )
        for candidate in candidates:
            if candidate.exists():
                return candidate
        raise FileNotFoundError("Seed watchdog runner script not found under scripts/")

    def _resolve_python_executable(self) -> str:
        candidates = (
            self.workspace_root / ".venv" / "bin" / "python",
            self.workspace_root / ".venv" / "Scripts" / "python.exe",
        )
        for candidate in candidates:
            if candidate.exists():
                # Skip Windows Python executables when running on POSIX shells.
                if os.name != "nt" and candidate.suffix.lower() == ".exe":
                    continue
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
            "merged_parquet": self._resolve_path(
                merged_parquet, DEFAULT_MERGED_PARQUET
            ),
            "log_file": self._resolve_path(log_file, DEFAULT_LOG_FILE),
        }

    @staticmethod
    def _read_status_file_payload(status_file: Path) -> dict[str, Any] | None:
        if not status_file.exists():
            return None
        try:
            parsed = json.loads(status_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if isinstance(parsed, dict):
            return parsed
        return None

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
        mtime_age_seconds = _path_age_seconds(paths["status_file"])
        if (
            isinstance(status_age_seconds, float)
            and isinstance(mtime_age_seconds, float)
            and process_rows
            and (mtime_age_seconds + 300.0) < status_age_seconds
        ):
            status_age_seconds = mtime_age_seconds
        elif status_age_seconds is None and isinstance(mtime_age_seconds, float):
            status_age_seconds = mtime_age_seconds
        progress = _derive_seed_progress(status_payload, dataset_count=dataset_count)
        guidance = _build_seed_guidance(
            policy=policy,
            progress=progress,
            process_rows=process_rows,
            status_age_seconds=status_age_seconds,
        )

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
                    and status_age_seconds > DEFAULT_STATUS_STALE_SECONDS
                ),
                "read_error": status_read_error,
            },
            "status": status_payload,
            "progress": progress,
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
            "guidance": guidance,
            "updated_at": _utc_now_iso(),
        }

        if include_log_tail:
            response["log_tail"] = {
                "lines": _tail_file_lines(paths["log_file"], max_lines=safe_tail_lines),
                "line_limit": safe_tail_lines,
                "mtime_utc": _mtime_iso(paths["log_file"]),
            }

        return response

    def health(
        self,
        *,
        status_file: str | None = None,
        merged_jsonl: str | None = None,
        merged_parquet: str | None = None,
        log_file: str | None = None,
        allow_live_automation: bool | None = None,
        stale_after_seconds: float = float(DEFAULT_STATUS_STALE_SECONDS),
        match_tokens: tuple[str, ...] = DEFAULT_PROCESS_MATCH_TOKENS,
    ) -> dict[str, Any]:
        status_payload = self.status(
            status_file=status_file,
            merged_jsonl=merged_jsonl,
            merged_parquet=merged_parquet,
            log_file=log_file,
            include_log_tail=False,
            allow_live_automation=allow_live_automation,
            match_tokens=match_tokens,
        )

        stale_threshold = _safe_float(
            stale_after_seconds,
            default=float(DEFAULT_STATUS_STALE_SECONDS),
            minimum=1.0,
        )
        policy = (
            status_payload.get("policy")
            if isinstance(status_payload.get("policy"), dict)
            else {}
        )
        progress = (
            status_payload.get("progress")
            if isinstance(status_payload.get("progress"), dict)
            else {}
        )
        process = (
            status_payload.get("process")
            if isinstance(status_payload.get("process"), dict)
            else {}
        )
        guidance = (
            status_payload.get("guidance")
            if isinstance(status_payload.get("guidance"), dict)
            else {}
        )
        status_file_meta = (
            status_payload.get("status_file")
            if isinstance(status_payload.get("status_file"), dict)
            else {}
        )

        status_age_seconds = status_file_meta.get("status_age_seconds")
        parsed_status_age = (
            float(status_age_seconds)
            if isinstance(status_age_seconds, (int, float))
            else None
        )
        status_stale = (
            parsed_status_age is not None and parsed_status_age > stale_threshold
        )

        next_action = str(guidance.get("next_action", "observe")).strip().lower()
        state = str(guidance.get("state", "attention")).strip().lower() or "attention"
        policy_decision = str(policy.get("decision", "")).strip().lower()
        remaining_rounds = _safe_int(
            progress.get("remaining_rounds"), default=0, minimum=0
        )
        completed_rounds = _safe_int(
            progress.get("completed_rounds"), default=0, minimum=0
        )
        target_rounds = _safe_int(
            progress.get("target_rounds"), default=DEFAULT_SEED_TARGET, minimum=1
        )
        completion_percent = _safe_float(
            progress.get("completion_percent"), default=0.0, minimum=0.0
        )
        worker_active = bool(process.get("active", False))
        worker_count = _safe_int(process.get("count"), default=0, minimum=0)

        return {
            "schema_name": "AAS.Merlin.SeedHealth",
            "schema_version": "1.0.0",
            "workspace_root": str(self.workspace_root),
            "state": state,
            "severity": _seed_health_severity(state),
            "policy_decision": policy_decision or POLICY_STUBBED,
            "next_action": next_action or "observe",
            "recommended_control_action": _recommended_control_action(
                next_action,
                policy_decision=policy_decision,
            ),
            "checks": {
                "policy_allowed": policy_decision == POLICY_ALLOWED,
                "status_stale": status_stale,
                "worker_active": worker_active,
                "progress_complete": remaining_rounds <= 0,
            },
            "progress": {
                "target_rounds": target_rounds,
                "completed_rounds": completed_rounds,
                "remaining_rounds": remaining_rounds,
                "completion_percent": round(completion_percent, 2),
            },
            "worker": {
                "active": worker_active,
                "count": worker_count,
            },
            "staleness": {
                "status_age_seconds": (
                    None if parsed_status_age is None else round(parsed_status_age, 3)
                ),
                "stale_after_seconds": round(stale_threshold, 3),
                "is_stale": status_stale,
            },
            "guidance": guidance,
            "status_snapshot_updated_at": status_payload.get("updated_at"),
            "updated_at": _utc_now_iso(),
        }

    def heartbeat(
        self,
        *,
        status_file: str | None = None,
        merged_jsonl: str | None = None,
        merged_parquet: str | None = None,
        log_file: str | None = None,
        allow_live_automation: bool | None = None,
        stale_after_seconds: float = float(DEFAULT_STATUS_STALE_SECONDS),
        heartbeat_file: str | None = None,
        write_event: bool = True,
        match_tokens: tuple[str, ...] = DEFAULT_PROCESS_MATCH_TOKENS,
    ) -> dict[str, Any]:
        health_payload = self.health(
            status_file=status_file,
            merged_jsonl=merged_jsonl,
            merged_parquet=merged_parquet,
            log_file=log_file,
            allow_live_automation=allow_live_automation,
            stale_after_seconds=stale_after_seconds,
            match_tokens=match_tokens,
        )

        resolved_heartbeat_file = self._resolve_path(
            heartbeat_file,
            DEFAULT_HEARTBEAT_FILE,
        )
        if write_event:
            resolved_heartbeat_file.parent.mkdir(parents=True, exist_ok=True)
            event_for_write = _normalized_seed_heartbeat_event(
                workspace_root=self.workspace_root,
                health_payload=health_payload,
                heartbeat_file=str(resolved_heartbeat_file),
                persisted=True,
            )
            with resolved_heartbeat_file.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        event_for_write,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                )
                handle.write("\n")
            return event_for_write

        return _normalized_seed_heartbeat_event(
            workspace_root=self.workspace_root,
            health_payload=health_payload,
            heartbeat_file=str(resolved_heartbeat_file),
            persisted=False,
        )

    def watchdog(
        self,
        *,
        status_file: str | None = None,
        merged_jsonl: str | None = None,
        merged_parquet: str | None = None,
        log_file: str | None = None,
        allow_live_automation: bool | None = None,
        stale_after_seconds: float = float(DEFAULT_STATUS_STALE_SECONDS),
        apply: bool = False,
        force: bool = False,
        dry_run_control: bool = False,
        match_tokens: tuple[str, ...] = DEFAULT_PROCESS_MATCH_TOKENS,
    ) -> dict[str, Any]:
        health_payload = self.health(
            status_file=status_file,
            merged_jsonl=merged_jsonl,
            merged_parquet=merged_parquet,
            log_file=log_file,
            allow_live_automation=allow_live_automation,
            stale_after_seconds=stale_after_seconds,
            match_tokens=match_tokens,
        )

        recommended_action = (
            str(health_payload.get("recommended_control_action", "none"))
            .strip()
            .lower()
        )
        if recommended_action not in WATCHDOG_ACTIONS:
            recommended_action = "none"

        apply_requested = bool(apply)
        policy_allowed = (
            str(health_payload.get("policy_decision", "")).strip().lower()
            == POLICY_ALLOWED
        )
        action_taken = "none"
        outcome_status = "noop"
        reason = "No control action recommended by health guidance."
        control_result: dict[str, Any] | None = None

        if recommended_action == "none" and apply_requested and not policy_allowed:
            outcome_status = "blocked"
            reason = (
                "Policy blocks live control actions. Enable ALLOW_LIVE_AUTOMATION "
                "or pass allow_live_automation=true."
            )

        if recommended_action != "none":
            if not apply_requested:
                outcome_status = "preview"
                reason = (
                    f"Watchdog recommends '{recommended_action}' but apply=false."
                )
            elif not policy_allowed:
                outcome_status = "blocked"
                reason = (
                    "Policy blocks live control actions. Enable ALLOW_LIVE_AUTOMATION "
                    "or pass allow_live_automation=true."
                )
            else:
                try:
                    control_result = self.control(
                        action=recommended_action,
                        allow_live_automation=allow_live_automation,
                        dry_run=bool(dry_run_control),
                        force=bool(force),
                        status_file=status_file,
                        merged_jsonl=merged_jsonl,
                        merged_parquet=merged_parquet,
                        log_file=log_file,
                        match_tokens=match_tokens,
                    )
                    action_taken = recommended_action
                    control_status = (
                        str(control_result.get("status", "")).strip().lower()
                        if isinstance(control_result, dict)
                        else ""
                    )
                    if dry_run_control or control_status == "preview":
                        outcome_status = "preview"
                        reason = (
                            f"Control dry-run executed for '{recommended_action}'."
                        )
                    elif control_status == "blocked":
                        outcome_status = "blocked"
                        reason = (
                            f"Control action '{recommended_action}' blocked by policy."
                        )
                    else:
                        outcome_status = "executed"
                        reason = f"Control action '{recommended_action}' executed."
                except (ValueError, FileNotFoundError, PermissionError) as exc:
                    outcome_status = "error"
                    reason = str(exc)

        return {
            "schema_name": "AAS.Merlin.SeedWatchdogTick",
            "schema_version": "1.0.0",
            "workspace_root": str(self.workspace_root),
            "health": health_payload,
            "decision": {
                "recommended_control_action": recommended_action,
                "apply_requested": apply_requested,
                "dry_run_control": bool(dry_run_control),
                "force": bool(force),
                "action_taken": action_taken,
                "outcome_status": outcome_status,
                "reason": reason,
            },
            "control_result": control_result,
            "updated_at": _utc_now_iso(),
        }

    def watchdog_runtime_status(
        self,
        *,
        status_file: str | None = None,
        merged_jsonl: str | None = None,
        merged_parquet: str | None = None,
        log_file: str | None = None,
        watchdog_log_file: str | None = None,
        append_jsonl: str | None = None,
        output_json: str | None = None,
        heartbeat_file: str | None = None,
        allow_live_automation: bool | None = None,
        stale_after_seconds: float = float(DEFAULT_STATUS_STALE_SECONDS),
        match_tokens: tuple[str, ...] = DEFAULT_WATCHDOG_RUNTIME_MATCH_TOKENS,
    ) -> dict[str, Any]:
        paths = self._resolve_common_paths(
            status_file=status_file,
            merged_jsonl=merged_jsonl,
            merged_parquet=merged_parquet,
            log_file=log_file,
        )
        runtime_log_path = self._resolve_path(
            watchdog_log_file,
            DEFAULT_WATCHDOG_RUNTIME_LOG_FILE,
        )
        append_jsonl_path = self._resolve_path(
            append_jsonl,
            DEFAULT_WATCHDOG_RUNTIME_APPEND_JSONL,
        )
        output_json_path = self._resolve_path(
            output_json,
            DEFAULT_WATCHDOG_RUNTIME_OUTPUT_JSON,
        )
        heartbeat_path = self._resolve_path(
            heartbeat_file,
            DEFAULT_HEARTBEAT_FILE,
        )

        policy = evaluate_seed_live_policy(allow_live_automation)
        process_rows = self._list_processes(match_tokens=match_tokens)
        latest_tick = _read_last_jsonl_object(append_jsonl_path)

        latest_report: dict[str, Any] | None = None
        report_read_error: str | None = None
        if output_json_path.exists():
            try:
                parsed = json.loads(output_json_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                report_read_error = str(exc)
            else:
                if isinstance(parsed, dict):
                    latest_report = parsed
                else:
                    report_read_error = "watchdog output report root is not an object"

        health_payload = self.health(
            status_file=status_file,
            merged_jsonl=merged_jsonl,
            merged_parquet=merged_parquet,
            log_file=log_file,
            allow_live_automation=allow_live_automation,
            stale_after_seconds=stale_after_seconds,
        )

        return {
            "schema_name": "AAS.Merlin.SeedWatchdogRuntimeStatus",
            "schema_version": "1.0.0",
            "workspace_root": str(self.workspace_root),
            "policy": policy,
            "paths": {
                "status_file": str(paths["status_file"]),
                "merged_jsonl": str(paths["merged_jsonl"]),
                "merged_parquet": str(paths["merged_parquet"]),
                "log_file": str(paths["log_file"]),
                "watchdog_log_file": str(runtime_log_path),
                "append_jsonl": str(append_jsonl_path),
                "output_json": str(output_json_path),
                "heartbeat_file": str(heartbeat_path),
            },
            "process": {
                "active": bool(process_rows),
                "count": len(process_rows),
                "rows": process_rows,
            },
            "telemetry": {
                "append_jsonl_exists": append_jsonl_path.exists(),
                "append_jsonl_line_count": _count_non_empty_lines(append_jsonl_path),
                "append_jsonl_mtime_utc": _mtime_iso(append_jsonl_path),
                "output_json_exists": output_json_path.exists(),
                "output_json_mtime_utc": _mtime_iso(output_json_path),
                "output_json_read_error": report_read_error,
                "last_tick": latest_tick,
                "last_report_summary": (
                    latest_report.get("summary")
                    if isinstance(latest_report, dict)
                    else None
                ),
            },
            "health": health_payload,
            "updated_at": _utc_now_iso(),
        }

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
            remaining = [
                row for row in remaining_rows if int(row["pid"]) in target_pids
            ]

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

    def _start_watchdog_runtime_process(
        self,
        *,
        command: list[str],
        watchdog_log_file: Path,
    ) -> dict[str, Any]:
        watchdog_log_file.parent.mkdir(parents=True, exist_ok=True)
        with watchdog_log_file.open("a", encoding="utf-8") as log_handle:
            log_handle.write(
                "["
                + _utc_now_iso()
                + "] merlin.seed.watchdog.control start: "
                + shlex.join(command)
                + "\n"
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

    def _build_watchdog_runtime_command(
        self,
        *,
        status_file: Path,
        merged_jsonl: Path,
        merged_parquet: Path,
        log_file: Path,
        stale_after_seconds: float,
        apply: bool,
        force: bool,
        dry_run_control: bool,
        allow_live_automation: bool | None,
        interval_seconds: float,
        max_iterations: int,
        emit_heartbeat: bool,
        heartbeat_file: Path,
        append_jsonl: Path,
        output_json: Path,
    ) -> list[str]:
        script_path = self._resolve_watchdog_script()
        python_exe = self._resolve_python_executable()
        command: list[str] = [
            python_exe,
            str(script_path),
            "--workspace-root",
            str(self.workspace_root),
            "--status-file",
            self._path_for_command(status_file),
            "--merged-jsonl",
            self._path_for_command(merged_jsonl),
            "--merged-parquet",
            self._path_for_command(merged_parquet),
            "--log-file",
            self._path_for_command(log_file),
            "--stale-after-seconds",
            str(stale_after_seconds),
            "--interval-seconds",
            str(interval_seconds),
            "--max-iterations",
            str(max_iterations),
            "--append-jsonl",
            self._path_for_command(append_jsonl),
            "--output-json",
            self._path_for_command(output_json),
        ]

        if apply:
            command.append("--apply")
        else:
            command.append("--no-apply")
        if force:
            command.append("--force")
        if dry_run_control:
            command.append("--dry-run-control")
        if allow_live_automation is True:
            command.append("--allow-live-automation")
        elif allow_live_automation is False:
            command.append("--no-live-automation")
        if emit_heartbeat:
            command.extend(["--emit-heartbeat", "--heartbeat-file"])
            command.append(self._path_for_command(heartbeat_file))
        else:
            command.append("--no-heartbeat")

        return command

    def watchdog_runtime_control(
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
        watchdog_log_file: str | None = None,
        append_jsonl: str | None = None,
        output_json: str | None = None,
        heartbeat_file: str | None = None,
        stale_after_seconds: float = float(DEFAULT_STATUS_STALE_SECONDS),
        apply: bool = False,
        dry_run_control: bool = False,
        interval_seconds: float = 60.0,
        max_iterations: int = 0,
        emit_heartbeat: bool = True,
        match_tokens: tuple[str, ...] = DEFAULT_WATCHDOG_RUNTIME_MATCH_TOKENS,
    ) -> dict[str, Any]:
        normalized_action = str(action or "").strip().lower()
        if normalized_action not in {"start", "stop", "restart"}:
            raise ValueError("action must be one of: start, stop, restart")

        policy = evaluate_seed_live_policy(allow_live_automation)
        if policy["decision"] != POLICY_ALLOWED:
            return {
                "schema_name": "AAS.Merlin.SeedWatchdogRuntimeControl",
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
        runtime_log_path = self._resolve_path(
            watchdog_log_file,
            DEFAULT_WATCHDOG_RUNTIME_LOG_FILE,
        )
        append_jsonl_path = self._resolve_path(
            append_jsonl,
            DEFAULT_WATCHDOG_RUNTIME_APPEND_JSONL,
        )
        output_json_path = self._resolve_path(
            output_json,
            DEFAULT_WATCHDOG_RUNTIME_OUTPUT_JSON,
        )
        heartbeat_path = self._resolve_path(
            heartbeat_file,
            DEFAULT_HEARTBEAT_FILE,
        )
        current = self._list_processes(match_tokens=match_tokens)

        normalized_stale_after_seconds = _safe_float(
            stale_after_seconds,
            default=float(DEFAULT_STATUS_STALE_SECONDS),
            minimum=1.0,
        )
        normalized_apply = bool(apply)
        normalized_dry_run_control = bool(dry_run_control)
        normalized_force = bool(force)
        normalized_interval_seconds = _safe_float(
            interval_seconds,
            default=60.0,
            minimum=0.0,
        )
        normalized_max_iterations = _safe_int(max_iterations, default=0, minimum=0)
        normalized_emit_heartbeat = bool(emit_heartbeat)

        result: dict[str, Any] = {
            "schema_name": "AAS.Merlin.SeedWatchdogRuntimeControl",
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
                "watchdog_log_file": str(runtime_log_path),
                "append_jsonl": str(append_jsonl_path),
                "output_json": str(output_json_path),
                "heartbeat_file": str(heartbeat_path),
            },
            "runtime": {
                "stale_after_seconds": normalized_stale_after_seconds,
                "apply": normalized_apply,
                "dry_run_control": normalized_dry_run_control,
                "force": normalized_force,
                "interval_seconds": normalized_interval_seconds,
                "max_iterations": normalized_max_iterations,
                "emit_heartbeat": normalized_emit_heartbeat,
            },
        }

        if normalized_action == "stop":
            if dry_run:
                result.update(
                    {
                        "status": "preview",
                        "message": (
                            "Dry-run preview only; no watchdog runtime processes were stopped"
                        ),
                        "preview": {
                            "would_stop_count": len(current),
                            "rows": current,
                        },
                    }
                )
                result["status_snapshot"] = self.watchdog_runtime_status(
                    status_file=status_file,
                    merged_jsonl=merged_jsonl,
                    merged_parquet=merged_parquet,
                    log_file=log_file,
                    watchdog_log_file=watchdog_log_file,
                    append_jsonl=append_jsonl,
                    output_json=output_json,
                    heartbeat_file=heartbeat_file,
                    allow_live_automation=allow_live_automation,
                    stale_after_seconds=normalized_stale_after_seconds,
                    match_tokens=match_tokens,
                )
                result["updated_at"] = _utc_now_iso()
                return result

            stopped = self._stop_processes(match_tokens=match_tokens)
            result.update(
                {
                    "status": (
                        "stopped" if stopped["before_count"] > 0 else "already_stopped"
                    ),
                    "message": (
                        "Seed watchdog runtime processes stopped"
                        if stopped["before_count"] > 0
                        else "No active seed watchdog runtime processes"
                    ),
                    "process": stopped,
                }
            )
            result["status_snapshot"] = self.watchdog_runtime_status(
                status_file=status_file,
                merged_jsonl=merged_jsonl,
                merged_parquet=merged_parquet,
                log_file=log_file,
                watchdog_log_file=watchdog_log_file,
                append_jsonl=append_jsonl,
                output_json=output_json,
                heartbeat_file=heartbeat_file,
                allow_live_automation=allow_live_automation,
                stale_after_seconds=normalized_stale_after_seconds,
                match_tokens=match_tokens,
            )
            result["updated_at"] = _utc_now_iso()
            return result

        preview_command = self._build_watchdog_runtime_command(
            status_file=paths["status_file"],
            merged_jsonl=paths["merged_jsonl"],
            merged_parquet=paths["merged_parquet"],
            log_file=paths["log_file"],
            stale_after_seconds=normalized_stale_after_seconds,
            apply=normalized_apply,
            force=normalized_force,
            dry_run_control=normalized_dry_run_control,
            allow_live_automation=allow_live_automation,
            interval_seconds=normalized_interval_seconds,
            max_iterations=normalized_max_iterations,
            emit_heartbeat=normalized_emit_heartbeat,
            heartbeat_file=heartbeat_path,
            append_jsonl=append_jsonl_path,
            output_json=output_json_path,
        )

        should_launch = not (current and not normalized_force)
        should_stop = normalized_action == "restart" or (
            normalized_action == "start" and current and normalized_force
        )

        if dry_run:
            result.update(
                {
                    "status": "preview",
                    "message": (
                        "Dry-run preview only; no watchdog runtime process started"
                        if should_launch
                        else "Dry-run preview: watchdog runtime already running (force=true required to relaunch)"
                    ),
                    "preview": {
                        "active_before_count": len(current),
                        "active_before_rows": current,
                        "force": normalized_force,
                        "would_launch": bool(should_launch),
                        "would_stop_count": len(current) if should_stop else 0,
                        "command": shlex.join(preview_command),
                    },
                }
            )
            result["status_snapshot"] = self.watchdog_runtime_status(
                status_file=status_file,
                merged_jsonl=merged_jsonl,
                merged_parquet=merged_parquet,
                log_file=log_file,
                watchdog_log_file=watchdog_log_file,
                append_jsonl=append_jsonl,
                output_json=output_json,
                heartbeat_file=heartbeat_file,
                allow_live_automation=allow_live_automation,
                stale_after_seconds=normalized_stale_after_seconds,
                match_tokens=match_tokens,
            )
            result["updated_at"] = _utc_now_iso()
            return result

        if current and not normalized_force:
            result.update(
                {
                    "status": "already_running",
                    "message": (
                        "Seed watchdog runtime already running (set force=true to restart)"
                    ),
                    "process": {
                        "before_count": len(current),
                        "rows": current,
                    },
                }
            )
            result["status_snapshot"] = self.watchdog_runtime_status(
                status_file=status_file,
                merged_jsonl=merged_jsonl,
                merged_parquet=merged_parquet,
                log_file=log_file,
                watchdog_log_file=watchdog_log_file,
                append_jsonl=append_jsonl,
                output_json=output_json,
                heartbeat_file=heartbeat_file,
                allow_live_automation=allow_live_automation,
                stale_after_seconds=normalized_stale_after_seconds,
                match_tokens=match_tokens,
            )
            result["updated_at"] = _utc_now_iso()
            return result

        stop_details: dict[str, Any] | None = None
        if should_stop:
            stop_details = self._stop_processes(match_tokens=match_tokens)

        start_details = self._start_watchdog_runtime_process(
            command=preview_command,
            watchdog_log_file=runtime_log_path,
        )
        result.update(
            {
                "status": "started" if normalized_action == "start" else "restarted",
                "message": (
                    "Seed watchdog runtime process started"
                    if normalized_action == "start"
                    else "Seed watchdog runtime process restarted"
                ),
                "start": {
                    "pid": start_details["pid"],
                    "command": shlex.join(start_details["command"]),
                },
            }
        )
        if stop_details is not None:
            result["stop"] = stop_details

        result["status_snapshot"] = self.watchdog_runtime_status(
            status_file=status_file,
            merged_jsonl=merged_jsonl,
            merged_parquet=merged_parquet,
            log_file=log_file,
            watchdog_log_file=watchdog_log_file,
            append_jsonl=append_jsonl,
            output_json=output_json,
            heartbeat_file=heartbeat_file,
            allow_live_automation=allow_live_automation,
            stale_after_seconds=normalized_stale_after_seconds,
            match_tokens=match_tokens,
        )
        result["updated_at"] = _utc_now_iso()
        return result

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

        prior_status_payload = self._read_status_file_payload(paths["status_file"])
        prior_endpoint = None
        if isinstance(prior_status_payload, dict):
            raw_prior_endpoint = prior_status_payload.get("endpoint")
            if isinstance(raw_prior_endpoint, str) and raw_prior_endpoint.strip():
                prior_endpoint = raw_prior_endpoint.strip()

        requested_endpoint = str(endpoint).strip() or "http://127.0.0.1:1234"
        if prior_endpoint and requested_endpoint == "http://127.0.0.1:1234":
            normalized_endpoint = prior_endpoint
        else:
            normalized_endpoint = requested_endpoint
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
                        "message": ("Dry-run preview only; no processes were stopped"),
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
                    "status": (
                        "stopped" if stopped["before_count"] > 0 else "already_stopped"
                    ),
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

        should_launch = not (
            normalized_action in {"start", "restart"} and current and not force
        )
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
        if normalized_action == "restart" or (
            normalized_action == "start" and current and force
        ):
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
