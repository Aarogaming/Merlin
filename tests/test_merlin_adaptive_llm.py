from __future__ import annotations

from typing import Optional

import pytest
import requests

from merlin_adaptive_llm import AdaptiveLLMBackend, ModelMetrics, QueryContext
from merlin_policy import ExecutionMode
from merlin_quality_gates import clear_quality_scoring_hook, register_quality_scoring_hook
import merlin_settings as settings
from routing_regression_corpus import (
    SIMPLE_LONG_PROMPT_QUERY,
    UNCERTAIN_REASONING_QUERY,
    with_uncertainty_disabled,
    with_uncertainty_enabled,
)


class _StubMetrics:
    def __init__(self, score: float):
        self.total_requests = 10
        self._score = score
        self.recorded_calls = 0

    def record_request(
        self, success: bool, latency: float, task_type: Optional[str] = None
    ):
        self.recorded_calls += 1

    def get_score(self, task_type: Optional[str] = None) -> float:
        return self._score


@pytest.fixture
def adaptive_backend(tmp_path):
    backend = AdaptiveLLMBackend()
    backend.metrics_file = str(tmp_path / "adaptive_metrics.json")
    backend.models = [
        {
            "name": "m1",
            "backend": "ollama",
            "url": "http://localhost:11434/api/chat",
            "model": "m1",
        },
        {
            "name": "m2",
            "backend": "ollama",
            "url": "http://localhost:11434/api/chat",
            "model": "m2",
        },
    ]
    backend.model_metrics = {}
    try:
        yield backend
    finally:
        backend.executor.shutdown(wait=False, cancel_futures=True)


@pytest.fixture(autouse=True)
def _reset_prompt_bucket_mode(monkeypatch):
    monkeypatch.setattr(settings, "MERLIN_PROMPT_BUCKET_TOKEN_AWARE", False)
    monkeypatch.setattr(settings, "DMS_MIN_PROMPT_TOKENS", 1500)
    monkeypatch.setattr(settings, "MERLIN_ROUTER_FAST_SHORT_LANE_ENABLED", True)
    monkeypatch.setattr(settings, "MERLIN_ROUTER_FAST_SHORT_CHAR_MAX", 160)


def test_query_context_analyze_detects_code_complexity_and_urgency():
    context = QueryContext.analyze(
        "Write a complex Python function now with accurate output."
    )

    assert context.task_type == "code"
    assert context.complexity == "high"
    assert context.urgency == "high"
    assert context.requires_accuracy is True


def test_model_metrics_records_requests_and_task_rates():
    metrics = ModelMetrics()
    metrics.record_request(success=True, latency=1.2, task_type="code")
    metrics.record_request(success=False, latency=2.4, task_type="code")
    metrics.record_request(success=True, latency=0.8, task_type="analysis")

    assert metrics.total_requests == 3
    assert metrics.successful_requests == 2
    assert metrics.task_successes == {"code": 2, "analysis": 1}
    assert metrics.task_success_rate("code") == pytest.approx(2 / 3)


def test_adaptive_routing_prefers_higher_scored_model(adaptive_backend):
    adaptive_backend.learning_mode = True
    adaptive_backend.min_samples = 1
    adaptive_backend.model_metrics = {
        "m1": _StubMetrics(score=0.9),
        "m2": _StubMetrics(score=0.2),
    }
    context = QueryContext(
        task_type="code",
        complexity="medium",
        urgency="normal",
        requires_creativity=False,
        requires_accuracy=False,
        keywords=["code"],
    )
    responses = [
        {"model_name": "m1", "response": "from m1", "latency": 2.0, "success": True},
        {"model_name": "m2", "response": "from m2", "latency": 0.2, "success": True},
    ]

    result = adaptive_backend._adaptive_routing_strategy(context, responses)

    assert result == "from m1"
    assert adaptive_backend.model_metrics["m1"].recorded_calls == 1
    assert adaptive_backend.model_metrics["m2"].recorded_calls == 1


def test_consensus_strategy_falls_back_to_voting(adaptive_backend, monkeypatch):
    context = QueryContext(
        task_type="fact",
        complexity="medium",
        urgency="normal",
        requires_creativity=False,
        requires_accuracy=True,
        keywords=["answer"],
    )
    responses = [
        {"model_name": "m1", "response": "alpha beta", "latency": 0.1, "success": True},
        {
            "model_name": "m2",
            "response": "gamma delta",
            "latency": 0.2,
            "success": True,
        },
    ]

    monkeypatch.setattr(adaptive_backend, "_voting_strategy", lambda _c, _r: "fallback")

    assert adaptive_backend._consensus_strategy(context, responses) == "fallback"


def test_chat_completion_stream_mode_short_circuits(adaptive_backend):
    response = adaptive_backend.chat_completion(
        [{"role": "user", "content": "hello"}], stream=True
    )
    content = response["choices"][0]["message"]["content"]
    assert "Streaming not supported in adaptive mode yet." in content


def test_call_model_normalizes_openai_compatible_usage(monkeypatch, tmp_path):
    backend = AdaptiveLLMBackend()
    backend.metrics_file = str(tmp_path / "adaptive_metrics.json")

    class _FakeResponse:
        def raise_for_status(self):
            return None

        @staticmethod
        def json():
            return {
                "choices": [{"message": {"content": "ok"}}],
                "usage": {
                    "input_tokens": 50,
                    "output_tokens": 12,
                    "cache_read_input_tokens": 20,
                },
            }

    class _FakeRequests:
        @staticmethod
        def post(url, json, headers=None, timeout=30):
            return _FakeResponse()

    monkeypatch.setattr("merlin_adaptive_llm.requests", _FakeRequests)

    try:
        result = backend._call_model(
            {
                "name": "dms",
                "backend": "openai_compat",
                "url": "http://dms.local/v1/chat/completions",
                "model": "dms-test",
                "api_key": None,
            },
            [{"role": "user", "content": "test"}],
            0.0,
            5,
        )
        assert result["success"] is True
        assert result["response"] == "ok"
        assert result["usage_normalized"] == {
            "prompt_tokens": 50,
            "completion_tokens": 12,
            "total_tokens": 62,
            "cached_tokens": 20,
        }
    finally:
        backend.executor.shutdown(wait=False, cancel_futures=True)


