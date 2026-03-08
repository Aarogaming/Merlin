from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from merlin_research_manager import (
    BRIEF_TEMPLATE_ID,
    BRIEF_TEMPLATE_VERSION,
    DEFAULT_CREATED_BY,
    DEFAULT_POLICY_VERSION,
    DEFAULT_RISK_IMPACT,
    DEFAULT_RISK_UNCERTAINTY,
    DEFAULT_SOURCE_OPERATION,
    RESEARCH_SESSION_EVENT_SCHEMA_NAME,
    RESEARCH_SESSION_EVENT_SCHEMA_VERSION,
    ResearchManager,
    SESSION_SNAPSHOT_SCHEMA_NAME,
    SESSION_SNAPSHOT_SCHEMA_VERSION,
    SESSION_SCHEMA_VERSION,
    calibrate_signal_confidence,
)

pytestmark = pytest.mark.critical_coverage


def _get_hypothesis(session: dict, hypothesis_id: str) -> dict:
    for hypothesis in session["hypotheses"]:
        if hypothesis["id"] == hypothesis_id:
            return hypothesis
    raise AssertionError(f"missing hypothesis: {hypothesis_id}")


def test_create_session_persists_state(tmp_path: Path):
    manager = ResearchManager(tmp_path, allow_writes=True)
    session = manager.create_session(
        objective="Create a local research command center",
        constraints=["repo-local-only", "fallback-safe"],
        horizon_days=7,
    )

    session_id = session["session_id"]
    session_path = tmp_path / "sessions" / f"{session_id}.json"
    assert session_path.exists()
    assert session["objective"] == "Create a local research command center"
    assert session["constraints"] == ["repo-local-only", "fallback-safe"]
    assert session["horizon_days"] == 7
    assert len(session["hypotheses"]) == 3
    assert len(session["tasks"]) == 3
    assert session["created_by"] == DEFAULT_CREATED_BY
    assert session["source_operation"] == DEFAULT_SOURCE_OPERATION
    assert session["policy_version"] == DEFAULT_POLICY_VERSION
    assert session["risk_rubric"]["impact"] == DEFAULT_RISK_IMPACT
    assert session["risk_rubric"]["uncertainty"] == DEFAULT_RISK_UNCERTAINTY
    assert session["risk_rubric"]["time_horizon"] == "near_term"

    loaded = manager.get_session(session_id)
    assert loaded["session_id"] == session_id
    assert loaded["status"] == "active"


def test_session_tags_persist_and_filter_list_sessions(tmp_path: Path):
    manager = ResearchManager(tmp_path, allow_writes=True)
    tagged = manager.create_session(
        objective="Planner reliability deep dive",
        tags=["CP2", "planner", "cp2"],
    )
    other = manager.create_session(
        objective="Voice model latency notes",
        tags=["voice"],
    )

    assert tagged["tags"] == ["cp2", "planner"]
    assert other["tags"] == ["voice"]

    tagged_only = manager.list_sessions(tag="CP2")
    assert len(tagged_only) == 1
    assert tagged_only[0]["session_id"] == tagged["session_id"]

    topic_filtered = manager.list_sessions(topic_query="latency")
    assert len(topic_filtered) == 1
    assert topic_filtered[0]["session_id"] == other["session_id"]


def test_list_sessions_page_supports_cursor_pagination(tmp_path: Path):
    manager = ResearchManager(tmp_path, allow_writes=True)
    one = manager.create_session("Session one")
    two = manager.create_session("Session two")

    first_page = manager.list_sessions_page(limit=1)
    assert len(first_page["sessions"]) == 1
    assert first_page["sessions"][0]["session_id"] == two["session_id"]
    assert first_page["next_cursor"] == "1"

    second_page = manager.list_sessions_page(limit=1, cursor=first_page["next_cursor"])
    assert len(second_page["sessions"]) == 1
    assert second_page["sessions"][0]["session_id"] == one["session_id"]
    assert second_page["next_cursor"] is None

    with pytest.raises(ValueError, match="cursor must be a non-negative integer string"):
        manager.list_sessions_page(limit=1, cursor="-1")


