import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker

import merlin_api_server as api_server
from merlin_research_manager import ResearchManager

ROOT_DIR = Path(__file__).resolve().parents[1]
CONTRACTS_DIR = ROOT_DIR / "contracts"
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "contracts"

OPERATION_ENVELOPE_VALIDATOR = Draft202012Validator(
    json.loads((CONTRACTS_DIR / "aas.operation-envelope.v1.schema.json").read_text()),
    format_checker=FormatChecker(),
)

EXPECTED_RESPONSE_FIXTURES: dict[str, tuple[str, str]] = {
    "assistant.chat.request": (
        "assistant.chat.request.json",
        "assistant.chat.request.expected_response.json",
    ),
    "assistant.tools.execute": (
        "assistant.tools.execute.request.json",
        "assistant.tools.execute.expected_response.json",
    ),
    "merlin.alerts.list": (
        "merlin.alerts.list.request.json",
        "merlin.alerts.list.expected_response.json",
    ),
    "merlin.aas.create_task": (
        "merlin.aas.create_task.request.json",
        "merlin.aas.create_task.expected_response.json",
    ),
    "merlin.command.execute": (
        "merlin.command.execute.request.json",
        "merlin.command.execute.expected_response.json",
    ),
    "merlin.context.get": (
        "merlin.context.get.request.json",
        "merlin.context.get.expected_response.json",
    ),
    "merlin.context.update": (
        "merlin.context.update.request.json",
        "merlin.context.update.expected_response.json",
    ),
    "merlin.discovery.run": (
        "merlin.discovery.run.request.json",
        "merlin.discovery.run.expected_response.json",
    ),
    "merlin.discovery.queue.status": (
        "merlin.discovery.queue.status.request.json",
        "merlin.discovery.queue.status.expected_response.json",
    ),
    "merlin.discovery.queue.drain": (
        "merlin.discovery.queue.drain.request.json",
        "merlin.discovery.queue.drain.expected_response.json",
    ),
    "merlin.discovery.queue.pause": (
        "merlin.discovery.queue.pause.request.json",
        "merlin.discovery.queue.pause.expected_response.json",
    ),
    "merlin.discovery.queue.resume": (
        "merlin.discovery.queue.resume.request.json",
        "merlin.discovery.queue.resume.expected_response.json",
    ),
    "merlin.discovery.queue.purge_deadletter": (
        "merlin.discovery.queue.purge_deadletter.request.json",
        "merlin.discovery.queue.purge_deadletter.expected_response.json",
    ),
    "merlin.dynamic_components.list": (
        "merlin.dynamic_components.list.request.json",
        "merlin.dynamic_components.list.expected_response.json",
    ),
    "merlin.genesis.logs": (
        "merlin.genesis.logs.request.json",
        "merlin.genesis.logs.expected_response.json",
    ),
    "merlin.genesis.manifest": (
        "merlin.genesis.manifest.request.json",
        "merlin.genesis.manifest.expected_response.json",
    ),
    "merlin.history.get": (
        "merlin.history.get.request.json",
        "merlin.history.get.expected_response.json",
    ),
    "merlin.llm.ab.complete": (
        "merlin.llm.ab.complete.request.json",
        "merlin.llm.ab.complete.expected_response.json",
    ),
    "merlin.llm.ab.create": (
        "merlin.llm.ab.create.request.json",
        "merlin.llm.ab.create.expected_response.json",
    ),
    "merlin.llm.ab.get": (
        "merlin.llm.ab.get.request.json",
        "merlin.llm.ab.get.expected_response.json",
    ),
    "merlin.llm.ab.list": (
        "merlin.llm.ab.list.request.json",
        "merlin.llm.ab.list.expected_response.json",
    ),
    "merlin.llm.ab.result": (
        "merlin.llm.ab.result.request.json",
        "merlin.llm.ab.result.expected_response.json",
    ),
    "merlin.llm.adaptive.feedback": (
        "merlin.llm.adaptive.feedback.request.json",
        "merlin.llm.adaptive.feedback.expected_response.json",
    ),
    "merlin.llm.adaptive.metrics": (
        "merlin.llm.adaptive.metrics.request.json",
        "merlin.llm.adaptive.metrics.expected_response.json",
    ),
    "merlin.llm.adaptive.reset": (
        "merlin.llm.adaptive.reset.request.json",
        "merlin.llm.adaptive.reset.expected_response.json",
    ),
    "merlin.llm.adaptive.status": (
        "merlin.llm.adaptive.status.request.json",
        "merlin.llm.adaptive.status.expected_response.json",
    ),
    "merlin.llm.cost.budget.get": (
        "merlin.llm.cost.budget.get.request.json",
        "merlin.llm.cost.budget.get.expected_response.json",
    ),
    "merlin.llm.cost.budget.set": (
        "merlin.llm.cost.budget.set.request.json",
        "merlin.llm.cost.budget.set.expected_response.json",
    ),
    "merlin.llm.cost.optimization.get": (
        "merlin.llm.cost.optimization.get.request.json",
        "merlin.llm.cost.optimization.get.expected_response.json",
    ),
    "merlin.llm.cost.pricing.set": (
        "merlin.llm.cost.pricing.set.request.json",
        "merlin.llm.cost.pricing.set.expected_response.json",
    ),
    "merlin.llm.cost.report": (
        "merlin.llm.cost.report.request.json",
        "merlin.llm.cost.report.expected_response.json",
    ),
    "merlin.llm.cost.thresholds.get": (
        "merlin.llm.cost.thresholds.get.request.json",
        "merlin.llm.cost.thresholds.get.expected_response.json",
    ),
    "merlin.llm.cost.thresholds.set": (
        "merlin.llm.cost.thresholds.set.request.json",
        "merlin.llm.cost.thresholds.set.expected_response.json",
    ),
    "merlin.llm.parallel.status": (
        "merlin.llm.parallel.status.request.json",
        "merlin.llm.parallel.status.expected_response.json",
    ),
    "merlin.llm.parallel.strategy": (
        "merlin.llm.parallel.strategy.request.json",
        "merlin.llm.parallel.strategy.expected_response.json",
    ),
    "merlin.llm.predictive.export": (
        "merlin.llm.predictive.export.request.json",
        "merlin.llm.predictive.export.expected_response.json",
    ),
    "merlin.llm.predictive.feedback": (
        "merlin.llm.predictive.feedback.request.json",
        "merlin.llm.predictive.feedback.expected_response.json",
    ),
    "merlin.llm.predictive.models": (
        "merlin.llm.predictive.models.request.json",
        "merlin.llm.predictive.models.expected_response.json",
    ),
    "merlin.llm.predictive.select": (
        "merlin.llm.predictive.select.request.json",
        "merlin.llm.predictive.select.expected_response.json",
    ),
    "merlin.llm.predictive.status": (
        "merlin.llm.predictive.status.request.json",
        "merlin.llm.predictive.status.expected_response.json",
    ),
    "merlin.plugins.execute": (
        "merlin.plugins.execute.request.json",
        "merlin.plugins.execute.expected_response.json",
    ),
    "merlin.plugins.list": (
        "merlin.plugins.list.request.json",
        "merlin.plugins.list.expected_response.json",
    ),
    "merlin.research.manager.session.create": (
        "merlin.research.manager.session.create.request.json",
        "merlin.research.manager.session.create.expected_response.json",
    ),
    "merlin.research.manager.sessions.list": (
        "merlin.research.manager.sessions.list.request.json",
        "merlin.research.manager.sessions.list.expected_response.json",
    ),
    "merlin.research.manager.session.get": (
        "merlin.research.manager.session.get.request.json",
        "merlin.research.manager.session.get.expected_response.json",
    ),
    "merlin.research.manager.session.signal.add": (
        "merlin.research.manager.session.signal.add.request.json",
        "merlin.research.manager.session.signal.add.expected_response.json",
    ),
    "merlin.research.manager.brief.get": (
        "merlin.research.manager.brief.get.request.json",
        "merlin.research.manager.brief.get.expected_response.json",
    ),
    "merlin.knowledge.search": (
        "merlin.knowledge.search.request.json",
        "merlin.knowledge.search.expected_response.json",
    ),
    "merlin.seed.status": (
        "merlin.seed.status.request.json",
        "merlin.seed.status.expected_response.json",
    ),
    "merlin.seed.health": (
        "merlin.seed.health.request.json",
        "merlin.seed.health.expected_response.json",
    ),
    "merlin.seed.health.heartbeat": (
        "merlin.seed.health.heartbeat.request.json",
        "merlin.seed.health.heartbeat.expected_response.json",
    ),
    "merlin.seed.watchdog.tick": (
        "merlin.seed.watchdog.tick.request.json",
        "merlin.seed.watchdog.tick.expected_response.json",
    ),
    "merlin.seed.watchdog.status": (
        "merlin.seed.watchdog.status.request.json",
        "merlin.seed.watchdog.status.expected_response.json",
    ),
    "merlin.seed.watchdog.control": (
        "merlin.seed.watchdog.control.request.json",
        "merlin.seed.watchdog.control.expected_response.json",
    ),
    "merlin.seed.control": (
        "merlin.seed.control.request.json",
        "merlin.seed.control.expected_response.json",
    ),
    "merlin.rag.query": (
        "merlin.rag.query.request.json",
        "merlin.rag.query.expected_response.json",
    ),
    "merlin.search.query": (
        "merlin.search.query.request.json",
        "merlin.search.query.expected_response.json",
    ),
    "merlin.system_info.get": (
        "merlin.system_info.get.request.json",
        "merlin.system_info.get.expected_response.json",
    ),
    "merlin.tasks.create": (
        "merlin.tasks.create.request.json",
        "merlin.tasks.create.expected_response.json",
    ),
    "merlin.tasks.list": (
        "merlin.tasks.list.request.json",
        "merlin.tasks.list.expected_response.json",
    ),
    "merlin.user_manager.authenticate": (
        "merlin.user_manager.authenticate.request.json",
        "merlin.user_manager.authenticate.expected_response.json",
    ),
    "merlin.user_manager.create": (
        "merlin.user_manager.create.request.json",
        "merlin.user_manager.create.expected_response.json",
    ),
    "merlin.voice.listen": (
        "merlin.voice.listen.request.json",
        "merlin.voice.listen.expected_response.json",
    ),
    "merlin.voice.status": (
        "merlin.voice.status.request.json",
        "merlin.voice.status.expected_response.json",
    ),
    "merlin.voice.synthesize": (
        "merlin.voice.synthesize.request.json",
        "merlin.voice.synthesize.expected_response.json",
    ),
    "merlin.voice.transcribe": (
        "merlin.voice.transcribe.request.json",
        "merlin.voice.transcribe.expected_response.json",
    ),
}

