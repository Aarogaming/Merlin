from __future__ import annotations

import merlin_hub_client


def test_emit_research_session_event_returns_false_without_webhook(monkeypatch):
    monkeypatch.delenv("AAS_RESEARCH_EVENT_WEBHOOK_URL", raising=False)
    client = merlin_hub_client.MerlinHubClient()

    assert client.emit_research_session_event({"session_id": "s1"}) is False


def test_emit_research_session_event_posts_to_webhook(monkeypatch):
    monkeypatch.setenv("AAS_RESEARCH_EVENT_WEBHOOK_URL", "http://localhost:9999/hook")
    captured: dict = {}

    class DummyResponse:
        def raise_for_status(self):
            return None

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return DummyResponse()

    monkeypatch.setattr(merlin_hub_client.requests, "post", fake_post)
    client = merlin_hub_client.MerlinHubClient()
    payload = {"session_id": "s1", "event_type": "session.created"}

    assert client.emit_research_session_event(payload) is True
    assert captured["url"] == "http://localhost:9999/hook"
    assert captured["json"] == payload
    assert captured["timeout"] == 5
