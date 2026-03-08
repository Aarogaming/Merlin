from __future__ import annotations

import asyncio
import pytest
import requests

import merlin_settings as settings

from merlin_streaming_llm import StreamingLLMBackend, StreamingModelResponse
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


def _collect_stream_output(backend: StreamingLLMBackend, messages):
    async def collect() -> str:
        chunks = []
        async for chunk in backend.chat_completion(
            messages, temperature=0.0, stream=True, timeout=5
        ):
            chunks.append(chunk)
        return "".join(chunks)

    return asyncio.run(collect())


def _stream_response(text: str):
    async def generator():
        yield text

    return generator()


def test_streaming_dms_model_registration_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_URL", "http://dms.local/v1/chat/completions")
    monkeypatch.setattr(settings, "DMS_MODEL", "nvidia/Qwen3-8B-DMS-8x")
    monkeypatch.setattr(settings, "DMS_API_KEY", "")
    monkeypatch.setattr(settings, "OLLAMA_MODELS", [])
    monkeypatch.setattr(settings, "GLM_API_KEY", "")
    monkeypatch.setattr(settings, "NEMOTRON_API_KEY", "")

    backend = StreamingLLMBackend()
    try:
        names = [model["name"] for model in backend.models]
        assert "dms" in names
    finally:
        backend.executor.shutdown(wait=False, cancel_futures=True)


def test_streaming_prefers_dms_for_long_prompt(
    monkeypatch, reset_router_metrics, assert_zero_fallback_reason_counts
):
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_MIN_PROMPT_CHARS", 50)
    monkeypatch.setattr(settings, "DMS_TASK_TYPES", ["analysis", "code", "planning"])

    backend = StreamingLLMBackend()
    backend.strategy = "voting"
    reset_router_metrics(backend)
    backend.models = [
        {
            "name": "dms",
            "backend": "openai_compat",
            "url": "http://dms.local/v1/chat/completions",
            "model": "nvidia/Qwen3-8B-DMS-8x",
        },
        {
            "name": "m1",
            "backend": "ollama",
            "url": "http://localhost:11434/api/chat",
            "model": "m1",
        },
    ]

    calls: list[str] = []

    async def fake_stream_model(model, messages, temperature):
        calls.append(model["name"])
        if model["name"] == "dms":
            return StreamingModelResponse(
                model_name="dms",
                response_generator=_stream_response("dms response"),
                latency=0.2,
                success=True,
                usage_normalized={
                    "prompt_tokens": 48,
                    "completion_tokens": 12,
                    "total_tokens": 60,
                    "cached_tokens": 8,
                },
            )
        return StreamingModelResponse(
            model_name="m1",
            response_generator=_stream_response("m1 response"),
            latency=0.1,
            success=True,
        )

    monkeypatch.setattr(backend, "_stream_model", fake_stream_model)

    try:
        response = _collect_stream_output(
            backend,
            [{"role": "user", "content": "A" * 200}],
        )
        assert response == "dms response"
        assert backend.last_decision["selected_model"] == "dms"
        assert backend.last_decision["dms_used"] is True
        assert backend.last_decision["fallback_reason"] is None
        assert backend.last_decision["fallback_reason_code"] is None
        assert backend.last_decision["router_backend"] == "streaming"
        assert backend.last_decision["router_policy_version"] == "cp2-2026-02-15"
        assert backend.last_decision["routing_trace_scheme"] == "sha256-v1"
        assert backend.last_decision["routing_trace_id"].startswith("rt_")
        assert len(backend.last_decision["routing_trace_fingerprint"]) == 64
        assert backend.last_decision["stream_ttft_seconds"] >= 0.0
        assert backend.last_decision["stream_completion_seconds"] >= 0.0
        assert backend.last_decision["stream_usage_normalized"] == {
            "prompt_tokens": 48,
            "completion_tokens": 12,
            "total_tokens": 60,
            "cached_tokens": 8,
        }
        usage_metrics = backend.routing_metrics["usage_economics"]
        assert usage_metrics["selected_samples"] == 1
        assert usage_metrics["selected_total_tokens"] == 60
        assert usage_metrics["by_prompt_bucket"]["long"]["samples"] == 1
        assert usage_metrics["by_ab_variant"]["dms"]["samples"] == 1
        assert calls == ["dms"]
        status = backend.get_status()
        stream_latency = status["routing_metrics"]["stream_latency"]
        assert stream_latency["requests"] == 1
        assert stream_latency["ttft_samples"] == 1
        assert stream_latency["completion_samples"] == 1
        status_usage = status["routing_metrics"]["usage_economics"]
        assert status_usage["selected_avg_total_tokens"] == 60.0
        assert status_usage["by_prompt_bucket"]["long"]["avg_total_tokens"] == 60.0
        assert status_usage["by_ab_variant"]["dms"]["avg_total_tokens"] == 60.0
        assert_zero_fallback_reason_counts(backend)
    finally:
        backend.executor.shutdown(wait=False, cancel_futures=True)


