from __future__ import annotations

import hashlib
import requests
import pytest

import merlin_settings as settings
from merlin_llm_backends import LLMBackend
from merlin_routing_contract import (
    PROMPT_WARNING_NEAR_TOKEN_LIMIT,
    PROMPT_WARNING_TRUNCATED_FOR_TOKEN_LIMIT,
)


class _FakeResponse:
    def __init__(self, payload):
        self.status_code = 200
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class _FakeRequests:
    class exceptions:
        RequestException = requests.exceptions.RequestException


@pytest.fixture(autouse=True)
def _reset_backend_flags(monkeypatch):
    monkeypatch.setattr(settings, "MERLIN_PROMPT_BUCKET_TOKEN_AWARE", False)
    monkeypatch.setattr(settings, "DMS_MIN_PROMPT_TOKENS", 1500)
    monkeypatch.setattr(settings, "DMS_WARMUP_ENABLED", False)
    monkeypatch.setattr(settings, "DMS_WARMUP_TIMEOUT_S", 5)
    monkeypatch.setattr(settings, "DMS_TIMEOUT_SPLIT_ENABLED", False)
    monkeypatch.setattr(settings, "DMS_CONNECT_TIMEOUT_S", 3)
    monkeypatch.setattr(settings, "DMS_READ_TIMEOUT_S", 45)
    monkeypatch.setattr(settings, "DMS_PROMPT_BUCKET_TIMEOUTS_ENABLED", False)
    monkeypatch.setattr(settings, "DMS_TIMEOUT_SHORT_S", 45)
    monkeypatch.setattr(settings, "DMS_TIMEOUT_MEDIUM_S", 45)
    monkeypatch.setattr(settings, "DMS_TIMEOUT_LONG_S", 45)
    monkeypatch.setattr(settings, "DMS_REQUEST_RATE_LIMIT_ENABLED", False)
    monkeypatch.setattr(settings, "DMS_REQUEST_RATE_LIMIT_PER_MINUTE", 60)
    monkeypatch.setattr(settings, "DMS_RETRY_MAX_ATTEMPTS", 1)
    monkeypatch.setattr(settings, "DMS_REASONING_EFFORT", "")
    monkeypatch.setattr(settings, "DMS_PROMPT_CACHE_KEY_ENABLED", False)
    monkeypatch.setattr(settings, "DMS_PROMPT_CACHE_KEY_PREFIX", "merlin:dms")
    monkeypatch.setattr(settings, "DMS_TRACE_HEADER_ENABLED", False)
    monkeypatch.setattr(settings, "DMS_TRACE_HEADER_NAME", "X-Merlin-Request-Id")
    monkeypatch.setattr(settings, "DMS_MODEL_PROVENANCE_ENFORCEMENT", False)
    monkeypatch.setattr(settings, "DMS_NON_COMMERCIAL_MODEL_WAIVER", False)
    monkeypatch.setattr(settings, "MERLIN_LLM_RETRY_ENABLED", False)
    monkeypatch.setattr(settings, "MERLIN_LLM_RETRY_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(settings, "MERLIN_LLM_RETRY_INITIAL_BACKOFF_MS", 1)
    monkeypatch.setattr(settings, "MERLIN_LLM_RETRY_MAX_BACKOFF_MS", 1)
    monkeypatch.setattr(settings, "MERLIN_LLM_RETRY_JITTER_RATIO", 0.0)
    monkeypatch.setattr(settings, "MERLIN_LLM_RETRY_BUDGET_MS", 100)


def test_dms_chat_enabled_uses_openai_compatible_api(monkeypatch):
    monkeypatch.setattr(settings, "LLM_BACKEND", "dms")
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_URL", "http://dms.local/v1/chat/completions")
    monkeypatch.setattr(settings, "DMS_MODEL", "nvidia/Qwen3-8B-DMS-8x")
    monkeypatch.setattr(settings, "DMS_API_KEY", "dms-token")

    backend = LLMBackend()

    captured = {}

    class FakeRequests(_FakeRequests):
        @staticmethod
        def post(url, json, headers=None, timeout=30):
            captured["url"] = url
            captured["payload"] = json
            captured["headers"] = headers
            captured["timeout"] = timeout
            return _FakeResponse(
                {
                    "choices": [{"message": {"content": "dms response"}}],
                    "usage": {
                        "prompt_tokens": 11,
                        "completion_tokens": 4,
                        "total_tokens": 15,
                        "cached_tokens": 2,
                    },
                }
            )

    monkeypatch.setattr("merlin_llm_backends.requests", FakeRequests)

    result = backend.chat_completion(
        [{"role": "user", "content": "hello"}],
        temperature=0.7,
        stream=False,
        timeout=7,
    )

    assert captured["url"] == settings.DMS_URL
    assert captured["payload"]["model"] == "nvidia/Qwen3-8B-DMS-8x"
    assert captured["payload"]["temperature"] == 0.7
    assert captured["headers"]["Authorization"] == "Bearer dms-token"
    assert captured["timeout"] == 7
    assert result["choices"][0]["message"]["content"] == "dms response"
    assert result["usage_normalized"] == {
        "prompt_tokens": 11,
        "completion_tokens": 4,
        "total_tokens": 15,
        "cached_tokens": 2,
    }


def test_dms_chat_includes_reasoning_effort_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "LLM_BACKEND", "dms")
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_URL", "http://dms.local/v1/chat/completions")
    monkeypatch.setattr(settings, "DMS_MODEL", "nvidia/Qwen3-8B-DMS-8x")
    monkeypatch.setattr(settings, "DMS_REASONING_EFFORT", "high")

    backend = LLMBackend()
    captured = {}

    class FakeRequests(_FakeRequests):
        @staticmethod
        def post(url, json, headers=None, timeout=30):
            del url, headers, timeout
            captured["payload"] = json
            return _FakeResponse({"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr("merlin_llm_backends.requests", FakeRequests)
    backend.chat_completion([{"role": "user", "content": "hello"}], timeout=8)

    assert captured["payload"]["reasoning_effort"] == "high"


def test_dms_chat_includes_prompt_cache_key_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, "LLM_BACKEND", "dms")
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_URL", "http://dms.local/v1/chat/completions")
    monkeypatch.setattr(settings, "DMS_MODEL", "nvidia/Qwen3-8B-DMS-8x")
    monkeypatch.setattr(settings, "DMS_PROMPT_CACHE_KEY_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_PROMPT_CACHE_KEY_PREFIX", "merlin:test")

    backend = LLMBackend()
    captured = {}

    class FakeRequests(_FakeRequests):
        @staticmethod
        def post(url, json, headers=None, timeout=30):
            del url, headers, timeout
            captured["payload"] = json
            return _FakeResponse({"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr("merlin_llm_backends.requests", FakeRequests)

    messages = [
        {"role": "system", "content": "policy"},
        {"role": "user", "content": "hello"},
    ]
    backend.chat_completion(messages, timeout=8)

    expected_hash = hashlib.sha256("policy\nhello".encode("utf-8")).hexdigest()
    assert captured["payload"]["prompt_cache_key"] == f"merlin:test:{expected_hash}"


def test_dms_chat_includes_trace_header_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, "LLM_BACKEND", "dms")
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_URL", "http://dms.local/v1/chat/completions")
    monkeypatch.setattr(settings, "DMS_MODEL", "nvidia/Qwen3-8B-DMS-8x")
    monkeypatch.setattr(settings, "DMS_API_KEY", "dms-token")
    monkeypatch.setattr(settings, "DMS_TRACE_HEADER_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_TRACE_HEADER_NAME", "X-Merlin-Trace-Id")

    backend = LLMBackend()
    captured = {}

    class FakeRequests(_FakeRequests):
        @staticmethod
        def post(url, json, headers=None, timeout=30):
            del url, json, timeout
            captured["headers"] = headers
            return _FakeResponse({"choices": [{"message": {"content": "ok"}}]})

    class _FixedUUID:
        hex = "trace-id-123"

    monkeypatch.setattr("merlin_llm_backends.requests", FakeRequests)
    monkeypatch.setattr("merlin_llm_backends.uuid.uuid4", lambda: _FixedUUID())
    backend.chat_completion([{"role": "user", "content": "hello"}], timeout=8)

    assert captured["headers"]["Authorization"] == "Bearer dms-token"
    assert captured["headers"]["X-Merlin-Trace-Id"] == "trace-id-123"


def test_dms_chat_uses_split_connect_read_timeout_profile(monkeypatch):
    monkeypatch.setattr(settings, "LLM_BACKEND", "dms")
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_URL", "http://dms.local/v1/chat/completions")
    monkeypatch.setattr(settings, "DMS_MODEL", "nvidia/Qwen3-8B-DMS-8x")
    monkeypatch.setattr(settings, "DMS_TIMEOUT_SPLIT_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_CONNECT_TIMEOUT_S", 2)

    backend = LLMBackend()
    captured = {}

    class FakeRequests(_FakeRequests):
        @staticmethod
        def post(url, json, headers=None, timeout=30):
            del url, json, headers
            captured["timeout"] = timeout
            return _FakeResponse({"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr("merlin_llm_backends.requests", FakeRequests)
    backend.chat_completion([{"role": "user", "content": "hello"}], timeout=11)

    assert captured["timeout"] == (2, 11)


def test_dms_chat_uses_prompt_bucket_timeout_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, "LLM_BACKEND", "dms")
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_URL", "http://dms.local/v1/chat/completions")
    monkeypatch.setattr(settings, "DMS_MODEL", "nvidia/Qwen3-8B-DMS-8x")
    monkeypatch.setattr(settings, "DMS_PROMPT_BUCKET_TIMEOUTS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_MIN_PROMPT_CHARS", 1000)
    monkeypatch.setattr(settings, "DMS_TIMEOUT_SHORT_S", 4)
    monkeypatch.setattr(settings, "DMS_TIMEOUT_MEDIUM_S", 9)
    monkeypatch.setattr(settings, "DMS_TIMEOUT_LONG_S", 13)

    backend = LLMBackend()
    captured = {}

    class FakeRequests(_FakeRequests):
        @staticmethod
        def post(url, json, headers=None, timeout=30):
            del url, json, headers
            captured["timeout"] = timeout
            return _FakeResponse({"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr("merlin_llm_backends.requests", FakeRequests)
    backend.chat_completion([{"role": "user", "content": "x" * 1400}], timeout=None)

    assert captured["timeout"] == 13


def test_dms_prompt_bucket_timeout_does_not_override_explicit_timeout(monkeypatch):
    monkeypatch.setattr(settings, "LLM_BACKEND", "dms")
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_URL", "http://dms.local/v1/chat/completions")
    monkeypatch.setattr(settings, "DMS_MODEL", "nvidia/Qwen3-8B-DMS-8x")
    monkeypatch.setattr(settings, "DMS_PROMPT_BUCKET_TIMEOUTS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_MIN_PROMPT_CHARS", 1000)
    monkeypatch.setattr(settings, "DMS_TIMEOUT_SHORT_S", 4)
    monkeypatch.setattr(settings, "DMS_TIMEOUT_MEDIUM_S", 9)
    monkeypatch.setattr(settings, "DMS_TIMEOUT_LONG_S", 13)

    backend = LLMBackend()
    captured = {}

    class FakeRequests(_FakeRequests):
        @staticmethod
        def post(url, json, headers=None, timeout=30):
            del url, json, headers
            captured["timeout"] = timeout
            return _FakeResponse({"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr("merlin_llm_backends.requests", FakeRequests)
    backend.chat_completion([{"role": "user", "content": "x" * 1400}], timeout=77)

    assert captured["timeout"] == 77


def test_dms_request_rate_cap_falls_back_to_lm_studio_when_exceeded(monkeypatch):
    monkeypatch.setattr(settings, "LLM_BACKEND", "dms")
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_URL", "http://dms.local/v1/chat/completions")
    monkeypatch.setattr(settings, "DMS_MODEL", "nvidia/Qwen3-8B-DMS-8x")
    monkeypatch.setattr(
        settings, "LM_STUDIO_URL", "http://lm.localhost/v1/chat/completions"
    )
    monkeypatch.setattr(settings, "OPENAI_MODEL", "fallback-model")
    monkeypatch.setattr(settings, "DMS_REQUEST_RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_REQUEST_RATE_LIMIT_PER_MINUTE", 1)

    backend = LLMBackend()
    calls = []

    class FakeRequests(_FakeRequests):
        @staticmethod
        def post(url, json, headers=None, timeout=30):
            del json, headers, timeout
            calls.append(url)
            if url == settings.DMS_URL:
                return _FakeResponse({"choices": [{"message": {"content": "dms-ok"}}]})
            return _FakeResponse({"choices": [{"message": {"content": "lm-ok"}}]})

    monkeypatch.setattr("merlin_llm_backends.requests", FakeRequests)

    first = backend.chat_completion([{"role": "user", "content": "hello"}], timeout=8)
    second = backend.chat_completion([{"role": "user", "content": "hello"}], timeout=8)

    assert first["choices"][0]["message"]["content"] == "dms-ok"
    assert second["choices"][0]["message"]["content"] == "lm-ok"
    assert calls == [settings.DMS_URL, settings.LM_STUDIO_URL]


def test_dms_disabled_falls_back_to_lm_studio(monkeypatch):
    monkeypatch.setattr(settings, "LLM_BACKEND", "dms")
    monkeypatch.setattr(settings, "DMS_ENABLED", False)
    monkeypatch.setattr(
        settings, "LM_STUDIO_URL", "http://lm.localhost/v1/chat/completions"
    )
    monkeypatch.setattr(settings, "OPENAI_MODEL", "gpt-3.5-turbo")

    backend = LLMBackend()
    captured = {}

    class FakeRequests(_FakeRequests):
        @staticmethod
        def post(url, json, headers=None, timeout=30):
            captured["url"] = url
            captured["payload"] = json
            return _FakeResponse({"choices": [{"message": {"content": "fallback"}}]})

    monkeypatch.setattr("merlin_llm_backends.requests", FakeRequests)

    result = backend.chat_completion([{"role": "user", "content": "hello"}], timeout=9)

    assert captured["url"] == settings.LM_STUDIO_URL
    assert captured["payload"]["model"] == settings.OPENAI_MODEL
    assert result["choices"][0]["message"]["content"] == "fallback"


def test_dms_failure_falls_back_to_lm_studio(monkeypatch):
    monkeypatch.setattr(settings, "LLM_BACKEND", "dms")
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_URL", "http://dms.local/v1/chat/completions")
    monkeypatch.setattr(settings, "DMS_MODEL", "nvidia/Qwen3-8B-DMS-8x")
    monkeypatch.setattr(
        settings, "LM_STUDIO_URL", "http://lm.localhost/v1/chat/completions"
    )

    backend = LLMBackend()
    calls = []

    class FakeRequests(_FakeRequests):
        @staticmethod
        def post(url, json, headers=None, timeout=30):
            calls.append(url)
            if url == settings.DMS_URL:
                raise requests.exceptions.RequestException("down")
            return _FakeResponse({"choices": [{"message": {"content": "lm"}}]})

        @staticmethod
        def get(url, headers=None, timeout=5):
            return _FakeResponse({"status": "ok"})

    monkeypatch.setattr("merlin_llm_backends.requests", FakeRequests)

    result = backend.chat_completion([{"role": "user", "content": "hello"}], timeout=8)

    assert calls[0] == settings.DMS_URL
    assert calls[1] == settings.LM_STUDIO_URL
    assert result["choices"][0]["message"]["content"] == "lm"


def test_openai_compatible_extracts_top_level_and_alt_shapes():
    assert (
        LLMBackend._extract_openai_compatible_content(
            {"content": "top-level-content"}
        )
        == "top-level-content"
    )
    assert (
        LLMBackend._extract_openai_compatible_content({"choices": [{"text": "legacy-text"}]})
        == "legacy-text"
    )
    assert (
        LLMBackend._extract_openai_compatible_content(
            {"choices": [{"message": {"content": "choice-message"}}]}
        )
        == "choice-message"
    )
    assert LLMBackend._extract_openai_compatible_content({"text": 123}) == "123"


def test_normalize_usage_openai_compatible_shape_with_cached_details():
    usage = LLMBackend._normalize_usage(
        {
            "usage": {
                "prompt_tokens": 12,
                "completion_tokens": 6,
                "total_tokens": 18,
                "prompt_tokens_details": {"cached_tokens": 5},
            }
        }
    )

    assert usage == {
        "prompt_tokens": 12,
        "completion_tokens": 6,
        "total_tokens": 18,
        "cached_tokens": 5,
    }


def test_normalize_usage_parses_reasoning_tokens_when_present():
    usage = LLMBackend._normalize_usage(
        {
            "usage": {
                "prompt_tokens": 12,
                "completion_tokens": 6,
                "total_tokens": 18,
                "completion_tokens_details": {"reasoning_tokens": 4},
            }
        }
    )

    assert usage == {
        "prompt_tokens": 12,
        "completion_tokens": 6,
        "total_tokens": 18,
        "cached_tokens": 0,
        "reasoning_tokens": 4,
    }


def test_normalize_usage_provider_alt_shape():
    usage = LLMBackend._normalize_usage(
        {
            "prompt_eval_count": 9,
            "eval_count": 3,
            "cache_read_input_tokens": 4,
        }
    )

    assert usage == {
        "prompt_tokens": 9,
        "completion_tokens": 3,
        "total_tokens": 12,
        "cached_tokens": 4,
    }


def test_openai_chat_normalizes_top_level_text_provider_shape(monkeypatch):
    monkeypatch.setattr(settings, "LLM_BACKEND", "openai")
    monkeypatch.setattr(settings, "OPENAI_URL", "http://openai.local/v1/chat/completions")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "token")
    backend = LLMBackend()

    class FakeRequests(_FakeRequests):
        @staticmethod
        def post(url, json, headers=None, timeout=30):
            return _FakeResponse(
                {
                    "text": "legacy output",
                    "prompt_eval_count": 9,
                    "eval_count": 3,
                }
            )

    monkeypatch.setattr("merlin_llm_backends.requests", FakeRequests)
    result = backend.chat_completion([{"role": "user", "content": "hello"}], timeout=8)

    assert result["choices"][0]["message"]["content"] == "legacy output"
    assert result["provider_payload_shape"] == "top_level_text"
    assert result["provider_payload_normalized"] is True
    assert result["usage_normalized"] == {
        "prompt_tokens": 9,
        "completion_tokens": 3,
        "total_tokens": 12,
        "cached_tokens": 0,
    }


def test_timeout_matrix_resolves_by_prompt_bucket(monkeypatch):
    monkeypatch.setattr(settings, "LLM_BACKEND", "dms")
    monkeypatch.setattr(settings, "MERLIN_PROMPT_BUCKET_TOKEN_AWARE", False)
    monkeypatch.setattr(settings, "DMS_MIN_PROMPT_CHARS", 6000)
    monkeypatch.setattr(
        settings,
        "MERLIN_MODEL_TIMEOUT_MATRIX",
        {
            "default": {"short": 10, "medium": 20, "long": 30},
            "dms": {"short": 15, "medium": 25, "long": 45},
        },
    )
    monkeypatch.setattr(settings, "MERLIN_MODEL_TIMEOUT_SHORT_S", 10)
    monkeypatch.setattr(settings, "MERLIN_MODEL_TIMEOUT_MEDIUM_S", 20)
    monkeypatch.setattr(settings, "MERLIN_MODEL_TIMEOUT_LONG_S", 30)
    backend = LLMBackend()

    assert backend._resolve_timeout([{"role": "user", "content": "x" * 100}], None) == 15
    assert (
        backend._resolve_timeout([{"role": "user", "content": "x" * 3500}], None) == 25
    )
    assert (
        backend._resolve_timeout([{"role": "user", "content": "x" * 7000}], None) == 45
    )


def test_explicit_timeout_overrides_timeout_matrix(monkeypatch):
    monkeypatch.setattr(settings, "LLM_BACKEND", "openai")
    monkeypatch.setattr(
        settings,
        "MERLIN_MODEL_TIMEOUT_MATRIX",
        {
            "default": {"short": 10, "medium": 20, "long": 30},
            "openai": {"short": 12, "medium": 22, "long": 32},
        },
    )
    backend = LLMBackend()

    assert backend._resolve_timeout([{"role": "user", "content": "hello"}], 77) == 77


def test_openai_retry_retries_transient_timeout_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, "LLM_BACKEND", "openai")
    monkeypatch.setattr(settings, "OPENAI_URL", "http://openai.local/v1/chat/completions")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "token")
    monkeypatch.setattr(settings, "MERLIN_LLM_RETRY_ENABLED", True)
    monkeypatch.setattr(settings, "MERLIN_LLM_RETRY_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(settings, "MERLIN_LLM_RETRY_INITIAL_BACKOFF_MS", 1)
    monkeypatch.setattr(settings, "MERLIN_LLM_RETRY_MAX_BACKOFF_MS", 1)
    monkeypatch.setattr(settings, "MERLIN_LLM_RETRY_JITTER_RATIO", 0.0)
    monkeypatch.setattr(settings, "MERLIN_LLM_RETRY_BUDGET_MS", 10)

    calls = []
    backend = LLMBackend()

    class FakeRequests(_FakeRequests):
        @staticmethod
        def post(url, json, headers=None, timeout=30):
            calls.append(url)
            if len(calls) == 1:
                raise requests.exceptions.Timeout("transient timeout")
            return _FakeResponse({"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr("merlin_llm_backends.requests", FakeRequests)
    result = backend.chat_completion([{"role": "user", "content": "hello"}], timeout=6)

    assert calls == [settings.OPENAI_URL, settings.OPENAI_URL]
    assert result["choices"][0]["message"]["content"] == "ok"


def test_openai_retry_skips_non_retryable_http_errors(monkeypatch):
    monkeypatch.setattr(settings, "LLM_BACKEND", "openai")
    monkeypatch.setattr(settings, "OPENAI_URL", "http://openai.local/v1/chat/completions")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "token")
    monkeypatch.setattr(settings, "MERLIN_LLM_RETRY_ENABLED", True)
    monkeypatch.setattr(settings, "MERLIN_LLM_RETRY_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(settings, "MERLIN_LLM_RETRY_INITIAL_BACKOFF_MS", 1)
    monkeypatch.setattr(settings, "MERLIN_LLM_RETRY_MAX_BACKOFF_MS", 1)
    monkeypatch.setattr(settings, "MERLIN_LLM_RETRY_JITTER_RATIO", 0.0)
    monkeypatch.setattr(settings, "MERLIN_LLM_RETRY_BUDGET_MS", 10)

    calls = []
    backend = LLMBackend()

    class _BadRequestResponse:
        status_code = 400

    class FakeRequests(_FakeRequests):
        @staticmethod
        def post(url, json, headers=None, timeout=30):
            calls.append(url)
            raise requests.exceptions.HTTPError(
                "bad request",
                response=_BadRequestResponse(),
            )

    monkeypatch.setattr("merlin_llm_backends.requests", FakeRequests)
    with pytest.raises(requests.exceptions.HTTPError):
        backend.chat_completion([{"role": "user", "content": "hello"}], timeout=6)

    assert calls == [settings.OPENAI_URL]


def test_dms_retry_attempts_are_capped_by_dms_profile(monkeypatch):
    monkeypatch.setattr(settings, "LLM_BACKEND", "dms")
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_URL", "http://dms.local/v1/chat/completions")
    monkeypatch.setattr(settings, "DMS_MODEL", "nvidia/Qwen3-8B-DMS-8x")
    monkeypatch.setattr(
        settings, "LM_STUDIO_URL", "http://lm.localhost/v1/chat/completions"
    )
    monkeypatch.setattr(settings, "MERLIN_LLM_RETRY_ENABLED", True)
    monkeypatch.setattr(settings, "MERLIN_LLM_RETRY_MAX_ATTEMPTS", 4)
    monkeypatch.setattr(settings, "MERLIN_LLM_RETRY_INITIAL_BACKOFF_MS", 1)
    monkeypatch.setattr(settings, "MERLIN_LLM_RETRY_MAX_BACKOFF_MS", 1)
    monkeypatch.setattr(settings, "MERLIN_LLM_RETRY_JITTER_RATIO", 0.0)
    monkeypatch.setattr(settings, "MERLIN_LLM_RETRY_BUDGET_MS", 100)
    monkeypatch.setattr(settings, "DMS_RETRY_MAX_ATTEMPTS", 2)

    backend = LLMBackend()
    calls: list[str] = []

    class FakeRequests(_FakeRequests):
        @staticmethod
        def post(url, json, headers=None, timeout=30):
            del json, headers, timeout
            calls.append(url)
            if url == settings.DMS_URL:
                raise requests.exceptions.Timeout("dms timeout")
            return _FakeResponse({"choices": [{"message": {"content": "fallback"}}]})

    monkeypatch.setattr("merlin_llm_backends.requests", FakeRequests)
    result = backend.chat_completion([{"role": "user", "content": "hello"}], timeout=8)

    assert result["choices"][0]["message"]["content"] == "fallback"
    assert calls.count(settings.DMS_URL) == 2
    assert calls[-1] == settings.LM_STUDIO_URL


def test_dms_warmup_success_marks_ready_and_allows_request(monkeypatch):
    monkeypatch.setattr(settings, "LLM_BACKEND", "dms")
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_URL", "http://dms.local/v1/chat/completions")
    monkeypatch.setattr(settings, "DMS_MODEL", "nvidia/Qwen3-8B-DMS-8x")
    monkeypatch.setattr(settings, "DMS_API_KEY", "")
    monkeypatch.setattr(settings, "DMS_WARMUP_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_WARMUP_TIMEOUT_S", 4)
    monkeypatch.setattr(settings, "DMS_WARMUP_PROMPT", "probe")

    calls: list[dict] = []

    class FakeRequests(_FakeRequests):
        @staticmethod
        def post(url, json, headers=None, timeout=30):
            calls.append({"url": url, "payload": json, "timeout": timeout})
            if len(calls) == 1:
                return _FakeResponse({"choices": [{"message": {"content": "warm"}}]})
            return _FakeResponse({"choices": [{"message": {"content": "dms response"}}]})

    monkeypatch.setattr("merlin_llm_backends.requests", FakeRequests)
    backend = LLMBackend()
    result = backend.chat_completion([{"role": "user", "content": "hello"}], timeout=9)
    readiness = backend.get_dms_readiness()

    assert result["choices"][0]["message"]["content"] == "dms response"
    assert calls[0]["url"] == settings.DMS_URL
    assert calls[0]["timeout"] == 4
    assert calls[0]["payload"]["messages"][0]["content"] == "probe"
    assert calls[1]["url"] == settings.DMS_URL
    assert calls[1]["timeout"] == 9
    assert readiness["ready"] is True
    assert readiness["checked"] is True
    assert readiness["detail"] == "warmup_ok"


def test_dms_warmup_failure_falls_back_to_lm_studio(monkeypatch):
    monkeypatch.setattr(settings, "LLM_BACKEND", "dms")
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_URL", "http://dms.local/v1/chat/completions")
    monkeypatch.setattr(settings, "DMS_MODEL", "nvidia/Qwen3-8B-DMS-8x")
    monkeypatch.setattr(settings, "DMS_API_KEY", "")
    monkeypatch.setattr(settings, "DMS_WARMUP_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_WARMUP_TIMEOUT_S", 4)
    monkeypatch.setattr(
        settings, "LM_STUDIO_URL", "http://lm.localhost/v1/chat/completions"
    )

    calls: list[str] = []

    class FakeRequests(_FakeRequests):
        @staticmethod
        def post(url, json, headers=None, timeout=30):
            calls.append(url)
            if url == settings.DMS_URL:
                raise requests.exceptions.RequestException("warmup unavailable")
            return _FakeResponse({"choices": [{"message": {"content": "fallback"}}]})

    monkeypatch.setattr("merlin_llm_backends.requests", FakeRequests)
    backend = LLMBackend()
    result = backend.chat_completion([{"role": "user", "content": "hello"}], timeout=8)
    readiness = backend.get_dms_readiness()

    assert result["choices"][0]["message"]["content"] == "fallback"
    assert calls[0] == settings.DMS_URL
    assert calls[-1] == settings.LM_STUDIO_URL
    assert readiness["ready"] is False
    assert readiness["checked"] is True
    assert "warmup_failed" in readiness["detail"]


def test_dms_model_provenance_warns_when_non_commercial_without_waiver(monkeypatch):
    monkeypatch.setattr(settings, "LLM_BACKEND", "dms")
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_MODEL", "nvidia/Qwen3-8B-DMS-8x")
    monkeypatch.setattr(settings, "DMS_MODEL_PROVENANCE_ENFORCEMENT", False)
    monkeypatch.setattr(settings, "DMS_NON_COMMERCIAL_MODEL_WAIVER", False)

    warning_messages: list[str] = []

    def _capture_warning(message, *args, **kwargs):
        del kwargs
        rendered = message % args if args else message
        warning_messages.append(str(rendered))

    monkeypatch.setattr("merlin_llm_backends.merlin_logger.warning", _capture_warning)

    backend = LLMBackend()
    readiness = backend.get_dms_readiness()
    provenance = readiness["model_provenance"]

    assert provenance["model"] == "nvidia/Qwen3-8B-DMS-8x"
    assert provenance["non_commercial"] is True
    assert provenance["policy_action"] == "warn"
    assert provenance["waiver_applied"] is False
    assert any("policy_action=warn" in message for message in warning_messages)


def test_dms_model_provenance_enforcement_blocks_dms_and_falls_back(monkeypatch):
    monkeypatch.setattr(settings, "LLM_BACKEND", "dms")
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_MODEL", "nvidia/Qwen3-8B-DMS-8x")
    monkeypatch.setattr(settings, "DMS_MODEL_PROVENANCE_ENFORCEMENT", True)
    monkeypatch.setattr(settings, "DMS_NON_COMMERCIAL_MODEL_WAIVER", False)
    monkeypatch.setattr(settings, "DMS_URL", "http://dms.local/v1/chat/completions")
    monkeypatch.setattr(
        settings, "LM_STUDIO_URL", "http://lm.localhost/v1/chat/completions"
    )

    backend = LLMBackend()
    calls: list[str] = []

    class FakeRequests(_FakeRequests):
        @staticmethod
        def post(url, json, headers=None, timeout=30):
            del json, headers, timeout
            calls.append(url)
            if url == settings.DMS_URL:
                raise AssertionError("DMS request should be blocked by provenance policy")
            return _FakeResponse({"choices": [{"message": {"content": "fallback"}}]})

    monkeypatch.setattr("merlin_llm_backends.requests", FakeRequests)

    result = backend.chat_completion([{"role": "user", "content": "hello"}], timeout=8)
    readiness = backend.get_dms_readiness()

    assert result["choices"][0]["message"]["content"] == "fallback"
    assert calls == [settings.LM_STUDIO_URL]
    assert readiness["detail"] == "provenance_blocked"
    assert readiness["model_provenance"]["policy_action"] == "block"


def test_dms_model_provenance_waiver_allows_dms(monkeypatch):
    monkeypatch.setattr(settings, "LLM_BACKEND", "dms")
    monkeypatch.setattr(settings, "DMS_ENABLED", True)
    monkeypatch.setattr(settings, "DMS_MODEL", "nvidia/Qwen3-8B-DMS-8x")
    monkeypatch.setattr(settings, "DMS_MODEL_PROVENANCE_ENFORCEMENT", True)
    monkeypatch.setattr(settings, "DMS_NON_COMMERCIAL_MODEL_WAIVER", True)
    monkeypatch.setattr(settings, "DMS_URL", "http://dms.local/v1/chat/completions")
    monkeypatch.setattr(
        settings, "LM_STUDIO_URL", "http://lm.localhost/v1/chat/completions"
    )

    backend = LLMBackend()
    calls: list[str] = []

    class FakeRequests(_FakeRequests):
        @staticmethod
        def post(url, json, headers=None, timeout=30):
            del json, headers, timeout
            calls.append(url)
            if url == settings.DMS_URL:
                return _FakeResponse({"choices": [{"message": {"content": "dms"}}]})
            return _FakeResponse({"choices": [{"message": {"content": "fallback"}}]})

    monkeypatch.setattr("merlin_llm_backends.requests", FakeRequests)

    result = backend.chat_completion([{"role": "user", "content": "hello"}], timeout=8)
    readiness = backend.get_dms_readiness()

    assert result["choices"][0]["message"]["content"] == "dms"
    assert calls and calls[0] == settings.DMS_URL
    assert readiness["model_provenance"]["policy_action"] == "allow"
    assert readiness["model_provenance"]["waiver_applied"] is True


def test_cached_system_prompt_prefix_reuses_cache(monkeypatch):
    monkeypatch.setattr(settings, "LLM_BACKEND", "huggingface")
    monkeypatch.setattr(settings, "MERLIN_SYSTEM_PROMPT_CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "MERLIN_SYSTEM_PROMPT_CACHE_MAX_ENTRIES", 2)
    backend = LLMBackend()
    messages = [
        {"role": "system", "content": "You are Merlin."},
        {"role": "user", "content": "Summarize this."},
    ]

    first_prompt = backend._build_cached_prefix_prompt(messages)
    second_prompt = backend._build_cached_prefix_prompt(messages)

    assert first_prompt == "You are Merlin.\n\nSummarize this."
    assert second_prompt == first_prompt
    assert len(backend._system_prompt_cache) == 1


def test_huggingface_chat_uses_cached_prefix_prompt(monkeypatch):
    monkeypatch.setattr(settings, "LLM_BACKEND", "huggingface")
    monkeypatch.setattr(settings, "HF_API_KEY", "hf-token")
    monkeypatch.setattr(settings, "HF_API_URL", "http://hf.local/model")
    monkeypatch.setattr(settings, "MERLIN_SYSTEM_PROMPT_CACHE_ENABLED", True)
    backend = LLMBackend()
    captured = {}

    class FakeRequests(_FakeRequests):
        @staticmethod
        def post(url, json, headers=None, timeout=30):
            captured["url"] = url
            captured["payload"] = json
            captured["headers"] = headers
            captured["timeout"] = timeout
            return _FakeResponse([{"generated_text": "ok"}])

    monkeypatch.setattr("merlin_llm_backends.requests", FakeRequests)
    result = backend.chat_completion(
        [
            {"role": "system", "content": "Follow policy."},
            {"role": "user", "content": "Help me."},
        ],
        timeout=6,
    )

    assert captured["url"] == "http://hf.local/model"
    assert captured["headers"]["Authorization"] == "Bearer hf-token"
    assert captured["payload"]["inputs"] == "Follow policy.\n\nHelp me."
    assert captured["timeout"] == 6
    assert result["choices"][0]["message"]["content"] == "ok"


def test_chat_completion_merges_prompt_preflight_warning_metadata(monkeypatch):
    monkeypatch.setattr(settings, "LLM_BACKEND", "openai")
    monkeypatch.setattr(settings, "OPENAI_URL", "http://openai.local/v1/chat/completions")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "token")
    monkeypatch.setattr(settings, "MERLIN_PROMPT_TOKEN_SOFT_LIMIT", 120)
    monkeypatch.setattr(settings, "MERLIN_PROMPT_TOKEN_TRUNCATE_TARGET", 100)
    monkeypatch.setattr(settings, "MERLIN_PROMPT_NEAR_LIMIT_RATIO", 0.9)
    backend = LLMBackend()
    captured = {}

    class FakeRequests(_FakeRequests):
        @staticmethod
        def post(url, json, headers=None, timeout=30):
            captured["url"] = url
            captured["payload"] = json
            captured["timeout"] = timeout
            return _FakeResponse(
                {
                    "choices": [{"message": {"content": "ok"}}],
                    "warnings": ["provider_warning"],
                }
            )

    monkeypatch.setattr("merlin_llm_backends.requests", FakeRequests)
    messages = [{"role": "user", "content": "x" * 440}]
    result = backend.chat_completion(messages, timeout=6)

    assert captured["url"] == settings.OPENAI_URL
    assert captured["payload"]["messages"] == messages
    assert captured["timeout"] == 6
    assert result["prompt_preflight"]["near_token_limit"] is True
    assert result["prompt_preflight"]["truncated"] is False
    assert result["prompt_preflight"]["warnings"] == [PROMPT_WARNING_NEAR_TOKEN_LIMIT]
    assert result["warnings"] == ["provider_warning", PROMPT_WARNING_NEAR_TOKEN_LIMIT]


def test_chat_completion_truncates_prompt_before_backend_dispatch(monkeypatch):
    monkeypatch.setattr(settings, "LLM_BACKEND", "openai")
    monkeypatch.setattr(settings, "OPENAI_URL", "http://openai.local/v1/chat/completions")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "token")
    monkeypatch.setattr(settings, "MERLIN_PROMPT_TOKEN_SOFT_LIMIT", 80)
    monkeypatch.setattr(settings, "MERLIN_PROMPT_TOKEN_TRUNCATE_TARGET", 50)
    monkeypatch.setattr(settings, "MERLIN_PROMPT_NEAR_LIMIT_RATIO", 0.9)
    backend = LLMBackend()
    captured = {}

    class FakeRequests(_FakeRequests):
        @staticmethod
        def post(url, json, headers=None, timeout=30):
            captured["payload"] = json
            return _FakeResponse({"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr("merlin_llm_backends.requests", FakeRequests)
    messages = [
        {"role": "system", "content": "policy"},
        {"role": "user", "content": "a" * 320},
        {"role": "assistant", "content": "b" * 220},
        {"role": "user", "content": "c" * 320},
    ]
    result = backend.chat_completion(messages, timeout=7)

    sent_messages = captured["payload"]["messages"]
    assert sent_messages != messages
    assert sent_messages[0]["role"] == "system"
    assert sent_messages[-1]["role"] == "user"
    assert result["prompt_preflight"]["truncated"] is True
    assert (
        result["prompt_preflight"]["estimated_tokens_after"]
        < result["prompt_preflight"]["estimated_tokens_before"]
    )
    assert PROMPT_WARNING_NEAR_TOKEN_LIMIT in result["warnings"]
    assert PROMPT_WARNING_TRUNCATED_FOR_TOKEN_LIMIT in result["warnings"]