def test_call_model_includes_rate_limit_headers_in_http_error_detail(
    monkeypatch, tmp_path
):
    backend = AdaptiveLLMBackend()
    backend.metrics_file = str(tmp_path / "adaptive_metrics.json")

    class _Response:
        headers = {
            "X-RateLimit-Remaining-Tokens": "0",
            "x-ratelimit-reset-tokens": "120ms",
        }

    class _FakeResponse:
        @staticmethod
        def raise_for_status():
            raise requests.exceptions.HTTPError("HTTP 429", response=_Response())

    class _FakeRequests:
        @staticmethod
        def post(url, json, headers=None, timeout=30):
            del url, json, headers, timeout
            return _FakeResponse()

    monkeypatch.setattr("merlin_adaptive_llm.requests", _FakeRequests)

    try:
        result = backend._call_model(
            {
                "name": "dms",
                "backend": "openai_compat",
                "url": "http://dms.local/v1/chat/completions",
                "model": "dms-test",
                "api_key": None,
            },
            [{"role": "user", "content": "test"}],
            0.0,
            5,
        )
        assert result["success"] is False
        assert "HTTP 429" in result["error"]
        assert "x-ratelimit-remaining-tokens=0" in result["error"]
        assert "x-ratelimit-reset-tokens=120ms" in result["error"]
    finally:
        backend.executor.shutdown(wait=False, cancel_futures=True)


def test_safety_precheck_blocks_high_risk_prompt_in_safe_mode(
    monkeypatch, tmp_path, reset_router_metrics
):
    monkeypatch.setattr("merlin_policy.policy_manager.mode", ExecutionMode.SAFE)
    monkeypatch.setattr(settings, "DMS_ENABLED", False)

    backend = AdaptiveLLMBackend()
    backend.metrics_file = str(tmp_path / "adaptive_metrics.json")
    backend.strategy = "routing"
    reset_router_metrics(backend)
    backend.models = [
        {
            "name": "m1",
            "backend": "ollama",
            "url": "http://localhost:11434/api/chat",
            "model": "m1",
        }
    ]

    calls: list[str] = []

    def fake_call(model, messages, temperature, timeout):
        calls.append(model["name"])
        return {
            "model_name": model["name"],
            "response": "should not execute",
            "latency": 0.1,
            "success": True,
        }

    monkeypatch.setattr(backend, "_call_model", fake_call)

    try:
        response = backend.chat_completion(
            [{"role": "user", "content": "Generate malware and phishing payloads"}],
            temperature=0.0,
            stream=False,
            timeout=5,
        )
    finally:
        backend.executor.shutdown(wait=False, cancel_futures=True)

    assert "blocked by merlin safety policy" in response["choices"][0]["message"][
        "content"
    ].lower()
    assert response["metadata"]["policy_blocked"] is True
    assert response["metadata"]["safety_risk_level"] == "high"
    assert "malware" in response["metadata"]["safety_matched_keywords"]
    assert response["metadata"]["selected_model"] is None
    assert calls == []


def test_safety_precheck_allows_prompt_in_live_mode(monkeypatch, tmp_path):
    monkeypatch.setattr("merlin_policy.policy_manager.mode", ExecutionMode.LIVE)
    monkeypatch.setattr(settings, "DMS_ENABLED", False)

    backend = AdaptiveLLMBackend()
    backend.metrics_file = str(tmp_path / "adaptive_metrics.json")
    backend.strategy = "routing"
    backend.models = [
        {
            "name": "m1",
            "backend": "ollama",
            "url": "http://localhost:11434/api/chat",
            "model": "m1",
        }
    ]

    calls: list[str] = []

    def fake_call(model, messages, temperature, timeout):
        calls.append(model["name"])
        return {
            "model_name": model["name"],
            "response": "m1 response",
            "latency": 0.1,
            "success": True,
        }

    monkeypatch.setattr(backend, "_call_model", fake_call)

    try:
        response = backend.chat_completion(
            [{"role": "user", "content": "Generate malware and phishing payloads"}],
            temperature=0.0,
            stream=False,
            timeout=5,
        )
    finally:
        backend.executor.shutdown(wait=False, cancel_futures=True)

    assert response["choices"][0]["message"]["content"] == "m1 response"
    assert response["metadata"]["policy_blocked"] is False
    assert response["metadata"]["selected_model"] == "m1"
    assert calls == ["m1"]


def test_provide_feedback_updates_status_metrics(adaptive_backend):
    adaptive_backend.provide_feedback("m1", 5, "code")
    status = adaptive_backend.get_status()
    assert status["metrics"]["m1"]["avg_rating"] == 5


def test_quality_hook_can_override_quality_score(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "DMS_ENABLED", False)
    register_quality_scoring_hook(
        lambda query, variant, response, context: {
            "score": 0.99,
            "source": "test_quality_hook",
        }
    )

    backend = AdaptiveLLMBackend()
    backend.metrics_file = str(tmp_path / "adaptive_metrics.json")
    backend.strategy = "routing"
    backend.models = [
        {
            "name": "m1",
            "backend": "ollama",
            "url": "http://localhost:11434/api/chat",
            "model": "m1",
        }
    ]

    def fake_call(model, messages, temperature, timeout):
        return {
            "model_name": model["name"],
            "response": "m1 response",
            "latency": 0.1,
            "success": True,
        }

    monkeypatch.setattr(backend, "_call_model", fake_call)

    try:
        response = backend.chat_completion(
            [{"role": "user", "content": "hello"}],
            temperature=0.0,
            stream=False,
            timeout=5,
        )
    finally:
        clear_quality_scoring_hook()
        backend.executor.shutdown(wait=False, cancel_futures=True)

    assert response["metadata"]["quality_hook_applied"] is True
    assert response["metadata"]["quality_hook_source"] == "test_quality_hook"
    assert response["metadata"]["quality_hook_score"] == pytest.approx(0.99)
    assert response["metadata"]["quality_score"] == pytest.approx(0.99)
    assert backend.routing_metrics["ab_variants"]["disabled"]["quality_sum"] == pytest.approx(
        0.99
    )