def test_streaming_fallback_when_dms_call_fails(monkeypatch, reset_router_metrics):
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_MIN_PROMPT_CHARS", 50)
    monkeypatch.setattr(settings, "DMS_TASK_TYPES", ["analysis", "code", "planning"])

    backend = StreamingLLMBackend()
    backend.strategy = "voting"
    reset_router_metrics(backend)
    backend.models = [
        {
            "name": "dms",
            "backend": "openai_compat",
            "url": "http://dms.local/v1/chat/completions",
            "model": "nvidia/Qwen3-8B-DMS-8x",
        },
        {
            "name": "m1",
            "backend": "ollama",
            "url": "http://localhost:11434/api/chat",
            "model": "m1",
        },
    ]

    async def fake_stream_model(model, messages, temperature):
        if model["name"] == "dms":
            return StreamingModelResponse(
                model_name="dms",
                response_generator=_stream_response(""),
                latency=1.0,
                success=False,
                error="connection timeout",
            )
        return StreamingModelResponse(
            model_name="m1",
            response_generator=_stream_response("fallback response"),
            latency=0.1,
            success=True,
        )

    monkeypatch.setattr(backend, "_stream_model", fake_stream_model)

    try:
        response = _collect_stream_output(
            backend,
            [{"role": "user", "content": "B" * 200}],
        )
        assert response.strip() == "fallback response"
        assert backend.last_decision["selected_model"] == "m1"
        assert backend.last_decision["dms_used"] is False
        assert (
            backend.last_decision["fallback_reason"] == "dms_error: connection timeout"
        )
        assert backend.last_decision["fallback_reason_code"] == "dms_timeout"
        assert backend.last_decision["fallback_detail"] == "connection timeout"
        assert backend.last_decision["fallback_retryable"] is True
        assert backend.last_decision["fallback_stage"] == "dms_primary"
        assert backend.last_decision["stream_ttft_seconds"] >= 0.0
        assert backend.last_decision["stream_completion_seconds"] >= 0.0
        assert backend.routing_metrics["fallback_reason_counts"]["dms_timeout"] == 1
        assert sum(backend.routing_metrics["fallback_reason_counts"].values()) == 1
    finally:
        backend.executor.shutdown(wait=False, cancel_futures=True)


def test_streaming_fallback_when_dms_stream_errors_before_content(
    monkeypatch, reset_router_metrics
):
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_MIN_PROMPT_CHARS", 50)
    monkeypatch.setattr(settings, "DMS_TASK_TYPES", ["analysis", "code", "planning"])

    backend = StreamingLLMBackend()
    backend.strategy = "voting"
    reset_router_metrics(backend)
    backend.models = [
        {
            "name": "dms",
            "backend": "openai_compat",
            "url": "http://dms.local/v1/chat/completions",
            "model": "nvidia/Qwen3-8B-DMS-8x",
        },
        {
            "name": "m1",
            "backend": "ollama",
            "url": "http://localhost:11434/api/chat",
            "model": "m1",
        },
    ]

    async def fake_stream_model(model, messages, temperature):
        if model["name"] == "dms":
            return StreamingModelResponse(
                model_name="dms",
                response_generator=_stream_response("[Error: HTTP 429 too many requests]"),
                latency=0.2,
                success=True,
            )
        return StreamingModelResponse(
            model_name="m1",
            response_generator=_stream_response("fallback response"),
            latency=0.1,
            success=True,
        )

    monkeypatch.setattr(backend, "_stream_model", fake_stream_model)

    try:
        response = _collect_stream_output(
            backend,
            [{"role": "user", "content": "C" * 200}],
        )
        assert response.strip() == "fallback response"
        assert backend.last_decision["selected_model"] == "m1"
        assert backend.last_decision["dms_used"] is False
        assert backend.last_decision["fallback_reason_code"] == "dms_rate_limited"
        assert backend.last_decision["fallback_stage"] == "dms_stream"
        assert backend.routing_metrics["fallback_reason_counts"]["dms_rate_limited"] == 1
        assert backend.routing_metrics["dms_fallbacks"] == 1
    finally:
        backend.executor.shutdown(wait=False, cancel_futures=True)