def test_search_sessions_filters_by_objective_keyword(tmp_path: Path):
    manager = ResearchManager(tmp_path, allow_writes=True)
    manager.create_session("Planner reliability investigation")
    voice = manager.create_session("Voice latency stabilization")

    result = manager.search_sessions("voice", limit=10)
    assert len(result["sessions"]) == 1
    assert result["sessions"][0]["session_id"] == voice["session_id"]

    with pytest.raises(ValueError, match="query must be non-empty"):
        manager.search_sessions("   ")


def test_create_session_persists_custom_provenance(tmp_path: Path):
    manager = ResearchManager(tmp_path, allow_writes=True)
    session = manager.create_session(
        objective="Capture provenance fields on session create",
        created_by="AaroneousAutomationSuite/Hub:hub_orchestrator",
        source_operation="merlin.research.manager.session.create",
        policy_version="operation-dispatch-v2",
    )
    loaded = manager.get_session(session["session_id"])

    assert loaded["created_by"] == "AaroneousAutomationSuite/Hub:hub_orchestrator"
    assert loaded["source_operation"] == "merlin.research.manager.session.create"
    assert loaded["policy_version"] == "operation-dispatch-v2"


def test_create_session_supports_custom_risk_rubric(tmp_path: Path):
    manager = ResearchManager(tmp_path, allow_writes=True)
    session = manager.create_session(
        objective="Risk rubric customization",
        horizon_days=90,
        impact=0.8,
        uncertainty=0.3,
        time_horizon="long_term",
    )

    assert session["risk_rubric"] == {
        "impact": 0.8,
        "uncertainty": 0.3,
        "time_horizon": "long_term",
    }


def test_create_session_supports_traceability_links(monkeypatch, tmp_path: Path):
    manager = ResearchManager(tmp_path, allow_writes=True)
    session = manager.create_session(
        objective="Traceability links for planner readiness",
        linked_task_ids=[3, 3, -1, 7],
        planner_artifacts=[
            "docs/research/CP_PACKET.md",
            "docs/research/CP_PACKET.md",
            " docs/planning/PLAN.md ",
        ],
    )

    assert session["linked_task_ids"] == [3, 7]
    assert session["planner_artifacts"] == [
        "docs/research/CP_PACKET.md",
        "docs/planning/PLAN.md",
    ]

    monkeypatch.setattr(
        "merlin_research_manager.task_manager.list_tasks_by_ids",
        lambda ids: [{"id": 3, "title": "Planner reliability task"}] if 3 in ids else [],
    )
    brief = manager.get_brief(session["session_id"])
    assert brief["linked_task_ids"] == [3, 7]
    assert brief["planner_artifacts"] == [
        "docs/research/CP_PACKET.md",
        "docs/planning/PLAN.md",
    ]
    assert brief["linked_tasks"] == [{"id": 3, "title": "Planner reliability task"}]


def test_ingest_planner_fallback_telemetry_adds_structured_signal(tmp_path: Path):
    manager = ResearchManager(tmp_path, allow_writes=True)
    session = manager.create_session("Ingest fallback telemetry into research session")

    ingest_result = manager.ingest_planner_fallback_telemetry(
        session_id=session["session_id"],
        telemetry={
            "fallback_reason_code": "dms_timeout",
            "fallback_stage": "dms_primary",
            "fallback_detail": "connect timeout",
            "selected_model": "control",
            "fallback_retryable": True,
        },
        source="assistant.chat.request",
    )

    assert ingest_result["ingested"] is True
    assert ingest_result["reason_code"] == "dms_timeout"
    stored = manager.get_session(session["session_id"])
    assert len(stored["signals"]) == 1
    signal = stored["signals"][0]
    assert signal["source"] == "assistant.chat.request:dms_timeout"
    assert "dms_timeout" in signal["claim"]
    assert "h_execution_success" in signal["contradicts"]


def test_ingest_planner_fallback_telemetry_without_fallback_supports_execution(tmp_path: Path):
    manager = ResearchManager(tmp_path, allow_writes=True)
    session = manager.create_session("Track no-fallback planner path")

    result = manager.ingest_planner_fallback_telemetry(
        session_id=session["session_id"],
        telemetry={
            "fallback_reason_code": "none",
            "selected_model": "dms",
            "fallback_stage": "none",
        },
        source="assistant.chat.request",
    )

    assert result["ingested"] is True
    stored = manager.get_session(session["session_id"])
    assert len(stored["signals"]) == 1
    assert "h_execution_success" in stored["signals"][0]["supports"]