def test_dms_model_registration_when_enabled(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_URL", "http://dms.local/v1/chat/completions")
    monkeypatch.setattr(settings, "DMS_MODEL", "nvidia/Qwen3-8B-DMS-8x")
    monkeypatch.setattr(settings, "DMS_API_KEY", "")
    monkeypatch.setattr(settings, "OLLAMA_MODELS", [])
    monkeypatch.setattr(settings, "GLM_API_KEY", "")
    monkeypatch.setattr(settings, "NEMOTRON_API_KEY", "")

    backend = AdaptiveLLMBackend()
    backend.metrics_file = str(tmp_path / "adaptive_metrics.json")
    try:
        names = [model["name"] for model in backend.models]
        assert "dms" in names
    finally:
        backend.executor.shutdown(wait=False, cancel_futures=True)


def test_routing_prefers_dms_for_long_prompt(
    monkeypatch, tmp_path, reset_router_metrics, assert_zero_fallback_reason_counts
):
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_MIN_PROMPT_CHARS", 50)
    monkeypatch.setattr(settings, "DMS_TASK_TYPES", ["analysis", "code", "planning"])

    backend = AdaptiveLLMBackend()
    backend.metrics_file = str(tmp_path / "adaptive_metrics.json")
    reset_router_metrics(backend)
    backend.models = [
        {
            "name": "dms",
            "backend": "openai_compat",
            "url": "http://dms.local/v1/chat/completions",
            "model": "nvidia/Qwen3-8B-DMS-8x",
            "api_key": None,
        },
        {
            "name": "m1",
            "backend": "ollama",
            "url": "http://localhost:11434/api/chat",
            "model": "m1",
        },
    ]

    calls: list[str] = []

    def fake_call(model, messages, temperature, timeout):
        calls.append(model["name"])
        if model["name"] == "dms":
            return {
                "model_name": "dms",
                "response": "dms response",
                "latency": 0.2,
                "success": True,
                "usage_normalized": {
                    "prompt_tokens": 120,
                    "completion_tokens": 30,
                    "total_tokens": 150,
                    "cached_tokens": 40,
                },
            }
        return {
            "model_name": "m1",
            "response": "m1 response",
            "latency": 0.1,
            "success": True,
            "usage_normalized": {},
        }

    monkeypatch.setattr(backend, "_call_model", fake_call)

    try:
        response = backend.chat_completion(
            [{"role": "user", "content": "A" * 200}],
            temperature=0.0,
            stream=False,
            timeout=5,
        )
        assert response["choices"][0]["message"]["content"] == "dms response"
        assert response["metadata"]["selected_model"] == "dms"
        assert response["metadata"]["dms_used"] is True
        assert response["metadata"]["fallback_reason"] is None
        assert response["metadata"]["fallback_reason_code"] is None
        assert response["metadata"]["router_backend"] == "adaptive"
        assert response["metadata"]["router_policy_version"] == "cp2-2026-02-15"
        assert response["metadata"]["routing_trace_scheme"] == "sha256-v1"
        assert response["metadata"]["routing_trace_id"].startswith("rt_")
        assert len(response["metadata"]["routing_trace_fingerprint"]) == 64
        assert response["metadata"]["usage_normalized"] == {
            "prompt_tokens": 120,
            "completion_tokens": 30,
            "total_tokens": 150,
            "cached_tokens": 40,
        }
        usage_metrics = backend.routing_metrics["usage_economics"]
        assert usage_metrics["selected_samples"] == 1
        assert usage_metrics["selected_total_tokens"] == 150
        assert usage_metrics["selected_cached_tokens"] == 40
        assert usage_metrics["by_prompt_bucket"]["long"]["samples"] == 1
        status_usage = backend.get_status()["routing_metrics"]["usage_economics"]
        assert status_usage["selected_avg_total_tokens"] == 150.0
        assert status_usage["by_prompt_bucket"]["long"]["avg_total_tokens"] == 150.0
        assert calls == ["dms"]
        assert_zero_fallback_reason_counts(backend)
    finally:
        backend.executor.shutdown(wait=False, cancel_futures=True)


def test_control_variant_skips_dms_for_ab_experiment(
    monkeypatch, tmp_path, reset_router_metrics, assert_zero_fallback_reason_counts
):
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_MIN_PROMPT_CHARS", 50)
    monkeypatch.setattr(settings, "DMS_TASK_TYPES", ["analysis", "code", "planning"])
    monkeypatch.setattr(settings, "DMS_AB_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_AB_DMS_PERCENTAGE", 0)

    backend = AdaptiveLLMBackend()
    backend.metrics_file = str(tmp_path / "adaptive_metrics.json")
    reset_router_metrics(backend)
    backend.models = [
        {
            "name": "dms",
            "backend": "openai_compat",
            "url": "http://dms.local/v1/chat/completions",
            "model": "nvidia/Qwen3-8B-DMS-8x",
            "api_key": None,
        },
        {
            "name": "m1",
            "backend": "ollama",
            "url": "http://localhost:11434/api/chat",
            "model": "m1",
        },
    ]

    calls: list[str] = []

    def fake_call(model, messages, temperature, timeout):
        calls.append(model["name"])
        if model["name"] == "dms":
            return {
                "model_name": "dms",
                "response": "dms response",
                "latency": 0.2,
                "success": True,
            }
        return {
            "model_name": "m1",
            "response": "fallback model response",
            "latency": 0.1,
            "success": True,
        }

    monkeypatch.setattr(backend, "_call_model", fake_call)

    try:
        response = backend.chat_completion(
            [{"role": "user", "content": "A" * 200}],
            temperature=0.0,
            stream=False,
            timeout=5,
        )
        assert response["choices"][0]["message"]["content"] == "fallback model response"
        assert response["metadata"]["ab_variant"] == "control"
        assert response["metadata"]["selected_model"] == "m1"
        assert response["metadata"]["dms_used"] is False
        assert response["metadata"]["dms_candidate"] is True
        assert response["metadata"]["dms_attempted"] is False
        assert response["metadata"]["fallback_reason"] is None
        assert calls == ["m1"]
        assert backend.routing_metrics["ab_variants"]["control"]["requests"] == 1
        assert_zero_fallback_reason_counts(backend)
    finally:
        backend.executor.shutdown(wait=False, cancel_futures=True)


def test_fallback_when_dms_call_fails(monkeypatch, tmp_path, reset_router_metrics):
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_MIN_PROMPT_CHARS", 50)
    monkeypatch.setattr(settings, "DMS_TASK_TYPES", ["analysis", "code", "planning"])

    backend = AdaptiveLLMBackend()
    backend.metrics_file = str(tmp_path / "adaptive_metrics.json")
    backend.strategy = "voting"
    reset_router_metrics(backend)
    backend.models = [
        {
            "name": "dms",
            "backend": "openai_compat",
            "url": "http://dms.local/v1/chat/completions",
            "model": "nvidia/Qwen3-8B-DMS-8x",
            "api_key": None,
        },
        {
            "name": "m1",
            "backend": "ollama",
            "url": "http://localhost:11434/api/chat",
            "model": "m1",
        },
    ]

    def fake_call(model, messages, temperature, timeout):
        if model["name"] == "dms":
            return {
                "model_name": "dms",
                "response": "",
                "latency": 1.0,
                "success": False,
                "error": "connection timeout",
            }
        return {
            "model_name": "m1",
            "response": "fallback model response",
            "latency": 0.1,
            "success": True,
        }

    monkeypatch.setattr(backend, "_call_model", fake_call)

    try:
        response = backend.chat_completion(
            [{"role": "user", "content": "B" * 200}],
            temperature=0.0,
            stream=False,
            timeout=5,
        )
        assert response["choices"][0]["message"]["content"] == "fallback model response"
        assert response["metadata"]["selected_model"] == "m1"
        assert response["metadata"]["dms_used"] is False
        assert (
            response["metadata"]["fallback_reason"] == "dms_error: connection timeout"
        )
        assert response["metadata"]["fallback_reason_code"] == "dms_timeout"
        assert response["metadata"]["fallback_detail"] == "connection timeout"
        assert response["metadata"]["fallback_retryable"] is True
        assert response["metadata"]["fallback_stage"] == "dms_primary"
        assert backend.routing_metrics["fallback_reason_counts"]["dms_timeout"] == 1
        assert sum(backend.routing_metrics["fallback_reason_counts"].values()) == 1
    finally:
        backend.executor.shutdown(wait=False, cancel_futures=True)


def test_dms_error_budget_blocks_after_repeated_failures(
    monkeypatch, tmp_path, reset_router_metrics
):
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_MIN_PROMPT_CHARS", 50)
    monkeypatch.setattr(settings, "DMS_TASK_TYPES", ["analysis", "code", "planning"])
    monkeypatch.setattr(settings, "DMS_ERROR_BUDGET_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_ERROR_BUDGET_WINDOW", 3)
    monkeypatch.setattr(settings, "DMS_ERROR_BUDGET_MIN_ATTEMPTS", 3)
    monkeypatch.setattr(settings, "DMS_ERROR_BUDGET_MAX_FAILURE_RATE", 0.66)
    monkeypatch.setattr(settings, "DMS_ERROR_BUDGET_COOLDOWN_SECONDS", 60)

    backend = AdaptiveLLMBackend()
    backend.metrics_file = str(tmp_path / "adaptive_metrics.json")
    backend.strategy = "voting"
    reset_router_metrics(backend)
    backend.models = [
        {
            "name": "dms",
            "backend": "openai_compat",
            "url": "http://dms.local/v1/chat/completions",
            "model": "nvidia/Qwen3-8B-DMS-8x",
            "api_key": None,
        },
        {
            "name": "m1",
            "backend": "ollama",
            "url": "http://localhost:11434/api/chat",
            "model": "m1",
        },
    ]

    calls: list[str] = []

    def fake_call(model, messages, temperature, timeout):
        calls.append(model["name"])
        if model["name"] == "dms":
            return {
                "model_name": "dms",
                "response": "",
                "latency": 0.2,
                "success": False,
                "error": "connection timeout",
            }
        return {
            "model_name": "m1",
            "response": "fallback model response",
            "latency": 0.1,
            "success": True,
        }

    monkeypatch.setattr(backend, "_call_model", fake_call)

    try:
        for _ in range(3):
            backend.chat_completion(
                [{"role": "user", "content": "analyze " + ("B" * 200)}],
                temperature=0.0,
                stream=False,
                timeout=5,
            )

        response = backend.chat_completion(
            [{"role": "user", "content": "analyze " + ("B" * 200)}],
            temperature=0.0,
            stream=False,
            timeout=5,
        )
    finally:
        backend.executor.shutdown(wait=False, cancel_futures=True)

    assert calls.count("dms") == 3
    assert response["choices"][0]["message"]["content"] == "fallback model response"
    assert response["metadata"]["dms_budget_blocked"] is True
    assert response["metadata"]["dms_attempted"] is False
    assert response["metadata"]["dms_used"] is False
    assert backend.get_status()["dms_error_budget"]["temporarily_disabled"] is True


def test_dms_error_budget_reenables_after_cooldown(
    monkeypatch, tmp_path, reset_router_metrics
):
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_MIN_PROMPT_CHARS", 50)
    monkeypatch.setattr(settings, "DMS_TASK_TYPES", ["analysis", "code", "planning"])
    monkeypatch.setattr(settings, "DMS_ERROR_BUDGET_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_ERROR_BUDGET_WINDOW", 1)
    monkeypatch.setattr(settings, "DMS_ERROR_BUDGET_MIN_ATTEMPTS", 1)
    monkeypatch.setattr(settings, "DMS_ERROR_BUDGET_MAX_FAILURE_RATE", 1.0)
    monkeypatch.setattr(settings, "DMS_ERROR_BUDGET_COOLDOWN_SECONDS", 10)

    class _Clock:
        def __init__(self, now: float):
            self.now = now

        def time(self) -> float:
            return self.now

    clock = _Clock(now=1000.0)
    monkeypatch.setattr("merlin_adaptive_llm.time.time", clock.time)

    backend = AdaptiveLLMBackend()
    backend.metrics_file = str(tmp_path / "adaptive_metrics.json")
    backend.strategy = "voting"
    reset_router_metrics(backend)
    backend.models = [
        {
            "name": "dms",
            "backend": "openai_compat",
            "url": "http://dms.local/v1/chat/completions",
            "model": "nvidia/Qwen3-8B-DMS-8x",
            "api_key": None,
        },
        {
            "name": "m1",
            "backend": "ollama",
            "url": "http://localhost:11434/api/chat",
            "model": "m1",
        },
    ]

    dms_attempts = 0
    calls: list[str] = []

    def fake_call(model, messages, temperature, timeout):
        nonlocal dms_attempts
        calls.append(model["name"])
        if model["name"] == "dms":
            dms_attempts += 1
            if dms_attempts == 1:
                return {
                    "model_name": "dms",
                    "response": "",
                    "latency": 0.2,
                    "success": False,
                    "error": "connection timeout",
                }
            return {
                "model_name": "dms",
                "response": "recovered dms response",
                "latency": 0.2,
                "success": True,
            }
        return {
            "model_name": "m1",
            "response": "fallback model response",
            "latency": 0.1,
            "success": True,
        }

    monkeypatch.setattr(backend, "_call_model", fake_call)

    try:
        first = backend.chat_completion(
            [{"role": "user", "content": "analyze " + ("C" * 200)}],
            temperature=0.0,
            stream=False,
            timeout=5,
        )
        clock.now += 1
        second = backend.chat_completion(
            [{"role": "user", "content": "analyze " + ("C" * 200)}],
            temperature=0.0,
            stream=False,
            timeout=5,
        )
        clock.now += 11
        third = backend.chat_completion(
            [{"role": "user", "content": "analyze " + ("C" * 200)}],
            temperature=0.0,
            stream=False,
            timeout=5,
        )
    finally:
        backend.executor.shutdown(wait=False, cancel_futures=True)

    assert first["metadata"]["dms_attempted"] is True
    assert second["metadata"]["dms_budget_blocked"] is True
    assert second["metadata"]["dms_attempted"] is False
    assert third["metadata"]["dms_attempted"] is True
    assert third["metadata"]["dms_used"] is True
    assert third["choices"][0]["message"]["content"] == "recovered dms response"
    assert calls == ["dms", "m1", "m1", "dms"]
    assert backend.get_status()["dms_error_budget"]["temporarily_disabled"] is False


def test_dms_quality_autopause_blocks_after_low_quality_scores(
    monkeypatch, tmp_path, reset_router_metrics
):
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_MIN_PROMPT_CHARS", 50)
    monkeypatch.setattr(settings, "DMS_TASK_TYPES", ["analysis", "code", "planning"])
    monkeypatch.setattr(settings, "DMS_AB_ENABLED", False)
    monkeypatch.setattr(settings, "DMS_ERROR_BUDGET_ENABLED", False)
    monkeypatch.setattr(settings, "DMS_QUALITY_AUTOPAUSE_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_QUALITY_AUTOPAUSE_WINDOW", 3)
    monkeypatch.setattr(settings, "DMS_QUALITY_AUTOPAUSE_MIN_SAMPLES", 3)
    monkeypatch.setattr(settings, "DMS_QUALITY_AUTOPAUSE_MIN_AVG_SCORE", 0.8)
    monkeypatch.setattr(settings, "DMS_QUALITY_AUTOPAUSE_COOLDOWN_SECONDS", 60)

    backend = AdaptiveLLMBackend()
    backend.metrics_file = str(tmp_path / "adaptive_metrics.json")
    backend.strategy = "voting"
    reset_router_metrics(backend)
    backend.models = [
        {
            "name": "dms",
            "backend": "openai_compat",
            "url": "http://dms.local/v1/chat/completions",
            "model": "nvidia/Qwen3-8B-DMS-8x",
            "api_key": None,
        },
        {
            "name": "m1",
            "backend": "ollama",
            "url": "http://localhost:11434/api/chat",
            "model": "m1",
        },
    ]

    calls: list[str] = []

    def fake_call(model, messages, temperature, timeout):
        calls.append(model["name"])
        if model["name"] == "dms":
            return {
                "model_name": "dms",
                "response": "low quality dms response",
                "latency": 0.2,
                "success": True,
            }
        return {
            "model_name": "m1",
            "response": "control response",
            "latency": 0.1,
            "success": True,
        }

    monkeypatch.setattr(backend, "_call_model", fake_call)
    monkeypatch.setattr(backend, "_score_with_quality_hook", lambda *args, **kwargs: 0.2)

    try:
        for _ in range(3):
            backend.chat_completion(
                [{"role": "user", "content": "analyze " + ("Q" * 200)}],
                temperature=0.0,
                stream=False,
                timeout=5,
            )

        response = backend.chat_completion(
            [{"role": "user", "content": "analyze " + ("Q" * 200)}],
            temperature=0.0,
            stream=False,
            timeout=5,
        )
    finally:
        backend.executor.shutdown(wait=False, cancel_futures=True)

    assert calls == ["dms", "dms", "dms", "m1"]
    assert response["metadata"]["dms_budget_blocked"] is True
    assert response["metadata"]["dms_attempted"] is False
    assert response["metadata"]["selected_model"] == "m1"
    budget_status = backend.get_status()["dms_error_budget"]
    assert budget_status["quality_autopause_enabled"] is True
    assert budget_status["quality_samples"] == 3
    assert budget_status["avg_quality"] == pytest.approx(0.2)
    assert budget_status["last_trip_reason"] == "quality_score_below_threshold"
    assert budget_status["temporarily_disabled"] is True


def test_short_prompt_does_not_prefer_dms(
    monkeypatch, tmp_path, reset_router_metrics, assert_zero_fallback_reason_counts
):
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_MIN_PROMPT_CHARS", 500)
    monkeypatch.setattr(settings, "DMS_TASK_TYPES", ["analysis", "code", "planning"])

    backend = AdaptiveLLMBackend()
    backend.metrics_file = str(tmp_path / "adaptive_metrics.json")
    backend.strategy = "voting"
    reset_router_metrics(backend)
    backend.models = [
        {
            "name": "dms",
            "backend": "openai_compat",
            "url": "http://dms.local/v1/chat/completions",
            "model": "nvidia/Qwen3-8B-DMS-8x",
            "api_key": None,
        },
        {
            "name": "m1",
            "backend": "ollama",
            "url": "http://localhost:11434/api/chat",
            "model": "m1",
        },
    ]

    calls: list[str] = []

    def fake_call(model, messages, temperature, timeout):
        calls.append(model["name"])
        return {
            "model_name": model["name"],
            "response": f"{model['name']} response",
            "latency": 0.1,
            "success": True,
        }

    monkeypatch.setattr(backend, "_call_model", fake_call)

    try:
        response = backend.chat_completion(
            [
                {"role": "user", "content": "short question"},
                {"role": "user", "content": "hello"},
            ],
            temperature=0.0,
            stream=False,
            timeout=5,
        )
        assert response["choices"][0]["message"]["content"] == "m1 response"
        assert response["metadata"]["selected_model"] == "m1"
        assert response["metadata"]["dms_used"] is False
        assert calls == ["m1"]
        assert response["metadata"]["prompt_size_bucket"] == "short"
        assert_zero_fallback_reason_counts(backend)
    finally:
        backend.executor.shutdown(wait=False, cancel_futures=True)


def test_sensitive_task_guardrail_blocks_general_long_prompt(
    monkeypatch, tmp_path, reset_router_metrics, assert_zero_fallback_reason_counts
):
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_MIN_PROMPT_CHARS", 50)
    monkeypatch.setattr(settings, "DMS_TASK_TYPES", ["analysis", "code", "planning"])
    monkeypatch.setattr(settings, "DMS_AB_ENABLED", False)
    monkeypatch.setattr(settings, "DMS_SENSITIVE_TASK_GUARDRAIL_ENABLED", True)
    monkeypatch.setattr(settings, "MERLIN_ROUTER_FAST_SHORT_LANE_ENABLED", False)

    backend = AdaptiveLLMBackend()
    backend.metrics_file = str(tmp_path / "adaptive_metrics.json")
    backend.strategy = "voting"
    reset_router_metrics(backend)
    backend.models = [
        {
            "name": "dms",
            "backend": "openai_compat",
            "url": "http://dms.local/v1/chat/completions",
            "model": "nvidia/Qwen3-8B-DMS-8x",
            "api_key": None,
        },
        {
            "name": "m1",
            "backend": "ollama",
            "url": "http://localhost:11434/api/chat",
            "model": "m1",
        },
    ]

    calls: list[str] = []

    def fake_call(model, messages, temperature, timeout):
        calls.append(model["name"])
        return {
            "model_name": model["name"],
            "response": f"{model['name']} response",
            "latency": 0.1,
            "success": True,
        }

    monkeypatch.setattr(backend, "_call_model", fake_call)

    try:
        response = backend.chat_completion(
            [{"role": "user", "content": "lorem ipsum dolor sit amet " * 40}],
            temperature=0.0,
            stream=False,
            timeout=5,
        )
        assert response["choices"][0]["message"]["content"] == "m1 response"
        assert response["metadata"]["selected_model"] == "m1"
        assert response["metadata"]["dms_candidate"] is False
        assert response["metadata"]["dms_used"] is False
        assert calls == ["m1"]
        assert response["metadata"]["prompt_size_bucket"] == "long"
        assert_zero_fallback_reason_counts(backend)
    finally:
        backend.executor.shutdown(wait=False, cancel_futures=True)


def test_shadow_validation_runs_dms_without_changing_control_selection(
    monkeypatch, tmp_path, reset_router_metrics, assert_zero_fallback_reason_counts
):
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_MIN_PROMPT_CHARS", 50)
    monkeypatch.setattr(settings, "DMS_TASK_TYPES", ["analysis", "code", "planning"])
    monkeypatch.setattr(settings, "DMS_AB_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_AB_DMS_PERCENTAGE", 0)
    monkeypatch.setattr(settings, "DMS_SHADOW_VALIDATION_ENABLED", True)
    monkeypatch.setattr(settings, "MERLIN_ROUTER_FAST_SHORT_LANE_ENABLED", False)

    backend = AdaptiveLLMBackend()
    backend.metrics_file = str(tmp_path / "adaptive_metrics.json")
    backend.strategy = "voting"
    reset_router_metrics(backend)
    backend.models = [
        {
            "name": "dms",
            "backend": "openai_compat",
            "url": "http://dms.local/v1/chat/completions",
            "model": "nvidia/Qwen3-8B-DMS-8x",
            "api_key": None,
        },
        {
            "name": "m1",
            "backend": "ollama",
            "url": "http://localhost:11434/api/chat",
            "model": "m1",
        },
    ]

    calls: list[str] = []

    def fake_call(model, messages, temperature, timeout):
        calls.append(model["name"])
        if model["name"] == "dms":
            return {
                "model_name": "dms",
                "response": "shadow dms response",
                "latency": 0.2,
                "success": True,
                "usage_normalized": {
                    "prompt_tokens": 130,
                    "completion_tokens": 35,
                    "total_tokens": 165,
                    "cached_tokens": 55,
                },
            }
        return {
            "model_name": "m1",
            "response": "control response",
            "latency": 0.1,
            "success": True,
            "usage_normalized": {
                "prompt_tokens": 110,
                "completion_tokens": 20,
                "total_tokens": 130,
                "cached_tokens": 25,
            },
        }

    monkeypatch.setattr(backend, "_call_model", fake_call)

    try:
        response = backend.chat_completion(
            [{"role": "user", "content": "analyze " + ("A" * 200)}],
            temperature=0.0,
            stream=False,
            timeout=5,
        )
        assert response["choices"][0]["message"]["content"] == "control response"
        assert response["metadata"]["selected_model"] == "m1"
        assert response["metadata"]["dms_used"] is False
        assert response["metadata"]["ab_variant"] == "control"
        assert response["metadata"]["dms_shadow_executed"] is True
        assert response["metadata"]["dms_shadow_success"] is True
        assert response["metadata"]["dms_shadow_quality_score"] > 0
        assert response["metadata"]["usage_normalized"] == {
            "prompt_tokens": 110,
            "completion_tokens": 20,
            "total_tokens": 130,
            "cached_tokens": 25,
        }
        assert response["metadata"]["dms_shadow_usage_normalized"] == {
            "prompt_tokens": 130,
            "completion_tokens": 35,
            "total_tokens": 165,
            "cached_tokens": 55,
        }
        assert response["metadata"]["dms_shadow_usage_delta"] == {
            "prompt_tokens": 20,
            "completion_tokens": 15,
            "total_tokens": 35,
            "cached_tokens": 30,
        }
        assert calls == ["m1", "dms"]
        assert backend.routing_metrics["dms_shadow_attempted"] == 1
        assert backend.routing_metrics["dms_shadow_successes"] == 1
        assert backend.routing_metrics["dms_shadow_failures"] == 0
        usage_metrics = backend.routing_metrics["usage_economics"]
        assert usage_metrics["selected_samples"] == 1
        assert usage_metrics["shadow_delta_samples"] == 1
        assert usage_metrics["shadow_dms_minus_control_total_tokens_sum"] == 35
        assert usage_metrics["shadow_dms_minus_control_cached_tokens_sum"] == 30
        status_usage = backend.get_status()["routing_metrics"]["usage_economics"]
        assert status_usage["selected_avg_total_tokens"] == 130.0
        assert status_usage["shadow_dms_minus_control_avg_total_tokens"] == 35.0
        assert status_usage["shadow_dms_minus_control_avg_cached_tokens"] == 30.0
        assert_zero_fallback_reason_counts(backend)
    finally:
        backend.executor.shutdown(wait=False, cancel_futures=True)


def test_token_aware_bucket_can_prefer_dms_when_char_threshold_not_met(
    monkeypatch, tmp_path, reset_router_metrics, assert_zero_fallback_reason_counts
):
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_MIN_PROMPT_CHARS", 10000)
    monkeypatch.setattr(settings, "DMS_MIN_PROMPT_TOKENS", 1500)
    monkeypatch.setattr(settings, "MERLIN_PROMPT_BUCKET_TOKEN_AWARE", True)
    monkeypatch.setattr(settings, "DMS_TASK_TYPES", ["analysis", "code", "planning"])
    monkeypatch.setattr(settings, "DMS_AB_ENABLED", False)

    backend = AdaptiveLLMBackend()
    backend.metrics_file = str(tmp_path / "adaptive_metrics.json")
    backend.strategy = "voting"
    reset_router_metrics(backend)
    backend.models = [
        {
            "name": "dms",
            "backend": "openai_compat",
            "url": "http://dms.local/v1/chat/completions",
            "model": "nvidia/Qwen3-8B-DMS-8x",
            "api_key": None,
        },
        {
            "name": "m1",
            "backend": "ollama",
            "url": "http://localhost:11434/api/chat",
            "model": "m1",
        },
    ]

    calls: list[str] = []

    def fake_call(model, messages, temperature, timeout):
        calls.append(model["name"])
        if model["name"] == "dms":
            return {
                "model_name": "dms",
                "response": "token-aware dms response",
                "latency": 0.2,
                "success": True,
            }
        return {
            "model_name": "m1",
            "response": "m1 response",
            "latency": 0.1,
            "success": True,
        }

    monkeypatch.setattr(backend, "_call_model", fake_call)
    query = "reasoning " * 1600

    try:
        response = backend.chat_completion(
            [{"role": "user", "content": query}],
            temperature=0.0,
            stream=False,
            timeout=5,
        )
        assert response["choices"][0]["message"]["content"] == "token-aware dms response"
        assert response["metadata"]["selected_model"] == "dms"
        assert response["metadata"]["dms_used"] is True
        assert response["metadata"]["dms_candidate"] is True
        assert response["metadata"]["prompt_size_bucket"] == "long"
        assert calls == ["dms"]
        assert_zero_fallback_reason_counts(backend)
    finally:
        backend.executor.shutdown(wait=False, cancel_futures=True)


def test_uncertainty_routing_blocks_simple_long_prompt(
    monkeypatch, tmp_path, reset_router_metrics, assert_zero_fallback_reason_counts
):
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_MIN_PROMPT_CHARS", 50)
    monkeypatch.setattr(settings, "DMS_TASK_TYPES", ["analysis", "code", "planning"])
    monkeypatch.setattr(settings, "DMS_AB_ENABLED", False)
    monkeypatch.setattr(settings, "DMS_UNCERTAINTY_ROUTING_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_UNCERTAINTY_SCORE_THRESHOLD", 0.55)
    monkeypatch.setattr(settings, "MERLIN_ROUTER_FAST_SHORT_LANE_ENABLED", False)

    backend = AdaptiveLLMBackend()
    backend.metrics_file = str(tmp_path / "adaptive_metrics.json")
    backend.strategy = "voting"
    reset_router_metrics(backend)
    backend.models = [
        {
            "name": "dms",
            "backend": "openai_compat",
            "url": "http://dms.local/v1/chat/completions",
            "model": "nvidia/Qwen3-8B-DMS-8x",
            "api_key": None,
        },
        {
            "name": "m1",
            "backend": "ollama",
            "url": "http://localhost:11434/api/chat",
            "model": "m1",
        },
    ]

    calls: list[str] = []

    def fake_call(model, messages, temperature, timeout):
        calls.append(model["name"])
        return {
            "model_name": model["name"],
            "response": f"{model['name']} response",
            "latency": 0.1,
            "success": True,
        }

    monkeypatch.setattr(backend, "_call_model", fake_call)

    try:
        response = backend.chat_completion(
            [{"role": "user", "content": "A" * 220}],
            temperature=0.0,
            stream=False,
            timeout=5,
        )
        assert response["choices"][0]["message"]["content"] == "m1 response"
        assert response["metadata"]["selected_model"] == "m1"
        assert response["metadata"]["dms_used"] is False
        assert response["metadata"]["dms_candidate"] is False
        assert calls == ["m1"]
        assert response["metadata"]["prompt_size_bucket"] == "long"
        assert_zero_fallback_reason_counts(backend)
    finally:
        backend.executor.shutdown(wait=False, cancel_futures=True)


def test_fast_short_lane_selects_single_preferred_model(
    monkeypatch, tmp_path, reset_router_metrics, assert_zero_fallback_reason_counts
):
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "MERLIN_ROUTER_FAST_SHORT_LANE_ENABLED", True)
    monkeypatch.setattr(settings, "MERLIN_ROUTER_FAST_SHORT_CHAR_MAX", 200)

    backend = AdaptiveLLMBackend()
    backend.metrics_file = str(tmp_path / "adaptive_metrics.json")
    backend.strategy = "voting"
    reset_router_metrics(backend)
    backend.models = [
        {
            "name": "dms",
            "backend": "openai_compat",
            "url": "http://dms.local/v1/chat/completions",
            "model": "nvidia/Qwen3-8B-DMS-8x",
            "api_key": None,
        },
        {
            "name": "llama3.2",
            "backend": "ollama",
            "url": "http://localhost:11434/api/chat",
            "model": "llama3.2",
        },
        {
            "name": "m1",
            "backend": "ollama",
            "url": "http://localhost:11434/api/chat",
            "model": "m1",
        },
    ]

    calls: list[str] = []

    def fake_call(model, messages, temperature, timeout):
        calls.append(model["name"])
        return {
            "model_name": model["name"],
            "response": f"{model['name']} response",
            "latency": 0.05,
            "success": True,
        }

    monkeypatch.setattr(backend, "_call_model", fake_call)

    try:
        response = backend.chat_completion(
            [{"role": "user", "content": "quick update"}],
            temperature=0.0,
            stream=False,
            timeout=5,
        )
        assert response["choices"][0]["message"]["content"] == "llama3.2 response"
        assert response["metadata"]["selected_model"] == "llama3.2"
        assert response["metadata"]["fast_short_lane"] is True
        assert response["metadata"]["fast_short_lane_model"] == "llama3.2"
        assert response["metadata"]["dms_candidate"] is False
        assert calls == ["llama3.2"]
        assert_zero_fallback_reason_counts(backend)
    finally:
        backend.executor.shutdown(wait=False, cancel_futures=True)


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(
            {
                "query": "hello",
                "strategy": "routing",
                "settings": with_uncertainty_disabled(
                    {
                        "DMS_MIN_PROMPT_CHARS": 500,
                        "MERLIN_ROUTER_FAST_SHORT_LANE_ENABLED": False,
                        "MERLIN_PROMPT_BUCKET_TOKEN_AWARE": False,
                    }
                ),
                "responses": {
                    "m1": {"response": "m1 response", "latency": 0.05, "success": True},
                    "m2": {"response": "m2 response", "latency": 0.2, "success": True},
                },
                "expected": {
                    "selected_model": "m1",
                    "dms_used": False,
                    "dms_candidate": False,
                },
                "expected_calls": {"llama3.2", "m1", "m2"},
            },
            id="short-fastest-non-dms",
        ),
        pytest.param(
            {
                "query": SIMPLE_LONG_PROMPT_QUERY,
                "strategy": "routing",
                "settings": with_uncertainty_disabled(
                    {
                        "DMS_MIN_PROMPT_CHARS": 50,
                        "MERLIN_ROUTER_FAST_SHORT_LANE_ENABLED": False,
                        "MERLIN_PROMPT_BUCKET_TOKEN_AWARE": False,
                    }
                ),
                "responses": {
                    "dms": {"response": "dms response", "latency": 0.2, "success": True},
                    "m1": {"response": "m1 response", "latency": 0.1, "success": True},
                    "m2": {"response": "m2 response", "latency": 0.3, "success": True},
                },
                "expected": {
                    "selected_model": "dms",
                    "dms_used": True,
                    "dms_candidate": True,
                },
                "expected_calls": {"dms"},
            },
            id="long-prefers-dms",
        ),
        pytest.param(
            {
                "query": "quick update",
                "strategy": "voting",
                "settings": with_uncertainty_disabled(
                    {
                        "DMS_MIN_PROMPT_CHARS": 500,
                        "MERLIN_ROUTER_FAST_SHORT_LANE_ENABLED": True,
                        "MERLIN_ROUTER_FAST_SHORT_CHAR_MAX": 200,
                        "MERLIN_PROMPT_BUCKET_TOKEN_AWARE": False,
                    }
                ),
                "responses": {
                    "llama3.2": {
                        "response": "llama3.2 response",
                        "latency": 0.05,
                        "success": True,
                    },
                    "m1": {"response": "m1 response", "latency": 0.1, "success": True},
                },
                "expected": {
                    "selected_model": "llama3.2",
                    "dms_used": False,
                    "dms_candidate": False,
                    "fast_short_lane": True,
                },
                "expected_calls": {"llama3.2"},
            },
            id="fast-short-lane-llama",
        ),
        pytest.param(
            {
                "query": "analysis " * 1700,
                "strategy": "routing",
                "settings": with_uncertainty_disabled(
                    {
                        "DMS_MIN_PROMPT_CHARS": 10000,
                        "DMS_MIN_PROMPT_TOKENS": 1500,
                        "MERLIN_ROUTER_FAST_SHORT_LANE_ENABLED": False,
                        "MERLIN_PROMPT_BUCKET_TOKEN_AWARE": True,
                    }
                ),
                "responses": {
                    "dms": {
                        "response": "token-aware dms response",
                        "latency": 0.2,
                        "success": True,
                    },
                    "m1": {"response": "m1 response", "latency": 0.1, "success": True},
                },
                "expected": {
                    "selected_model": "dms",
                    "dms_used": True,
                    "dms_candidate": True,
                    "prompt_size_bucket": "long",
                },
                "expected_calls": {"dms"},
            },
            id="token-aware-prefers-dms",
        ),
        pytest.param(
            {
                "query": SIMPLE_LONG_PROMPT_QUERY,
                "strategy": "routing",
                "settings": with_uncertainty_enabled(
                    {
                        "DMS_MIN_PROMPT_CHARS": 50,
                        "MERLIN_ROUTER_FAST_SHORT_LANE_ENABLED": False,
                        "MERLIN_PROMPT_BUCKET_TOKEN_AWARE": False,
                    }
                ),
                "responses": {
                    "m1": {"response": "m1 response", "latency": 0.05, "success": True},
                    "m2": {"response": "m2 response", "latency": 0.2, "success": True},
                },
                "expected": {
                    "selected_model": "m1",
                    "dms_used": False,
                    "dms_candidate": False,
                    "prompt_size_bucket": "long",
                },
                "expected_calls": {"llama3.2", "m1", "m2"},
            },
            id="uncertainty-mode-blocks-simple-long",
        ),
        pytest.param(
            {
                "query": UNCERTAIN_REASONING_QUERY,
                "strategy": "routing",
                "settings": with_uncertainty_enabled(
                    {
                        "DMS_MIN_PROMPT_CHARS": 50,
                        "MERLIN_ROUTER_FAST_SHORT_LANE_ENABLED": False,
                        "MERLIN_PROMPT_BUCKET_TOKEN_AWARE": False,
                    }
                ),
                "responses": {
                    "dms": {"response": "dms response", "latency": 0.2, "success": True},
                    "m1": {"response": "m1 response", "latency": 0.1, "success": True},
                    "m2": {"response": "m2 response", "latency": 0.3, "success": True},
                },
                "expected": {
                    "selected_model": "dms",
                    "dms_used": True,
                    "dms_candidate": True,
                },
                "expected_calls": {"dms"},
            },
            id="uncertainty-mode-prefers-uncertain-reasoning",
        ),
    ],
)
def test_adaptive_router_selection_regression_corpus(
    case, monkeypatch, tmp_path, reset_router_metrics
):
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_TASK_TYPES", ["analysis", "code", "planning"])
    monkeypatch.setattr(settings, "DMS_AB_ENABLED", False)
    for key, value in case["settings"].items():
        monkeypatch.setattr(settings, key, value)

    backend = AdaptiveLLMBackend()
    backend.metrics_file = str(tmp_path / "adaptive_metrics.json")
    backend.strategy = case["strategy"]
    backend.learning_mode = False
    reset_router_metrics(backend)
    backend.models = [
        {
            "name": "dms",
            "backend": "openai_compat",
            "url": "http://dms.local/v1/chat/completions",
            "model": "nvidia/Qwen3-8B-DMS-8x",
            "api_key": None,
        },
        {
            "name": "llama3.2",
            "backend": "ollama",
            "url": "http://localhost:11434/api/chat",
            "model": "llama3.2",
        },
        {
            "name": "m1",
            "backend": "ollama",
            "url": "http://localhost:11434/api/chat",
            "model": "m1",
        },
        {
            "name": "m2",
            "backend": "ollama",
            "url": "http://localhost:11434/api/chat",
            "model": "m2",
        },
    ]

    calls: list[str] = []

    def fake_call(model, messages, temperature, timeout):
        calls.append(model["name"])
        result = case["responses"].get(model["name"])
        if result is None:
            return {
                "model_name": model["name"],
                "response": f"{model['name']} response",
                "latency": 0.2,
                "success": True,
            }
        payload = {
            "model_name": model["name"],
            "response": result["response"],
            "latency": result["latency"],
            "success": result["success"],
        }
        if not result["success"]:
            payload["error"] = result.get("error", "simulated failure")
        return payload

    monkeypatch.setattr(backend, "_call_model", fake_call)

    try:
        response = backend.chat_completion(
            [{"role": "user", "content": case["query"]}],
            temperature=0.0,
            stream=False,
            timeout=5,
        )
    finally:
        backend.executor.shutdown(wait=False, cancel_futures=True)

    metadata = response["metadata"]
    for key, expected_value in case["expected"].items():
        assert metadata[key] == expected_value
    assert set(calls) == case["expected_calls"]
    assert metadata["router_backend"] == "adaptive"