def test_streaming_short_prompt_does_not_prefer_dms(
    monkeypatch, reset_router_metrics, assert_zero_fallback_reason_counts
):
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_MIN_PROMPT_CHARS", 500)
    monkeypatch.setattr(settings, "DMS_TASK_TYPES", ["analysis", "code", "planning"])

    backend = StreamingLLMBackend()
    backend.strategy = "voting"
    reset_router_metrics(backend)
    backend.models = [
        {
            "name": "dms",
            "backend": "openai_compat",
            "url": "http://dms.local/v1/chat/completions",
            "model": "nvidia/Qwen3-8B-DMS-8x",
        },
        {
            "name": "m1",
            "backend": "ollama",
            "url": "http://localhost:11434/api/chat",
            "model": "m1",
        },
    ]

    calls: list[str] = []

    async def fake_stream_model(model, messages, temperature):
        calls.append(model["name"])
        if model["name"] == "dms":
            return StreamingModelResponse(
                model_name="dms",
                response_generator=_stream_response("dms response"),
                latency=0.2,
                success=True,
            )
        return StreamingModelResponse(
            model_name="m1",
            response_generator=_stream_response("fallback response"),
            latency=0.1,
            success=True,
            usage_normalized={
                "prompt_tokens": 5,
                "completion_tokens": 2,
                "total_tokens": 7,
                "cached_tokens": 0,
            },
        )

    monkeypatch.setattr(backend, "_stream_model", fake_stream_model)

    try:
        response = _collect_stream_output(
            backend,
            [
                {"role": "user", "content": "hello"},
                {"role": "user", "content": "quick"},
            ],
        )
        assert response == "fallback response "
        assert backend.last_decision["selected_model"] == "m1"
        assert backend.last_decision["dms_used"] is False
        assert calls == ["m1"]
        assert backend.last_decision["prompt_size_bucket"] == "short"
        assert backend.last_decision["fallback_reason"] is None
        assert backend.last_decision["stream_usage_normalized"] == {
            "prompt_tokens": 5,
            "completion_tokens": 2,
            "total_tokens": 7,
            "cached_tokens": 0,
        }
        usage_metrics = backend.routing_metrics["usage_economics"]
        assert usage_metrics["selected_samples"] == 1
        assert usage_metrics["selected_total_tokens"] == 7
        assert usage_metrics["by_prompt_bucket"]["short"]["samples"] == 1
        assert usage_metrics["by_ab_variant"]["disabled"]["samples"] == 1
        assert_zero_fallback_reason_counts(backend)
    finally:
        backend.executor.shutdown(wait=False, cancel_futures=True)