def test_add_signal_updates_hypothesis_probability(tmp_path: Path):
    manager = ResearchManager(tmp_path, allow_writes=True)
    session = manager.create_session("Harden local orchestrator reliability")
    session_id = session["session_id"]

    update = manager.add_signal(
        session_id=session_id,
        source="routing-smoke",
        claim="Fallback telemetry and schema checks are passing consistently.",
        confidence=0.90,
        novelty=0.75,
        risk=0.10,
        supports=["h_execution_success"],
    )

    assert update["signal"]["source"] == "routing-smoke"
    assert "next_actions" in update
    assert len(update["next_actions"]) > 0

    loaded = manager.get_session(session_id)
    hypothesis = _get_hypothesis(loaded, "h_execution_success")
    assert hypothesis["supporting_signals"] == 1
    assert hypothesis["contradicting_signals"] == 0
    assert hypothesis["probability"] > hypothesis["base_probability"]


def test_calibrate_signal_confidence_accounts_for_risk_and_novelty():
    low_risk = calibrate_signal_confidence(0.8, novelty=0.5, risk=0.1)
    high_risk = calibrate_signal_confidence(0.8, novelty=0.5, risk=0.9)
    assert high_risk < low_risk

    low_novelty = calibrate_signal_confidence(0.7, novelty=0.1, risk=0.2)
    high_novelty = calibrate_signal_confidence(0.7, novelty=0.9, risk=0.2)
    assert high_novelty > low_novelty

    assert calibrate_signal_confidence(1.5, novelty=1.0, risk=0.0) == 1.0
    assert calibrate_signal_confidence(-0.5, novelty=0.0, risk=1.0) == 0.0


def test_add_signal_stores_raw_and_calibrated_confidence(tmp_path: Path):
    manager = ResearchManager(tmp_path, allow_writes=True)
    session = manager.create_session("Calibrate confidence in stored signal")

    update = manager.add_signal(
        session_id=session["session_id"],
        source="calibration-check",
        claim="High-risk evidence should be confidence-calibrated down.",
        confidence=0.9,
        novelty=0.4,
        risk=0.9,
        supports=["h_execution_success"],
    )

    signal = update["signal"]
    assert signal["confidence_raw"] == 0.9
    assert signal["confidence"] < signal["confidence_raw"]


def test_add_signal_deduplicates_by_stable_claim_hash(tmp_path: Path):
    manager = ResearchManager(tmp_path, allow_writes=True)
    session = manager.create_session("Deduplicate noisy repeated claim evidence")
    session_id = session["session_id"]

    first = manager.add_signal(
        session_id=session_id,
        source="source-a",
        claim="Fallback telemetry is passing",
        confidence=0.85,
        novelty=0.6,
        risk=0.2,
        supports=["h_execution_success"],
    )
    second = manager.add_signal(
        session_id=session_id,
        source="source-b",
        claim="  fallback   telemetry   is PASSING ",
        confidence=0.9,
        novelty=0.6,
        risk=0.2,
        supports=["h_execution_success"],
    )

    assert first.get("deduplicated") is None
    assert second["deduplicated"] is True
    assert second["dedup_reason"] == "duplicate_claim_hash"
    assert second["signal"]["duplicate_count"] == 1
    assert second["signal"]["last_duplicate_source"] == "source-b"

    loaded = manager.get_session(session_id)
    assert len(loaded["signals"]) == 1
    assert loaded["signals"][0]["duplicate_count"] == 1

    hypothesis = _get_hypothesis(loaded, "h_execution_success")
    assert hypothesis["supporting_signals"] == 1


def test_duplicate_signal_reinforcement_increases_effective_memory_strength(tmp_path: Path):
    manager = ResearchManager(tmp_path, allow_writes=True)
    session = manager.create_session("Reinforce confidence with corroborated evidence")
    session_id = session["session_id"]

    manager.add_signal(
        session_id=session_id,
        source="source-a",
        claim="Corroborated execution signal",
        confidence=0.82,
        novelty=0.6,
        risk=0.1,
        supports=["h_execution_success"],
    )
    baseline = _get_hypothesis(manager.get_session(session_id), "h_execution_success")[
        "probability"
    ]

    result = manager.add_signal(
        session_id=session_id,
        source="source-b",
        claim="corroborated execution signal",
        confidence=0.85,
        novelty=0.6,
        risk=0.1,
        supports=["h_execution_success"],
    )

    assert result["deduplicated"] is True
    loaded = manager.get_session(session_id)
    reinforced = _get_hypothesis(loaded, "h_execution_success")["probability"]
    assert reinforced > baseline
    signal = loaded["signals"][0]
    assert signal["memory_reinforcement_multiplier"] > 1.0
    assert signal["memory_effective_strength"] > 0.0


