from __future__ import annotations

import pytest

from merlin_quality_gates import (
    clear_planner_fallback_telemetry_sink,
    clear_quality_scoring_hook,
    ingest_planner_fallback_telemetry,
    register_planner_fallback_telemetry_sink,
    register_quality_scoring_hook,
    score_response_quality_with_hook,
)


@pytest.fixture(autouse=True)
def _clear_quality_hook():
    clear_quality_scoring_hook()
    clear_planner_fallback_telemetry_sink()
    try:
        yield
    finally:
        clear_quality_scoring_hook()
        clear_planner_fallback_telemetry_sink()


def test_score_response_quality_with_hook_unapplied_without_hook():
    result = score_response_quality_with_hook(
        query="hello",
        variant="disabled",
        response="ok",
        context={},
    )

    assert result == {
        "applied": False,
        "score": None,
        "source": "none",
        "error": None,
    }


def test_score_response_quality_with_hook_supports_numeric_return():
    register_quality_scoring_hook(lambda query, variant, response, context: 0.91)

    result = score_response_quality_with_hook(
        query="hello",
        variant="dms",
        response="ok",
        context={"task_type": "analysis"},
    )

    assert result["applied"] is True
    assert result["score"] == pytest.approx(0.91)
    assert result["source"] == "custom"
    assert result["error"] is None


def test_score_response_quality_with_hook_supports_dict_return():
    register_quality_scoring_hook(
        lambda query, variant, response, context: {"score": 0.66, "source": "test_hook"}
    )

    result = score_response_quality_with_hook(
        query="hello",
        variant="control",
        response="ok",
        context={},
    )

    assert result["applied"] is True
    assert result["score"] == pytest.approx(0.66)
    assert result["source"] == "test_hook"
    assert result["error"] is None


def test_score_response_quality_with_hook_handles_exceptions():
    def _boom(query, variant, response, context):
        raise RuntimeError("hook failed")

    register_quality_scoring_hook(_boom)
    result = score_response_quality_with_hook(
        query="hello",
        variant="disabled",
        response="ok",
        context={},
    )

    assert result["applied"] is False
    assert result["score"] is None
    assert result["source"] == "error"
    assert "hook failed" in result["error"]


def test_ingest_planner_fallback_telemetry_returns_no_sink_when_unconfigured():
    result = ingest_planner_fallback_telemetry(
        session_id="session-1",
        metadata={"fallback_reason_code": "dms_timeout"},
        source="assistant.chat.request",
    )

    assert result["ingested"] is False
    assert result["reason"] == "no_sink"
    assert result["telemetry"]["session_id"] == "session-1"
    assert result["telemetry"]["fallback_reason_code"] == "dms_timeout"


def test_ingest_planner_fallback_telemetry_dispatches_to_sink():
    captured: list[dict] = []

    def _sink(payload: dict):
        captured.append(payload)
        return {"stored": True, "reason_code": payload["fallback_reason_code"]}

    register_planner_fallback_telemetry_sink(_sink)

    result = ingest_planner_fallback_telemetry(
        session_id="session-2",
        metadata={
            "fallback_reason_code": "dms_timeout",
            "fallback_stage": "dms_primary",
            "selected_model": "control",
            "router_backend": "adaptive",
        },
        source="assistant.chat.request",
    )

    assert result["ingested"] is True
    assert result["sink_result"]["stored"] is True
    assert captured
    assert captured[0]["session_id"] == "session-2"
    assert captured[0]["fallback_reason_code"] == "dms_timeout"