def test_streaming_control_variant_skips_dms_for_ab_experiment(
    monkeypatch, reset_router_metrics, assert_zero_fallback_reason_counts
):
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_MIN_PROMPT_CHARS", 50)
    monkeypatch.setattr(settings, "DMS_TASK_TYPES", ["analysis", "code", "planning"])
    monkeypatch.setattr(settings, "DMS_AB_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_AB_DMS_PERCENTAGE", 0)

    backend = StreamingLLMBackend()
    backend.strategy = "voting"
    reset_router_metrics(backend)
    backend.models = [
        {
            "name": "dms",
            "backend": "openai_compat",
            "url": "http://dms.local/v1/chat/completions",
            "model": "nvidia/Qwen3-8B-DMS-8x",
        },
        {
            "name": "m1",
            "backend": "ollama",
            "url": "http://localhost:11434/api/chat",
            "model": "m1",
        },
    ]

    calls: list[str] = []

    async def fake_stream_model(model, messages, temperature):
        calls.append(model["name"])
        if model["name"] == "dms":
            return StreamingModelResponse(
                model_name="dms",
                response_generator=_stream_response("dms response"),
                latency=0.2,
                success=True,
            )
        return StreamingModelResponse(
            model_name="m1",
            response_generator=_stream_response("stream response"),
            latency=0.1,
            success=True,
            usage_normalized={
                "prompt_tokens": 70,
                "completion_tokens": 14,
                "total_tokens": 84,
                "cached_tokens": 6,
            },
        )

    monkeypatch.setattr(backend, "_stream_model", fake_stream_model)

    try:
        response = _collect_stream_output(
            backend,
            [{"role": "user", "content": "A" * 200}],
        )
        assert response.strip() == "stream response"
        assert backend.last_decision["selected_model"] == "m1"
        assert backend.last_decision["dms_used"] is False
        assert backend.last_decision["dms_candidate"] is True
        assert backend.last_decision["dms_attempted"] is False
        assert backend.last_decision["fallback_reason"] is None
        assert backend.last_decision["ab_variant"] == "control"
        assert backend.last_decision["stream_usage_normalized"] == {
            "prompt_tokens": 70,
            "completion_tokens": 14,
            "total_tokens": 84,
            "cached_tokens": 6,
        }
        assert calls == ["m1"]
        assert backend.routing_metrics["ab_variants"]["control"]["requests"] == 1
        usage_metrics = backend.routing_metrics["usage_economics"]
        assert usage_metrics["selected_samples"] == 1
        assert usage_metrics["selected_total_tokens"] == 84
        assert usage_metrics["by_prompt_bucket"]["long"]["samples"] == 1
        assert usage_metrics["by_ab_variant"]["control"]["samples"] == 1
        status_usage = backend.get_status()["routing_metrics"]["usage_economics"]
        assert status_usage["selected_avg_total_tokens"] == 84.0
        assert status_usage["by_ab_variant"]["control"]["avg_total_tokens"] == 84.0
        assert_zero_fallback_reason_counts(backend)
        assert (
            backend.get_status()["routing_metrics"]["ab_variants"]["control"][
                "success_rate"
            ]
            == 1.0
        )
    finally:
        backend.executor.shutdown(wait=False, cancel_futures=True)


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(
            {
                "query": "hello",
                "settings": with_uncertainty_disabled(
                    {
                        "DMS_MIN_PROMPT_CHARS": 500,
                        "MERLIN_PROMPT_BUCKET_TOKEN_AWARE": False,
                    }
                ),
                "responses": {
                    "m1": {
                        "response": "m1 response",
                        "latency": 0.1,
                        "success": True,
                    },
                },
                "expected": {
                    "selected_model": "m1",
                    "dms_used": False,
                    "dms_candidate": False,
                    "dms_attempted": False,
                    "prompt_size_bucket": "short",
                },
                "expected_calls": {"m1"},
            },
            id="short-prefers-control",
        ),
        pytest.param(
            {
                "query": SIMPLE_LONG_PROMPT_QUERY,
                "settings": with_uncertainty_disabled(
                    {
                        "DMS_MIN_PROMPT_CHARS": 50,
                        "MERLIN_PROMPT_BUCKET_TOKEN_AWARE": False,
                    }
                ),
                "responses": {
                    "dms": {
                        "response": "dms response",
                        "latency": 0.2,
                        "success": True,
                    },
                    "m1": {
                        "response": "m1 response",
                        "latency": 0.1,
                        "success": True,
                    },
                },
                "expected": {
                    "selected_model": "dms",
                    "dms_used": True,
                    "dms_candidate": True,
                    "dms_attempted": True,
                    "prompt_size_bucket": "long",
                },
                "expected_calls": {"dms"},
            },
            id="long-prefers-dms",
        ),
        pytest.param(
            {
                "query": "analysis " * 1700,
                "settings": with_uncertainty_disabled(
                    {
                        "DMS_MIN_PROMPT_CHARS": 10000,
                        "DMS_MIN_PROMPT_TOKENS": 1500,
                        "MERLIN_PROMPT_BUCKET_TOKEN_AWARE": True,
                    }
                ),
                "responses": {
                    "dms": {
                        "response": "token-aware dms response",
                        "latency": 0.2,
                        "success": True,
                    },
                    "m1": {
                        "response": "m1 response",
                        "latency": 0.1,
                        "success": True,
                    },
                },
                "expected": {
                    "selected_model": "dms",
                    "dms_used": True,
                    "dms_candidate": True,
                    "dms_attempted": True,
                    "prompt_size_bucket": "long",
                },
                "expected_calls": {"dms"},
            },
            id="token-aware-prefers-dms",
        ),
        pytest.param(
            {
                "query": SIMPLE_LONG_PROMPT_QUERY,
                "settings": with_uncertainty_enabled(
                    {
                        "DMS_MIN_PROMPT_CHARS": 50,
                        "MERLIN_PROMPT_BUCKET_TOKEN_AWARE": False,
                    }
                ),
                "responses": {
                    "m1": {
                        "response": "m1 response",
                        "latency": 0.1,
                        "success": True,
                    },
                },
                "expected": {
                    "selected_model": "m1",
                    "dms_used": False,
                    "dms_candidate": False,
                    "dms_attempted": False,
                    "prompt_size_bucket": "long",
                },
                "expected_calls": {"m1"},
            },
            id="uncertainty-mode-blocks-simple-long",
        ),
        pytest.param(
            {
                "query": UNCERTAIN_REASONING_QUERY,
                "settings": with_uncertainty_enabled(
                    {
                        "DMS_MIN_PROMPT_CHARS": 50,
                        "MERLIN_PROMPT_BUCKET_TOKEN_AWARE": False,
                    }
                ),
                "responses": {
                    "dms": {
                        "response": "dms response",
                        "latency": 0.2,
                        "success": True,
                    },
                    "m1": {
                        "response": "m1 response",
                        "latency": 0.1,
                        "success": True,
                    },
                },
                "expected": {
                    "selected_model": "dms",
                    "dms_used": True,
                    "dms_candidate": True,
                    "dms_attempted": True,
                },
                "expected_calls": {"dms"},
            },
            id="uncertainty-mode-prefers-uncertain-reasoning",
        ),
    ],
)
def test_streaming_router_selection_regression_corpus(
    case, monkeypatch, reset_router_metrics, assert_zero_fallback_reason_counts
):
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_TASK_TYPES", ["analysis", "code", "planning"])
    monkeypatch.setattr(settings, "DMS_AB_ENABLED", False)
    for key, value in case["settings"].items():
        monkeypatch.setattr(settings, key, value)

    backend = StreamingLLMBackend()
    backend.strategy = "voting"
    reset_router_metrics(backend)
    backend.models = [
        {
            "name": "dms",
            "backend": "openai_compat",
            "url": "http://dms.local/v1/chat/completions",
            "model": "nvidia/Qwen3-8B-DMS-8x",
        },
        {
            "name": "m1",
            "backend": "ollama",
            "url": "http://localhost:11434/api/chat",
            "model": "m1",
        },
    ]

    calls: list[str] = []

    async def fake_stream_model(model, messages, temperature):
        calls.append(model["name"])
        result = case["responses"].get(model["name"])
        if result is None:
            result = {
                "response": f"{model['name']} response",
                "latency": 0.1,
                "success": True,
            }
        return StreamingModelResponse(
            model_name=model["name"],
            response_generator=_stream_response(result["response"]),
            latency=result["latency"],
            success=result["success"],
            error=result.get("error"),
        )

    monkeypatch.setattr(backend, "_stream_model", fake_stream_model)

    try:
        _collect_stream_output(
            backend,
            [{"role": "user", "content": case["query"]}],
        )
        metadata = backend.last_decision
        for key, expected_value in case["expected"].items():
            assert metadata[key] == expected_value
        assert metadata["router_backend"] == "streaming"
        assert set(calls) == case["expected_calls"]
        assert_zero_fallback_reason_counts(backend)
    finally:
        backend.executor.shutdown(wait=False, cancel_futures=True)