def test_memory_confidence_decay_reduces_influence_of_stale_signal(tmp_path: Path):
    manager = ResearchManager(tmp_path, allow_writes=True)
    session = manager.create_session("Decay stale confidence signals over time")
    session_id = session["session_id"]

    manager.add_signal(
        session_id=session_id,
        source="fresh-signal",
        claim="Fresh signal should have stronger influence",
        confidence=0.9,
        novelty=0.7,
        risk=0.1,
        supports=["h_execution_success"],
    )
    fresh_brief = manager.get_brief(session_id)
    fresh_probability = _get_hypothesis(
        {"hypotheses": fresh_brief["hypotheses"]}, "h_execution_success"
    )["probability"]

    loaded = manager.get_session(session_id)
    stale_timestamp = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
    loaded["signals"][0]["timestamp_utc"] = stale_timestamp
    manager._write_session(loaded)

    decayed_brief = manager.get_brief(session_id)
    decayed_probability = _get_hypothesis(
        {"hypotheses": decayed_brief["hypotheses"]}, "h_execution_success"
    )["probability"]

    assert decayed_probability < fresh_probability


def test_add_contradicting_signal_decreases_probability(tmp_path: Path):
    manager = ResearchManager(tmp_path, allow_writes=True)
    session = manager.create_session("Ship a bounded autonomy pilot")
    session_id = session["session_id"]

    manager.add_signal(
        session_id=session_id,
        source="integration-probe",
        claim="Hub proto package missing in this runtime.",
        confidence=0.85,
        novelty=0.60,
        risk=0.25,
        contradicts=["h_dependency_risk"],
    )

    loaded = manager.get_session(session_id)
    dependency_hypothesis = _get_hypothesis(loaded, "h_dependency_risk")
    assert dependency_hypothesis["contradicting_signals"] == 1
    assert dependency_hypothesis["probability"] < dependency_hypothesis["base_probability"]


def test_brief_and_list_sessions_surface_forsight_and_ordering(tmp_path: Path):
    manager = ResearchManager(tmp_path, allow_writes=True)
    first = manager.create_session("First objective")
    second = manager.create_session("Second objective")

    brief = manager.get_brief(second["session_id"])
    assert brief["session_id"] == second["session_id"]
    assert brief["brief_template_id"] == BRIEF_TEMPLATE_ID
    assert brief["brief_template_version"] == BRIEF_TEMPLATE_VERSION
    assert brief["contradicting_signal_count"] == 0
    assert brief["conflict_count"] == 0
    assert brief["conflict_hypotheses"] == []
    assert len(brief["causal_chains"]) == 3
    assert "risk_rubric" in brief
    assert len(brief["foresight"]) == 3
    assert {item["scenario"] for item in brief["foresight"]} == {
        "best_case",
        "base_case",
        "worst_case",
    }

    sessions = manager.list_sessions()
    assert sessions[0]["session_id"] == second["session_id"]
    assert sessions[1]["session_id"] == first["session_id"]


def test_brief_exposes_conflict_counts_for_contradicting_signals(tmp_path: Path):
    manager = ResearchManager(tmp_path, allow_writes=True)
    session = manager.create_session("Track contradictory signal coverage in briefs")
    session_id = session["session_id"]

    manager.add_signal(
        session_id=session_id,
        source="conflict-check-a",
        claim="Dependency latency blocks timeline",
        confidence=0.8,
        contradicts=["h_timeline_fit"],
    )
    manager.add_signal(
        session_id=session_id,
        source="conflict-check-b",
        claim="Integration burden exceeds current window",
        confidence=0.75,
        contradicts=["h_timeline_fit", "h_dependency_risk"],
    )

    brief = manager.get_brief(session_id)
    assert brief["contradicting_signal_count"] == 2
    assert brief["conflict_count"] == 3
    assert brief["conflict_hypotheses"][0] == {
        "hypothesis_id": "h_timeline_fit",
        "conflict_count": 2,
    }


