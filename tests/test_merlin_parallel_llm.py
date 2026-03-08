from __future__ import annotations

import merlin_settings as settings
import pytest
import requests
from merlin_parallel_llm import ModelConfig, ModelResponse, ParallelLLMBackend
from routing_regression_corpus import (
    SIMPLE_LONG_PROMPT_QUERY,
    UNCERTAIN_REASONING_QUERY,
    with_uncertainty_disabled,
    with_uncertainty_enabled,
)


@pytest.fixture(autouse=True)
def _reset_prompt_bucket_mode(monkeypatch):
    monkeypatch.setattr(settings, "MERLIN_PROMPT_BUCKET_TOKEN_AWARE", False)
    monkeypatch.setattr(settings, "DMS_MIN_PROMPT_TOKENS", 1500)
    monkeypatch.setattr(settings, "MERLIN_ROUTER_FAST_SHORT_LANE_ENABLED", True)
    monkeypatch.setattr(settings, "MERLIN_ROUTER_FAST_SHORT_CHAR_MAX", 160)


def test_dms_model_registration_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_URL", "http://dms.local/v1/chat/completions")
    monkeypatch.setattr(settings, "DMS_MODEL", "nvidia/Qwen3-8B-DMS-8x")
    monkeypatch.setattr(settings, "DMS_API_KEY", "")
    monkeypatch.setattr(settings, "OLLAMA_MODELS", [])
    monkeypatch.setattr(settings, "GLM_API_KEY", "")
    monkeypatch.setattr(settings, "NEMOTRON_API_KEY", "")

    backend = ParallelLLMBackend()
    try:
        names = [model.name for model in backend.models]
        assert "dms" in names
    finally:
        backend.executor.shutdown(wait=False, cancel_futures=True)


def test_call_model_normalizes_openai_compatible_usage(monkeypatch):
    backend = ParallelLLMBackend()

    class _FakeResponse:
        def raise_for_status(self):
            return None

        @staticmethod
        def json():
            return {
                "choices": [{"message": {"content": "ok"}}],
                "usage": {
                    "input_tokens": 44,
                    "output_tokens": 11,
                    "cache_read_input_tokens": 19,
                },
            }

    class _FakeRequests:
        @staticmethod
        def post(url, json, headers=None, timeout=30):
            return _FakeResponse()

    monkeypatch.setattr("merlin_parallel_llm.requests", _FakeRequests)

    try:
        result = backend._call_model(
            ModelConfig(
                name="dms",
                backend="openai_compat",
                url="http://dms.local/v1/chat/completions",
                model="dms-test",
            ),
            [{"role": "user", "content": "test"}],
            0.0,
            5,
        )
        assert result.success is True
        assert result.response == "ok"
        assert result.usage_normalized == {
            "prompt_tokens": 44,
            "completion_tokens": 11,
            "total_tokens": 55,
            "cached_tokens": 19,
        }
    finally:
        backend.executor.shutdown(wait=False, cancel_futures=True)