RESEARCH_MANAGER_ERROR_VARIANT_CASES = json.loads(
    (FIXTURES_DIR / "merlin.research.manager.error_variants.cases.json").read_text(
        encoding="utf-8"
    )
)["cases"]


def auth_headers():
    return {"X-Merlin-Key": "merlin-secret-key"}


def load_contract_fixture(filename: str):
    with (FIXTURES_DIR / filename).open("r", encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def _schema_errors(validator: Draft202012Validator, data: dict):
    return [error.message for error in validator.iter_errors(data)]


def _assert_expected_subset(actual, expected):
    if isinstance(expected, dict):
        assert isinstance(actual, dict)
        for key, expected_value in expected.items():
            assert key in actual, f"Missing expected key: {key}"
            _assert_expected_subset(actual[key], expected_value)
        return

    if isinstance(expected, list):
        assert isinstance(actual, list)
        assert len(actual) == len(expected)
        for actual_item, expected_item in zip(actual, expected):
            _assert_expected_subset(actual_item, expected_item)
        return

    assert actual == expected


def _replace_case_tokens(value, tokens: dict[str, str]):
    if isinstance(value, dict):
        return {key: _replace_case_tokens(item, tokens) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_case_tokens(item, tokens) for item in value]
    if isinstance(value, str):
        resolved = value
        for token, replacement in tokens.items():
            resolved = resolved.replace(token, replacement)
        return resolved
    return value


def _apply_research_manager_error_case_setup(
    monkeypatch, tmp_path: Path, setup_name: str | None
) -> dict[str, str]:
    if not setup_name or setup_name == "research_manager_default":
        manager = ResearchManager(tmp_path / "research_manager", allow_writes=True)
        monkeypatch.setattr(api_server, "research_manager", manager)
        return {}

    if setup_name == "research_manager_read_only":
        manager = ResearchManager(tmp_path / "research_manager", allow_writes=True)
        manager.allow_writes = False
        monkeypatch.setattr(api_server, "research_manager", manager)
        return {}

    if setup_name == "research_manager_read_only_seeded":
        manager = ResearchManager(tmp_path / "research_manager", allow_writes=True)
        seeded = manager.create_session("Seeded session for read-only error case")
        manager.allow_writes = False
        monkeypatch.setattr(api_server, "research_manager", manager)
        return {"__SEEDED_SESSION_ID__": seeded["session_id"]}

    raise AssertionError(f"Unknown research-manager setup: {setup_name}")


def _prepare_success_mocks(monkeypatch):
    class DummyUsage:
        def __init__(self, date, total_cost):
            self.date = date
            self.total_cost = total_cost

    class DummyCostManager:
        def __init__(self):
            month_prefix = api_server.datetime.now().strftime("%Y-%m")
            self.budget_limit = 100.0
            self.cost_thresholds = {"warning": 70.0, "critical": 90.0}
            self.daily_usage = {
                "fixture-model": [
                    DummyUsage(f"{month_prefix}-10", 12.5),
                    DummyUsage("2026-01-31", 4.0),
                ]
            }

        def get_cost_report(self, days):
            return {
                "period_days": days,
                "budget_limit": self.budget_limit,
                "total_spend": 12.5,
                "model_breakdown": {"fixture-model": {"total_cost": 12.5}},
                "recommendations": {"switch_to_free_model": False},
            }

        def get_cost_optimization_recommendation(self):
            return {"switch_to_free_model": False, "reduce_usage": True}

    class DummyContext:
        def __init__(self):
            self.state = {
                "last_active_platform": "FixtureOS",
                "current_task": "fixture-task",
                "perception_data": {},
                "divine_guidance": [],
            }

        def update(self, data):
            self.state.update(data)

    class DummyVoice:
        def status(self):
            return {"tts": {"primary": "dummy"}, "stt": {"primary": "dummy"}}

        def synthesize_to_file(self, text, engine=None):
            output_path = Path("/tmp/merlin-fixture-voice.wav")
            output_path.write_bytes(b"RIFFDATA")
            return str(output_path)

        def listen(self, engine=None):
            return "fixture-heard"

        def transcribe_file(self, file_path, engine=None):
            return "fixture-transcribed"

    class DummyResearchManager:
        def create_session(
            self,
            objective,
            constraints=None,
            horizon_days=14,
            *,
            created_by=None,
            source_operation=None,
            policy_version=None,
            tags=None,
            impact=None,
            uncertainty=None,
            time_horizon=None,
            linked_task_ids=None,
            planner_artifacts=None,
        ):
            return {
                "session_id": "fixture-session-id",
                "objective": objective,
                "constraints": constraints or [],
                "tags": tags or [],
                "linked_task_ids": linked_task_ids or [],
                "planner_artifacts": planner_artifacts or [],
                "risk_rubric": {
                    "impact": 0.5 if impact is None else impact,
                    "uncertainty": 0.5 if uncertainty is None else uncertainty,
                    "time_horizon": time_horizon or "near_term",
                },
                "horizon_days": horizon_days,
                "status": "active",
                "created_by": created_by or "fixture-created-by",
                "source_operation": source_operation or "fixture-source-operation",
                "policy_version": policy_version or "fixture-policy-version",
                "created_at_utc": "2026-02-14T00:00:00Z",
                "updated_at_utc": "2026-02-14T00:00:00Z",
                "hypotheses": [
                    {
                        "id": "h_execution_success",
                        "statement": "Fixture execution hypothesis",
                        "probability": 0.67,
                        "confidence": 0.51,
                        "supporting_signals": 1,
                        "contradicting_signals": 0,
                    }
                ],
                "signals": [],
                "tasks": [],
                "foresight": [
                    {"scenario": "best_case", "probability": 0.75},
                    {"scenario": "base_case", "probability": 0.61},
                    {"scenario": "worst_case", "probability": 0.37},
                ],
            }

        def next_actions(self, session_id):
            return [
                "Collect targeted evidence on h_execution_success.",
                "Run adversarial challenge against dependency assumptions.",
                "Publish decision packet with go/no-go thresholds.",
            ]

        def list_sessions(self, limit=20, *, tag=None, topic_query=None):
            return [
                {
                    "session_id": "fixture-session-id",
                    "objective": "Fixture research objective",
                    "tags": ["fixture-tag"],
                    "status": "active",
                    "created_at_utc": "2026-02-14T00:00:00Z",
                    "updated_at_utc": "2026-02-14T00:00:00Z",
                    "signal_count": 1,
                    "linked_task_count": 1,
                    "planner_artifact_count": 1,
                }
            ][:limit]

        def get_session(self, session_id):
            return {
                "session_id": session_id,
                "objective": "Fixture research objective",
                "constraints": ["repo-local-only"],
                "tags": ["fixture-tag"],
                "linked_task_ids": [1],
                "planner_artifacts": ["docs/research/fixture.md"],
                "risk_rubric": {
                    "impact": 0.5,
                    "uncertainty": 0.5,
                    "time_horizon": "near_term",
                },
                "horizon_days": 14,
                "status": "active",
                "created_at_utc": "2026-02-14T00:00:00Z",
                "updated_at_utc": "2026-02-14T00:00:00Z",
                "hypotheses": [
                    {
                        "id": "h_execution_success",
                        "statement": "Fixture execution hypothesis",
                        "probability": 0.67,
                        "confidence": 0.51,
                        "supporting_signals": 1,
                        "contradicting_signals": 0,
                    }
                ],
                "signals": [
                    {
                        "signal_id": "fixture-signal-id",
                        "source": "fixture-source",
                        "claim": "fixture claim",
                        "confidence": 0.88,
                    }
                ],
                "tasks": [],
                "foresight": [
                    {"scenario": "best_case", "probability": 0.75},
                    {"scenario": "base_case", "probability": 0.61},
                    {"scenario": "worst_case", "probability": 0.37},
                ],
            }

        def add_signal(
            self,
            session_id,
            source,
            claim,
            confidence,
            *,
            novelty=0.5,
            risk=0.2,
            supports=None,
            contradicts=None,
        ):
            return {
                "session_id": session_id,
                "signal": {
                    "signal_id": "fixture-signal-id",
                    "source": source,
                    "claim": claim,
                    "confidence": confidence,
                    "novelty": novelty,
                    "risk": risk,
                    "supports": supports or [],
                    "contradicts": contradicts or [],
                    "timestamp_utc": "2026-02-14T00:00:00Z",
                },
                "hypotheses": [
                    {
                        "id": "h_execution_success",
                        "probability": 0.67,
                        "confidence": 0.51,
                    }
                ],
                "next_actions": self.next_actions(session_id),
            }

        def get_brief(self, session_id):
            return {
                "session_id": session_id,
                "objective": "Fixture research objective",
                "status": "active",
                "brief_template_id": "research_manager.default",
                "brief_template_version": "1.0.0",
                "probability_of_success": 0.67,
                "signal_count": 1,
                "risk_rubric": {
                    "impact": 0.5,
                    "uncertainty": 0.5,
                    "time_horizon": "near_term",
                },
                "linked_task_ids": [1],
                "linked_tasks": [{"id": 1, "title": "Fixture task"}],
                "planner_artifacts": ["docs/research/fixture.md"],
                "contradicting_signal_count": 0,
                "conflict_count": 0,
                "conflict_hypotheses": [],
                "causal_chains": [
                    {
                        "hypothesis_id": "h_execution_success",
                        "supporting_count": 1,
                        "contradicting_count": 0,
                    }
                ],
                "hypotheses": [
                    {
                        "id": "h_execution_success",
                        "probability": 0.67,
                        "confidence": 0.51,
                    }
                ],
                "foresight": [
                    {"scenario": "best_case", "probability": 0.75},
                    {"scenario": "base_case", "probability": 0.61},
                    {"scenario": "worst_case", "probability": 0.37},
                ],
                "next_actions": self.next_actions(session_id),
                "updated_at_utc": "2026-02-14T00:00:00Z",
            }

    class DummyDiscoveryEngine:
        def __init__(self, workspace_root: Path, merlin_mode: str = "local"):
            self.workspace_root = Path(workspace_root)
            self.merlin_mode = merlin_mode

        def _queue_status(self, paused: bool = False) -> dict[str, Any]:
            return {
                "schema_name": "AAS.Discovery.QueueStatus",
                "schema_version": "1.0.0",
                "queue_root": str(self.workspace_root / "queue"),
                "seeds": 1,
                "work": 1,
                "deadletter": 0,
                "paused": paused,
                "counts": {
                    "new": 1,
                    "claimed": 0,
                    "done": 0,
                    "failed": 0,
                    "blocked": 0,
                },
            }

        def run(self, **kwargs: Any) -> dict[str, Any]:
            profile = str(kwargs.get("profile", "public")).strip().lower() or "public"
            allow_live_automation = kwargs.get("allow_live_automation")
            if allow_live_automation is None:
                allow_live_automation = True
            run_id = "run_20260224T123000Z_fixture01"
            return {
                "schema_name": "AAS.Discovery.RunReport",
                "schema_version": "1.0.0",
                "run_id": run_id,
                "profile": profile,
                "allow_live_automation": bool(allow_live_automation),
                "merlin_mode": "local",
                "started_at": "2026-02-24T12:30:00Z",
                "completed_at": "2026-02-24T12:30:03Z",
                "status": "ok",
                "counts": {
                    "seeds_added": 1,
                    "work_promoted": 1,
                    "work_claimed": 1,
                    "items_collected": 1,
                    "items_scored": 1,
                    "topics_selected": 1,
                    "artifacts_generated": 1,
                    "artifacts_written": 1,
                    "artifacts_skipped": 0,
                    "blocked_by_policy": 0,
                    "failed": 0,
                },
                "policy": {
                    "profile": profile,
                    "allow_live_automation": bool(allow_live_automation),
                    "collector_decisions": {},
                    "publisher_decisions": {},
                    "dry_run": False,
                    "no_write": False,
                },
                "publish_result": {
                    "schema_name": "AAS.Discovery.PublishResult",
                    "schema_version": "1.0.0",
                    "run_id": run_id,
                    "publisher_mode": "stage_only",
                    "status": "staged",
                    "blocked_by_policy": False,
                    "decision": "allowed",
                    "message": "fixture publish",
                    "created_paths": [
                        "knowledge/research/2026/02/24/discovery-envelope-fixture.md"
                    ],
                },
                "plan": [
                    {
                        "artifact_id": "artifact_fixture0001",
                        "path": "knowledge/research/2026/02/24/discovery-envelope-fixture.md",
                        "action": "CREATE",
                        "valid": True,
                    }
                ],
                "paths": {
                    "output_root": str(self.workspace_root),
                    "knowledge_root": str(self.workspace_root / "knowledge"),
                    "queue_root": str(self.workspace_root / "queue"),
                    "run_dir": str(self.workspace_root / "runs" / run_id),
                },
            }

        def queue_status(self, *, out=None):
            return self._queue_status(paused=False)

        def queue_drain(self, *, out=None, run_id=None):
            return {
                "schema_name": "AAS.Discovery.QueueDrain",
                "schema_version": "1.0.0",
                "promoted": 1,
                "status": self._queue_status(paused=False),
            }

        def queue_pause(self, *, out=None):
            return {
                "schema_name": "AAS.Discovery.QueuePause",
                "schema_version": "1.0.0",
                "status": self._queue_status(paused=True),
            }

        def queue_resume(self, *, out=None):
            return {
                "schema_name": "AAS.Discovery.QueueResume",
                "schema_version": "1.0.0",
                "status": self._queue_status(paused=False),
            }

        def queue_purge_deadletter(self, *, out=None):
            return {
                "schema_name": "AAS.Discovery.QueuePurgeDeadletter",
                "schema_version": "1.0.0",
                "purged": 1,
                "status": self._queue_status(paused=False),
            }

        def knowledge_search(self, *, query: str, out=None, limit: int = 20, tag=None):
            return {
                "schema_name": "AAS.Knowledge.SearchResult",
                "schema_version": "1.0.0",
                "query": query,
                "tag": tag,
                "count": 1,
                "results": [
                    {
                        "canonical_key": "ck_fixture000000000000000001",
                        "title": "Discovery fixture result",
                        "path": "knowledge/research/2026/02/24/discovery-envelope-fixture.md",
                        "canonical_url": "https://example.org/discovery-envelope",
                        "tags": ["policy"],
                        "run_id": "run_20260224T123000Z_fixture01",
                        "updated_at": "2026-02-24T12:30:02Z",
                    }
                ],
                "index_path": str(self.workspace_root / "knowledge" / "index.json"),
            }

    class DummySeedAccess:
        def __init__(self, workspace_root: Path | None = None):
            self.workspace_root = Path(workspace_root or "/tmp/merlin-seed-fixture")

        def status(
            self,
            *,
            status_file=None,
            merged_jsonl=None,
            merged_parquet=None,
            log_file=None,
            include_log_tail=True,
            tail_lines=40,
            allow_live_automation=None,
            match_tokens=(),
        ):
            payload = {
                "schema_name": "AAS.Merlin.SeedStatus",
                "schema_version": "1.0.0",
                "workspace_root": str(self.workspace_root),
                "policy": {
                    "decision": "allowed",
                    "allow_live_automation": True,
                    "allow_live_automation_default": True,
                    "reason": "live automation is enabled",
                },
                "paths": {
                    "status_file": str(
                        self.workspace_root / "artifacts" / "merlin_seed_status.json"
                    ),
                    "merged_jsonl": str(
                        self.workspace_root
                        / "guild"
                        / "data"
                        / "merlin_distill_merged.jsonl"
                    ),
                    "merged_parquet": str(
                        self.workspace_root
                        / "guild"
                        / "data"
                        / "merlin_distill_merged.parquet"
                    ),
                    "log_file": str(
                        self.workspace_root / "logs" / "merlin_seed_task.log"
                    ),
                },
                "status_file": {
                    "exists": True,
                    "mtime_utc": "2026-02-24T12:30:00Z",
                    "status_age_seconds": 12.0,
                    "stale": False,
                    "read_error": None,
                },
                "status": {
                    "status": "running",
                    "target": 50000,
                    "current_total": 4641,
                    "updated_at": "2026-02-24T12:30:00Z",
                },
                "progress": {
                    "target_rounds": 50000,
                    "completed_rounds": 4641,
                    "remaining_rounds": 45359,
                    "completion_ratio": 0.09282,
                    "completion_percent": 9.28,
                    "source": "status_or_dataset_max",
                    "eta_seconds": 48630.0,
                    "throughput_per_min": 55.96,
                },
                "dataset": {
                    "exists": True,
                    "line_count": 4641,
                    "mtime_utc": "2026-02-24T12:30:00Z",
                },
                "process": {
                    "active": True,
                    "count": 1,
                    "rows": [
                        {
                            "pid": 4242,
                            "command": "python scripts/run_merlin_seed_until.py",
                        }
                    ],
                },
                "guidance": {
                    "schema_name": "AAS.Merlin.SeedGuidance",
                    "schema_version": "1.0.0",
                    "state": "healthy",
                    "next_action": "observe",
                    "recommendations": [],
                },
                "updated_at": "2026-02-24T12:30:12Z",
            }
            if include_log_tail:
                payload["log_tail"] = {
                    "lines": ["[fixture] seed worker active"],
                    "line_limit": tail_lines,
                    "mtime_utc": "2026-02-24T12:30:12Z",
                }
            return payload

        def health(
            self,
            *,
            status_file=None,
            merged_jsonl=None,
            merged_parquet=None,
            log_file=None,
            allow_live_automation=None,
            stale_after_seconds=3600.0,
            match_tokens=(),
        ):
            return {
                "schema_name": "AAS.Merlin.SeedHealth",
                "schema_version": "1.0.0",
                "workspace_root": str(self.workspace_root),
                "state": "healthy",
                "severity": "ok",
                "policy_decision": "allowed",
                "next_action": "observe",
                "recommended_control_action": "none",
                "checks": {
                    "policy_allowed": True,
                    "status_stale": False,
                    "worker_active": True,
                    "progress_complete": False,
                },
                "progress": {
                    "target_rounds": 50000,
                    "completed_rounds": 4641,
                    "remaining_rounds": 45359,
                    "completion_percent": 9.28,
                },
                "worker": {
                    "active": True,
                    "count": 1,
                },
                "staleness": {
                    "status_age_seconds": 12.0,
                    "stale_after_seconds": stale_after_seconds,
                    "is_stale": False,
                },
                "guidance": {
                    "schema_name": "AAS.Merlin.SeedGuidance",
                    "schema_version": "1.0.0",
                    "state": "healthy",
                    "next_action": "observe",
                    "recommendations": [],
                },
                "status_snapshot_updated_at": "2026-02-24T12:30:12Z",
                "updated_at": "2026-02-24T12:30:12Z",
            }

        def heartbeat(
            self,
            *,
            status_file=None,
            merged_jsonl=None,
            merged_parquet=None,
            log_file=None,
            allow_live_automation=None,
            stale_after_seconds=3600.0,
            heartbeat_file=None,
            write_event=True,
            match_tokens=(),
        ):
            health_payload = self.health(
                status_file=status_file,
                merged_jsonl=merged_jsonl,
                merged_parquet=merged_parquet,
                log_file=log_file,
                allow_live_automation=allow_live_automation,
                stale_after_seconds=stale_after_seconds,
                match_tokens=match_tokens,
            )
            return {
                "schema_name": "AAS.Merlin.SeedHealthHeartbeat",
                "schema_version": "1.0.0",
                "event_id": "hb_fixture_seed_health_heartbeat_0001",
                "event_type": "merlin.seed.health.heartbeat",
                "workspace_root": str(self.workspace_root),
                "state": "healthy",
                "severity": "ok",
                "policy_decision": "allowed",
                "next_action": "observe",
                "recommended_control_action": "none",
                "checks": health_payload["checks"],
                "progress": health_payload["progress"],
                "worker": health_payload["worker"],
                "staleness": {
                    "status_age_seconds": 12.0,
                    "stale_after_seconds": stale_after_seconds,
                    "is_stale": False,
                },
                "health_snapshot": health_payload,
                "heartbeat_file": (
                    heartbeat_file
                    or str(
                        self.workspace_root
                        / "artifacts"
                        / "diagnostics"
                        / "merlin_seed_health_heartbeat.jsonl"
                    )
                ),
                "persisted": bool(write_event),
                "emitted_at": "2026-02-24T12:30:12Z",
            }

        def watchdog(
            self,
            *,
            status_file=None,
            merged_jsonl=None,
            merged_parquet=None,
            log_file=None,
            allow_live_automation=None,
            stale_after_seconds=3600.0,
            apply=False,
            force=False,
            dry_run_control=False,
            match_tokens=(),
        ):
            health_payload = self.health(
                status_file=status_file,
                merged_jsonl=merged_jsonl,
                merged_parquet=merged_parquet,
                log_file=log_file,
                allow_live_automation=allow_live_automation,
                stale_after_seconds=stale_after_seconds,
                match_tokens=match_tokens,
            )
            return {
                "schema_name": "AAS.Merlin.SeedWatchdogTick",
                "schema_version": "1.0.0",
                "workspace_root": str(self.workspace_root),
                "health": health_payload,
                "decision": {
                    "recommended_control_action": "none",
                    "apply_requested": bool(apply),
                    "dry_run_control": bool(dry_run_control),
                    "force": bool(force),
                    "action_taken": "none",
                    "outcome_status": "noop",
                    "reason": "No control action recommended by health guidance.",
                },
                "control_result": None,
                "updated_at": "2026-02-24T12:30:12Z",
            }

        def watchdog_runtime_status(
            self,
            *,
            status_file=None,
            merged_jsonl=None,
            merged_parquet=None,
            log_file=None,
            watchdog_log_file=None,
            append_jsonl=None,
            output_json=None,
            heartbeat_file=None,
            allow_live_automation=None,
            stale_after_seconds=3600.0,
            match_tokens=(),
        ):
            return {
                "schema_name": "AAS.Merlin.SeedWatchdogRuntimeStatus",
                "schema_version": "1.0.0",
                "workspace_root": str(self.workspace_root),
                "policy": {
                    "decision": "allowed",
                    "allow_live_automation": True,
                    "allow_live_automation_default": True,
                    "reason": "live automation is enabled",
                },
                "paths": {
                    "watchdog_log_file": str(
                        self.workspace_root / "logs" / "merlin_seed_watchdog_runtime.log"
                    ),
                    "append_jsonl": str(
                        self.workspace_root
                        / "artifacts"
                        / "diagnostics"
                        / "merlin_seed_watchdog_runtime_ticks.jsonl"
                    ),
                    "output_json": str(
                        self.workspace_root
                        / "artifacts"
                        / "diagnostics"
                        / "merlin_seed_watchdog_runtime_latest.json"
                    ),
                    "heartbeat_file": str(
                        self.workspace_root
                        / "artifacts"
                        / "diagnostics"
                        / "merlin_seed_health_heartbeat.jsonl"
                    ),
                },
                "process": {
                    "active": False,
                    "count": 0,
                    "rows": [],
                },
                "telemetry": {
                    "append_jsonl_exists": True,
                    "append_jsonl_line_count": 1,
                    "append_jsonl_mtime_utc": "2026-02-24T12:30:12Z",
                    "output_json_exists": True,
                    "output_json_mtime_utc": "2026-02-24T12:30:12Z",
                    "output_json_read_error": None,
                    "last_tick": {
                        "iteration": 1,
                        "watchdog": {
                            "schema_name": "AAS.Merlin.SeedWatchdogTick",
                            "decision": {"outcome_status": "preview"},
                        },
                    },
                    "last_report_summary": {"total_ticks": 1, "preview": 1},
                },
                "health": self.health(stale_after_seconds=stale_after_seconds),
                "updated_at": "2026-02-24T12:30:12Z",
            }

        def watchdog_runtime_control(
            self,
            *,
            action,
            allow_live_automation=None,
            dry_run=False,
            force=False,
            status_file=None,
            merged_jsonl=None,
            merged_parquet=None,
            log_file=None,
            watchdog_log_file=None,
            append_jsonl=None,
            output_json=None,
            heartbeat_file=None,
            stale_after_seconds=3600.0,
            apply=False,
            dry_run_control=False,
            interval_seconds=60.0,
            max_iterations=0,
            emit_heartbeat=True,
            match_tokens=(),
        ):
            return {
                "schema_name": "AAS.Merlin.SeedWatchdogRuntimeControl",
                "schema_version": "1.0.0",
                "action": action,
                "decision": "allowed",
                "status": "preview" if dry_run else "started",
                "message": (
                    "Dry-run preview only; no watchdog runtime process started"
                    if dry_run
                    else "Seed watchdog runtime process started"
                ),
                "dry_run": bool(dry_run),
                "runtime": {
                    "stale_after_seconds": stale_after_seconds,
                    "apply": bool(apply),
                    "dry_run_control": bool(dry_run_control),
                    "force": bool(force),
                    "interval_seconds": interval_seconds,
                    "max_iterations": max_iterations,
                    "emit_heartbeat": bool(emit_heartbeat),
                },
                "start": (
                    None
                    if dry_run
                    else {
                        "pid": 4545,
                        "command": "python scripts/run_merlin_seed_watchdog.py --workspace-root /tmp/merlin-seed-fixture",
                    }
                ),
                "updated_at": "2026-02-24T12:30:12Z",
            }

        def control(
            self,
            *,
            action,
            allow_live_automation=None,
            dry_run=False,
            force=False,
            status_file=None,
            merged_jsonl=None,
            merged_parquet=None,
            log_file=None,
            endpoint="http://127.0.0.1:1234",
            prompt_set="scripts/eval/prompts_guild.json",
            target=50000,
            increment=500,
            repeat=13,
            eta_window=5,
            sleep_seconds=0.1,
            delay_seconds=1.0,
            resource_aware=True,
            cpu_max=85.0,
            mem_max=85.0,
            resource_wait=5.0,
            notify_on_complete=False,
            teachers=None,
            config=None,
            match_tokens=(),
        ):
            return {
                "schema_name": "AAS.Merlin.SeedControl",
                "schema_version": "1.0.0",
                "action": action,
                "decision": "allowed",
                "status": "preview" if dry_run else "started",
                "message": (
                    "Dry-run preview only; no process started"
                    if dry_run
                    else "Seed worker process started"
                ),
                "policy": {
                    "decision": "allowed",
                    "allow_live_automation": True,
                    "allow_live_automation_default": True,
                    "reason": "live automation is enabled",
                },
                "workspace_root": str(self.workspace_root),
                "paths": {
                    "status_file": str(
                        self.workspace_root / "artifacts" / "merlin_seed_status.json"
                    ),
                    "merged_jsonl": str(
                        self.workspace_root
                        / "guild"
                        / "data"
                        / "merlin_distill_merged.jsonl"
                    ),
                    "merged_parquet": str(
                        self.workspace_root
                        / "guild"
                        / "data"
                        / "merlin_distill_merged.parquet"
                    ),
                    "log_file": str(
                        self.workspace_root / "logs" / "merlin_seed_task.log"
                    ),
                },
                "start": {
                    "pid": 4343,
                    "command": "python scripts/run_merlin_seed_until.py --target 50000",
                },
                "status_snapshot": self.status(include_log_tail=False),
                "updated_at": "2026-02-24T12:30:12Z",
            }

    monkeypatch.setattr(
        api_server,
        "merlin_emotion_chat",
        lambda user_input, user_id: "fixture-chat-reply",
    )
    monkeypatch.setattr(
        api_server,
        "build_discovery_engine",
        lambda workspace_root, merlin_mode="local": DummyDiscoveryEngine(
            workspace_root=Path(workspace_root),
            merlin_mode=merlin_mode,
        ),
    )
    monkeypatch.setattr(
        api_server,
        "build_seed_access",
        lambda workspace_root=None: DummySeedAccess(
            workspace_root=(
                Path(workspace_root)
                if isinstance(workspace_root, str) and workspace_root.strip()
                else None
            )
        ),
    )
    monkeypatch.setattr(api_server, "research_manager", DummyResearchManager())
    monkeypatch.setattr(
        api_server,
        "load_chat",
        lambda user_id: [{"user": "u", "merlin": "m"}],
    )
    monkeypatch.setattr(api_server, "global_context", DummyContext())
    monkeypatch.setattr(
        api_server.plugin_manager,
        "execute_plugin",
        lambda name, *args, **kwargs: {"ok": True},
    )
    monkeypatch.setattr(
        api_server.plugin_manager,
        "list_plugin_info",
        lambda: {"demo": {"name": "Demo", "description": "d", "category": "general"}},
    )
    monkeypatch.setattr(
        api_server.policy_manager, "is_command_allowed", lambda command: True
    )
    monkeypatch.setattr(
        api_server,
        "execute_command",
        lambda command: {"stdout": "ok", "stderr": "", "returncode": 0},
    )
    monkeypatch.setattr(
        api_server.merlin_rag,
        "search",
        lambda query, limit=5: [
            {"text": "doc", "metadata": {"path": "docs/readme.md"}},
            {"text": "standalone match", "metadata": {}},
        ],
    )
    monkeypatch.setattr(
        api_server.task_manager,
        "list_tasks",
        lambda: [{"id": 1, "title": "existing task", "priority": "Low"}],
    )
    monkeypatch.setattr(
        api_server.task_manager,
        "add_task",
        lambda title, description, priority: {
            "id": 101,
            "title": title,
            "description": description,
            "priority": priority,
        },
    )
    monkeypatch.setattr(
        api_server.user_manager,
        "create_user",
        lambda username, password, role="user": {"username": username, "role": role},
    )
    monkeypatch.setattr(
        api_server.user_manager,
        "authenticate_user",
        lambda username, password: {
            "username": username,
            "role": "admin",
            "hashed_password": "x",
        },
    )
    monkeypatch.setattr(
        api_server,
        "create_access_token",
        lambda data, expires_delta=None: "fixture-token",
    )
    monkeypatch.setattr(
        api_server.hub_client,
        "create_aas_task",
        lambda title, description, priority: "fixture-task-id",
    )
    monkeypatch.setattr(
        api_server, "get_system_info", lambda: {"platform": "fixture-os"}
    )
    monkeypatch.setattr(
        api_server, "get_recent_logs", lambda: [{"message": "fixture-log"}]
    )
    monkeypatch.setattr(
        api_server.ab_testing_manager,
        "create_test",
        lambda **kwargs: "fixture-ab-test-id",
    )
    monkeypatch.setattr(
        api_server.ab_testing_manager,
        "list_active_tests",
        lambda: [
            {
                "test_id": "fixture-ab-test-id",
                "name": "Fixture AB",
                "variants": ["routing", "voting"],
                "weights": [0.6, 0.4],
                "status": "active",
                "start_time": "2026-02-14T00:00:00Z",
                "variant_stats": {
                    "routing": {
                        "requests": 12,
                        "success_rate": 0.92,
                        "avg_latency": 0.42,
                        "avg_rating": 4.7,
                    },
                    "voting": {
                        "requests": 10,
                        "success_rate": 0.8,
                        "avg_latency": 0.6,
                        "avg_rating": 4.2,
                    },
                },
            }
        ],
    )
    monkeypatch.setattr(
        api_server.ab_testing_manager,
        "get_test_status",
        lambda test_id: {
            "test_id": test_id,
            "name": "Fixture AB",
            "status": "active",
            "variants": ["routing", "voting"],
            "weights": [0.6, 0.4],
            "start_time": "2026-02-14T00:00:00Z",
            "end_time": None,
            "duration_hours": 1.0,
            "variant_stats": {
                "routing": {
                    "requests": 12,
                    "success_rate": 0.92,
                    "avg_latency": 0.42,
                    "avg_rating": 4.7,
                },
                "voting": {
                    "requests": 10,
                    "success_rate": 0.8,
                    "avg_latency": 0.6,
                    "avg_rating": 4.2,
                },
            },
            "winner": None,
        },
    )
    monkeypatch.setattr(
        api_server.ab_testing_manager,
        "record_result",
        lambda test_id, variant, user_rating=None, latency=0.0, success=True: None,
    )
    monkeypatch.setattr(
        api_server.ab_testing_manager,
        "complete_test",
        lambda test_id: {
            "variant": "routing",
            "score": 0.9,
            "stats": {
                "requests": 12,
                "success_rate": 0.92,
                "avg_latency": 0.42,
                "avg_rating": 4.7,
            },
        },
    )
    monkeypatch.setattr(
        api_server.parallel_llm_backend,
        "get_status",
        lambda: {
            "strategy": "voting",
            "models": [{"name": "fixture-model", "backend": "fixture-backend"}],
            "health": {"fixture-model": True},
        },
    )
    monkeypatch.setattr(
        api_server.adaptive_llm_backend,
        "provide_feedback",
        lambda model_name, rating, task_type=None: None,
    )
    monkeypatch.setattr(
        api_server.adaptive_llm_backend,
        "reset_metrics",
        lambda model_name=None: None,
    )
    monkeypatch.setattr(
        api_server.adaptive_llm_backend,
        "get_status",
        lambda: {
            "strategy": "auto",
            "learning_mode": True,
            "min_samples": 1,
            "models": [{"name": "fixture-model", "backend": "fixture-backend"}],
            "metrics": {
                "fixture-model": {
                    "total_requests": 2,
                    "success_rate": 1.0,
                    "avg_latency": 0.25,
                    "avg_rating": 4.5,
                }
            },
        },
    )
    predictive_weights = {
        "fixture-model": {
            "task_type": 0.4,
            "complexity": 0.2,
            "urgency": 0.2,
            "creativity": 0.1,
            "accuracy": 0.05,
            "latency": 0.05,
        }
    }
    predictive_feature_importance = {"task_type": 0.9}
    monkeypatch.setattr(
        api_server.predictive_model_selector,
        "model_weights",
        predictive_weights,
        raising=False,
    )
    monkeypatch.setattr(
        api_server.predictive_model_selector,
        "feature_importance",
        predictive_feature_importance,
        raising=False,
    )
    monkeypatch.setattr(
        api_server.predictive_model_selector,
        "select_model",
        lambda query: "fixture-model",
    )
    monkeypatch.setattr(
        api_server.predictive_model_selector,
        "get_model_explanation",
        lambda model_name, query: "Fixture explanation",
    )
    monkeypatch.setattr(
        api_server.predictive_model_selector,
        "record_feedback",
        lambda model_name, was_successful, latency, task_type, rating=None: None,
    )
    monkeypatch.setattr(
        api_server.predictive_model_selector,
        "get_status",
        lambda: {
            "model_count": 1,
            "training_samples": 0,
            "last_updated": "2026-02-14T00:00:00Z",
            "model_scores": {"fixture-model": 0.4},
            "feature_importance": predictive_feature_importance,
        },
    )
    monkeypatch.setattr(
        api_server.predictive_model_selector,
        "export_model_data",
        lambda: {
            "model_weights": predictive_weights,
            "training_data": [],
            "feature_importance": predictive_feature_importance,
            "export_timestamp": "2026-02-14T00:00:00Z",
        },
    )
    dummy_cost_manager = DummyCostManager()
    monkeypatch.setattr(api_server, "_cost_manager", lambda: dummy_cost_manager)
    monkeypatch.setattr(api_server, "append_manifest_entry", lambda entry: None)
    monkeypatch.setattr(api_server, "get_voice", lambda: DummyVoice())


def test_expected_response_fixtures_cover_supported_operations():
    assert set(EXPECTED_RESPONSE_FIXTURES) == set(
        api_server.SUPPORTED_ENVELOPE_OPERATIONS
    )

    for request_file, expected_file in EXPECTED_RESPONSE_FIXTURES.values():
        assert (
            FIXTURES_DIR / request_file
        ).exists(), f"Missing request fixture: {request_file}"
        assert (
            FIXTURES_DIR / expected_file
        ).exists(), f"Missing expected-response fixture: {expected_file}"


def test_research_manager_error_variant_case_ids_are_unique():
    case_ids = [case["case_id"] for case in RESEARCH_MANAGER_ERROR_VARIANT_CASES]
    assert len(case_ids) == len(set(case_ids))


@pytest.mark.parametrize(
    "case",
    RESEARCH_MANAGER_ERROR_VARIANT_CASES,
    ids=[case["case_id"] for case in RESEARCH_MANAGER_ERROR_VARIANT_CASES],
)
def test_research_manager_error_variants_match_fixtures(
    monkeypatch, tmp_path: Path, case: dict
):
    tokens = _apply_research_manager_error_case_setup(
        monkeypatch,
        tmp_path,
        case.get("setup"),
    )
    client = TestClient(api_server.app)
    request_fixture = load_contract_fixture(case["request_fixture"])
    if "payload" in case:
        request_fixture["payload"] = _replace_case_tokens(case["payload"], tokens)

    response = client.post(
        "/merlin/operations",
        json=request_fixture,
        headers=auth_headers(),
    )
    assert response.status_code == case["expected_status"]

    body = response.json()
    errors = _schema_errors(OPERATION_ENVELOPE_VALIDATOR, body)
    assert not errors, f"Response failed schema validation: {errors}"

    assert body["operation"]["name"] == api_server._response_operation_name(
        request_fixture["operation"]["name"]
    )
    expected_error = case["expected_error"]
    assert body["payload"]["error"]["code"] == expected_error["code"]
    assert body["payload"]["error"]["message"] == expected_error["message"]
    assert body["payload"]["error"]["retryable"] == expected_error["retryable"]


@pytest.mark.parametrize("operation_name", sorted(EXPECTED_RESPONSE_FIXTURES))
def test_operation_success_responses_match_expected_fixtures(
    monkeypatch, operation_name: str
):
    _prepare_success_mocks(monkeypatch)
    client = TestClient(api_server.app)

    request_file, expected_file = EXPECTED_RESPONSE_FIXTURES[operation_name]
    request_fixture = load_contract_fixture(request_file)
    expected_fixture = load_contract_fixture(expected_file)

    response = client.post(
        "/merlin/operations",
        json=request_fixture,
        headers=auth_headers(),
    )
    assert response.status_code == 200

    body = response.json()
    errors = _schema_errors(OPERATION_ENVELOPE_VALIDATOR, body)
    assert not errors, f"Response failed schema validation: {errors}"

    _assert_expected_subset(body, expected_fixture)
    assert isinstance(body["message_id"], str)
    assert isinstance(body["timestamp_utc"], str)


def test_operation_chat_with_metadata_response_matches_expected_fixture(monkeypatch):
    _prepare_success_mocks(monkeypatch)
    metadata_fixture = load_contract_fixture(
        "assistant.chat.routing_metadata.contract.json"
    )
    monkeypatch.setattr(
        api_server,
        "merlin_emotion_chat_with_metadata",
        lambda user_input, user_id: ("fixture-chat-reply", metadata_fixture),
    )
    client = TestClient(api_server.app)
    request_fixture = load_contract_fixture("assistant.chat.request.with_metadata.json")
    expected_fixture = load_contract_fixture(
        "assistant.chat.request.with_metadata.expected_response.json"
    )

    response = client.post(
        "/merlin/operations",
        json=request_fixture,
        headers=auth_headers(),
    )
    assert response.status_code == 200

    body = response.json()
    errors = _schema_errors(OPERATION_ENVELOPE_VALIDATOR, body)
    assert not errors, f"Response failed schema validation: {errors}"

    _assert_expected_subset(body, expected_fixture)
    assert isinstance(body["message_id"], str)
    assert isinstance(body["timestamp_utc"], str)