def test_brief_exposes_causal_chains_with_evidence_links(tmp_path: Path):
    manager = ResearchManager(tmp_path, allow_writes=True)
    session = manager.create_session("Render causal chain evidence for hypotheses")
    session_id = session["session_id"]

    manager.add_signal(
        session_id=session_id,
        source="causal-source-support",
        claim="Local fallback telemetry remains stable",
        confidence=0.86,
        supports=["h_execution_success"],
    )
    manager.add_signal(
        session_id=session_id,
        source="causal-source-contradict",
        claim="Dependency fragility increases execution risk",
        confidence=0.8,
        contradicts=["h_execution_success"],
    )

    brief = manager.get_brief(session_id)
    target_chain = next(
        chain for chain in brief["causal_chains"] if chain["hypothesis_id"] == "h_execution_success"
    )

    assert target_chain["supporting_count"] == 1
    assert target_chain["contradicting_count"] == 1
    assert target_chain["supporting_evidence"][0]["source"] == "causal-source-support"
    assert (
        target_chain["contradicting_evidence"][0]["source"]
        == "causal-source-contradict"
    )


def test_get_session_missing_raises(tmp_path: Path):
    manager = ResearchManager(tmp_path, allow_writes=True)
    with pytest.raises(FileNotFoundError):
        manager.get_session("missing-session")


def test_export_and_import_session_snapshot_round_trip(tmp_path: Path):
    source_manager = ResearchManager(tmp_path / "source", allow_writes=True)
    created = source_manager.create_session("Export/import snapshot flow")
    source_manager.add_signal(
        session_id=created["session_id"],
        source="snapshot-source",
        claim="Snapshot includes signal evidence",
        confidence=0.88,
        supports=["h_execution_success"],
    )
    snapshot = source_manager.export_session_snapshot(created["session_id"])

    assert snapshot["schema_name"] == SESSION_SNAPSHOT_SCHEMA_NAME
    assert snapshot["schema_version"] == SESSION_SNAPSHOT_SCHEMA_VERSION
    assert snapshot["session"]["session_id"] == created["session_id"]

    target_manager = ResearchManager(tmp_path / "target", allow_writes=True)
    imported = target_manager.import_session_snapshot(snapshot)
    loaded = target_manager.get_session(imported["session_id"])

    assert loaded["objective"] == created["objective"]
    assert len(loaded["signals"]) == 1
    assert loaded["signals"][0]["source"] == "snapshot-source"


def test_import_session_snapshot_requires_overwrite_for_existing_session(tmp_path: Path):
    manager = ResearchManager(tmp_path, allow_writes=True)
    created = manager.create_session("Overwrite gate check")
    snapshot = manager.export_session_snapshot(created["session_id"])

    with pytest.raises(ValueError, match="already exists"):
        manager.import_session_snapshot(snapshot)

    imported = manager.import_session_snapshot(snapshot, overwrite=True)
    assert imported["session_id"] == created["session_id"]


def test_research_manager_emits_session_events_for_updates(tmp_path: Path):
    captured_events: list[dict] = []

    manager = ResearchManager(
        tmp_path,
        allow_writes=True,
        event_emitter=lambda payload: captured_events.append(payload),
    )
    session = manager.create_session(
        objective="Emit session lifecycle events",
        tags=["events"],
    )
    manager.add_signal(
        session_id=session["session_id"],
        source="event-source",
        claim="Unique evidence for emitted event",
        confidence=0.85,
        supports=["h_execution_success"],
    )
    manager.add_signal(
        session_id=session["session_id"],
        source="event-source-dup",
        claim="Unique evidence for emitted event",
        confidence=0.9,
        supports=["h_execution_success"],
    )

    event_types = [event["event_type"] for event in captured_events]
    assert event_types == [
        "session.created",
        "session.signal_added",
        "session.signal_deduplicated",
    ]
    for event in captured_events:
        assert event["schema_name"] == RESEARCH_SESSION_EVENT_SCHEMA_NAME
        assert event["schema_version"] == RESEARCH_SESSION_EVENT_SCHEMA_VERSION
        assert event["session_id"] == session["session_id"]