def test_call_model_includes_rate_limit_headers_in_http_error_detail(monkeypatch):
    backend = ParallelLLMBackend()

    class _Response:
        headers = {
            "X-RateLimit-Remaining-Requests": "0",
            "x-ratelimit-reset-requests": "15ms",
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

    monkeypatch.setattr("merlin_parallel_llm.requests", _FakeRequests)

    try:
        result = backend._call_model(
            ModelConfig(
                name="dms",
                backend="openai_compat",
                url="http://dms.local/v1/chat/completions",
                model="dms-test",
            ),
            [{"role": "user", "content": "test"}],
            0.0,
            5,
        )
        assert result.success is False
        assert "HTTP 429" in str(result.error)
        assert "x-ratelimit-remaining-requests=0" in str(result.error)
        assert "x-ratelimit-reset-requests=15ms" in str(result.error)
    finally:
        backend.executor.shutdown(wait=False, cancel_futures=True)


def test_routing_prefers_dms_for_long_prompt(
    monkeypatch, reset_router_metrics, assert_zero_fallback_reason_counts
):
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_MIN_PROMPT_CHARS", 50)
    monkeypatch.setattr(settings, "DMS_TASK_TYPES", ["analysis", "code", "planning"])

    backend = ParallelLLMBackend()
    backend.strategy = "voting"
    reset_router_metrics(backend)
    backend.models = [
        ModelConfig(
            name="dms",
            backend="openai_compat",
            url="http://dms.local/v1/chat/completions",
            model="nvidia/Qwen3-8B-DMS-8x",
        ),
        ModelConfig(
            name="m1",
            backend="ollama",
            url="http://localhost:11434/api/chat",
            model="m1",
        ),
    ]

    calls: list[str] = []

    def fake_call(model, messages, temperature, timeout):
        calls.append(model.name)
        if model.name == "dms":
            return ModelResponse(
                model_name="dms",
                response="dms response",
                latency=0.2,
                success=True,
                usage_normalized={
                    "prompt_tokens": 80,
                    "completion_tokens": 20,
                    "total_tokens": 100,
                    "cached_tokens": 30,
                },
            )
        return ModelResponse(
            model_name="m1",
            response="m1 response",
            latency=0.1,
            success=True,
            usage_normalized={},
        )

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
        assert response["metadata"]["router_backend"] == "parallel"
        assert response["metadata"]["router_policy_version"] == "cp2-2026-02-15"
        assert response["metadata"]["routing_trace_scheme"] == "sha256-v1"
        assert response["metadata"]["routing_trace_id"].startswith("rt_")
        assert len(response["metadata"]["routing_trace_fingerprint"]) == 64
        assert response["metadata"]["usage_normalized"] == {
            "prompt_tokens": 80,
            "completion_tokens": 20,
            "total_tokens": 100,
            "cached_tokens": 30,
        }
        usage_metrics = backend.routing_metrics["usage_economics"]
        assert usage_metrics["selected_samples"] == 1
        assert usage_metrics["selected_total_tokens"] == 100
        assert usage_metrics["by_prompt_bucket"]["long"]["samples"] == 1
        assert usage_metrics["by_ab_variant"]["dms"]["samples"] == 1
        status_usage = backend.get_status()["routing_metrics"]["usage_economics"]
        assert status_usage["selected_avg_total_tokens"] == 100.0
        assert status_usage["by_prompt_bucket"]["long"]["avg_total_tokens"] == 100.0
        assert status_usage["by_ab_variant"]["dms"]["avg_total_tokens"] == 100.0
        assert calls == ["dms"]
        assert_zero_fallback_reason_counts(backend)
    finally:
        backend.executor.shutdown(wait=False, cancel_futures=True)


def test_fallback_when_dms_call_fails(monkeypatch, reset_router_metrics):
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_MIN_PROMPT_CHARS", 50)
    monkeypatch.setattr(settings, "DMS_TASK_TYPES", ["analysis", "code", "planning"])

    backend = ParallelLLMBackend()
    backend.strategy = "voting"
    reset_router_metrics(backend)
    backend.models = [
        ModelConfig(
            name="dms",
            backend="openai_compat",
            url="http://dms.local/v1/chat/completions",
            model="nvidia/Qwen3-8B-DMS-8x",
        ),
        ModelConfig(
            name="m1",
            backend="ollama",
            url="http://localhost:11434/api/chat",
            model="m1",
        ),
    ]

    def fake_call(model, messages, temperature, timeout):
        if model.name == "dms":
            return ModelResponse(
                model_name="dms",
                response="",
                latency=1.0,
                success=False,
                error="connection timeout",
            )
        return ModelResponse(
            model_name="m1",
            response="fallback model response",
            latency=0.1,
            success=True,
        )

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


def test_short_prompt_does_not_prefer_dms(
    monkeypatch, reset_router_metrics, assert_zero_fallback_reason_counts
):
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_MIN_PROMPT_CHARS", 500)
    monkeypatch.setattr(settings, "DMS_TASK_TYPES", ["analysis", "code", "planning"])

    backend = ParallelLLMBackend()
    backend.strategy = "voting"
    reset_router_metrics(backend)
    backend.models = [
        ModelConfig(
            name="dms",
            backend="openai_compat",
            url="http://dms.local/v1/chat/completions",
            model="nvidia/Qwen3-8B-DMS-8x",
        ),
        ModelConfig(
            name="m1",
            backend="ollama",
            url="http://localhost:11434/api/chat",
            model="m1",
        ),
    ]

    calls: list[str] = []

    def fake_call(model, messages, temperature, timeout):
        calls.append(model.name)
        if model.name == "dms":
            return ModelResponse(
                model_name="dms", response="dms response", latency=0.2, success=True
            )
        return ModelResponse(
            model_name="m1",
            response="fallback model response",
            latency=0.1,
            success=True,
        )

    monkeypatch.setattr(backend, "_call_model", fake_call)

    try:
        response = backend.chat_completion(
            [{"role": "user", "content": "A quick hello"}],
            temperature=0.0,
            stream=False,
            timeout=5,
        )
        assert response["choices"][0]["message"]["content"] == "fallback model response"
        assert response["metadata"]["selected_model"] == "m1"
        assert response["metadata"]["dms_used"] is False
        assert calls == ["m1"]
        assert response["metadata"]["prompt_size_bucket"] == "short"
        assert response["metadata"]["fallback_reason"] is None
        assert_zero_fallback_reason_counts(backend)
    finally:
        backend.executor.shutdown(wait=False, cancel_futures=True)


def test_token_aware_bucket_can_prefer_dms_when_char_threshold_not_met(
    monkeypatch, reset_router_metrics, assert_zero_fallback_reason_counts
):
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_MIN_PROMPT_CHARS", 10000)
    monkeypatch.setattr(settings, "DMS_MIN_PROMPT_TOKENS", 1500)
    monkeypatch.setattr(settings, "MERLIN_PROMPT_BUCKET_TOKEN_AWARE", True)
    monkeypatch.setattr(settings, "DMS_TASK_TYPES", ["analysis", "code", "planning"])
    monkeypatch.setattr(settings, "DMS_AB_ENABLED", False)

    backend = ParallelLLMBackend()
    backend.strategy = "voting"
    reset_router_metrics(backend)
    backend.models = [
        ModelConfig(
            name="dms",
            backend="openai_compat",
            url="http://dms.local/v1/chat/completions",
            model="nvidia/Qwen3-8B-DMS-8x",
        ),
        ModelConfig(
            name="m1",
            backend="ollama",
            url="http://localhost:11434/api/chat",
            model="m1",
        ),
    ]

    calls: list[str] = []

    def fake_call(model, messages, temperature, timeout):
        calls.append(model.name)
        if model.name == "dms":
            return ModelResponse(
                model_name="dms",
                response="token-aware dms response",
                latency=0.2,
                success=True,
            )
        return ModelResponse(
            model_name="m1",
            response="m1 response",
            latency=0.1,
            success=True,
        )

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


def test_fast_short_lane_selects_single_preferred_model(
    monkeypatch, reset_router_metrics, assert_zero_fallback_reason_counts
):
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "MERLIN_ROUTER_FAST_SHORT_LANE_ENABLED", True)
    monkeypatch.setattr(settings, "MERLIN_ROUTER_FAST_SHORT_CHAR_MAX", 200)

    backend = ParallelLLMBackend()
    backend.strategy = "voting"
    reset_router_metrics(backend)
    backend.models = [
        ModelConfig(
            name="dms",
            backend="openai_compat",
            url="http://dms.local/v1/chat/completions",
            model="nvidia/Qwen3-8B-DMS-8x",
        ),
        ModelConfig(
            name="llama3.2",
            backend="ollama",
            url="http://localhost:11434/api/chat",
            model="llama3.2",
        ),
        ModelConfig(
            name="m1",
            backend="ollama",
            url="http://localhost:11434/api/chat",
            model="m1",
        ),
    ]

    calls: list[str] = []

    def fake_call(model, messages, temperature, timeout):
        calls.append(model.name)
        return ModelResponse(
            model_name=model.name,
            response=f"{model.name} response",
            latency=0.05,
            success=True,
        )

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
                "query": "quick summary",
                "strategy": "routing",
                "settings": with_uncertainty_disabled(
                    {
                        "DMS_MIN_PROMPT_CHARS": 500,
                        "MERLIN_ROUTER_FAST_SHORT_LANE_ENABLED": False,
                        "MERLIN_PROMPT_BUCKET_TOKEN_AWARE": False,
                    }
                ),
                "responses": {
                    "llama3.2": {
                        "response": "llama response",
                        "latency": 0.05,
                        "success": True,
                    },
                    "m1": {"response": "m1 response", "latency": 0.1, "success": True},
                },
                "expected": {
                    "selected_model": "llama3.2",
                    "dms_used": False,
                    "dms_candidate": False,
                },
            },
            id="short-routing-prefers-llama",
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
                    "llama3.2": {
                        "response": "llama response",
                        "latency": 0.05,
                        "success": True,
                    },
                },
                "expected": {
                    "selected_model": "dms",
                    "dms_used": True,
                    "dms_candidate": True,
                },
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
                        "response": "llama response",
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
                    "llama3.2": {
                        "response": "llama response",
                        "latency": 0.05,
                        "success": True,
                    },
                },
                "expected": {
                    "selected_model": "dms",
                    "dms_used": True,
                    "dms_candidate": True,
                    "prompt_size_bucket": "long",
                },
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
                    "llama3.2": {
                        "response": "llama response",
                        "latency": 0.05,
                        "success": True,
                    },
                    "m1": {"response": "m1 response", "latency": 0.1, "success": True},
                },
                "expected": {
                    "selected_model": "llama3.2",
                    "dms_used": False,
                    "dms_candidate": False,
                    "prompt_size_bucket": "long",
                },
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
                    "llama3.2": {
                        "response": "llama response",
                        "latency": 0.05,
                        "success": True,
                    },
                },
                "expected": {
                    "selected_model": "dms",
                    "dms_used": True,
                    "dms_candidate": True,
                },
            },
            id="uncertainty-mode-prefers-uncertain-reasoning",
        ),
    ],
)
def test_parallel_router_selection_regression_corpus(
    case, monkeypatch, reset_router_metrics
):
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_TASK_TYPES", ["analysis", "code", "planning"])
    monkeypatch.setattr(settings, "DMS_AB_ENABLED", False)
    for key, value in case["settings"].items():
        monkeypatch.setattr(settings, key, value)

    backend = ParallelLLMBackend()
    backend.strategy = case["strategy"]
    reset_router_metrics(backend)
    backend.models = [
        ModelConfig(
            name="dms",
            backend="openai_compat",
            url="http://dms.local/v1/chat/completions",
            model="nvidia/Qwen3-8B-DMS-8x",
        ),
        ModelConfig(
            name="llama3.2",
            backend="ollama",
            url="http://localhost:11434/api/chat",
            model="llama3.2",
        ),
        ModelConfig(
            name="m1",
            backend="ollama",
            url="http://localhost:11434/api/chat",
            model="m1",
        ),
    ]

    def fake_call(model, messages, temperature, timeout):
        result = case["responses"].get(model.name)
        if result is None:
            return ModelResponse(
                model_name=model.name,
                response=f"{model.name} response",
                latency=0.2,
                success=True,
            )
        return ModelResponse(
            model_name=model.name,
            response=result["response"],
            latency=result["latency"],
            success=result["success"],
            error=result.get("error"),
        )

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
    assert metadata["router_backend"] == "parallel"