def test_stream_chunk_extractor_supports_alternative_shapes():
    assert (
        StreamingLLMBackend._extract_openai_compatible_stream_chunk(
            {"text": "stream-text"}
        )
        == "stream-text"
    )
    assert (
        StreamingLLMBackend._extract_openai_compatible_stream_chunk(
            {"done": True, "choices": [{"delta": {"content": "ignored"}}]}
        )
        == ""
    )
    assert (
        StreamingLLMBackend._extract_openai_compatible_stream_chunk(
            {"choices": [{"delta": {"content": "chunk"}}]}
        )
        == "chunk"
    )


def test_normalize_stream_usage_prefers_nested_usage_and_details():
    normalized = StreamingLLMBackend._normalize_stream_usage(
        {
            "usage": {
                "prompt_tokens": 11,
                "completion_tokens": 6,
                "total_tokens": 17,
                "prompt_tokens_details": {"cached_tokens": 3},
                "completion_tokens_details": {"reasoning_tokens": 2},
            }
        }
    )
    assert normalized == {
        "prompt_tokens": 11,
        "completion_tokens": 6,
        "total_tokens": 17,
        "cached_tokens": 3,
        "reasoning_tokens": 2,
    }


def test_normalize_stream_usage_supports_alt_openai_compat_fields():
    normalized = StreamingLLMBackend._normalize_stream_usage(
        {
            "usage": {
                "input_tokens": 9,
                "output_tokens": 4,
                "cache_read_input_tokens": 5,
                "reasoning_tokens": 1,
            }
        }
    )
    assert normalized == {
        "prompt_tokens": 9,
        "completion_tokens": 4,
        "total_tokens": 13,
        "cached_tokens": 5,
        "reasoning_tokens": 1,
    }