def test_brief_queue_disabled_raises_runtime_error(tmp_path: Path):
    manager = ResearchManager(tmp_path, allow_writes=True, brief_queue_enabled=False)
    session = manager.create_session("Queue disabled test")

    with pytest.raises(RuntimeError, match="disabled"):
        manager.enqueue_brief_generation(session["session_id"])


def test_brief_queue_enqueue_and_process_updates_task_status(monkeypatch, tmp_path: Path):
    recorded_tasks: list[dict] = []
    status_updates: list[tuple[int, str]] = []

    class FakeTaskManager:
        def add_task(self, title, description, priority="Medium"):
            task_id = len(recorded_tasks) + 1
            task = {
                "id": task_id,
                "title": title,
                "description": description,
                "priority": priority,
            }
            recorded_tasks.append(task)
            return task

        def update_task_status(self, task_id, status):
            status_updates.append((task_id, status))
            return True

    monkeypatch.setattr("merlin_research_manager.task_manager", FakeTaskManager())

    manager = ResearchManager(tmp_path, allow_writes=True, brief_queue_enabled=True)
    session = manager.create_session("Queued brief generation")
    job = manager.enqueue_brief_generation(session["session_id"])

    assert job["status"] == "queued"
    assert isinstance(job["task_id"], int)

    processed = manager.process_brief_queue(max_jobs=1)
    assert processed == 1

    completed = manager.get_brief_job(job["job_id"])
    assert completed["status"] == "completed"
    assert completed["result"]["brief"]["session_id"] == session["session_id"]
    assert status_updates[-1] == (job["task_id"], "Completed")


def test_create_session_read_only_raises(tmp_path: Path):
    manager = ResearchManager(tmp_path, allow_writes=False)
    with pytest.raises(PermissionError):
        manager.create_session("Should not be allowed")


def test_create_session_read_only_emits_audit_rejection(monkeypatch, tmp_path: Path):
    captured: list[dict] = []

    def _capture(component, operation, details=None, request_id=None):
        captured.append(
            {
                "component": component,
                "operation": operation,
                "details": details,
                "request_id": request_id,
            }
        )

    monkeypatch.setattr("merlin_research_manager.log_read_only_rejection", _capture)
    manager = ResearchManager(tmp_path, allow_writes=False)

    with pytest.raises(PermissionError):
        manager.create_session("Audit read-only create path")

    assert captured
    event = captured[0]
    assert event["component"] == "merlin_research_manager"
    assert event["operation"] == "merlin.research.manager.session.create"


def test_add_signal_read_only_raises(tmp_path: Path):
    manager = ResearchManager(tmp_path, allow_writes=True)
    session = manager.create_session("Prepare research workflow")
    manager.allow_writes = False

    with pytest.raises(PermissionError):
        manager.add_signal(
            session_id=session["session_id"],
            source="fixture",
            claim="should fail in read-only mode",
            confidence=0.8,
        )


def test_add_signal_read_only_emits_audit_rejection(monkeypatch, tmp_path: Path):
    captured: list[dict] = []

    def _capture(component, operation, details=None, request_id=None):
        captured.append(
            {
                "component": component,
                "operation": operation,
                "details": details,
                "request_id": request_id,
            }
        )

    monkeypatch.setattr("merlin_research_manager.log_read_only_rejection", _capture)
    manager = ResearchManager(tmp_path, allow_writes=True)
    session = manager.create_session("Prepare audit check for read-only signal path")
    manager.allow_writes = False

    with pytest.raises(PermissionError):
        manager.add_signal(
            session_id=session["session_id"],
            source="audit-read-only-check",
            claim="should fail in read-only mode",
            confidence=0.8,
        )

    assert captured
    event = captured[0]
    assert event["component"] == "merlin_research_manager"
    assert event["operation"] == "merlin.research.manager.session.signal.add"
    assert event["details"]["session_id"] == session["session_id"]