def test_control_variant_skips_dms_for_ab_experiment(
    monkeypatch, reset_router_metrics, assert_zero_fallback_reason_counts
):
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_MIN_PROMPT_CHARS", 50)
    monkeypatch.setattr(settings, "DMS_TASK_TYPES", ["analysis", "code", "planning"])
    monkeypatch.setattr(settings, "DMS_AB_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_AB_DMS_PERCENTAGE", 0)

    backend = ParallelLLMBackend()
    backend.strategy = "voting"
    reset_router_metrics(backend)
    backend.models = [
        ModelConfig(
            name="dms",
            backend="openai_compat",
            url="http://dms.local/v1/chat/completions",
            model="nvidia/Qwen3-8B-DMS-8x",
        ),
        ModelConfig(
            name="m1",
            backend="ollama",
            url="http://localhost:11434/api/chat",
            model="m1",
        ),
    ]

    calls: list[str] = []

    def fake_call(model, messages, temperature, timeout):
        calls.append(model.name)
        if model.name == "dms":
            return ModelResponse(
                model_name="dms",
                response="dms response",
                latency=0.2,
                success=True,
                usage_normalized={
                    "prompt_tokens": 130,
                    "completion_tokens": 35,
                    "total_tokens": 165,
                    "cached_tokens": 45,
                },
            )
        return ModelResponse(
            model_name="m1",
            response="m1 response",
            latency=0.1,
            success=True,
            usage_normalized={
                "prompt_tokens": 90,
                "completion_tokens": 15,
                "total_tokens": 105,
                "cached_tokens": 10,
            },
        )

    monkeypatch.setattr(backend, "_call_model", fake_call)

    try:
        response = backend.chat_completion(
            [{"role": "user", "content": "A" * 200}],
            temperature=0.0,
            stream=False,
            timeout=5,
        )
        assert response["choices"][0]["message"]["content"] == "m1 response"
        assert response["metadata"]["ab_variant"] == "control"
        assert response["metadata"]["dms_used"] is False
        assert response["metadata"]["dms_candidate"] is True
        assert response["metadata"]["dms_attempted"] is False
        assert calls == ["m1"]
        assert response["metadata"]["selected_model"] == "m1"
        assert response["metadata"]["fallback_reason"] is None
        assert response["metadata"]["usage_normalized"] == {
            "prompt_tokens": 90,
            "completion_tokens": 15,
            "total_tokens": 105,
            "cached_tokens": 10,
        }
        assert backend.routing_metrics["ab_variants"]["control"]["requests"] == 1
        usage_metrics = backend.routing_metrics["usage_economics"]
        assert usage_metrics["selected_samples"] == 1
        assert usage_metrics["by_ab_variant"]["control"]["samples"] == 1
        assert usage_metrics["selected_total_tokens"] == 105
        status_usage = backend.get_status()["routing_metrics"]["usage_economics"]
        assert status_usage["selected_avg_total_tokens"] == 105.0
        assert status_usage["by_ab_variant"]["control"]["avg_total_tokens"] == 105.0
        assert_zero_fallback_reason_counts(backend)
        assert (
            backend.get_status()["routing_metrics"]["ab_variants"]["control"][
                "success_rate"
            ]
            == 1.0
        )
    finally:
        backend.executor.shutdown(wait=False, cancel_futures=True)