def test_iter_sse_payloads_handles_comments_and_done_frames():
    payloads = list(
        StreamingLLMBackend._iter_sse_payloads(
            [
                b": heartbeat",
                b"event: message",
                b'data: {"choices":[{"delta":{"content":"hello"}}]}',
                b"",
                b": another heartbeat",
                b'data: {"choices":[{"delta":{"content":" world"}}]}',
                b"",
                b"data: [DONE]",
                b"",
            ]
        )
    )

    assert payloads == [
        '{"choices":[{"delta":{"content":"hello"}}]}',
        '{"choices":[{"delta":{"content":" world"}}]}',
        "[DONE]",
    ]


def test_iter_sse_payloads_supports_multiline_data_frames():
    payloads = list(
        StreamingLLMBackend._iter_sse_payloads(
            [
                'data: {"message":',
                'data: {"content":"hi"}}',
                "",
            ]
        )
    )
    assert payloads == ['{"message":\n{"content":"hi"}}']


def test_iter_sse_payloads_supports_json_lines_without_data_prefix():
    payloads = list(
        StreamingLLMBackend._iter_sse_payloads(
            [
                '{"message":{"content":"line1"}}',
                '{"message":{"content":"line2"}}',
            ]
        )
    )
    assert payloads == [
        '{"message":{"content":"line1"}}',
        '{"message":{"content":"line2"}}',
    ]


def test_iter_sse_frames_tracks_event_names():
    frames = list(
        StreamingLLMBackend._iter_sse_frames(
            [
                b"event: message",
                b'data: {"choices":[{"delta":{"content":"hello"}}]}',
                b"",
                b"event: error",
                b'data: {"error":{"message":"boom","code":"stream_error"}}',
                b"",
                b"data: [DONE]",
                b"",
            ]
        )
    )

    assert frames == [
        ("message", '{"choices":[{"delta":{"content":"hello"}}]}'),
        ("error", '{"error":{"message":"boom","code":"stream_error"}}'),
        ("message", "[DONE]"),
    ]


def test_iter_sse_frames_ignores_malformed_and_unknown_lines():
    frames = list(
        StreamingLLMBackend._iter_sse_frames(
            [
                b"event: message",
                b"id: 42",
                b"retry: 1000",
                b"malformed-without-colon",
                b"x-custom: ignored",
                b'data: {"choices":[{"delta":{"content":"hello"}}]}',
                b"",
            ]
        )
    )

    assert frames == [
        ("message", '{"choices":[{"delta":{"content":"hello"}}]}'),
    ]


def test_stream_model_stops_consuming_after_done_frame(monkeypatch):
    class _FakeResponse:
        def raise_for_status(self):
            return None

        def iter_lines(self):
            return iter(
                [
                    b": heartbeat",
                    b'data: {"choices":[{"delta":{"content":"hello"}}]}',
                    b"",
                    b"data: [DONE]",
                    b"",
                    b'data: {"choices":[{"delta":{"content":"ignored"}}]}',
                    b"",
                ]
            )

    class _FakeRequests:
        @staticmethod
        def post(url, json, headers=None, stream=False, timeout=30):
            return _FakeResponse()

    monkeypatch.setattr("merlin_streaming_llm.requests", _FakeRequests)
    backend = StreamingLLMBackend()

    async def _collect() -> str:
        response = await backend._stream_model(
            {
                "name": "dms",
                "backend": "openai_compat",
                "url": "http://dms.local/v1/chat/completions",
                "model": "dms-test",
            },
            [{"role": "user", "content": "test"}],
            temperature=0.0,
        )
        chunks = []
        async for chunk in response.response_generator:
            chunks.append(chunk)
        return "".join(chunks)

    try:
        assert asyncio.run(_collect()) == "hello"
    finally:
        backend.executor.shutdown(wait=False, cancel_futures=True)