def test_openai_compat_payload_sends_top_level_temperature(monkeypatch):
    model = {
        "name": "dms",
        "backend": "openai_compat",
        "url": "http://dms.local/v1/chat/completions",
        "model": "nvidia/Qwen3-8B-DMS-8x",
    }
    backend = AdaptiveLLMBackend.__new__(AdaptiveLLMBackend)
    captured: dict = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "choices": [{"message": {"content": "ok"}}],
            }

        def raise_for_status(self):
            return None

    class FakeRequests:
        @staticmethod
        def post(url, json, headers, timeout):
            captured["payload"] = json
            captured["url"] = url
            captured["headers"] = headers
            captured["timeout"] = timeout
            return FakeResponse()

    monkeypatch.setattr("merlin_adaptive_llm.requests", FakeRequests)
    backend.model = None
    result = backend._call_model(model, [{"role": "user", "content": "hello"}], 0.7, 5)

    assert result["response"] == "ok"
    assert result["model_name"] == "dms"
    assert captured["payload"]["model"] == "nvidia/Qwen3-8B-DMS-8x"
    assert captured["payload"]["temperature"] == 0.7
    assert "options" not in captured["payload"]


def test_openai_compatible_content_extractor_supports_alternate_shapes():
    assert (
        AdaptiveLLMBackend._extract_openai_compatible_content(
            {"content": "top-level-content"}
        )
        == "top-level-content"
    )
    assert (
        AdaptiveLLMBackend._extract_openai_compatible_content(
            {"choices": [{"text": "legacy-text"}]}
        )
        == "legacy-text"
    )
    assert (
        AdaptiveLLMBackend._extract_openai_compatible_content(
            {"choices": [{"message": {"content": "choice-message"}}]}
        )
        == "choice-message"
    )