def test_routing_strategy_early_cancels_losing_parallel_branches(monkeypatch):
    monkeypatch.setattr(settings, "DMS_ENABLED", False)

    backend = ParallelLLMBackend()
    backend.strategy = "routing"
    backend.models = [
        ModelConfig(
            name="llama3.2",
            backend="ollama",
            url="http://localhost:11434/api/chat",
            model="llama3.2",
        ),
        ModelConfig(
            name="m2",
            backend="ollama",
            url="http://localhost:11434/api/chat",
            model="m2",
        ),
        ModelConfig(
            name="m3",
            backend="ollama",
            url="http://localhost:11434/api/chat",
            model="m3",
        ),
    ]

    class _FakeFuture:
        def __init__(self, response):
            self._response = response
            self.cancel_calls = 0

        def result(self):
            return self._response

        def cancel(self):
            self.cancel_calls += 1
            return True

    winner = _FakeFuture(
        ModelResponse(
            model_name="llama3.2",
            response="winner",
            latency=0.1,
            success=True,
        )
    )
    loser_m2 = _FakeFuture(
        ModelResponse(
            model_name="m2",
            response="loser2",
            latency=0.4,
            success=True,
        )
    )
    loser_m3 = _FakeFuture(
        ModelResponse(
            model_name="m3",
            response="loser3",
            latency=0.5,
            success=True,
        )
    )
    future_by_model = {
        "llama3.2": winner,
        "m2": loser_m2,
        "m3": loser_m3,
    }

    class _FakeExecutor:
        def submit(self, fn, model, messages, temperature, timeout):
            return future_by_model[model.name]

    monkeypatch.setattr("merlin_parallel_llm.as_completed", lambda futures: iter([winner]))
    real_executor = backend.executor
    backend.executor = _FakeExecutor()

    try:
        response = backend.chat_completion(
            [{"role": "user", "content": "quick answer"}],
            temperature=0.0,
            stream=False,
            timeout=5,
        )
    finally:
        real_executor.shutdown(wait=False, cancel_futures=True)

    assert response["choices"][0]["message"]["content"] == "winner"
    assert response["metadata"]["selected_model"] == "llama3.2"
    assert response["metadata"]["parallel_early_cancel_triggered"] is True
    assert response["metadata"]["parallel_early_cancelled_branches"] == 2
    assert loser_m2.cancel_calls == 1
    assert loser_m3.cancel_calls == 1