def test_stream_model_ignores_malformed_sse_lines_and_continues(monkeypatch):
    class _FakeResponse:
        def raise_for_status(self):
            return None

        def iter_lines(self):
            return iter(
                [
                    b"bad-line-without-colon",
                    b'x-custom: {"ignored":true}',
                    b"event: message",
                    b'data: {"choices":[{"delta":{"content":"hello"}}]}',
                    b"",
                    b'data: {"choices":[{"delta":{"content":" world"}}]}',
                    b"",
                    b"data: [DONE]",
                    b"",
                ]
            )

    class _FakeRequests:
        @staticmethod
        def post(url, json, headers=None, stream=False, timeout=30):
            return _FakeResponse()

    monkeypatch.setattr("merlin_streaming_llm.requests", _FakeRequests)
    backend = StreamingLLMBackend()

    async def _collect() -> str:
        response = await backend._stream_model(
            {
                "name": "dms",
                "backend": "openai_compat",
                "url": "http://dms.local/v1/chat/completions",
                "model": "dms-test",
            },
            [{"role": "user", "content": "test"}],
            temperature=0.0,
        )
        chunks = []
        async for chunk in response.response_generator:
            chunks.append(chunk)
        return "".join(chunks)

    try:
        assert asyncio.run(_collect()) == "hello world"
    finally:
        backend.executor.shutdown(wait=False, cancel_futures=True)


def test_stream_model_surfaces_sse_error_event_as_error_chunk(monkeypatch):
    class _FakeResponse:
        def raise_for_status(self):
            return None

        def iter_lines(self):
            return iter(
                [
                    b"event: error",
                    (
                        b'data: {"error":{"status":429,"code":"rate_limit",'
                        b'"message":"too many requests"}}'
                    ),
                    b"",
                ]
            )

    class _FakeRequests:
        @staticmethod
        def post(url, json, headers=None, stream=False, timeout=30):
            return _FakeResponse()

    monkeypatch.setattr("merlin_streaming_llm.requests", _FakeRequests)
    backend = StreamingLLMBackend()

    async def _collect() -> str:
        response = await backend._stream_model(
            {
                "name": "dms",
                "backend": "openai_compat",
                "url": "http://dms.local/v1/chat/completions",
                "model": "dms-test",
            },
            [{"role": "user", "content": "test"}],
            temperature=0.0,
        )
        chunks = []
        async for chunk in response.response_generator:
            chunks.append(chunk)
        return "".join(chunks)

    try:
        chunk = asyncio.run(_collect())
        assert chunk.startswith("[Error: ")
        assert "429" in chunk
        assert "rate_limit" in chunk
    finally:
        backend.executor.shutdown(wait=False, cancel_futures=True)


def test_stream_model_http_error_chunk_includes_rate_limit_headers(monkeypatch):
    class _ResponseHeaders:
        headers = {
            "X-RateLimit-Remaining-Requests": "0",
            "x-ratelimit-reset-requests": "20ms",
        }

    class _FakeResponse:
        @staticmethod
        def raise_for_status():
            raise requests.exceptions.HTTPError("HTTP 429", response=_ResponseHeaders())

        @staticmethod
        def iter_lines():
            return iter([])

    class _FakeRequests:
        @staticmethod
        def post(url, json, headers=None, stream=False, timeout=30):
            del url, json, headers, stream, timeout
            return _FakeResponse()

    monkeypatch.setattr("merlin_streaming_llm.requests", _FakeRequests)
    backend = StreamingLLMBackend()

    async def _collect() -> str:
        response = await backend._stream_model(
            {
                "name": "dms",
                "backend": "openai_compat",
                "url": "http://dms.local/v1/chat/completions",
                "model": "dms-test",
            },
            [{"role": "user", "content": "test"}],
            temperature=0.0,
        )
        chunks = []
        async for chunk in response.response_generator:
            chunks.append(chunk)
        return "".join(chunks)

    try:
        chunk = asyncio.run(_collect())
        assert chunk.startswith("[Error: HTTP 429")
        assert "x-ratelimit-remaining-requests=0" in chunk
        assert "x-ratelimit-reset-requests=20ms" in chunk
    finally:
        backend.executor.shutdown(wait=False, cancel_futures=True)


