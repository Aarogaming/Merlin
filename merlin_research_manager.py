from __future__ import annotations

import json
import math
import os
import re
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

try:
    from merlin_audit import log_read_only_rejection
except (ImportError, AttributeError):  # pragma: no cover - standalone fallback

    def log_read_only_rejection(*_args: Any, **_kwargs: Any) -> None:
        return None
from merlin_tasks import task_manager
from merlin_utils import stable_claim_hash

DEFAULT_STORAGE_ROOT = Path("artifacts") / "research_manager"
SESSION_SCHEMA_VERSION = "1.0.0"
READ_ONLY_ENV_VAR = "MERLIN_RESEARCH_MANAGER_READ_ONLY"
SESSION_TTL_DAYS_ENV_VAR = "MERLIN_RESEARCH_SESSION_TTL_DAYS"
AUTO_ARCHIVE_ENV_VAR = "MERLIN_RESEARCH_AUTO_ARCHIVE_ENABLED"
BRIEF_QUEUE_ENABLED_ENV_VAR = "MERLIN_RESEARCH_BRIEF_QUEUE_ENABLED"
DEFAULT_SESSION_TTL_DAYS = 90
DEFAULT_CREATED_BY = "merlin.research_manager"
DEFAULT_SOURCE_OPERATION = "merlin.research.manager.session.create"
DEFAULT_POLICY_VERSION = "research-session-provenance-v1"
BRIEF_TEMPLATE_ID = "research_manager.default"
BRIEF_TEMPLATE_VERSION = "1.0.0"
SESSION_SNAPSHOT_SCHEMA_NAME = "AAS.ResearchSessionSnapshot"
SESSION_SNAPSHOT_SCHEMA_VERSION = "1.0.0"
RESEARCH_SESSION_EVENT_SCHEMA_NAME = "AAS.ResearchSessionEvent"
RESEARCH_SESSION_EVENT_SCHEMA_VERSION = "1.0.0"
DEFAULT_RISK_IMPACT = 0.5
DEFAULT_RISK_UNCERTAINTY = 0.5
MEMORY_DECAY_HALF_LIFE_DAYS = 30.0
MEMORY_MIN_DECAY_WEIGHT = 0.2
MEMORY_REINFORCEMENT_PER_DUPLICATE = 0.08
MEMORY_MAX_REINFORCEMENT_MULTIPLIER = 1.4
SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _coerce_positive_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_provenance_text(value: Any, default: str) -> str:
    if not isinstance(value, str):
        return default
    normalized = value.strip()
    return normalized if normalized else default


def _normalize_tags(tags: list[str] | None) -> list[str]:
    normalized: list[str] = []
    for item in tags or []:
        if not isinstance(item, str):
            continue
        tag = item.strip().lower()
        if not tag or tag in normalized:
            continue
        normalized.append(tag)
    return normalized


def _normalize_linked_task_ids(task_ids: list[Any] | None) -> list[int]:
    normalized: list[int] = []
    for item in task_ids or []:
        if isinstance(item, bool):
            continue
        task_id: int | None = None
        if isinstance(item, int):
            task_id = item
        elif isinstance(item, str):
            raw = item.strip()
            if raw.isdigit():
                task_id = int(raw)
        if task_id is None or task_id <= 0 or task_id in normalized:
            continue
        normalized.append(task_id)
    return normalized


def _normalize_planner_artifacts(artifacts: list[Any] | None) -> list[str]:
    normalized: list[str] = []
    for item in artifacts or []:
        artifact_ref = ""
        if isinstance(item, str):
            artifact_ref = item.strip()
        elif isinstance(item, dict):
            for key in ("artifact_ref", "artifact_path", "path", "id"):
                raw_value = item.get(key)
                if isinstance(raw_value, str) and raw_value.strip():
                    artifact_ref = raw_value.strip()
                    break
        if not artifact_ref or artifact_ref in normalized:
            continue
        normalized.append(artifact_ref)
    return normalized


def calibrate_signal_confidence(
    confidence: float, *, novelty: float = 0.5, risk: float = 0.2
) -> float:
    """
    Calibrate signal confidence before hypothesis scoring.

    - Higher novelty provides a small uplift.
    - Higher risk applies a stronger penalty.
    """
    base_confidence = _clamp(float(confidence), 0.0, 1.0)
    novelty_score = _clamp(float(novelty), 0.0, 1.0)
    risk_score = _clamp(float(risk), 0.0, 1.0)
    novelty_uplift = (novelty_score - 0.5) * 0.12
    risk_penalty = risk_score * 0.18
    return round(_clamp(base_confidence + novelty_uplift - risk_penalty, 0.0, 1.0), 4)


def _default_time_horizon_bucket(horizon_days: int) -> str:
    if horizon_days <= 14:
        return "near_term"
    if horizon_days <= 60:
        return "mid_term"
    return "long_term"


def _normalize_time_horizon(value: Any, horizon_days: int) -> str:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"near_term", "mid_term", "long_term"}:
            return normalized
    return _default_time_horizon_bucket(horizon_days)