def test_openai_compat_payload_sends_top_level_temperature(monkeypatch):
    model = ModelConfig(
        name="dms",
        backend="openai_compat",
        url="http://dms.local/v1/chat/completions",
        model="nvidia/Qwen3-8B-DMS-8x",
    )
    backend = ParallelLLMBackend.__new__(ParallelLLMBackend)
    backend.executor = None

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
            captured["timeout"] = timeout
            captured["headers"] = headers
            return FakeResponse()

    monkeypatch.setattr("merlin_parallel_llm.requests", FakeRequests)

    result = backend._call_model(model, [{"role": "user", "content": "hello"}], 0.7, 5)

    assert result.response == "ok"
    assert captured["payload"]["model"] == "nvidia/Qwen3-8B-DMS-8x"
    assert captured["payload"]["temperature"] == 0.7
    assert "options" not in captured["payload"]


def test_openai_compatible_content_extractor_supports_alternate_shapes():
    assert (
        ParallelLLMBackend._extract_openai_compatible_content(
            {"content": "top-level-content"}
        )
        == "top-level-content"
    )
    assert (
        ParallelLLMBackend._extract_openai_compatible_content(
            {"choices": [{"text": "legacy-text"}]}
        )
        == "legacy-text"
    )
    assert (
        ParallelLLMBackend._extract_openai_compatible_content(
            {"choices": [{"message": {"content": "choice-message"}}]}
        )
        == "choice-message"
    )