def test_stream_model_accumulates_stream_usage_events(monkeypatch):
    class _FakeResponse:
        def raise_for_status(self):
            return None

        def iter_lines(self):
            return iter(
                [
                    (
                        b'data: {"choices":[{"delta":{"content":"hello "}}],'
                        b'"usage":{"prompt_tokens":10,"completion_tokens":2,'
                        b'"total_tokens":12,"prompt_tokens_details":{"cached_tokens":4}}}'
                    ),
                    b"",
                    (
                        b'data: {"choices":[{"delta":{"content":"world"}}],'
                        b'"usage":{"prompt_tokens":10,"completion_tokens":5,'
                        b'"total_tokens":15,"completion_tokens_details":{"reasoning_tokens":3}}}'
                    ),
                    b"",
                    b"data: [DONE]",
                    b"",
                ]
            )

    class _FakeRequests:
        @staticmethod
        def post(url, json, headers=None, stream=False, timeout=30):
            return _FakeResponse()

    monkeypatch.setattr("merlin_streaming_llm.requests", _FakeRequests)
    backend = StreamingLLMBackend()

    async def _collect():
        response = await backend._stream_model(
            {
                "name": "dms",
                "backend": "openai_compat",
                "url": "http://dms.local/v1/chat/completions",
                "model": "dms-test",
            },
            [{"role": "user", "content": "test"}],
            temperature=0.0,
        )
        chunks = []
        async for chunk in response.response_generator:
            chunks.append(chunk)
        return "".join(chunks), response.usage_normalized

    try:
        output, usage = asyncio.run(_collect())
        assert output == "hello world"
        assert usage == {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
            "cached_tokens": 4,
            "reasoning_tokens": 3,
        }
    finally:
        backend.executor.shutdown(wait=False, cancel_futures=True)


def test_stream_model_ignores_non_json_data_frames_and_continues(monkeypatch):
    class _FakeResponse:
        def raise_for_status(self):
            return None

        def iter_lines(self):
            return iter(
                [
                    b"data: this-is-not-json",
                    b"",
                    b'data: {"choices":[{"delta":{"content":"hello"}}]}',
                    b"",
                    b"data: [DONE]",
                    b"",
                ]
            )

    class _FakeRequests:
        @staticmethod
        def post(url, json, headers=None, stream=False, timeout=30):
            return _FakeResponse()

    monkeypatch.setattr("merlin_streaming_llm.requests", _FakeRequests)
    backend = StreamingLLMBackend()

    async def _collect():
        response = await backend._stream_model(
            {
                "name": "dms",
                "backend": "openai_compat",
                "url": "http://dms.local/v1/chat/completions",
                "model": "dms-test",
            },
            [{"role": "user", "content": "test"}],
            temperature=0.0,
        )
        chunks = []
        async for chunk in response.response_generator:
            chunks.append(chunk)
        return "".join(chunks)

    try:
        assert asyncio.run(_collect()) == "hello"
    finally:
        backend.executor.shutdown(wait=False, cancel_futures=True)


def test_stream_model_handles_terminal_usage_only_chunk(monkeypatch):
    class _FakeResponse:
        def raise_for_status(self):
            return None

        def iter_lines(self):
            return iter(
                [
                    b'data: {"choices":[{"delta":{"content":"hello"}}]}',
                    b"",
                    (
                        b'data: {"usage":{"prompt_tokens":10,"completion_tokens":4,'
                        b'"total_tokens":14,"prompt_tokens_details":{"cached_tokens":2},'
                        b'"completion_tokens_details":{"reasoning_tokens":1}}}'
                    ),
                    b"",
                    b"data: [DONE]",
                    b"",
                ]
            )

    class _FakeRequests:
        @staticmethod
        def post(url, json, headers=None, stream=False, timeout=30):
            return _FakeResponse()

    monkeypatch.setattr("merlin_streaming_llm.requests", _FakeRequests)
    backend = StreamingLLMBackend()

    async def _collect():
        response = await backend._stream_model(
            {
                "name": "dms",
                "backend": "openai_compat",
                "url": "http://dms.local/v1/chat/completions",
                "model": "dms-test",
            },
            [{"role": "user", "content": "test"}],
            temperature=0.0,
        )
        chunks = []
        async for chunk in response.response_generator:
            chunks.append(chunk)
        return "".join(chunks), response.usage_normalized

    try:
        output, usage = asyncio.run(_collect())
        assert output == "hello"
        assert usage == {
            "prompt_tokens": 10,
            "completion_tokens": 4,
            "total_tokens": 14,
            "cached_tokens": 2,
            "reasoning_tokens": 1,
        }
    finally:
        backend.executor.shutdown(wait=False, cancel_futures=True)