def _from_iso8601_utc(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _signal_age_days(signal: dict[str, Any], *, now_utc: datetime) -> float:
    signal_timestamp = _from_iso8601_utc(signal.get("timestamp_utc"))
    if signal_timestamp is None:
        return 0.0
    age_seconds = max(0.0, (now_utc - signal_timestamp).total_seconds())
    return age_seconds / 86400.0


def _memory_decay_weight(age_days: float) -> float:
    half_life = max(1e-6, float(MEMORY_DECAY_HALF_LIFE_DAYS))
    raw_weight = math.exp((-math.log(2.0) * max(0.0, age_days)) / half_life)
    return _clamp(raw_weight, MEMORY_MIN_DECAY_WEIGHT, 1.0)


def _memory_reinforcement_multiplier(signal: dict[str, Any]) -> float:
    duplicate_count_raw = signal.get("duplicate_count", 0)
    if isinstance(duplicate_count_raw, int) and duplicate_count_raw > 0:
        duplicate_count = duplicate_count_raw
    else:
        duplicate_count = 0
    bonus = min(duplicate_count, 5) * MEMORY_REINFORCEMENT_PER_DUPLICATE
    return _clamp(1.0 + bonus, 1.0, MEMORY_MAX_REINFORCEMENT_MULTIPLIER)


class ResearchManager:
    """
    Local research manager for hypothesis-driven execution.

    This engine stores session state on disk so Merlin can maintain continuity
    between API calls and produce probability-guided decision briefs.
    """

    def __init__(
        self,
        storage_root: str | Path = DEFAULT_STORAGE_ROOT,
        allow_writes: bool | None = None,
        session_ttl_days: int | None = None,
        auto_archive: bool | None = None,
        brief_queue_enabled: bool | None = None,
        event_emitter: Callable[[dict[str, Any]], Any] | None = None,
    ):
        self.storage_root = Path(storage_root)
        self.sessions_dir = self.storage_root / "sessions"
        self.archive_dir = self.storage_root / "archive"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        if allow_writes is None:
            self.allow_writes = not _is_truthy(os.getenv(READ_ONLY_ENV_VAR))
        else:
            self.allow_writes = bool(allow_writes)
        if session_ttl_days is None:
            session_ttl_days = _coerce_positive_int(
                os.getenv(SESSION_TTL_DAYS_ENV_VAR), DEFAULT_SESSION_TTL_DAYS
            )
        self.session_ttl_days = max(1, int(session_ttl_days))
        if auto_archive is None:
            auto_archive = os.getenv(AUTO_ARCHIVE_ENV_VAR, "true").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
        self.auto_archive = bool(auto_archive)
        if brief_queue_enabled is None:
            brief_queue_enabled = _is_truthy(os.getenv(BRIEF_QUEUE_ENABLED_ENV_VAR))
        self.brief_queue_enabled = bool(brief_queue_enabled)
        self._brief_jobs: dict[str, dict[str, Any]] = {}
        self._brief_job_queue: deque[str] = deque()
        self.event_emitter = event_emitter

    def create_session(
        self,
        objective: str,
        constraints: list[str] | None = None,
        horizon_days: int = 14,
        *,
        created_by: str | None = None,
        source_operation: str | None = None,
        policy_version: str | None = None,
        tags: list[str] | None = None,
        impact: float | None = None,
        uncertainty: float | None = None,
        time_horizon: str | None = None,
        linked_task_ids: list[int] | None = None,
        planner_artifacts: list[str] | None = None,
    ) -> dict[str, Any]:
        self._ensure_writes_allowed(operation="merlin.research.manager.session.create")

        objective_clean = objective.strip()
        if not objective_clean:
            raise ValueError("objective must be non-empty")

        now = _utc_now()
        session_id = uuid.uuid4().hex
        normalized_constraints = [
            item.strip() for item in (constraints or []) if item and item.strip()
        ]

        hypotheses = self._seed_hypotheses(objective_clean)
        normalized_tags = _normalize_tags(tags)
        normalized_linked_task_ids = _normalize_linked_task_ids(linked_task_ids)
        normalized_planner_artifacts = _normalize_planner_artifacts(planner_artifacts)
        normalized_horizon_days = max(1, int(horizon_days))
        impact_value = _clamp(
            float(DEFAULT_RISK_IMPACT if impact is None else impact), 0.0, 1.0
        )
        uncertainty_value = _clamp(
            float(DEFAULT_RISK_UNCERTAINTY if uncertainty is None else uncertainty), 0.0, 1.0
        )
        time_horizon_value = _normalize_time_horizon(time_horizon, normalized_horizon_days)
        created_by_value = _normalize_provenance_text(created_by, DEFAULT_CREATED_BY)
        source_operation_value = _normalize_provenance_text(
            source_operation, DEFAULT_SOURCE_OPERATION
        )
        policy_version_value = _normalize_provenance_text(
            policy_version, DEFAULT_POLICY_VERSION
        )
        session = {
            "schema_version": SESSION_SCHEMA_VERSION,
            "session_id": session_id,
            "objective": objective_clean,
            "constraints": normalized_constraints,
            "tags": normalized_tags,
            "linked_task_ids": normalized_linked_task_ids,
            "planner_artifacts": normalized_planner_artifacts,
            "horizon_days": normalized_horizon_days,
            "risk_rubric": {
                "impact": round(impact_value, 4),
                "uncertainty": round(uncertainty_value, 4),
                "time_horizon": time_horizon_value,
            },
            "status": "active",
            "created_by": created_by_value,
            "source_operation": source_operation_value,
            "policy_version": policy_version_value,
            "created_at_utc": now,
            "updated_at_utc": now,
            "hypotheses": hypotheses,
            "signals": [],
            "tasks": self._seed_tasks(objective_clean, hypotheses),
            "foresight": self._foresight_from_hypotheses(hypotheses),
        }
        self._write_session(session)
        self._emit_session_event("session.created", session)
        return session

    def list_sessions(
        self,
        limit: int = 20,
        *,
        tag: str | None = None,
        topic_query: str | None = None,
    ) -> list[dict[str, Any]]:
        page = self.list_sessions_page(
            limit=limit,
            cursor=None,
            tag=tag,
            topic_query=topic_query,
        )
        return page["sessions"]

    def list_sessions_page(
        self,
        limit: int = 20,
        *,
        cursor: str | None = None,
        tag: str | None = None,
        topic_query: str | None = None,
    ) -> dict[str, Any]:
        if self.auto_archive and self.allow_writes:
            self.archive_expired_sessions()

        normalized_limit = max(1, int(limit))
        offset = self._decode_sessions_cursor(cursor)
        items = self._collect_session_summaries(tag=tag, topic_query=topic_query)
        paged = items[offset : offset + normalized_limit]
        next_offset = offset + len(paged)
        next_cursor = str(next_offset) if next_offset < len(items) else None
        return {
            "sessions": paged,
            "next_cursor": next_cursor,
        }

    def search_sessions(
        self,
        query: str,
        *,
        limit: int = 20,
        cursor: str | None = None,
        tag: str | None = None,
    ) -> dict[str, Any]:
        query_text = query.strip()
        if not query_text:
            raise ValueError("query must be non-empty")
        return self.list_sessions_page(
            limit=limit,
            cursor=cursor,
            tag=tag,
            topic_query=query_text,
        )

    def enqueue_brief_generation(self, session_id: str) -> dict[str, Any]:
        self._ensure_brief_queue_enabled()
        session = self.get_session(session_id)
        job_id = uuid.uuid4().hex
        task_id: int | None = None
        try:
            task = task_manager.add_task(
                title=f"Generate research brief: {session_id}",
                description=f"Queued research brief generation for {session.get('objective', '')}",
                priority="Medium",
            )
            raw_task_id = task.get("id")
            task_id = raw_task_id if isinstance(raw_task_id, int) else None
        except Exception:
            task_id = None

        job = {
            "job_id": job_id,
            "session_id": session_id,
            "status": "queued",
            "created_at_utc": _utc_now(),
            "task_id": task_id,
        }
        self._brief_jobs[job_id] = job
        self._brief_job_queue.append(job_id)
        return dict(job)

    def process_brief_queue(self, max_jobs: int = 1) -> int:
        self._ensure_brief_queue_enabled()
        allowed = max(1, int(max_jobs))
        processed = 0
        while self._brief_job_queue and processed < allowed:
            job_id = self._brief_job_queue.popleft()
            job = self._brief_jobs.get(job_id)
            if not job or job.get("status") != "queued":
                continue
            job["status"] = "running"
            job["started_at_utc"] = _utc_now()
            try:
                brief = self.get_brief(job["session_id"])
                job["status"] = "completed"
                job["result"] = {"brief": brief}
                job["completed_at_utc"] = _utc_now()
                if isinstance(job.get("task_id"), int):
                    task_manager.update_task_status(job["task_id"], "Completed")
            except Exception as exc:
                job["status"] = "failed"
                job["error"] = str(exc)
                job["completed_at_utc"] = _utc_now()
                if isinstance(job.get("task_id"), int):
                    task_manager.update_task_status(job["task_id"], "Failed")
            processed += 1
        return processed

    def get_brief_job(self, job_id: str) -> dict[str, Any]:
        normalized_job_id = job_id.strip()
        if not normalized_job_id:
            raise ValueError("job_id must be non-empty")
        job = self._brief_jobs.get(normalized_job_id)
        if job is None:
            raise FileNotFoundError(f"brief job not found: {normalized_job_id}")
        return json.loads(json.dumps(job))

    def list_brief_jobs(self, limit: int = 20) -> list[dict[str, Any]]:
        self._ensure_brief_queue_enabled()
        jobs = sorted(
            self._brief_jobs.values(),
            key=lambda item: item.get("created_at_utc", ""),
            reverse=True,
        )
        return [json.loads(json.dumps(item)) for item in jobs[: max(1, int(limit))]]

    def _collect_session_summaries(
        self,
        *,
        tag: str | None = None,
        topic_query: str | None = None,
    ) -> list[dict[str, Any]]:
        filter_tag = tag.strip().lower() if isinstance(tag, str) else ""
        filter_topic = topic_query.strip().lower() if isinstance(topic_query, str) else ""
        items: list[dict[str, Any]] = []
        for file_path in sorted(self._iter_session_files()):
            try:
                session = self._read_session(file_path)
            except ValueError:
                continue
            session_tags = _normalize_tags(session.get("tags", []))
            objective = session.get("objective", "")
            objective_text = objective if isinstance(objective, str) else ""
            if filter_tag and filter_tag not in session_tags:
                continue
            if filter_topic and filter_topic not in objective_text.lower():
                continue
            items.append(
                {
                    "session_id": session["session_id"],
                    "objective": objective_text,
                    "tags": session_tags,
                    "status": session.get("status", "unknown"),
                    "created_at_utc": session.get("created_at_utc"),
                    "updated_at_utc": session.get("updated_at_utc"),
                    "signal_count": len(session.get("signals", [])),
                    "linked_task_count": len(session.get("linked_task_ids", [])),
                    "planner_artifact_count": len(session.get("planner_artifacts", [])),
                }
            )
        items.sort(key=lambda entry: entry.get("updated_at_utc", ""), reverse=True)
        return items

    def _decode_sessions_cursor(self, cursor: str | None) -> int:
        if cursor is None:
            return 0
        cursor_text = cursor.strip()
        if not cursor_text:
            return 0
        try:
            offset = int(cursor_text)
        except ValueError as exc:
            raise ValueError("cursor must be a non-negative integer string") from exc
        if offset < 0:
            raise ValueError("cursor must be a non-negative integer string")
        return offset

    def get_session(self, session_id: str) -> dict[str, Any]:
        path = self._session_path(session_id)
        archive_path = self._archive_session_path(session_id)
        if path.exists():
            session = self._read_session(path)
            if self.auto_archive and self.allow_writes:
                session = self._archive_session_if_expired(path, session)
            return session
        if archive_path.exists():
            return self._read_session(archive_path)
        raise FileNotFoundError(f"research session not found: {session_id}")

    def add_signal(
        self,
        session_id: str,
        source: str,
        claim: str,
        confidence: float,
        *,
        novelty: float = 0.5,
        risk: float = 0.2,
        supports: list[str] | None = None,
        contradicts: list[str] | None = None,
    ) -> dict[str, Any]:
        self._ensure_writes_allowed(
            operation="merlin.research.manager.session.signal.add",
            details={"session_id": session_id.strip()},
        )
        session = self.get_session(session_id)
        if session.get("status") == "archived":
            raise ValueError(
                f"research session is archived and read-only: {session['session_id']}"
            )

        source_clean = source.strip()
        claim_clean = claim.strip()
        if not source_clean:
            raise ValueError("signal source must be non-empty")
        if not claim_clean:
            raise ValueError("signal claim must be non-empty")

        confidence_raw = _clamp(float(confidence), 0.0, 1.0)
        novelty_score = _clamp(float(novelty), 0.0, 1.0)
        risk_score = _clamp(float(risk), 0.0, 1.0)
        confidence_calibrated = calibrate_signal_confidence(
            confidence_raw,
            novelty=novelty_score,
            risk=risk_score,
        )
        claim_hash = stable_claim_hash(claim_clean)

        existing_signals = session.setdefault("signals", [])
        duplicate_signal: dict[str, Any] | None = None
        for existing_signal in existing_signals:
            if not isinstance(existing_signal, dict):
                continue
            existing_claim = existing_signal.get("claim")
            existing_claim_hash_raw = existing_signal.get("claim_hash")
            existing_claim_hash = (
                existing_claim_hash_raw
                if isinstance(existing_claim_hash_raw, str) and existing_claim_hash_raw
                else stable_claim_hash(existing_claim if isinstance(existing_claim, str) else "")
            )
            existing_signal["claim_hash"] = existing_claim_hash
            if existing_claim_hash == claim_hash:
                duplicate_signal = existing_signal
                break

        if duplicate_signal is not None:
            duplicate_count_raw = duplicate_signal.get("duplicate_count", 0)
            duplicate_count = (
                duplicate_count_raw
                if isinstance(duplicate_count_raw, int) and duplicate_count_raw >= 0
                else 0
            )
            duplicate_signal["duplicate_count"] = duplicate_count + 1
            duplicate_signal["last_duplicate_at_utc"] = _utc_now()
            duplicate_signal["last_duplicate_source"] = source_clean
            self._update_hypotheses(session)
            session["foresight"] = self._foresight_from_hypotheses(session["hypotheses"])
            session["updated_at_utc"] = _utc_now()
            self._write_session(session)
            self._emit_session_event(
                "session.signal_deduplicated",
                session,
                metadata={
                    "signal_id": duplicate_signal.get("signal_id"),
                    "claim_hash": duplicate_signal.get("claim_hash"),
                },
            )
            return {
                "session_id": session_id,
                "signal": duplicate_signal,
                "deduplicated": True,
                "dedup_reason": "duplicate_claim_hash",
                "hypotheses": session["hypotheses"],
                "next_actions": self._next_actions_for_session(session),
            }

        signal = {
            "signal_id": uuid.uuid4().hex,
            "source": source_clean,
            "claim": claim_clean,
            "claim_hash": claim_hash,
            "confidence": confidence_calibrated,
            "confidence_raw": round(confidence_raw, 4),
            "novelty": round(novelty_score, 4),
            "risk": round(risk_score, 4),
            "duplicate_count": 0,
            "supports": list(supports or []),
            "contradicts": list(contradicts or []),
            "timestamp_utc": _utc_now(),
        }
        existing_signals.append(signal)
        self._update_hypotheses(session)
        session["foresight"] = self._foresight_from_hypotheses(session["hypotheses"])
        session["updated_at_utc"] = _utc_now()
        self._write_session(session)
        self._emit_session_event(
            "session.signal_added",
            session,
            metadata={
                "signal_id": signal["signal_id"],
                "claim_hash": signal["claim_hash"],
            },
        )
        return {
            "session_id": session_id,
            "signal": signal,
            "hypotheses": session["hypotheses"],
            "next_actions": self._next_actions_for_session(session),
        }

    def ingest_planner_fallback_telemetry(
        self,
        session_id: str,
        telemetry: dict[str, Any],
        *,
        source: str = "assistant.chat.request",
    ) -> dict[str, Any]:
        if not isinstance(telemetry, dict):
            raise ValueError("telemetry must be an object")

        reason_code_raw = telemetry.get("fallback_reason_code")
        if isinstance(reason_code_raw, str) and reason_code_raw.strip():
            reason_code = reason_code_raw.strip().lower()
        else:
            reason_code = "none"

        fallback_stage_raw = telemetry.get("fallback_stage")
        fallback_stage = (
            fallback_stage_raw.strip().lower()
            if isinstance(fallback_stage_raw, str) and fallback_stage_raw.strip()
            else "unspecified"
        )

        detail_raw = telemetry.get("fallback_detail") or telemetry.get("fallback_reason")
        detail = detail_raw.strip() if isinstance(detail_raw, str) and detail_raw.strip() else ""

        selected_model_raw = telemetry.get("selected_model")
        selected_model = (
            selected_model_raw.strip()
            if isinstance(selected_model_raw, str) and selected_model_raw.strip()
            else "unknown"
        )

        source_label = source.strip() if isinstance(source, str) and source.strip() else "assistant.chat.request"

        if reason_code == "none":
            confidence = 0.66
            risk = 0.2
            supports = ["h_execution_success"]
            contradicts: list[str] = []
            claim = (
                "Routing completed without fallback "
                f"(selected_model={selected_model}, stage={fallback_stage})."
            )
        else:
            confidence = 0.78 if telemetry.get("fallback_retryable") else 0.84
            risk = 0.72 if reason_code.startswith("dms_") else 0.64
            supports = []
            contradicts = ["h_execution_success"]
            if reason_code.startswith("dms_") or reason_code in {
                "provider_error",
                "provider_timeout",
                "network_error",
            }:
                contradicts.append("h_dependency_risk")
            claim = (
                f"Planner fallback triggered ({reason_code}) at stage={fallback_stage}; "
                f"selected_model={selected_model}"
            )
            if detail:
                claim = f"{claim}; detail={detail}"

        signal_result = self.add_signal(
            session_id=session_id,
            source=f"{source_label}:{reason_code}",
            claim=claim,
            confidence=confidence,
            novelty=0.45,
            risk=risk,
            supports=supports,
            contradicts=contradicts,
        )
        return {
            "session_id": session_id,
            "ingested": True,
            "reason_code": reason_code,
            "signal": signal_result.get("signal"),
            "deduplicated": bool(signal_result.get("deduplicated", False)),
        }

    def get_brief(self, session_id: str) -> dict[str, Any]:
        session = self.get_session(session_id)
        self._update_hypotheses(session)
        session["foresight"] = self._foresight_from_hypotheses(session["hypotheses"])
        signals = session.get("signals", [])
        hypotheses = sorted(
            session.get("hypotheses", []),
            key=lambda hyp: float(hyp.get("probability", 0.0)),
            reverse=True,
        )
        conflict_summary = self._summarize_signal_conflicts(signals)
        causal_chains = self._build_causal_chains(signals, hypotheses)
        probability_of_success = 0.0
        if hypotheses:
            probability_of_success = sum(
                float(item.get("probability", 0.0)) for item in hypotheses
            ) / len(hypotheses)
        return {
            "session_id": session["session_id"],
            "objective": session["objective"],
            "status": session.get("status", "active"),
            "brief_template_id": BRIEF_TEMPLATE_ID,
            "brief_template_version": BRIEF_TEMPLATE_VERSION,
            "probability_of_success": round(_clamp(probability_of_success, 0.0, 1.0), 4),
            "signal_count": len(session.get("signals", [])),
            "risk_rubric": session.get("risk_rubric", {}),
            "linked_task_ids": list(session.get("linked_task_ids", [])),
            "linked_tasks": self._resolve_linked_tasks(session.get("linked_task_ids", [])),
            "planner_artifacts": list(session.get("planner_artifacts", [])),
            "contradicting_signal_count": conflict_summary["contradicting_signal_count"],
            "conflict_count": conflict_summary["conflict_count"],
            "conflict_hypotheses": conflict_summary["conflict_hypotheses"],
            "causal_chains": causal_chains,
            "hypotheses": hypotheses,
            "foresight": session.get("foresight", []),
            "next_actions": self._next_actions_for_session(session),
            "updated_at_utc": session.get("updated_at_utc"),
        }

    def next_actions(self, session_id: str) -> list[str]:
        session = self.get_session(session_id)
        return self._next_actions_for_session(session)

    def export_session_snapshot(self, session_id: str) -> dict[str, Any]:
        session = self.get_session(session_id)
        snapshot_session = json.loads(json.dumps(session))
        return {
            "schema_name": SESSION_SNAPSHOT_SCHEMA_NAME,
            "schema_version": SESSION_SNAPSHOT_SCHEMA_VERSION,
            "exported_at_utc": _utc_now(),
            "session": snapshot_session,
        }

    def import_session_snapshot(
        self,
        snapshot: dict[str, Any],
        *,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        self._ensure_writes_allowed(operation="merlin.research.manager.session.import")

        if not isinstance(snapshot, dict):
            raise ValueError("snapshot payload must be an object")

        schema_name = snapshot.get("schema_name")
        if schema_name != SESSION_SNAPSHOT_SCHEMA_NAME:
            raise ValueError(
                f"unsupported snapshot schema_name: {schema_name}"
            )

        schema_version = snapshot.get("schema_version")
        if schema_version != SESSION_SNAPSHOT_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported snapshot schema_version: {schema_version}"
            )

        raw_session = snapshot.get("session")
        if not isinstance(raw_session, dict):
            raise ValueError("snapshot.session must be an object")

        normalized_session, _ = self._normalize_session(dict(raw_session))
        session_id = normalized_session["session_id"]
        active_path = self._session_path(session_id)
        archive_path = self._archive_session_path(session_id)
        existing_paths = [path for path in (active_path, archive_path) if path.exists()]
        if existing_paths and not overwrite:
            raise ValueError(
                f"research session already exists: {session_id}; use overwrite to replace"
            )

        if overwrite:
            for path in existing_paths:
                path.unlink()

        target_path = (
            archive_path if normalized_session.get("status") == "archived" else active_path
        )
        self._write_session(normalized_session, path=target_path)
        self._emit_session_event("session.imported", normalized_session)
        return normalized_session

    def _session_path(self, session_id: str) -> Path:
        normalized = session_id.strip()
        if not normalized:
            raise ValueError("session_id must be non-empty")
        if not SESSION_ID_PATTERN.fullmatch(normalized):
            raise ValueError(
                "session_id contains invalid characters; allowed: A-Z, a-z, 0-9, _, -"
            )
        return self.sessions_dir / f"{normalized}.json"

    def _archive_session_path(self, session_id: str) -> Path:
        normalized = session_id.strip()
        if not normalized:
            raise ValueError("session_id must be non-empty")
        if not SESSION_ID_PATTERN.fullmatch(normalized):
            raise ValueError(
                "session_id contains invalid characters; allowed: A-Z, a-z, 0-9, _, -"
            )
        return self.archive_dir / f"{normalized}.json"

    def _iter_session_files(self) -> list[Path]:
        files: list[Path] = []
        files.extend(sorted(self.sessions_dir.glob("*.json")))
        files.extend(sorted(self.archive_dir.glob("*.json")))
        return files

    def archive_expired_sessions(self, *, now_utc: datetime | None = None) -> int:
        now = now_utc or datetime.now(timezone.utc)
        archived_count = 0
        for file_path in sorted(self.sessions_dir.glob("*.json")):
            try:
                session = self._read_session(file_path)
            except ValueError:
                continue
            archived = self._archive_session_if_expired(
                file_path,
                session,
                now_utc=now,
            )
            if archived.get("status") == "archived":
                archived_count += 1
        return archived_count

    def _session_is_expired(self, session: dict[str, Any], *, now_utc: datetime) -> bool:
        reference_timestamp = _from_iso8601_utc(session.get("updated_at_utc"))
        if reference_timestamp is None:
            reference_timestamp = _from_iso8601_utc(session.get("created_at_utc"))
        if reference_timestamp is None:
            return False
        ttl_delta = timedelta(days=self.session_ttl_days)
        return now_utc - reference_timestamp > ttl_delta

    def _archive_session_if_expired(
        self,
        source_path: Path,
        session: dict[str, Any],
        *,
        now_utc: datetime | None = None,
    ) -> dict[str, Any]:
        if source_path.parent != self.sessions_dir:
            return session
        if session.get("status") == "archived":
            return session
        now = now_utc or datetime.now(timezone.utc)
        if not self._session_is_expired(session, now_utc=now):
            return session
        archived_session = dict(session)
        archived_session["status"] = "archived"
        archived_session["archive_reason"] = "ttl_expired"
        archived_session["archived_at_utc"] = now.isoformat()
        archived_session["updated_at_utc"] = now.isoformat()
        archive_path = self._archive_session_path(session["session_id"])
        temp_path = archive_path.with_suffix(".json.tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(archived_session, handle, indent=2, sort_keys=True)
            handle.write("\n")
        temp_path.replace(archive_path)
        if source_path.exists():
            source_path.unlink()
        return archived_session

    def _read_session(self, path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError(f"invalid session payload at {path}")
        normalized, migrated = self._normalize_session(data)
        if migrated:
            self._write_session(normalized, path=path)
        return normalized

    def _write_session(self, session: dict[str, Any], *, path: Path | None = None) -> None:
        write_path = path or self._session_path(session["session_id"])
        temp_path = write_path.with_suffix(".json.tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(session, handle, indent=2, sort_keys=True)
            handle.write("\n")
        temp_path.replace(write_path)

    def _ensure_writes_allowed(
        self,
        *,
        operation: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        if not self.allow_writes:
            log_read_only_rejection(
                component="merlin_research_manager",
                operation=operation,
                details=details,
            )
            raise PermissionError("Research manager is read-only")

    def _ensure_brief_queue_enabled(self) -> None:
        if not self.brief_queue_enabled:
            raise RuntimeError("Research brief queue is disabled")

    def set_event_emitter(
        self,
        emitter: Callable[[dict[str, Any]], Any] | None,
    ) -> None:
        self.event_emitter = emitter

    def _emit_session_event(
        self,
        event_type: str,
        session: dict[str, Any],
        *,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if self.event_emitter is None:
            return
        event_payload = {
            "schema_name": RESEARCH_SESSION_EVENT_SCHEMA_NAME,
            "schema_version": RESEARCH_SESSION_EVENT_SCHEMA_VERSION,
            "event_type": event_type,
            "timestamp_utc": _utc_now(),
            "session_id": session.get("session_id"),
            "status": session.get("status"),
            "objective": session.get("objective"),
            "tags": session.get("tags", []),
            "signal_count": len(session.get("signals", [])),
        }
        if metadata:
            event_payload["metadata"] = metadata
        try:
            self.event_emitter(event_payload)
        except Exception:
            return

    def _resolve_linked_tasks(self, task_ids: Any) -> list[dict[str, Any]]:
        normalized_task_ids = _normalize_linked_task_ids(
            task_ids if isinstance(task_ids, list) else None
        )
        if not normalized_task_ids:
            return []
        try:
            if hasattr(task_manager, "list_tasks_by_ids"):
                resolved = task_manager.list_tasks_by_ids(normalized_task_ids)
            else:
                catalog = task_manager.list_tasks()
                by_id = {
                    int(item.get("id")): item
                    for item in catalog
                    if isinstance(item, dict) and isinstance(item.get("id"), int)
                }
                resolved = [by_id[item] for item in normalized_task_ids if item in by_id]
        except Exception:
            return []
        return [json.loads(json.dumps(item)) for item in resolved if isinstance(item, dict)]

    def _normalize_session(self, session: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        migrated = False

        raw_session_id = session.get("session_id")
        session_id = raw_session_id if isinstance(raw_session_id, str) else ""
        if not session_id.strip():
            raise ValueError("session_id is required in stored session payload")
        if session_id != raw_session_id:
            session["session_id"] = session_id
            migrated = True

        raw_objective = session.get("objective")
        objective = raw_objective if isinstance(raw_objective, str) else ""
        if not objective.strip():
            raise ValueError(f"objective is required in stored session payload: {session_id}")
        if objective != raw_objective:
            session["objective"] = objective
            migrated = True

        raw_version = session.get("schema_version")
        if raw_version is None:
            session["schema_version"] = SESSION_SCHEMA_VERSION
            migrated = True
        elif raw_version != SESSION_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported session schema_version: {raw_version} for {session_id}"
            )

        constraints_present = "constraints" in session
        raw_constraints = session.get("constraints", [])
        normalized_constraints: list[str] = []
        if isinstance(raw_constraints, list):
            normalized_constraints = [
                item.strip()
                for item in raw_constraints
                if isinstance(item, str) and item.strip()
            ]
        if (not constraints_present) or normalized_constraints != raw_constraints:
            session["constraints"] = normalized_constraints
            migrated = True

        tags_present = "tags" in session
        raw_tags = session.get("tags", [])
        normalized_tags = _normalize_tags(raw_tags if isinstance(raw_tags, list) else None)
        if (not tags_present) or normalized_tags != raw_tags:
            session["tags"] = normalized_tags
            migrated = True

        linked_task_ids_present = "linked_task_ids" in session
        raw_linked_task_ids = session.get("linked_task_ids", [])
        normalized_linked_task_ids = _normalize_linked_task_ids(
            raw_linked_task_ids if isinstance(raw_linked_task_ids, list) else None
        )
        if (not linked_task_ids_present) or normalized_linked_task_ids != raw_linked_task_ids:
            session["linked_task_ids"] = normalized_linked_task_ids
            migrated = True

        planner_artifacts_present = "planner_artifacts" in session
        raw_planner_artifacts = session.get("planner_artifacts", [])
        normalized_planner_artifacts = _normalize_planner_artifacts(
            raw_planner_artifacts if isinstance(raw_planner_artifacts, list) else None
        )
        if (not planner_artifacts_present) or normalized_planner_artifacts != raw_planner_artifacts:
            session["planner_artifacts"] = normalized_planner_artifacts
            migrated = True

        horizon_present = "horizon_days" in session
        raw_horizon_days = session.get("horizon_days", 14)
        if isinstance(raw_horizon_days, int) and raw_horizon_days > 0:
            horizon_days = raw_horizon_days
        else:
            horizon_days = 14
        if (not horizon_present) or horizon_days != raw_horizon_days:
            session["horizon_days"] = horizon_days
            migrated = True

        risk_rubric_present = "risk_rubric" in session
        raw_risk_rubric = session.get("risk_rubric")
        rubric_data = raw_risk_rubric if isinstance(raw_risk_rubric, dict) else {}
        impact = _clamp(
            _coerce_float(rubric_data.get("impact"), DEFAULT_RISK_IMPACT),
            0.0,
            1.0,
        )
        uncertainty = _clamp(
            _coerce_float(rubric_data.get("uncertainty"), DEFAULT_RISK_UNCERTAINTY),
            0.0,
            1.0,
        )
        time_horizon = _normalize_time_horizon(rubric_data.get("time_horizon"), horizon_days)
        normalized_risk_rubric = {
            "impact": round(impact, 4),
            "uncertainty": round(uncertainty, 4),
            "time_horizon": time_horizon,
        }
        if (not risk_rubric_present) or normalized_risk_rubric != raw_risk_rubric:
            session["risk_rubric"] = normalized_risk_rubric
            migrated = True

        status_present = "status" in session
        raw_status = session.get("status", "active")
        status = raw_status if isinstance(raw_status, str) and raw_status.strip() else "active"
        if (not status_present) or status != raw_status:
            session["status"] = status
            migrated = True

        created_by_present = "created_by" in session
        raw_created_by = session.get("created_by")
        created_by = _normalize_provenance_text(raw_created_by, DEFAULT_CREATED_BY)
        if (not created_by_present) or created_by != raw_created_by:
            session["created_by"] = created_by
            migrated = True

        source_operation_present = "source_operation" in session
        raw_source_operation = session.get("source_operation")
        source_operation = _normalize_provenance_text(
            raw_source_operation, DEFAULT_SOURCE_OPERATION
        )
        if (not source_operation_present) or source_operation != raw_source_operation:
            session["source_operation"] = source_operation
            migrated = True

        policy_version_present = "policy_version" in session
        raw_policy_version = session.get("policy_version")
        policy_version = _normalize_provenance_text(
            raw_policy_version, DEFAULT_POLICY_VERSION
        )
        if (not policy_version_present) or policy_version != raw_policy_version:
            session["policy_version"] = policy_version
            migrated = True

        created_at_present = "created_at_utc" in session
        raw_created_at = session.get("created_at_utc")
        created_at = (
            raw_created_at
            if isinstance(raw_created_at, str) and raw_created_at
            else _utc_now()
        )
        if (not created_at_present) or created_at != raw_created_at:
            session["created_at_utc"] = created_at
            migrated = True

        updated_at_present = "updated_at_utc" in session
        raw_updated_at = session.get("updated_at_utc")
        updated_at = (
            raw_updated_at
            if isinstance(raw_updated_at, str) and raw_updated_at
            else created_at
        )
        if (not updated_at_present) or updated_at != raw_updated_at:
            session["updated_at_utc"] = updated_at
            migrated = True

        hypotheses = session.get("hypotheses")
        if not isinstance(hypotheses, list) or not hypotheses:
            session["hypotheses"] = self._seed_hypotheses(objective)
            migrated = True

        tasks = session.get("tasks")
        if not isinstance(tasks, list):
            session["tasks"] = self._seed_tasks(objective, session["hypotheses"])
            migrated = True

        signals = session.get("signals")
        if not isinstance(signals, list):
            session["signals"] = []
            migrated = True
        else:
            for signal in signals:
                if not isinstance(signal, dict):
                    continue
                claim_raw = signal.get("claim")
                claim_hash_raw = signal.get("claim_hash")
                claim_hash = (
                    claim_hash_raw
                    if isinstance(claim_hash_raw, str) and claim_hash_raw
                    else stable_claim_hash(claim_raw if isinstance(claim_raw, str) else "")
                )
                if claim_hash != claim_hash_raw:
                    signal["claim_hash"] = claim_hash
                    migrated = True
                duplicate_count_raw = signal.get("duplicate_count", 0)
                if isinstance(duplicate_count_raw, int) and duplicate_count_raw >= 0:
                    duplicate_count = duplicate_count_raw
                else:
                    duplicate_count = 0
                if duplicate_count != duplicate_count_raw:
                    signal["duplicate_count"] = duplicate_count
                    migrated = True

        foresight = session.get("foresight")
        if not isinstance(foresight, list):
            session["foresight"] = self._foresight_from_hypotheses(session["hypotheses"])
            migrated = True

        return session, migrated

    def _seed_hypotheses(self, objective: str) -> list[dict[str, Any]]:
        return [
            {
                "id": "h_execution_success",
                "statement": (
                    "The objective can be executed with current local Merlin/AAS "
                    "capabilities and bounded integration effort."
                ),
                "probability": 0.58,
                "base_probability": 0.58,
                "confidence": 0.32,
                "supporting_signals": 0,
                "contradicting_signals": 0,
            },
            {
                "id": "h_dependency_risk",
                "statement": (
                    "External dependency and integration gaps will remain manageable "
                    "without blocking critical milestones."
                ),
                "probability": 0.52,
                "base_probability": 0.52,
                "confidence": 0.28,
                "supporting_signals": 0,
                "contradicting_signals": 0,
            },
            {
                "id": "h_timeline_fit",
                "statement": (
                    f"The objective '{objective}' can ship within the active horizon "
                    "if sequencing and fallback controls stay enforced."
                ),
                "probability": 0.55,
                "base_probability": 0.55,
                "confidence": 0.30,
                "supporting_signals": 0,
                "contradicting_signals": 0,
            },
        ]

    def _seed_tasks(
        self, objective: str, hypotheses: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        return [
            {
                "task_id": "t_baseline",
                "title": "Establish baseline and boundary assumptions",
                "status": "pending",
                "priority": "high",
                "linked_hypothesis": hypotheses[0]["id"],
            },
            {
                "task_id": "t_adversarial",
                "title": "Run adversarial review for the highest-risk hypothesis",
                "status": "pending",
                "priority": "high",
                "linked_hypothesis": hypotheses[1]["id"],
            },
            {
                "task_id": "t_decision_packet",
                "title": f"Prepare decision packet for: {objective}",
                "status": "pending",
                "priority": "medium",
                "linked_hypothesis": hypotheses[2]["id"],
            },
        ]

    def _update_hypotheses(
        self, session: dict[str, Any], *, now_utc: datetime | None = None
    ) -> None:
        now = now_utc or datetime.now(timezone.utc)
        signals = session.get("signals", [])
        hypotheses = session.get("hypotheses", [])
        for hyp in hypotheses:
            hyp_id = hyp["id"]
            posterior = float(hyp.get("base_probability", hyp.get("probability", 0.5)))
            supporting = 0
            contradicting = 0

            for signal in signals:
                supports = signal.get("supports", [])
                contradicts = signal.get("contradicts", [])
                if not isinstance(supports, list):
                    supports = []
                if not isinstance(contradicts, list):
                    contradicts = []

                confidence = _clamp(float(signal.get("confidence", 0.5)), 0.0, 1.0)
                novelty = _clamp(float(signal.get("novelty", 0.5)), 0.0, 1.0)
                risk = _clamp(float(signal.get("risk", 0.0)), 0.0, 1.0)
                age_days = _signal_age_days(signal, now_utc=now)
                decay_weight = _memory_decay_weight(age_days)
                reinforcement_multiplier = _memory_reinforcement_multiplier(signal)
                strength = (
                    confidence
                    * (0.6 + (0.4 * novelty))
                    * (1.0 - risk)
                    * decay_weight
                    * reinforcement_multiplier
                )
                signal["memory_age_days"] = round(age_days, 4)
                signal["memory_decay_weight"] = round(decay_weight, 4)
                signal["memory_reinforcement_multiplier"] = round(
                    reinforcement_multiplier, 4
                )
                signal["memory_effective_strength"] = round(_clamp(strength, 0.0, 1.0), 4)

                if hyp_id in supports:
                    posterior += 0.35 * strength
                    supporting += 1
                if hyp_id in contradicts:
                    posterior -= 0.40 * strength
                    contradicting += 1

            posterior = _clamp(posterior, 0.01, 0.99)
            evidence_count = supporting + contradicting
            confidence_score = _clamp(
                0.25 + (evidence_count * 0.15) + (abs(posterior - 0.5) * 0.5), 0.0, 0.99
            )
            hyp["probability"] = round(posterior, 4)
            hyp["confidence"] = round(confidence_score, 4)
            hyp["supporting_signals"] = supporting
            hyp["contradicting_signals"] = contradicting

    def _foresight_from_hypotheses(
        self, hypotheses: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if not hypotheses:
            return []

        probabilities = [
            _clamp(float(item.get("probability", 0.5)), 0.0, 1.0) for item in hypotheses
        ]
        confidences = [
            _clamp(float(item.get("confidence", 0.5)), 0.0, 1.0) for item in hypotheses
        ]
        avg_probability = sum(probabilities) / len(probabilities)
        avg_confidence = sum(confidences) / len(confidences)
        uncertainty = sum(1.0 - abs((prob * 2.0) - 1.0) for prob in probabilities) / len(
            probabilities
        )

        best = _clamp(avg_probability + (0.18 * avg_confidence), 0.01, 0.99)
        base = _clamp(avg_probability, 0.01, 0.99)
        worst = _clamp(avg_probability - (0.24 * (0.5 + uncertainty)), 0.01, 0.99)

        return [
            {
                "scenario": "best_case",
                "probability": round(best, 4),
                "trigger": "supporting evidence accumulates with low contradiction rate",
            },
            {
                "scenario": "base_case",
                "probability": round(base, 4),
                "trigger": "current evidence trend holds without major external shocks",
            },
            {
                "scenario": "worst_case",
                "probability": round(worst, 4),
                "trigger": "dependency risk and contradiction signals outpace execution gains",
            },
        ]

    def _summarize_signal_conflicts(self, signals: list[dict[str, Any]]) -> dict[str, Any]:
        contradictory_signal_count = 0
        conflict_count = 0
        conflict_by_hypothesis: dict[str, int] = {}

        for signal in signals:
            if not isinstance(signal, dict):
                continue
            contradicts = signal.get("contradicts", [])
            if not isinstance(contradicts, list):
                continue
            normalized = [
                item.strip()
                for item in contradicts
                if isinstance(item, str) and item.strip()
            ]
            if not normalized:
                continue
            contradictory_signal_count += 1
            for hypothesis_id in normalized:
                conflict_count += 1
                conflict_by_hypothesis[hypothesis_id] = (
                    conflict_by_hypothesis.get(hypothesis_id, 0) + 1
                )

        conflict_hypotheses = [
            {"hypothesis_id": hypothesis_id, "conflict_count": count}
            for hypothesis_id, count in sorted(
                conflict_by_hypothesis.items(),
                key=lambda item: (-item[1], item[0]),
            )
        ]
        return {
            "contradicting_signal_count": contradictory_signal_count,
            "conflict_count": conflict_count,
            "conflict_hypotheses": conflict_hypotheses,
        }

    def _build_causal_chains(
        self,
        signals: list[dict[str, Any]],
        hypotheses: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        normalized_signals = [item for item in signals if isinstance(item, dict)]
        chains: list[dict[str, Any]] = []
        for hypothesis in hypotheses:
            if not isinstance(hypothesis, dict):
                continue
            hypothesis_id = str(hypothesis.get("id", "")).strip()
            if not hypothesis_id:
                continue

            supporting_evidence: list[dict[str, Any]] = []
            contradicting_evidence: list[dict[str, Any]] = []
            for signal in normalized_signals:
                supports = signal.get("supports", [])
                contradicts = signal.get("contradicts", [])
                if not isinstance(supports, list):
                    supports = []
                if not isinstance(contradicts, list):
                    contradicts = []

                evidence = {
                    "signal_id": signal.get("signal_id"),
                    "source": signal.get("source"),
                    "claim": signal.get("claim"),
                    "claim_hash": signal.get("claim_hash"),
                    "confidence": signal.get("confidence"),
                    "timestamp_utc": signal.get("timestamp_utc"),
                }
                if hypothesis_id in supports:
                    supporting_evidence.append(evidence)
                if hypothesis_id in contradicts:
                    contradicting_evidence.append(evidence)

            chains.append(
                {
                    "hypothesis_id": hypothesis_id,
                    "hypothesis_statement": hypothesis.get("statement"),
                    "supporting_count": len(supporting_evidence),
                    "contradicting_count": len(contradicting_evidence),
                    "supporting_evidence": supporting_evidence,
                    "contradicting_evidence": contradicting_evidence,
                }
            )

        return chains

    def _next_actions_for_session(self, session: dict[str, Any]) -> list[str]:
        hypotheses = list(session.get("hypotheses", []))
        if not hypotheses:
            return ["Define initial hypotheses before proceeding."]

        signals = list(session.get("signals", []))
        if not signals:
            return [
                "Collect initial evidence signal for each hypothesis.",
                "Run adversarial challenge against highest-risk assumption.",
                "Build first decision brief with explicit go/no-go thresholds.",
            ]

        by_uncertainty = sorted(
            hypotheses,
            key=lambda hyp: abs(float(hyp.get("probability", 0.5)) - 0.5),
        )

        actions: list[str] = []
        for hyp in by_uncertainty[:2]:
            actions.append(
                f"Collect targeted evidence to resolve uncertainty on {hyp['id']}."
            )

        contradicting_total = sum(
            int(hyp.get("contradicting_signals", 0)) for hyp in hypotheses
        )
        supporting_total = sum(int(hyp.get("supporting_signals", 0)) for hyp in hypotheses)
        if contradicting_total >= supporting_total:
            actions.append("Trigger fallback plan review before committing new execution.")
        else:
            actions.append("Prepare execution checkpoint with explicit probability gates.")

        return actions[:3]