def test_get_session_migrates_legacy_payload(tmp_path: Path):
    manager = ResearchManager(tmp_path, allow_writes=True)
    session_id = "legacy-session"
    legacy_path = tmp_path / "sessions" / f"{session_id}.json"
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_text(
        json.dumps(
            {
                "session_id": session_id,
                "objective": "Legacy objective format",
            }
        ),
        encoding="utf-8",
    )

    session = manager.get_session(session_id)
    assert session["schema_version"] == SESSION_SCHEMA_VERSION
    assert session["objective"] == "Legacy objective format"
    assert isinstance(session["constraints"], list)
    assert isinstance(session["tags"], list)
    assert isinstance(session["linked_task_ids"], list)
    assert isinstance(session["planner_artifacts"], list)
    assert isinstance(session["risk_rubric"], dict)
    assert isinstance(session["hypotheses"], list)
    assert isinstance(session["tasks"], list)
    assert isinstance(session["foresight"], list)
    assert session["created_by"] == DEFAULT_CREATED_BY
    assert session["source_operation"] == DEFAULT_SOURCE_OPERATION
    assert session["policy_version"] == DEFAULT_POLICY_VERSION

    stored = json.loads(legacy_path.read_text(encoding="utf-8"))
    assert stored["schema_version"] == SESSION_SCHEMA_VERSION
    assert stored["created_by"] == DEFAULT_CREATED_BY
    assert stored["source_operation"] == DEFAULT_SOURCE_OPERATION
    assert stored["policy_version"] == DEFAULT_POLICY_VERSION
    assert isinstance(stored["linked_task_ids"], list)
    assert isinstance(stored["planner_artifacts"], list)
    assert stored["risk_rubric"]["impact"] == DEFAULT_RISK_IMPACT
    assert stored["risk_rubric"]["uncertainty"] == DEFAULT_RISK_UNCERTAINTY


def test_get_session_rejects_unsupported_schema_version(tmp_path: Path):
    manager = ResearchManager(tmp_path, allow_writes=True)
    session_id = "future-session"
    session_path = tmp_path / "sessions" / f"{session_id}.json"
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text(
        json.dumps(
            {
                "schema_version": "9.9.9",
                "session_id": session_id,
                "objective": "Future format",
                "hypotheses": [],
                "signals": [],
                "tasks": [],
                "foresight": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unsupported session schema_version"):
        manager.get_session(session_id)


def test_read_only_env_var_blocks_writes(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("MERLIN_RESEARCH_MANAGER_READ_ONLY", "1")
    manager = ResearchManager(tmp_path)

    with pytest.raises(PermissionError):
        manager.create_session("blocked by env flag")


def test_allow_writes_override_ignores_read_only_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("MERLIN_RESEARCH_MANAGER_READ_ONLY", "1")
    manager = ResearchManager(tmp_path, allow_writes=True)
    session = manager.create_session("override env read-only")

    assert session["objective"] == "override env read-only"


def test_get_session_invalid_session_id_raises(tmp_path: Path):
    manager = ResearchManager(tmp_path, allow_writes=True)
    with pytest.raises(ValueError, match="session_id contains invalid characters"):
        manager.get_session("../bad")


def test_expired_session_is_archived_by_ttl_policy(tmp_path: Path):
    manager = ResearchManager(
        tmp_path,
        allow_writes=True,
        session_ttl_days=1,
        auto_archive=True,
    )
    session = manager.create_session("Archive old sessions")
    session_id = session["session_id"]
    old_ts = (datetime.now(timezone.utc) - timedelta(days=4)).isoformat()
    session["updated_at_utc"] = old_ts
    session["created_at_utc"] = old_ts
    manager._write_session(session)

    archived_count = manager.archive_expired_sessions()
    archived = manager.get_session(session_id)

    assert archived_count == 1
    assert archived["status"] == "archived"
    assert archived["archive_reason"] == "ttl_expired"
    assert (tmp_path / "sessions" / f"{session_id}.json").exists() is False
    assert (tmp_path / "archive" / f"{session_id}.json").exists()


def test_add_signal_rejects_archived_session(tmp_path: Path):
    manager = ResearchManager(
        tmp_path,
        allow_writes=True,
        session_ttl_days=1,
        auto_archive=True,
    )
    session = manager.create_session("Locked archive behavior")
    session_id = session["session_id"]
    old_ts = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    session["updated_at_utc"] = old_ts
    session["created_at_utc"] = old_ts
    manager._write_session(session)
    manager.archive_expired_sessions()

    with pytest.raises(ValueError, match="archived and read-only"):
        manager.add_signal(
            session_id=session_id,
            source="archive-check",
            claim="late mutation should fail",
            confidence=0.9,
        )
