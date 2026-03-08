from __future__ import annotations

import merlin_emotion_chat as emotion_chat
from merlin_routing_contract import RoutingFallbackReasonCode


def _stub_completion_ok(*_args, **_kwargs):
    return {"choices": [{"message": {"content": "ok"}}]}


def test_prompt_size_bucket_uses_shared_token_aware_policy(monkeypatch):
    query = "word " * 120

    monkeypatch.setattr(
        "merlin_emotion_chat.settings.MERLIN_PROMPT_BUCKET_TOKEN_AWARE", True
    )
    monkeypatch.setattr("merlin_emotion_chat.settings.DMS_MIN_PROMPT_CHARS", 6000)
    monkeypatch.setattr("merlin_emotion_chat.settings.DMS_MIN_PROMPT_TOKENS", 100)

    assert emotion_chat._prompt_size_bucket(query) == "long"

    monkeypatch.setattr(
        "merlin_emotion_chat.settings.MERLIN_PROMPT_BUCKET_TOKEN_AWARE", False
    )
    assert emotion_chat._prompt_size_bucket(query) == "short"


def test_merlin_emotion_chat_uses_disabled_reason_code_when_dms_is_disabled(monkeypatch):
    monkeypatch.setattr("merlin_emotion_chat.settings.LLM_BACKEND", "dms")
    monkeypatch.setattr("merlin_emotion_chat.settings.DMS_ENABLED", False)
    monkeypatch.setattr("merlin_emotion_chat.load_chat", lambda _user_id: [])
    monkeypatch.setattr("merlin_emotion_chat.save_chat", lambda _user_id, _history: None)
    monkeypatch.setattr(emotion_chat.llm_backend, "chat_completion", _stub_completion_ok)

    reply, metadata = emotion_chat.merlin_emotion_chat_with_metadata("hello", "user-1")

    assert reply == "ok"
    assert metadata["fallback_reason_code"] == RoutingFallbackReasonCode.DMS_DISABLED.value
    assert metadata["fallback_stage"] == "config_gate"
    assert metadata["fallback_retryable"] is False


def test_merlin_emotion_chat_classifies_error_fallback_reason(monkeypatch):
    def _raise_timeout(*_args, **_kwargs):
        raise TimeoutError("connection timeout")

    monkeypatch.setattr("merlin_emotion_chat.settings.LLM_BACKEND", "dms")
    monkeypatch.setattr("merlin_emotion_chat.settings.DMS_ENABLED", True)
    monkeypatch.setattr("merlin_emotion_chat.load_chat", lambda _user_id: [])
    monkeypatch.setattr("merlin_emotion_chat.save_chat", lambda _user_id, _history: None)
    monkeypatch.setattr(emotion_chat.llm_backend, "chat_completion", _raise_timeout)

    reply, metadata = emotion_chat.merlin_emotion_chat_with_metadata(
        "hello timeout", "user-2"
    )

    assert "neural link is flickering" in reply
    assert metadata["selected_model"] == "error"
    assert metadata["fallback_reason_code"] == RoutingFallbackReasonCode.DMS_TIMEOUT.value
    assert metadata["fallback_stage"] == "chat_completion"
    assert metadata["fallback_retryable"] is True
