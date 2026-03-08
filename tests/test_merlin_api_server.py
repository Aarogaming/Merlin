import json
import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import merlin_api_server as api_server
from merlin_research_manager import ResearchManager

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "contracts"


def auth_headers():
    return {"X-Merlin-Key": "merlin-secret-key"}


def load_contract_fixture(filename: str):
    with (FIXTURES_DIR / filename).open("r", encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def operation_envelope(
    operation_name: str = "assistant.chat.request", payload: dict | None = None
):
    if payload is None:
        payload = {"user_input": "hello", "user_id": "u1"}
    return {
        "schema_name": "AAS.OperationEnvelope",
        "schema_version": "1.0.0",
        "message_id": "5de2f11e-6ff0-4dc6-b241-3e00edbdfed5",
        "correlation_id": "f2c95520-6e66-4a56-ae9e-5c9497ce2e8b",
        "trace_id": "8c25874f-08f3-4948-b031-451de59c151f",
        "timestamp_utc": "2026-02-13T02:30:00Z",
        "source": {
            "repo": "AaroneousAutomationSuite/Hub",
            "component": "hub_orchestrator",
        },
        "target": {
            "repo": "AaroneousAutomationSuite/Merlin",
            "component": "merlin_api_server",
        },
        "operation": {
            "name": operation_name,
            "version": "1.0.0",
            "timeout_ms": 30000,
            "idempotency_key": "chat-req-2026-02-13-0001",
            "expects_ack": True,
            "retry": {"max_attempts": 2},
        },
        "payload": payload,
    }


def test_install_request_body_replay_replays_payload_once():
    class DummyRequest:
        pass

    request = DummyRequest()
    api_server._install_request_body_replay(request, b'{"k":"v"}')

    first = asyncio.run(request._receive())  # type: ignore[attr-defined]
    second = asyncio.run(request._receive())  # type: ignore[attr-defined]

    assert first == {"type": "http.request", "body": b'{"k":"v"}', "more_body": False}
    assert second == {"type": "http.disconnect"}


def test_install_request_body_replay_supports_empty_payload():
    class DummyRequest:
        pass

    request = DummyRequest()
    api_server._install_request_body_replay(request, b"")

    first = asyncio.run(request._receive())  # type: ignore[attr-defined]
    second = asyncio.run(request._receive())  # type: ignore[attr-defined]

    assert first == {"type": "http.request", "body": b"", "more_body": False}
    assert second == {"type": "http.disconnect"}


@pytest.mark.parametrize(
    "version_text,expected",
    [
        ("0.27.0", True),
        ("0.36.3", False),
        ("0.40.0", False),
        ("invalid", False),
    ],
)
def test_requires_legacy_request_body_replay(version_text, expected):
    assert api_server._requires_legacy_request_body_replay(version_text) is expected


def test_health_and_chat(monkeypatch):
    monkeypatch.setattr(
        api_server, "merlin_emotion_chat", lambda user_input, user_id: "ok"
    )
    client = TestClient(api_server.app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    chat = client.post(
        "/merlin/chat",
        json={"user_input": "hi", "user_id": "u1"},
        headers=auth_headers(),
    )
    assert chat.status_code == 200
    assert chat.json()["reply"] == "ok"

    invalid = client.post(
        "/merlin/chat", json={"user_input": ""}, headers=auth_headers()
    )
    assert invalid.status_code == 422


def test_is_valid_api_key_accepts_rotated_keys_from_env(monkeypatch):
    monkeypatch.setenv("MERLIN_API_KEY_ROTATION_STRICT", "true")
    monkeypatch.setenv("MERLIN_API_KEY", "primary-key")
    monkeypatch.setenv("MERLIN_API_KEYS", "secondary-1,secondary-2")
    monkeypatch.delenv("MERLIN_API_KEY_ROTATION_FILE", raising=False)

    assert api_server.is_valid_api_key("primary-key") is True
    assert api_server.is_valid_api_key("secondary-1") is True
    assert api_server.is_valid_api_key("secondary-2") is True
    assert api_server.is_valid_api_key("merlin-secret-key") is False


def test_is_valid_api_key_hot_reloads_rotation_file(monkeypatch, tmp_path):
    key_file = tmp_path / "keys.txt"
    key_file.write_text("file-key-a\n", encoding="utf-8")

    monkeypatch.setenv("MERLIN_API_KEY_ROTATION_STRICT", "true")
    monkeypatch.setenv("MERLIN_API_KEY", "")
    monkeypatch.setenv("MERLIN_API_KEYS", "")
    monkeypatch.setenv("MERLIN_API_KEY_ROTATION_FILE", str(key_file))

    assert api_server.is_valid_api_key("file-key-a") is True
    assert api_server.is_valid_api_key("file-key-b") is False

    key_file.write_text("file-key-b\n", encoding="utf-8")
    assert api_server.is_valid_api_key("file-key-a") is False
    assert api_server.is_valid_api_key("file-key-b") is True


def test_http_access_log_redacts_sensitive_operation_payload_fields(monkeypatch):
    captured_logs: list[dict] = []

    def capture_log(level, message, request_id=None, **kwargs):
        captured_logs.append(
            {
                "level": level,
                "message": message,
                "request_id": request_id,
                "fields": kwargs,
            }
        )

    monkeypatch.setattr(api_server, "log_with_context", capture_log)
    monkeypatch.setattr(
        api_server, "merlin_emotion_chat", lambda user_input, user_id: "ok"
    )
    client = TestClient(api_server.app)

    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="assistant.chat.request",
            payload={
                "user_input": "secret-input",
                "user_id": "u1",
                "content": "secret-content",
                "nested": {"prompt": "hide me", "keep": "visible"},
            },
        ),
        headers=auth_headers(),
    )

    assert response.status_code == 200
    access_entries = [
        entry
        for entry in captured_logs
        if entry["fields"].get("event") == "http_access"
    ]
    assert access_entries
    access_fields = access_entries[-1]["fields"]
    payload = access_fields["request_payload"]["payload"]

    assert payload["user_input"] == "[REDACTED]"
    assert payload["content"] == "[REDACTED]"
    assert payload["nested"]["prompt"] == "[REDACTED]"
    assert payload["nested"]["keep"] == "visible"


def test_operation_dispatch_audit_metadata_contract(monkeypatch):
    captured_audit: list[dict] = []

    def capture_audit(action, details, user="system", request_id=None):
        captured_audit.append(
            {
                "action": action,
                "details": details,
                "user": user,
                "request_id": request_id,
            }
        )

    monkeypatch.setattr(api_server, "log_audit_event", capture_audit)
    monkeypatch.setattr(
        api_server, "merlin_emotion_chat", lambda user_input, user_id: "ok"
    )
    client = TestClient(api_server.app)

    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="assistant.chat.request",
            payload={"user_input": "hello", "user_id": "u1"},
        ),
        headers=auth_headers(),
    )

    assert response.status_code == 200
    assert captured_audit

    event = captured_audit[-1]
    details = event["details"]
    assert event["action"] == "operation.dispatch"
    assert event["user"] == "api_server"
    assert event["request_id"] is not None
    assert details["request_id"] == event["request_id"]
    assert details["route"] == "/merlin/operations"
    assert details["decision_version"] == "operation-dispatch-v1"
    assert details["operation_name"] == "assistant.chat.request"
    assert details["status_code"] == 200


def test_chat_include_metadata(monkeypatch):
    metadata = load_contract_fixture("assistant.chat.routing_metadata.contract.json")
    monkeypatch.setattr(
        api_server,
        "merlin_emotion_chat_with_metadata",
        lambda user_input, user_id: ("ok", metadata),
    )
    monkeypatch.setattr(
        api_server, "merlin_emotion_chat", lambda user_input, user_id: "ok"
    )
    client = TestClient(api_server.app)

    chat = client.post(
        "/merlin/chat",
        json={
            "user_input": "hello",
            "user_id": "u1",
            "include_metadata": True,
        },
        headers=auth_headers(),
    )
    assert chat.status_code == 200
    payload = chat.json()
    assert payload["reply"] == "ok"
    assert payload["metadata"] == metadata
    assert payload["metadata"]["router_policy_version"] == "cp2-2026-02-15"
    assert payload["metadata"]["router_rule_version"] == "cp2-2026-02-15"
    assert payload["metadata"]["routing_telemetry_schema"] == "1.0.0"
    assert "fallback_reason_code" in payload["metadata"]
    assert "fallback_retryable" in payload["metadata"]

    chat_without_metadata = client.post(
        "/merlin/chat",
        json={"user_input": "hello", "user_id": "u1"},
        headers=auth_headers(),
    )
    assert chat_without_metadata.status_code == 200
    assert chat_without_metadata.json()["reply"] == "ok"
    assert "metadata" not in chat_without_metadata.json()


def test_operation_envelope_chat_request_with_metadata(monkeypatch):
    metadata = load_contract_fixture("assistant.chat.routing_metadata.contract.json")
    monkeypatch.setattr(
        api_server,
        "merlin_emotion_chat_with_metadata",
        lambda user_input, user_id: ("fixture-chat-reply", metadata),
    )
    monkeypatch.setattr(
        api_server, "merlin_emotion_chat", lambda user_input, user_id: "ok"
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
    assert body["schema_name"] == expected_fixture["schema_name"]
    assert body["schema_version"] == expected_fixture["schema_version"]
    assert body["operation"]["name"] == expected_fixture["operation"]["name"]
    assert body["payload"] == expected_fixture["payload"]


def test_operation_response_includes_maturity_runtime_metadata(monkeypatch):
    monkeypatch.setattr(api_server.settings, "MERLIN_MATURITY_TIER", "M2")
    monkeypatch.setattr(
        api_server.settings,
        "MERLIN_MATURITY_POLICY_VERSION",
        "mdmm-test-policy-v1",
    )
    monkeypatch.setattr(
        api_server, "merlin_emotion_chat", lambda user_input, user_id: "ok"
    )
    client = TestClient(api_server.app)

    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="assistant.chat.request",
            payload={"user_input": "hello", "user_id": "u1"},
        ),
        headers=auth_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["maturity_tier"] == "M2"
    assert body["metadata"]["maturity_policy_version"] == "mdmm-test-policy-v1"


def test_operation_envelope_chat_request_metadata_ingests_research_signal(
    monkeypatch, tmp_path
):
    manager = ResearchManager(tmp_path / "research_manager", allow_writes=True)
    session = manager.create_session("Ingest planner fallback telemetry")
    session_id = session["session_id"]

    metadata = load_contract_fixture("assistant.chat.routing_metadata.contract.json")
    metadata["fallback_reason_code"] = "dms_timeout"
    metadata["fallback_stage"] = "dms_primary"
    metadata["fallback_reason"] = "timeout"
    metadata["fallback_detail"] = "connect timeout"
    metadata["fallback_retryable"] = True

    monkeypatch.setattr(api_server, "research_manager", manager)
    api_server.register_planner_fallback_telemetry_sink(
        lambda payload: manager.ingest_planner_fallback_telemetry(
            session_id=payload["session_id"],
            telemetry={
                key: value
                for key, value in payload.items()
                if key not in {"session_id", "source"}
            },
            source=str(payload.get("source", "assistant.chat.request")),
        )
    )
    monkeypatch.setattr(
        api_server,
        "merlin_emotion_chat_with_metadata",
        lambda user_input, user_id: ("fixture-chat-reply", metadata),
    )
    client = TestClient(api_server.app)

    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="assistant.chat.request",
            payload={
                "user_input": "capture telemetry",
                "user_id": "u1",
                "include_metadata": True,
                "research_session_id": session_id,
            },
        ),
        headers=auth_headers(),
    )

    assert response.status_code == 200
    payload = response.json()["payload"]
    assert payload["reply"] == "fixture-chat-reply"
    assert payload["research_signal_ingest"]["ingested"] is True
    stored = manager.get_session(session_id)
    assert len(stored["signals"]) == 1
    assert stored["signals"][0]["source"] == "assistant.chat.request:dms_timeout"


def test_operation_capabilities_endpoint():
    client = TestClient(api_server.app)

    response = client.get(
        "/merlin/operations/capabilities",
        headers=auth_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["schema_name"] == "AAS.RepoCapabilityManifest"
    assert body["schema_version"] == "1.0.0"
    assert body["endpoint"] == "/merlin/operations"

    capability_names = {cap["name"] for cap in body["capabilities"]}
    assert "assistant.tools.execute" in capability_names
    assert "merlin.voice.transcribe" in capability_names
    assert "merlin.aas.create_task" in capability_names
    assert "merlin.discovery.run" in capability_names
    assert "merlin.knowledge.search" in capability_names
    assert "merlin.seed.status" in capability_names
    assert "merlin.seed.health" in capability_names
    assert "merlin.seed.health.heartbeat" in capability_names
    assert "merlin.seed.watchdog.tick" in capability_names
    assert "merlin.seed.watchdog.status" in capability_names
    assert "merlin.seed.watchdog.control" in capability_names
    assert "merlin.seed.control" in capability_names


def test_operation_spec_snapshot_endpoint():
    client = TestClient(api_server.app)

    response = client.get(
        "/merlin/operations/spec",
        headers=auth_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["schema_name"] == "AAS.OperationSpecSnapshot"
    assert body["schema_version"] == "1.0.0"
    assert body["endpoint"] == "/merlin/operations"
    assert body["request_schema"]["schema_name"] == "AAS.OperationEnvelope"
    assert body["request_schema"]["schema_version"] == "1.0.0"
    assert body["request_schema"]["contract_path"].endswith(
        "aas.operation-envelope.v1.schema.json"
    )

    operation_rows = {entry["name"]: entry for entry in body["operations"]}
    assert "assistant.chat.request" in operation_rows
    assert operation_rows["assistant.chat.request"]["deprecated"] is False
    assert operation_rows["merlin.voice.listen"]["deprecated"] is True
    assert (
        operation_rows["merlin.voice.listen"]["replacement_operation"]
        == "merlin.voice.transcribe"
    )


def test_operation_capability_flags_endpoint_reports_sources(monkeypatch):
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    monkeypatch.setenv("DMS_ENABLED", "true")
    monkeypatch.setenv("MERLIN_DISABLE_PROMETHEUS_METRICS", "1")
    monkeypatch.setenv("MERLIN_OPERATION_RATE_LIMIT_PER_MINUTE", "30")
    monkeypatch.setenv(
        "MERLIN_OPERATION_RATE_LIMIT_PER_MINUTE_BY_OPERATION",
        "merlin.tasks.create=5",
    )
    monkeypatch.setenv(
        "MERLIN_OPERATION_FEATURE_FLAGS",
        "merlin.tasks.create=disabled",
    )
    monkeypatch.setattr(api_server.settings, "LLM_BACKEND", "adaptive")
    monkeypatch.setattr(api_server.settings, "DMS_ENABLED", True)
    monkeypatch.setattr(
        api_server.settings, "MERLIN_OPERATION_RATE_LIMIT_PER_MINUTE", 30
    )
    monkeypatch.setattr(
        api_server.settings,
        "MERLIN_OPERATION_RATE_LIMIT_PER_MINUTE_BY_OPERATION",
        {"merlin.tasks.create": 5},
    )
    monkeypatch.setattr(
        api_server.settings,
        "MERLIN_OPERATION_FEATURE_FLAGS",
        {"merlin.tasks.create": False},
    )

    class DummyResearchManager:
        allow_writes = False

    monkeypatch.setattr(api_server, "research_manager", DummyResearchManager())

    client = TestClient(api_server.app)
    response = client.get(
        "/merlin/operations/capability-flags",
        headers=auth_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["schema_name"] == "AAS.RepoCapabilityFlags"
    assert body["schema_version"] == "1.0.0"
    flags = {entry["name"]: entry for entry in body["flags"]}

    assert flags["llm_backend"]["source"] == "default"
    assert flags["llm_backend"]["value"] == "adaptive"
    assert flags["dms_enabled"]["source"] == "env"
    assert flags["dms_enabled"]["value"] is True
    assert flags["operation_rate_limit_enabled"]["source"] == "env"
    assert flags["operation_rate_limit_enabled"]["value"] is True
    assert flags["operation_feature_flags"]["source"] == "env"
    assert flags["operation_feature_flags"]["value"]["merlin.tasks.create"] is False
    assert flags["prometheus_metrics_enabled"]["source"] == "env"
    assert flags["prometheus_metrics_enabled"]["value"] is False
    assert flags["research_manager_writable"]["source"] == "runtime"
    assert flags["research_manager_writable"]["value"] is False
    assert flags["research_manager_writable"]["details"]["read_only_mode"] is True


def test_operation_replay_diagnostics_endpoint_disabled(monkeypatch):
    monkeypatch.setattr(
        api_server.settings,
        "MERLIN_OPERATION_REPLAY_DIAGNOSTICS_ENABLED",
        False,
    )
    client = TestClient(api_server.app)

    response = client.get(
        "/merlin/operations/replay-diagnostics",
        headers=auth_headers(),
    )

    assert response.status_code == 404


def test_operation_replay_diagnostics_endpoint_reports_cached_entries(monkeypatch):
    monkeypatch.setattr(
        api_server.settings,
        "MERLIN_OPERATION_REPLAY_DIAGNOSTICS_ENABLED",
        True,
    )
    monkeypatch.setattr(
        api_server.task_manager,
        "add_task",
        lambda title, description, priority: {"id": 1, "title": title},
    )
    client = TestClient(api_server.app)

    envelope = operation_envelope(
        operation_name="merlin.tasks.create",
        payload={"title": "diag task"},
    )
    envelope["operation"]["idempotency_key"] = "diag-key-0001"
    create_response = client.post(
        "/merlin/operations",
        json=envelope,
        headers=auth_headers(),
    )
    assert create_response.status_code == 200

    diagnostics_response = client.get(
        "/merlin/operations/replay-diagnostics",
        headers=auth_headers(),
    )
    assert diagnostics_response.status_code == 200

    body = diagnostics_response.json()
    assert body["schema_name"] == "AAS.OperationReplayDiagnostics"
    assert body["schema_version"] == "1.0.0"
    assert body["enabled"] is True
    assert body["entry_count"] >= 1

    entry = next(
        item
        for item in body["entries"]
        if item["operation_name"] == "merlin.tasks.create"
    )
    assert entry["idempotency_key_preview"] == "diag...0001"
    assert entry["status_code"] == 200
    assert entry["age_seconds"] >= 0.0


def test_uvicorn_runtime_kwargs_honor_settings(monkeypatch):
    monkeypatch.setattr(api_server.settings, "MERLIN_API_HOST", "127.0.0.1")
    monkeypatch.setattr(api_server.settings, "MERLIN_API_PORT", 8123)
    monkeypatch.setattr(api_server.settings, "MERLIN_HTTP_KEEP_ALIVE_TIMEOUT_S", 20)
    monkeypatch.setattr(
        api_server.settings, "MERLIN_HTTP_GRACEFUL_SHUTDOWN_TIMEOUT_S", 50
    )
    monkeypatch.setattr(api_server.settings, "MERLIN_HTTP_LIMIT_CONCURRENCY", 64)
    monkeypatch.setenv("MERLIN_API_RELOAD", "false")

    kwargs = api_server._uvicorn_runtime_kwargs()

    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == 8123
    assert kwargs["reload"] is False
    assert kwargs["timeout_keep_alive"] == 20
    assert kwargs["timeout_graceful_shutdown"] == 50
    assert kwargs["limit_concurrency"] == 64


def test_uvicorn_runtime_kwargs_omit_concurrency_limit_when_unset(monkeypatch):
    monkeypatch.setattr(api_server.settings, "MERLIN_HTTP_LIMIT_CONCURRENCY", None)
    monkeypatch.delenv("MERLIN_API_RELOAD", raising=False)

    kwargs = api_server._uvicorn_runtime_kwargs()

    assert kwargs["reload"] is True
    assert "limit_concurrency" not in kwargs


def test_required_contract_schema_self_check_passes():
    api_server._validate_required_contract_schemas()


def test_required_contract_schema_self_check_fails_when_missing(monkeypatch, tmp_path):
    existing = tmp_path / "exists.schema.json"
    existing.write_text("{}", encoding="utf-8")
    missing = tmp_path / "missing.schema.json"

    monkeypatch.setattr(
        api_server,
        "REQUIRED_CONTRACT_SCHEMA_PATHS",
        (existing, missing),
    )

    with pytest.raises(RuntimeError) as raised:
        api_server._validate_required_contract_schemas()

    message = str(raised.value)
    assert "Missing required contract schema file(s)" in message
    assert str(missing) in message


def test_operation_metrics_endpoint_collects_operation_stats(monkeypatch):
    monkeypatch.setattr(
        api_server, "merlin_emotion_chat", lambda user_input, user_id: "ok"
    )
    with api_server._OPERATION_METRICS_LOCK:
        api_server._OPERATION_METRICS.clear()

    client = TestClient(api_server.app)

    success_response = client.post(
        "/merlin/operations",
        json=operation_envelope(),
        headers=auth_headers(),
    )
    assert success_response.status_code == 200

    invalid_schema = operation_envelope()
    invalid_schema["schema_name"] = "Wrong.Schema"
    error_response = client.post(
        "/merlin/operations",
        json=invalid_schema,
        headers=auth_headers(),
    )
    assert error_response.status_code == 422

    metrics_response = client.get(
        "/merlin/operations/metrics",
        headers=auth_headers(),
    )

    assert metrics_response.status_code == 200
    body = metrics_response.json()
    assert body["schema_name"] == "AAS.OperationMetrics"
    assert body["schema_version"] == "1.0.0"
    assert body["service"] == "merlin_api_server"

    op_rows = {
        entry["name"]: entry
        for entry in body["operations"]
        if entry.get("name") == "assistant.chat.request"
    }
    assert "assistant.chat.request" in op_rows
    chat_metrics = op_rows["assistant.chat.request"]
    assert chat_metrics["count"] == 2
    assert chat_metrics["error_count"] == 1
    assert chat_metrics["latency_ms"]["sample_count"] == 2
    assert chat_metrics["latency_ms"]["p50"] is not None


def test_operation_envelope_chat_request(monkeypatch):
    monkeypatch.setattr(
        api_server, "merlin_emotion_chat", lambda user_input, user_id: "ok"
    )
    client = TestClient(api_server.app)

    response = client.post(
        "/merlin/operations",
        json=operation_envelope(),
        headers=auth_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["schema_name"] == "AAS.OperationEnvelope"
    assert body["schema_version"] == "1.0.0"
    assert body["correlation_id"] == "f2c95520-6e66-4a56-ae9e-5c9497ce2e8b"
    assert body["operation"]["name"] == "assistant.chat.result"
    assert body["payload"]["reply"] == "ok"
    assert body["payload"]["user_id"] == "u1"


def test_operation_envelope_rejects_invalid_schema(monkeypatch):
    monkeypatch.setattr(
        api_server, "merlin_emotion_chat", lambda user_input, user_id: "ok"
    )
    client = TestClient(api_server.app)
    envelope = operation_envelope()
    envelope["schema_name"] = "Wrong.Schema"

    response = client.post(
        "/merlin/operations",
        json=envelope,
        headers=auth_headers(),
    )

    assert response.status_code == 422
    body = response.json()
    assert body["payload"]["error"]["code"] == "INVALID_SCHEMA"
    assert body["payload"]["error"]["retryable"] is False
    assert body["payload"]["error"]["category"] == "validation"


def test_operation_envelope_rejects_newer_schema_version_with_downgrade_error(
    monkeypatch,
):
    monkeypatch.setattr(
        api_server, "merlin_emotion_chat", lambda user_input, user_id: "ok"
    )
    client = TestClient(api_server.app)
    envelope = operation_envelope()
    envelope["schema_version"] = "2.0.0"

    response = client.post(
        "/merlin/operations",
        json=envelope,
        headers=auth_headers(),
    )

    assert response.status_code == 422
    body = response.json()
    assert body["payload"]["error"]["code"] == "SCHEMA_VERSION_DOWNGRADE_REQUIRED"
    assert "downgrade" in body["payload"]["error"]["message"]
    assert body["payload"]["error"]["category"] == "validation"


def test_operation_envelope_rejects_older_schema_version_with_upgrade_error(
    monkeypatch,
):
    monkeypatch.setattr(
        api_server, "merlin_emotion_chat", lambda user_input, user_id: "ok"
    )
    client = TestClient(api_server.app)
    envelope = operation_envelope()
    envelope["schema_version"] = "0.9.0"

    response = client.post(
        "/merlin/operations",
        json=envelope,
        headers=auth_headers(),
    )

    assert response.status_code == 422
    body = response.json()
    assert body["payload"]["error"]["code"] == "SCHEMA_VERSION_UPGRADE_REQUIRED"
    assert "upgrade" in body["payload"]["error"]["message"]
    assert body["payload"]["error"]["category"] == "validation"


def test_operation_envelope_rejects_non_semver_schema_version(monkeypatch):
    monkeypatch.setattr(
        api_server, "merlin_emotion_chat", lambda user_input, user_id: "ok"
    )
    client = TestClient(api_server.app)
    envelope = operation_envelope()
    envelope["schema_version"] = "v1"

    response = client.post(
        "/merlin/operations",
        json=envelope,
        headers=auth_headers(),
    )

    assert response.status_code == 422
    body = response.json()
    assert body["payload"]["error"]["code"] == "INVALID_SCHEMA_VERSION"
    assert "semver" in body["payload"]["error"]["message"]
    assert body["payload"]["error"]["category"] == "validation"


def test_operation_envelope_requires_correlation_id_for_mutating_operation(monkeypatch):
    monkeypatch.setattr(
        api_server, "merlin_emotion_chat", lambda user_input, user_id: "ok"
    )
    client = TestClient(api_server.app)
    envelope = operation_envelope(
        operation_name="merlin.tasks.create",
        payload={"title": "task title"},
    )
    envelope["correlation_id"] = None

    response = client.post(
        "/merlin/operations",
        json=envelope,
        headers=auth_headers(),
    )

    assert response.status_code == 422
    body = response.json()
    assert body["payload"]["error"]["code"] == "MISSING_CORRELATION_ID"
    assert body["payload"]["error"]["category"] == "validation"
    assert "merlin.tasks.create" in body["payload"]["error"]["message"]


def test_operation_envelope_allows_missing_correlation_id_for_read_operation(
    monkeypatch,
):
    monkeypatch.setattr(api_server.task_manager, "list_tasks", lambda: [])
    client = TestClient(api_server.app)
    envelope = operation_envelope(
        operation_name="merlin.tasks.list",
        payload={},
    )
    envelope["correlation_id"] = None

    response = client.post(
        "/merlin/operations",
        json=envelope,
        headers=auth_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["payload"]["tasks"] == []


def test_operation_envelope_requires_idempotency_key_for_create_operation(monkeypatch):
    monkeypatch.setattr(api_server.task_manager, "add_task", lambda *args, **kwargs: {})
    client = TestClient(api_server.app)
    envelope = operation_envelope(
        operation_name="merlin.tasks.create",
        payload={"title": "task title"},
    )
    envelope["operation"]["idempotency_key"] = None

    response = client.post(
        "/merlin/operations",
        json=envelope,
        headers=auth_headers(),
    )

    assert response.status_code == 422
    body = response.json()
    assert body["payload"]["error"]["code"] == "MISSING_IDEMPOTENCY_KEY"
    assert body["payload"]["error"]["category"] == "validation"


def test_operation_envelope_replays_cached_response_for_same_idempotency_key(
    monkeypatch,
):
    api_server._IDEMPOTENCY_RESPONSE_CACHE.clear()
    created: list[tuple[str, str, str]] = []

    def fake_add_task(title, description, priority):
        created.append((title, description, priority))
        return {"id": len(created), "title": title, "priority": priority}

    monkeypatch.setattr(api_server.task_manager, "add_task", fake_add_task)
    client = TestClient(api_server.app)
    envelope = operation_envelope(
        operation_name="merlin.tasks.create",
        payload={"title": "task title", "description": "desc", "priority": "High"},
    )
    envelope["operation"]["idempotency_key"] = "task-create-dup-1"

    first = client.post(
        "/merlin/operations",
        json=envelope,
        headers=auth_headers(),
    )
    second = client.post(
        "/merlin/operations",
        json=envelope,
        headers=auth_headers(),
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(created) == 1
    assert second.headers["X-Merlin-Idempotent-Replay"] == "true"
    assert second.json() == first.json()


def test_operation_envelope_different_idempotency_keys_execute_distinct_creates(
    monkeypatch,
):
    api_server._IDEMPOTENCY_RESPONSE_CACHE.clear()
    created: list[str] = []

    def fake_add_task(title, description, priority):
        created.append(title)
        return {"id": len(created), "title": title}

    monkeypatch.setattr(api_server.task_manager, "add_task", fake_add_task)
    client = TestClient(api_server.app)

    first_envelope = operation_envelope(
        operation_name="merlin.tasks.create",
        payload={"title": "task alpha"},
    )
    first_envelope["operation"]["idempotency_key"] = "task-create-key-1"

    second_envelope = operation_envelope(
        operation_name="merlin.tasks.create",
        payload={"title": "task alpha"},
    )
    second_envelope["operation"]["idempotency_key"] = "task-create-key-2"

    first = client.post(
        "/merlin/operations",
        json=first_envelope,
        headers=auth_headers(),
    )
    second = client.post(
        "/merlin/operations",
        json=second_envelope,
        headers=auth_headers(),
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(created) == 2


def test_operation_envelope_feature_flag_blocks_disabled_operation(monkeypatch):
    monkeypatch.setattr(
        api_server.settings,
        "MERLIN_OPERATION_FEATURE_FLAGS",
        {"merlin.tasks.create": False},
    )
    monkeypatch.setattr(
        api_server.task_manager,
        "add_task",
        lambda title, description, priority: {"id": 1, "title": title},
    )
    client = TestClient(api_server.app)

    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.tasks.create",
            payload={"title": "blocked"},
        ),
        headers=auth_headers(),
    )

    assert response.status_code == 403
    body = response.json()
    assert body["payload"]["error"]["code"] == "OPERATION_DISABLED"
    assert body["payload"]["error"]["category"] == "policy"


def test_operation_envelope_feature_flag_allows_enabled_operation(monkeypatch):
    monkeypatch.setattr(
        api_server.settings,
        "MERLIN_OPERATION_FEATURE_FLAGS",
        {"merlin.tasks.create": True},
    )
    monkeypatch.setattr(
        api_server.task_manager,
        "add_task",
        lambda title, description, priority: {"id": 1, "title": title},
    )
    client = TestClient(api_server.app)

    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.tasks.create",
            payload={"title": "enabled"},
        ),
        headers=auth_headers(),
    )

    assert response.status_code == 200
    assert response.json()["payload"]["task"]["title"] == "enabled"


def test_operation_envelope_maturity_allowlist_blocks_disallowed_operation(monkeypatch):
    monkeypatch.setattr(api_server.settings, "MERLIN_MATURITY_TIER", "M0")
    monkeypatch.setattr(
        api_server.settings,
        "MERLIN_MATURITY_OPERATION_ALLOWLISTS",
        {
            "M0": frozenset({"assistant.chat.request"}),
            "M1": frozenset({"*"}),
            "M2": frozenset({"*"}),
            "M3": frozenset({"*"}),
            "M4": frozenset({"*"}),
        },
    )
    monkeypatch.setattr(api_server.settings, "MERLIN_OPERATION_FEATURE_FLAGS", {})
    monkeypatch.setattr(
        api_server.settings, "MERLIN_OPERATION_RATE_LIMIT_PER_MINUTE", 0
    )
    monkeypatch.setattr(
        api_server.settings, "MERLIN_OPERATION_RATE_LIMIT_PER_MINUTE_BY_OPERATION", {}
    )
    with api_server._OPERATION_RATE_LIMIT_LOCK:
        api_server._OPERATION_RATE_WINDOWS.clear()
    client = TestClient(api_server.app)

    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.alerts.list",
            payload={},
        ),
        headers=auth_headers(),
    )

    assert response.status_code == 403
    body = response.json()
    assert body["payload"]["error"]["code"] == "OPERATION_NOT_ALLOWED_FOR_MATURITY_TIER"
    assert body["payload"]["error"]["category"] == "policy"
    assert "maturity tier M0" in body["payload"]["error"]["message"]


def test_operation_envelope_maturity_allowlist_allows_configured_operation(monkeypatch):
    monkeypatch.setattr(api_server.settings, "MERLIN_MATURITY_TIER", "M0")
    monkeypatch.setattr(
        api_server.settings,
        "MERLIN_MATURITY_OPERATION_ALLOWLISTS",
        {
            "M0": frozenset({"assistant.chat.request", "merlin.alerts.list"}),
            "M1": frozenset({"*"}),
            "M2": frozenset({"*"}),
            "M3": frozenset({"*"}),
            "M4": frozenset({"*"}),
        },
    )
    monkeypatch.setattr(api_server.settings, "MERLIN_OPERATION_FEATURE_FLAGS", {})
    monkeypatch.setattr(
        api_server.settings, "MERLIN_OPERATION_RATE_LIMIT_PER_MINUTE", 0
    )
    monkeypatch.setattr(
        api_server.settings, "MERLIN_OPERATION_RATE_LIMIT_PER_MINUTE_BY_OPERATION", {}
    )
    with api_server._OPERATION_RATE_LIMIT_LOCK:
        api_server._OPERATION_RATE_WINDOWS.clear()
    client = TestClient(api_server.app)

    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.alerts.list",
            payload={},
        ),
        headers=auth_headers(),
    )

    assert response.status_code == 200
    assert response.json()["payload"]["alerts"][0]["severity"] == "warning"


def test_operation_envelope_mentor_pass_blocks_high_risk_operation(monkeypatch):
    monkeypatch.setenv("MERLIN_MENTOR_PASS_REQUIRED_TIERS", "M1")
    monkeypatch.setattr(api_server.settings, "MERLIN_MATURITY_TIER", "M1")
    monkeypatch.setattr(
        api_server.settings,
        "MERLIN_MATURITY_OPERATION_ALLOWLISTS",
        {
            "M0": frozenset({"*"}),
            "M1": frozenset({"*"}),
            "M2": frozenset({"*"}),
            "M3": frozenset({"*"}),
            "M4": frozenset({"*"}),
        },
    )
    monkeypatch.setattr(api_server.settings, "MERLIN_OPERATION_FEATURE_FLAGS", {})
    monkeypatch.setattr(
        api_server.settings, "MERLIN_OPERATION_RATE_LIMIT_PER_MINUTE", 0
    )
    monkeypatch.setattr(
        api_server.settings, "MERLIN_OPERATION_RATE_LIMIT_PER_MINUTE_BY_OPERATION", {}
    )
    with api_server._OPERATION_RATE_LIMIT_LOCK:
        api_server._OPERATION_RATE_WINDOWS.clear()
    client = TestClient(api_server.app)

    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.command.execute",
            payload={"command": "echo hi"},
        ),
        headers=auth_headers(),
    )

    assert response.status_code == 403
    body = response.json()
    assert body["payload"]["error"]["code"] == "OPERATION_REQUIRES_MENTOR_PASS"
    assert body["payload"]["error"]["category"] == "policy"
    assert "requires mentor pass" in body["payload"]["error"]["message"]


def test_operation_envelope_mentor_pass_allows_high_risk_operation(monkeypatch):
    monkeypatch.setenv("MERLIN_MENTOR_PASS_REQUIRED_TIERS", "M1")
    monkeypatch.setattr(api_server.settings, "MERLIN_MATURITY_TIER", "M1")
    monkeypatch.setattr(
        api_server.settings,
        "MERLIN_MATURITY_OPERATION_ALLOWLISTS",
        {
            "M0": frozenset({"*"}),
            "M1": frozenset({"*"}),
            "M2": frozenset({"*"}),
            "M3": frozenset({"*"}),
            "M4": frozenset({"*"}),
        },
    )
    monkeypatch.setattr(api_server.settings, "MERLIN_OPERATION_FEATURE_FLAGS", {})
    monkeypatch.setattr(
        api_server.settings, "MERLIN_OPERATION_RATE_LIMIT_PER_MINUTE", 0
    )
    monkeypatch.setattr(
        api_server.settings, "MERLIN_OPERATION_RATE_LIMIT_PER_MINUTE_BY_OPERATION", {}
    )
    monkeypatch.setattr(
        api_server.policy_manager, "is_command_allowed", lambda command: True
    )
    monkeypatch.setattr(
        api_server,
        "execute_command",
        lambda command: {"stdout": "ok", "stderr": "", "returncode": 0},
    )
    with api_server._OPERATION_RATE_LIMIT_LOCK:
        api_server._OPERATION_RATE_WINDOWS.clear()
    client = TestClient(api_server.app)
    envelope = operation_envelope(
        operation_name="merlin.command.execute",
        payload={"command": "echo hi"},
    )
    envelope["metadata"] = {"mentor_pass": {"approved": True, "reviewer": "mentor-1"}}

    response = client.post(
        "/merlin/operations",
        json=envelope,
        headers=auth_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["payload"]["output"] == "ok"
    assert body["payload"]["returncode"] == 0


def test_operation_envelope_rejects_payload_too_large(monkeypatch):
    monkeypatch.setattr(
        api_server, "merlin_emotion_chat", lambda user_input, user_id: "ok"
    )
    monkeypatch.setattr(api_server.settings, "MERLIN_OPERATION_PAYLOAD_MAX_BYTES", 128)
    monkeypatch.setattr(
        api_server.settings, "MERLIN_OPERATION_PAYLOAD_MAX_BYTES_BY_OPERATION", {}
    )
    client = TestClient(api_server.app)

    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            payload={"user_input": "x" * 512, "user_id": "u1"},
        ),
        headers=auth_headers(),
    )

    assert response.status_code == 413
    body = response.json()
    assert body["payload"]["error"]["code"] == "PAYLOAD_TOO_LARGE"
    assert body["payload"]["error"]["category"] == "validation"
    assert "payload exceeds max bytes" in body["payload"]["error"]["message"]


def test_operation_envelope_payload_size_uses_operation_override(monkeypatch):
    monkeypatch.setattr(
        api_server, "merlin_emotion_chat", lambda user_input, user_id: "ok"
    )
    monkeypatch.setattr(api_server.settings, "MERLIN_OPERATION_PAYLOAD_MAX_BYTES", 4096)
    monkeypatch.setattr(
        api_server.settings,
        "MERLIN_OPERATION_PAYLOAD_MAX_BYTES_BY_OPERATION",
        {"assistant.chat.request": 64},
    )
    client = TestClient(api_server.app)

    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            payload={"user_input": "x" * 256, "user_id": "u1"},
        ),
        headers=auth_headers(),
    )

    assert response.status_code == 413
    body = response.json()
    assert body["payload"]["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_operation_envelope_rate_limit_applies_per_operation(monkeypatch):
    monkeypatch.setattr(
        api_server, "merlin_emotion_chat", lambda user_input, user_id: "ok"
    )
    monkeypatch.setattr(
        api_server.settings, "MERLIN_OPERATION_RATE_LIMIT_PER_MINUTE", 1
    )
    monkeypatch.setattr(
        api_server.settings, "MERLIN_OPERATION_RATE_LIMIT_PER_MINUTE_BY_OPERATION", {}
    )
    with api_server._OPERATION_RATE_LIMIT_LOCK:
        api_server._OPERATION_RATE_WINDOWS.clear()

    client = TestClient(api_server.app)
    first = client.post(
        "/merlin/operations",
        json=operation_envelope(),
        headers=auth_headers(),
    )
    assert first.status_code == 200

    second = client.post(
        "/merlin/operations",
        json=operation_envelope(),
        headers=auth_headers(),
    )
    assert second.status_code == 429
    error = second.json()["payload"]["error"]
    assert error["code"] == "RATE_LIMITED"
    assert error["retryable"] is True
    assert error["category"] == "policy"


def test_error_category_mapping_defaults_to_unknown():
    assert api_server._error_category_for_code("SOME_UNKNOWN_CODE") == "unknown"
    assert api_server._error_category_for_code("COMMAND_BLOCKED") == "policy"
    assert (
        api_server._error_category_for_code("OPERATION_REQUIRES_MENTOR_PASS")
        == "policy"
    )
    assert api_server._error_category_for_code("VOICE_UNAVAILABLE") == "dependency"
    assert (
        api_server._error_category_for_code("DEPENDENCY_CIRCUIT_OPEN") == "dependency"
    )
    assert api_server._error_category_for_code("PLUGIN_CRASH_ISOLATED") == "dependency"
    assert (
        api_server._error_category_for_code("PLUGIN_PROCESS_SERIALIZATION_ERROR")
        == "dependency"
    )


def test_operation_envelope_rejects_unsupported_operation(monkeypatch):
    monkeypatch.setattr(
        api_server, "merlin_emotion_chat", lambda user_input, user_id: "ok"
    )
    client = TestClient(api_server.app)

    response = client.post(
        "/merlin/operations",
        json=operation_envelope(operation_name="assistant.magic.request"),
        headers=auth_headers(),
    )

    assert response.status_code == 400
    body = response.json()
    assert body["operation"]["name"] == "assistant.magic.result"
    assert body["payload"]["error"]["code"] == "UNSUPPORTED_OPERATION"


def test_operation_envelope_tools_execute(monkeypatch):
    monkeypatch.setattr(
        api_server.plugin_manager,
        "execute_plugin",
        lambda name, *args, **kwargs: {
            "name": name,
            "args": list(args),
            "kwargs": kwargs,
        },
    )
    client = TestClient(api_server.app)

    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="assistant.tools.execute",
            payload={"name": "demo_tool", "args": ["a"], "kwargs": {"flag": True}},
        ),
        headers=auth_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["operation"]["name"] == "assistant.tools.execute.result"
    assert body["payload"]["name"] == "demo_tool"
    assert body["payload"]["result"]["args"] == ["a"]
    assert body["payload"]["result"]["kwargs"]["flag"] is True


def test_operation_envelope_tools_execute_not_found(monkeypatch):
    monkeypatch.setattr(
        api_server.plugin_manager,
        "execute_plugin",
        lambda name, *args, **kwargs: {"error": f"Plugin {name} not found"},
    )
    client = TestClient(api_server.app)

    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="assistant.tools.execute",
            payload={"name": "missing_tool"},
        ),
        headers=auth_headers(),
    )

    assert response.status_code == 404
    body = response.json()
    assert body["payload"]["error"]["code"] == "TOOL_NOT_FOUND"
    assert "missing_tool" in body["payload"]["error"]["message"]


def test_operation_envelope_tools_execute_permission_denied(monkeypatch):
    monkeypatch.setattr(
        api_server.plugin_manager,
        "execute_plugin",
        lambda name, *args, **kwargs: {
            "error": "Plugin demo_tool denied by policy for permission tiers: exec",
            "code": "PLUGIN_PERMISSION_DENIED",
            "denied_permissions": ["exec"],
        },
    )
    client = TestClient(api_server.app)

    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="assistant.tools.execute",
            payload={"name": "demo_tool"},
        ),
        headers=auth_headers(),
    )

    assert response.status_code == 403
    body = response.json()
    assert body["payload"]["error"]["code"] == "PLUGIN_PERMISSION_DENIED"
    assert body["payload"]["error"]["category"] == "policy"


def test_operation_envelope_tools_execute_timeout(monkeypatch):
    monkeypatch.setattr(
        api_server.plugin_manager,
        "execute_plugin",
        lambda name, *args, **kwargs: {
            "error": "Plugin demo_tool timed out after 0.01s",
            "code": "PLUGIN_TIMEOUT",
            "timeout_seconds": 0.01,
        },
    )
    client = TestClient(api_server.app)

    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="assistant.tools.execute",
            payload={"name": "demo_tool"},
        ),
        headers=auth_headers(),
    )

    assert response.status_code == 504
    body = response.json()
    assert body["payload"]["error"]["code"] == "PLUGIN_TIMEOUT"
    assert body["payload"]["error"]["retryable"] is True
    assert body["payload"]["error"]["category"] == "dependency"


def test_operation_envelope_tools_execute_process_serialization_error(monkeypatch):
    monkeypatch.setattr(
        api_server.plugin_manager,
        "execute_plugin",
        lambda name, *args, **kwargs: {
            "error": "Plugin demo_tool process serialization failed: cannot pickle",
            "code": "PLUGIN_PROCESS_SERIALIZATION_ERROR",
        },
    )
    client = TestClient(api_server.app)

    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="assistant.tools.execute",
            payload={"name": "demo_tool"},
        ),
        headers=auth_headers(),
    )

    assert response.status_code == 502
    body = response.json()
    assert body["payload"]["error"]["code"] == "PLUGIN_PROCESS_SERIALIZATION_ERROR"
    assert body["payload"]["error"]["retryable"] is False
    assert body["payload"]["error"]["category"] == "dependency"


def test_operation_envelope_tools_execute_crash_isolated(monkeypatch):
    monkeypatch.setattr(
        api_server.plugin_manager,
        "execute_plugin",
        lambda name, *args, **kwargs: {
            "error": "Plugin demo_tool is isolated after repeated crashes",
            "code": "PLUGIN_CRASH_ISOLATED",
        },
    )
    client = TestClient(api_server.app)

    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="assistant.tools.execute",
            payload={"name": "demo_tool"},
        ),
        headers=auth_headers(),
    )

    assert response.status_code == 503
    body = response.json()
    assert body["payload"]["error"]["code"] == "PLUGIN_CRASH_ISOLATED"
    assert body["payload"]["error"]["retryable"] is True
    assert body["payload"]["error"]["category"] == "dependency"


def test_operation_envelope_tools_execute_contract_fixture(monkeypatch):
    monkeypatch.setattr(
        api_server.plugin_manager,
        "execute_plugin",
        lambda name, *args, **kwargs: {"ok": True},
    )
    client = TestClient(api_server.app)
    request_fixture = load_contract_fixture("assistant.tools.execute.request.json")
    expected_fixture = load_contract_fixture(
        "assistant.tools.execute.expected_response.json"
    )

    response = client.post(
        "/merlin/operations",
        json=request_fixture,
        headers=auth_headers(),
    )

    assert response.status_code == 200
    body = response.json()

    assert body["schema_name"] == expected_fixture["schema_name"]
    assert body["schema_version"] == expected_fixture["schema_version"]
    assert body["correlation_id"] == expected_fixture["correlation_id"]
    assert body["trace_id"] == expected_fixture["trace_id"]
    assert body["operation"]["name"] == expected_fixture["operation"]["name"]
    assert body["operation"]["version"] == expected_fixture["operation"]["version"]
    assert body["payload"]["name"] == expected_fixture["payload"]["name"]
    assert body["payload"]["result"] == expected_fixture["payload"]["result"]
    assert isinstance(body["message_id"], str)
    assert isinstance(body["timestamp_utc"], str)


def test_operation_envelope_voice_status_and_synthesize(monkeypatch, tmp_path):
    class DummyVoice:
        def status(self):
            return {"tts": {"primary": "dummy"}, "stt": {"primary": "dummy"}}

        def synthesize_to_file(self, text, engine=None):
            output = tmp_path / "voice.wav"
            output.write_bytes(b"RIFFDATA")
            return str(output)

    monkeypatch.setattr(api_server, "get_voice", lambda: DummyVoice())
    client = TestClient(api_server.app)

    status_response = client.post(
        "/merlin/operations",
        json=operation_envelope(operation_name="merlin.voice.status", payload={}),
        headers=auth_headers(),
    )

    assert status_response.status_code == 200
    assert status_response.json()["payload"]["status"]["tts"]["primary"] == "dummy"

    synth_response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.voice.synthesize",
            payload={"text": "hello world", "engine": "dummy"},
        ),
        headers=auth_headers(),
    )

    assert synth_response.status_code == 200
    synth_payload = synth_response.json()["payload"]
    assert synth_payload["filename"] == "voice.wav"
    assert synth_payload["path"].endswith("voice.wav")


def test_operation_envelope_voice_unavailable(monkeypatch):
    monkeypatch.setattr(api_server, "get_voice", lambda: None)
    client = TestClient(api_server.app)

    response = client.post(
        "/merlin/operations",
        json=operation_envelope(operation_name="merlin.voice.status", payload={}),
        headers=auth_headers(),
    )

    assert response.status_code == 503
    assert response.json()["payload"]["error"]["code"] == "VOICE_UNAVAILABLE"


def test_operation_envelope_voice_listen_and_transcribe(monkeypatch):
    class DummyVoice:
        def listen(self, engine=None):
            return "heard text"

        def transcribe_file(self, path, engine=None):
            return f"transcribed:{path}"

    monkeypatch.setattr(api_server, "get_voice", lambda: DummyVoice())
    client = TestClient(api_server.app)

    listen_response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.voice.listen", payload={"engine": "dummy"}
        ),
        headers=auth_headers(),
    )
    assert listen_response.status_code == 200
    assert listen_response.json()["payload"]["text"] == "heard text"

    transcribe_response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.voice.transcribe",
            payload={"file_path": "/tmp/sample.wav", "engine": "dummy"},
        ),
        headers=auth_headers(),
    )
    assert transcribe_response.status_code == 200
    transcribe_payload = transcribe_response.json()["payload"]
    assert transcribe_payload["text"] == "transcribed:/tmp/sample.wav"
    assert transcribe_payload["file_path"] == "/tmp/sample.wav"


def test_operation_envelope_deprecated_operation_includes_headers(monkeypatch):
    class DummyVoice:
        def listen(self, engine=None):
            return "heard text"

        def transcribe_file(self, path, engine=None):
            return "transcribed text"

    monkeypatch.setattr(api_server, "get_voice", lambda: DummyVoice())
    client = TestClient(api_server.app)

    deprecated_response = client.post(
        "/merlin/operations",
        json=operation_envelope(operation_name="merlin.voice.listen", payload={}),
        headers=auth_headers(),
    )
    assert deprecated_response.status_code == 200
    assert deprecated_response.headers["Deprecation"] == "true"
    assert deprecated_response.headers["Sunset"] == "2026-06-30T00:00:00Z"
    assert (
        deprecated_response.headers["X-Merlin-Replacement-Operation"]
        == "merlin.voice.transcribe"
    )
    assert "deprecation-policy" in deprecated_response.headers["Link"]

    active_response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.voice.transcribe",
            payload={"file_path": "/tmp/sample.wav"},
        ),
        headers=auth_headers(),
    )
    assert active_response.status_code == 200
    assert "Deprecation" not in active_response.headers


def test_operation_envelope_voice_transcribe_contract_fixture(monkeypatch):
    class DummyVoice:
        def transcribe_file(self, path, engine=None):
            return "fixture-transcribed"

    monkeypatch.setattr(api_server, "get_voice", lambda: DummyVoice())
    client = TestClient(api_server.app)
    request_fixture = load_contract_fixture("merlin.voice.transcribe.request.json")
    expected_fixture = load_contract_fixture(
        "merlin.voice.transcribe.expected_response.json"
    )

    response = client.post(
        "/merlin/operations",
        json=request_fixture,
        headers=auth_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["schema_name"] == expected_fixture["schema_name"]
    assert body["schema_version"] == expected_fixture["schema_version"]
    assert body["correlation_id"] == expected_fixture["correlation_id"]
    assert body["trace_id"] == expected_fixture["trace_id"]
    assert body["operation"]["name"] == expected_fixture["operation"]["name"]
    assert body["operation"]["version"] == expected_fixture["operation"]["version"]
    assert body["payload"]["text"] == expected_fixture["payload"]["text"]
    assert body["payload"]["file_path"] == expected_fixture["payload"]["file_path"]
    assert isinstance(body["message_id"], str)
    assert isinstance(body["timestamp_utc"], str)


def test_operation_envelope_user_create_and_authenticate(monkeypatch):
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
        lambda data, expires_delta=None: "token-123",
    )
    client = TestClient(api_server.app)

    create_response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.user_manager.create",
            payload={"username": "alice", "password": "pw", "role": "admin"},
        ),
        headers=auth_headers(),
    )
    assert create_response.status_code == 200
    assert create_response.json()["payload"]["user"]["username"] == "alice"

    auth_response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.user_manager.authenticate",
            payload={"username": "alice", "password": "pw"},
        ),
        headers=auth_headers(),
    )
    assert auth_response.status_code == 200
    auth_payload = auth_response.json()["payload"]
    assert auth_payload["access_token"] == "token-123"
    assert auth_payload["token_type"] == "bearer"
    assert auth_payload["role"] == "admin"


def test_operation_envelope_user_create_conflict(monkeypatch):
    def _raise_exists(username, password, role="user"):
        raise ValueError("User already exists")

    monkeypatch.setattr(api_server.user_manager, "create_user", _raise_exists)
    client = TestClient(api_server.app)

    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.user_manager.create",
            payload={"username": "alice", "password": "pw"},
        ),
        headers=auth_headers(),
    )

    assert response.status_code == 409
    body = response.json()
    assert body["payload"]["error"]["code"] == "USER_EXISTS"


def test_operation_envelope_user_auth_contract_fixture(monkeypatch):
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
    client = TestClient(api_server.app)
    request_fixture = load_contract_fixture(
        "merlin.user_manager.authenticate.request.json"
    )
    expected_fixture = load_contract_fixture(
        "merlin.user_manager.authenticate.expected_response.json"
    )

    response = client.post(
        "/merlin/operations",
        json=request_fixture,
        headers=auth_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["schema_name"] == expected_fixture["schema_name"]
    assert body["schema_version"] == expected_fixture["schema_version"]
    assert body["correlation_id"] == expected_fixture["correlation_id"]
    assert body["trace_id"] == expected_fixture["trace_id"]
    assert body["operation"]["name"] == expected_fixture["operation"]["name"]
    assert body["operation"]["version"] == expected_fixture["operation"]["version"]
    assert (
        body["payload"]["access_token"] == expected_fixture["payload"]["access_token"]
    )
    assert body["payload"]["token_type"] == expected_fixture["payload"]["token_type"]
    assert body["payload"]["username"] == expected_fixture["payload"]["username"]
    assert body["payload"]["role"] == expected_fixture["payload"]["role"]
    assert (
        body["payload"]["expires_in_minutes"]
        == expected_fixture["payload"]["expires_in_minutes"]
    )
    assert isinstance(body["message_id"], str)
    assert isinstance(body["timestamp_utc"], str)


def test_operation_envelope_system_info_and_genesis_logs(monkeypatch):
    monkeypatch.setattr(api_server, "get_system_info", lambda: {"platform": "linux"})
    monkeypatch.setattr(api_server, "get_recent_logs", lambda: [{"message": "ok"}])
    client = TestClient(api_server.app)

    system_info_response = client.post(
        "/merlin/operations",
        json=operation_envelope(operation_name="merlin.system_info.get", payload={}),
        headers=auth_headers(),
    )
    assert system_info_response.status_code == 200
    assert system_info_response.json()["payload"]["system_info"]["platform"] == "linux"

    logs_response = client.post(
        "/merlin/operations",
        json=operation_envelope(operation_name="merlin.genesis.logs", payload={}),
        headers=auth_headers(),
    )
    assert logs_response.status_code == 200
    assert logs_response.json()["payload"]["logs"][0]["message"] == "ok"


def test_operation_envelope_aas_create_task(monkeypatch):
    monkeypatch.setattr(
        api_server.hub_client,
        "create_aas_task",
        lambda title, description, priority: "task-123",
    )
    client = TestClient(api_server.app)

    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.aas.create_task",
            payload={"title": "New Task", "description": "Desc", "priority": "High"},
        ),
        headers=auth_headers(),
    )

    assert response.status_code == 200
    assert response.json()["payload"]["task_id"] == "task-123"


def test_operation_envelope_aas_create_task_failed(monkeypatch):
    monkeypatch.setattr(
        api_server.hub_client,
        "create_aas_task",
        lambda title, description, priority: None,
    )
    client = TestClient(api_server.app)

    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.aas.create_task",
            payload={"title": "New Task"},
        ),
        headers=auth_headers(),
    )

    assert response.status_code == 502
    assert response.json()["payload"]["error"]["code"] == "AAS_TASK_CREATE_FAILED"


def test_operation_envelope_dependency_circuit_breaker_opens_for_aas_failures(
    monkeypatch,
):
    monkeypatch.setattr(
        api_server.settings,
        "MERLIN_DEPENDENCY_CIRCUIT_BREAKER_ENABLED",
        True,
    )
    monkeypatch.setattr(
        api_server,
        "_DEPENDENCY_CIRCUIT_BREAKER",
        api_server.EndpointCircuitBreaker(
            failure_threshold=2,
            recovery_timeout_seconds=60.0,
        ),
    )
    monkeypatch.setattr(
        api_server.hub_client,
        "create_aas_task",
        lambda title, description, priority: None,
    )
    client = TestClient(api_server.app)

    request_one = operation_envelope(
        operation_name="merlin.aas.create_task",
        payload={"title": "New Task"},
    )
    request_one["operation"]["idempotency_key"] = "cb-aas-open-1"

    request_two = operation_envelope(
        operation_name="merlin.aas.create_task",
        payload={"title": "New Task"},
    )
    request_two["operation"]["idempotency_key"] = "cb-aas-open-2"

    request_three = operation_envelope(
        operation_name="merlin.aas.create_task",
        payload={"title": "New Task"},
    )
    request_three["operation"]["idempotency_key"] = "cb-aas-open-3"

    first = client.post("/merlin/operations", json=request_one, headers=auth_headers())
    second = client.post("/merlin/operations", json=request_two, headers=auth_headers())
    third = client.post(
        "/merlin/operations", json=request_three, headers=auth_headers()
    )

    assert first.status_code == 502
    assert second.status_code == 502
    assert third.status_code == 503
    error = third.json()["payload"]["error"]
    assert error["code"] == "DEPENDENCY_CIRCUIT_OPEN"
    assert error["retryable"] is True
    assert error["category"] == "dependency"


def test_operation_envelope_dependency_circuit_breaker_recovers_after_timeout(
    monkeypatch,
):
    now = [100.0]

    def _time() -> float:
        return now[0]

    monkeypatch.setattr(
        api_server.settings,
        "MERLIN_DEPENDENCY_CIRCUIT_BREAKER_ENABLED",
        True,
    )
    breaker = api_server.EndpointCircuitBreaker(
        failure_threshold=1,
        recovery_timeout_seconds=5.0,
        time_fn=_time,
    )
    monkeypatch.setattr(api_server, "_DEPENDENCY_CIRCUIT_BREAKER", breaker)

    call_count = {"count": 0}

    def _create_task(title, description, priority):
        call_count["count"] += 1
        if call_count["count"] == 1:
            return None
        return "task-123"

    monkeypatch.setattr(api_server.hub_client, "create_aas_task", _create_task)
    client = TestClient(api_server.app)

    first_request = operation_envelope(
        operation_name="merlin.aas.create_task",
        payload={"title": "New Task"},
    )
    first_request["operation"]["idempotency_key"] = "cb-aas-recovery-1"
    first = client.post(
        "/merlin/operations",
        json=first_request,
        headers=auth_headers(),
    )
    assert first.status_code == 502

    blocked_request = operation_envelope(
        operation_name="merlin.aas.create_task",
        payload={"title": "New Task"},
    )
    blocked_request["operation"]["idempotency_key"] = "cb-aas-recovery-2"
    blocked = client.post(
        "/merlin/operations",
        json=blocked_request,
        headers=auth_headers(),
    )
    assert blocked.status_code == 503
    assert call_count["count"] == 1

    now[0] += 5.0
    recovered_request = operation_envelope(
        operation_name="merlin.aas.create_task",
        payload={"title": "New Task"},
    )
    recovered_request["operation"]["idempotency_key"] = "cb-aas-recovery-3"
    recovered = client.post(
        "/merlin/operations",
        json=recovered_request,
        headers=auth_headers(),
    )
    assert recovered.status_code == 200
    assert recovered.json()["payload"]["task_id"] == "task-123"
    assert breaker.get_state("merlin.aas.create_task")["state"] == "closed"


def test_operation_envelope_aas_create_task_contract_fixture(monkeypatch):
    monkeypatch.setattr(
        api_server.hub_client,
        "create_aas_task",
        lambda title, description, priority: "fixture-task-id",
    )
    client = TestClient(api_server.app)
    request_fixture = load_contract_fixture("merlin.aas.create_task.request.json")
    expected_fixture = load_contract_fixture(
        "merlin.aas.create_task.expected_response.json"
    )

    response = client.post(
        "/merlin/operations",
        json=request_fixture,
        headers=auth_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["schema_name"] == expected_fixture["schema_name"]
    assert body["schema_version"] == expected_fixture["schema_version"]
    assert body["correlation_id"] == expected_fixture["correlation_id"]
    assert body["trace_id"] == expected_fixture["trace_id"]
    assert body["operation"]["name"] == expected_fixture["operation"]["name"]
    assert body["operation"]["version"] == expected_fixture["operation"]["version"]
    assert body["payload"]["task_id"] == expected_fixture["payload"]["task_id"]
    assert isinstance(body["message_id"], str)
    assert isinstance(body["timestamp_utc"], str)


def test_operation_envelope_plugins_list_and_execute(monkeypatch):
    monkeypatch.setattr(
        api_server.plugin_manager,
        "list_plugin_info",
        lambda: {"demo": {"name": "Demo", "description": "d", "category": "general"}},
    )
    monkeypatch.setattr(
        api_server.plugin_manager,
        "execute_plugin",
        lambda name, *args, **kwargs: {"ok": True, "name": name},
    )
    client = TestClient(api_server.app)

    list_response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.plugins.list",
            payload={"format": "list"},
        ),
        headers=auth_headers(),
    )
    assert list_response.status_code == 200
    list_payload = list_response.json()["payload"]
    assert list_payload["format"] == "list"
    assert list_payload["plugins"][0]["name"] == "Demo"

    execute_response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.plugins.execute",
            payload={"name": "demo", "args": ["a"], "kwargs": {"flag": True}},
        ),
        headers=auth_headers(),
    )
    assert execute_response.status_code == 200
    execute_payload = execute_response.json()["payload"]
    assert execute_payload["name"] == "demo"
    assert execute_payload["result"]["ok"] is True


def test_operation_envelope_plugins_list_filters_by_capability_and_health_state(
    monkeypatch,
):
    monkeypatch.setattr(
        api_server.plugin_manager,
        "list_plugin_info",
        lambda: {
            "healthy_demo": {
                "name": "Healthy Demo",
                "capabilities": ["merlin.demo.run"],
                "health_state": "healthy",
            },
            "isolated_demo": {
                "name": "Isolated Demo",
                "capabilities": ["merlin.demo.run", "merlin.other.run"],
                "health_state": "isolated",
            },
            "healthy_other": {
                "name": "Healthy Other",
                "capabilities": ["merlin.other.run"],
                "health_state": "healthy",
            },
        },
    )
    client = TestClient(api_server.app)

    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.plugins.list",
            payload={
                "format": "list",
                "capability": "merlin.demo.run",
                "health_state": "healthy",
            },
        ),
        headers=auth_headers(),
    )
    assert response.status_code == 200
    payload = response.json()["payload"]
    assert payload["filters"]["capability"] == "merlin.demo.run"
    assert payload["filters"]["health_state"] == "healthy"
    assert len(payload["plugins"]) == 1
    assert payload["plugins"][0]["name"] == "Healthy Demo"


def test_operation_envelope_plugins_list_rejects_invalid_health_state(monkeypatch):
    monkeypatch.setattr(api_server.plugin_manager, "list_plugin_info", lambda: {})
    client = TestClient(api_server.app)

    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.plugins.list",
            payload={"format": "list", "health_state": "broken"},
        ),
        headers=auth_headers(),
    )

    assert response.status_code == 422
    body = response.json()
    assert body["payload"]["error"]["code"] == "VALIDATION_ERROR"
    assert "health_state" in body["payload"]["error"]["message"]


def test_operation_envelope_plugins_execute_not_found(monkeypatch):
    monkeypatch.setattr(
        api_server.plugin_manager,
        "execute_plugin",
        lambda name, *args, **kwargs: {"error": f"Plugin {name} not found"},
    )
    client = TestClient(api_server.app)

    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.plugins.execute",
            payload={"name": "missing"},
        ),
        headers=auth_headers(),
    )
    assert response.status_code == 404
    assert response.json()["payload"]["error"]["code"] == "PLUGIN_NOT_FOUND"


def test_operation_envelope_plugins_execute_permission_denied(monkeypatch):
    monkeypatch.setattr(
        api_server.plugin_manager,
        "execute_plugin",
        lambda name, *args, **kwargs: {
            "error": "Plugin demo denied by policy for permission tiers: exec",
            "code": "PLUGIN_PERMISSION_DENIED",
            "denied_permissions": ["exec"],
        },
    )
    client = TestClient(api_server.app)

    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.plugins.execute",
            payload={"name": "demo"},
        ),
        headers=auth_headers(),
    )
    assert response.status_code == 403
    body = response.json()
    assert body["payload"]["error"]["code"] == "PLUGIN_PERMISSION_DENIED"
    assert body["payload"]["error"]["category"] == "policy"


def test_operation_envelope_plugins_execute_timeout(monkeypatch):
    monkeypatch.setattr(
        api_server.plugin_manager,
        "execute_plugin",
        lambda name, *args, **kwargs: {
            "error": "Plugin demo timed out after 0.01s",
            "code": "PLUGIN_TIMEOUT",
            "timeout_seconds": 0.01,
        },
    )
    client = TestClient(api_server.app)

    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.plugins.execute",
            payload={"name": "demo"},
        ),
        headers=auth_headers(),
    )
    assert response.status_code == 504
    body = response.json()
    assert body["payload"]["error"]["code"] == "PLUGIN_TIMEOUT"
    assert body["payload"]["error"]["retryable"] is True
    assert body["payload"]["error"]["category"] == "dependency"


def test_operation_envelope_plugins_execute_process_serialization_error(monkeypatch):
    monkeypatch.setattr(
        api_server.plugin_manager,
        "execute_plugin",
        lambda name, *args, **kwargs: {
            "error": "Plugin demo process serialization failed: cannot pickle",
            "code": "PLUGIN_PROCESS_SERIALIZATION_ERROR",
        },
    )
    client = TestClient(api_server.app)

    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.plugins.execute",
            payload={"name": "demo"},
        ),
        headers=auth_headers(),
    )
    assert response.status_code == 502
    body = response.json()
    assert body["payload"]["error"]["code"] == "PLUGIN_PROCESS_SERIALIZATION_ERROR"
    assert body["payload"]["error"]["retryable"] is False
    assert body["payload"]["error"]["category"] == "dependency"


def test_operation_envelope_plugins_execute_crash_isolated(monkeypatch):
    monkeypatch.setattr(
        api_server.plugin_manager,
        "execute_plugin",
        lambda name, *args, **kwargs: {
            "error": "Plugin demo is isolated after repeated crashes",
            "code": "PLUGIN_CRASH_ISOLATED",
        },
    )
    client = TestClient(api_server.app)

    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.plugins.execute",
            payload={"name": "demo"},
        ),
        headers=auth_headers(),
    )
    assert response.status_code == 503
    body = response.json()
    assert body["payload"]["error"]["code"] == "PLUGIN_CRASH_ISOLATED"
    assert body["payload"]["error"]["retryable"] is True
    assert body["payload"]["error"]["category"] == "dependency"


def test_operation_envelope_research_manager_operations(monkeypatch, tmp_path):
    manager = ResearchManager(tmp_path / "research_manager", allow_writes=True)
    monkeypatch.setattr(api_server, "research_manager", manager)
    client = TestClient(api_server.app)

    create_response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.research.manager.session.create",
            payload={
                "objective": "Build a local research command center",
                "constraints": ["repo-local-only"],
                "horizon_days": 7,
                "tags": ["cp2", "routing"],
                "linked_task_ids": [11, 42],
                "planner_artifacts": [
                    "docs/planning/COMPOSITION_MAELSTROM_CP4A_PROMPTS_2026-02-15.md",
                    "docs/research/CHIMERA_V2_CP4A_PLANNER_READINESS_STATUS_2026-02-15.md",
                ],
            },
        ),
        headers=auth_headers(),
    )
    assert create_response.status_code == 200
    create_payload = create_response.json()["payload"]
    session_id = create_payload["session"]["session_id"]
    assert (
        create_payload["session"]["objective"]
        == "Build a local research command center"
    )
    assert create_payload["session"]["tags"] == ["cp2", "routing"]
    assert create_payload["session"]["linked_task_ids"] == [11, 42]
    assert create_payload["session"]["planner_artifacts"] == [
        "docs/planning/COMPOSITION_MAELSTROM_CP4A_PROMPTS_2026-02-15.md",
        "docs/research/CHIMERA_V2_CP4A_PLANNER_READINESS_STATUS_2026-02-15.md",
    ]
    assert "risk_rubric" in create_payload["session"]
    assert (
        create_payload["session"]["created_by"]
        == "AaroneousAutomationSuite/Hub:hub_orchestrator"
    )
    assert (
        create_payload["session"]["source_operation"]
        == "merlin.research.manager.session.create"
    )
    assert (
        create_payload["session"]["policy_version"]
        == api_server.RESEARCH_SESSION_PROVENANCE_POLICY_VERSION
    )
    assert len(create_payload["next_actions"]) == 3

    list_response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.research.manager.sessions.list",
            payload={"limit": 20, "tag": "cp2"},
        ),
        headers=auth_headers(),
    )
    assert list_response.status_code == 200
    list_payload = list_response.json()["payload"]
    assert list_payload["sessions"][0]["session_id"] == session_id
    assert list_payload["next_cursor"] is None

    signal_response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.research.manager.session.signal.add",
            payload={
                "session_id": session_id,
                "source": "routing-smoke",
                "claim": "Fallback and telemetry checks are passing.",
                "confidence": 0.9,
                "supports": ["h_execution_success"],
            },
        ),
        headers=auth_headers(),
    )
    assert signal_response.status_code == 200
    assert signal_response.json()["payload"]["session_id"] == session_id

    get_response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.research.manager.session.get",
            payload={"session_id": session_id},
        ),
        headers=auth_headers(),
    )
    assert get_response.status_code == 200
    assert get_response.json()["payload"]["session"]["session_id"] == session_id

    brief_response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.research.manager.brief.get",
            payload={"session_id": session_id},
        ),
        headers=auth_headers(),
    )
    assert brief_response.status_code == 200
    brief_payload = brief_response.json()["payload"]["brief"]
    assert brief_payload["session_id"] == session_id
    assert brief_payload["brief_template_id"] == "research_manager.default"
    assert brief_payload["brief_template_version"] == "1.0.0"
    assert "risk_rubric" in brief_payload
    assert brief_payload["contradicting_signal_count"] == 0
    assert brief_payload["conflict_count"] == 0
    assert len(brief_payload["causal_chains"]) == 3

    missing_response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.research.manager.session.get",
            payload={"session_id": "missing-session"},
        ),
        headers=auth_headers(),
    )
    assert missing_response.status_code == 404
    assert missing_response.json()["payload"]["error"]["code"] == "SESSION_NOT_FOUND"


def test_operation_envelope_research_manager_sessions_list_cursor(
    monkeypatch, tmp_path
):
    manager = ResearchManager(tmp_path / "research_manager", allow_writes=True)
    first = manager.create_session("First cursor session")
    second = manager.create_session("Second cursor session")
    monkeypatch.setattr(api_server, "research_manager", manager)
    client = TestClient(api_server.app)

    first_page_response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.research.manager.sessions.list",
            payload={"limit": 1},
        ),
        headers=auth_headers(),
    )
    assert first_page_response.status_code == 200
    first_page = first_page_response.json()["payload"]
    assert first_page["sessions"][0]["session_id"] == second["session_id"]
    assert first_page["next_cursor"] == "1"

    second_page_response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.research.manager.sessions.list",
            payload={"limit": 1, "cursor": first_page["next_cursor"]},
        ),
        headers=auth_headers(),
    )
    assert second_page_response.status_code == 200
    second_page = second_page_response.json()["payload"]
    assert second_page["sessions"][0]["session_id"] == first["session_id"]
    assert second_page["next_cursor"] is None


def test_operation_envelope_research_manager_create_rejects_invalid_traceability(
    monkeypatch, tmp_path
):
    manager = ResearchManager(tmp_path / "research_manager", allow_writes=True)
    monkeypatch.setattr(api_server, "research_manager", manager)
    client = TestClient(api_server.app)

    bad_task_ids = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.research.manager.session.create",
            payload={
                "objective": "Invalid traceability input",
                "linked_task_ids": ["bad-id"],
            },
        ),
        headers=auth_headers(),
    )
    assert bad_task_ids.status_code == 422
    assert bad_task_ids.json()["payload"]["error"]["code"] == "VALIDATION_ERROR"
    assert "linked_task_ids" in bad_task_ids.json()["payload"]["error"]["message"]

    bad_artifacts_request = operation_envelope(
        operation_name="merlin.research.manager.session.create",
        payload={
            "objective": "Invalid artifact input",
            "planner_artifacts": [123],
        },
    )
    bad_artifacts_request["operation"][
        "idempotency_key"
    ] = "research-manager-session-create-invalid-artifacts"

    bad_artifacts = client.post(
        "/merlin/operations",
        json=bad_artifacts_request,
        headers=auth_headers(),
    )
    assert bad_artifacts.status_code == 422
    assert bad_artifacts.json()["payload"]["error"]["code"] == "VALIDATION_ERROR"
    assert "planner_artifacts" in bad_artifacts.json()["payload"]["error"]["message"]


def test_operation_envelope_research_manager_read_only(monkeypatch, tmp_path):
    manager = ResearchManager(tmp_path / "research_manager", allow_writes=True)
    seeded = manager.create_session("Seed session")
    manager.allow_writes = False
    monkeypatch.setattr(api_server, "research_manager", manager)
    client = TestClient(api_server.app)

    create_response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.research.manager.session.create",
            payload={"objective": "Attempt blocked write"},
        ),
        headers=auth_headers(),
    )
    assert create_response.status_code == 403
    create_error = create_response.json()["payload"]["error"]
    assert create_error["code"] == "RESEARCH_MANAGER_READ_ONLY"

    signal_response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.research.manager.session.signal.add",
            payload={
                "session_id": seeded["session_id"],
                "source": "test",
                "claim": "blocked write",
                "confidence": 0.7,
            },
        ),
        headers=auth_headers(),
    )
    assert signal_response.status_code == 403
    signal_error = signal_response.json()["payload"]["error"]
    assert signal_error["code"] == "RESEARCH_MANAGER_READ_ONLY"


def test_operation_envelope_research_manager_invalid_session_id(monkeypatch, tmp_path):
    manager = ResearchManager(tmp_path / "research_manager", allow_writes=True)
    monkeypatch.setattr(api_server, "research_manager", manager)
    client = TestClient(api_server.app)

    get_response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.research.manager.session.get",
            payload={"session_id": "../bad"},
        ),
        headers=auth_headers(),
    )
    assert get_response.status_code == 422
    get_error = get_response.json()["payload"]["error"]
    assert get_error["code"] == "VALIDATION_ERROR"

    brief_response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.research.manager.brief.get",
            payload={"session_id": "../bad"},
        ),
        headers=auth_headers(),
    )
    assert brief_response.status_code == 422
    brief_error = brief_response.json()["payload"]["error"]
    assert brief_error["code"] == "VALIDATION_ERROR"


def test_operation_envelope_genesis_manifest_contract_fixture(monkeypatch):
    recorded = {}

    def _record(entry):
        recorded.update(entry)

    monkeypatch.setattr(api_server, "append_manifest_entry", _record)
    client = TestClient(api_server.app)
    request_fixture = load_contract_fixture("merlin.genesis.manifest.request.json")

    response = client.post(
        "/merlin/operations",
        json=request_fixture,
        headers=auth_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["operation"]["name"] == "merlin.genesis.manifest.result"
    assert body["payload"]["status"] == "queued"
    assert body["payload"]["filename"] == request_fixture["payload"]["filename"]
    assert recorded["filename"] == request_fixture["payload"]["filename"]
    assert "received_at" in recorded


def test_operation_envelope_command_execute(monkeypatch):
    monkeypatch.setattr(
        api_server.policy_manager, "is_command_allowed", lambda command: True
    )
    monkeypatch.setattr(
        api_server,
        "execute_command",
        lambda command: {"stdout": "ok", "stderr": "", "returncode": 0},
    )
    client = TestClient(api_server.app)

    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.command.execute",
            payload={"command": "echo ok"},
        ),
        headers=auth_headers(),
    )

    assert response.status_code == 200
    payload = response.json()["payload"]
    assert payload["output"] == "ok"
    assert payload["returncode"] == 0


def test_operation_envelope_command_blocked(monkeypatch):
    monkeypatch.setattr(
        api_server.policy_manager, "is_command_allowed", lambda command: False
    )
    client = TestClient(api_server.app)

    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.command.execute",
            payload={"command": "rm -rf /"},
        ),
        headers=auth_headers(),
    )

    assert response.status_code == 403
    assert response.json()["payload"]["error"]["code"] == "COMMAND_BLOCKED"


def test_operation_envelope_search_query_contract_fixture(monkeypatch):
    monkeypatch.setattr(
        api_server.merlin_rag,
        "search",
        lambda query, limit=5: [
            {"text": "doc", "metadata": {"path": "docs/readme.md"}},
            {"text": "match", "metadata": {}},
        ],
    )
    client = TestClient(api_server.app)
    request_fixture = load_contract_fixture("merlin.search.query.request.json")

    response = client.post(
        "/merlin/operations",
        json=request_fixture,
        headers=auth_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["operation"]["name"] == "merlin.search.query.result"
    assert body["payload"]["count"] == 2
    assert body["payload"]["results"][0].startswith("docs/readme.md")
    assert body["payload"]["citations"][0]["path"] == "docs/readme.md"
    assert body["payload"]["citations"][0]["source_id"].startswith("src_")


def test_operation_envelope_discovery_operations(tmp_path):
    fixture_feed = tmp_path / "fixture" / "local_fixture.jsonl"
    fixture_feed.parent.mkdir(parents=True, exist_ok=True)
    fixture_feed.write_text(
        json.dumps(
            {
                "title": "Discovery envelope fixture article",
                "url": "https://example.org/discovery-envelope",
                "snippet": "Policy governed discovery operations through operation envelope.",
                "source": "fixture:discovery",
                "published_at": "2026-02-24T12:00:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    seed_file = tmp_path / "seed.json"
    seed_file.write_text(
        json.dumps(
            [
                {
                    "topic": "discovery envelope operations",
                    "source": "local_seed",
                    "metadata": {"collector": "local_fixture"},
                }
            ]
        ),
        encoding="utf-8",
    )
    out_root = tmp_path / "out"

    client = TestClient(api_server.app)
    run_request = operation_envelope(
        operation_name="merlin.discovery.run",
        payload={
            "profile": "public",
            "out": str(out_root),
            "seeds_file": str(seed_file),
            "fixture_feed": str(fixture_feed),
            "top_k": 1,
            "min_score": 0.01,
            "allow_live_automation": True,
            "publisher_mode": "stage_only",
        },
    )
    run_request["operation"][
        "idempotency_key"
    ] = "merlin-discovery-run-contract-fixture-2026-02-24-0001"
    run_response = client.post(
        "/merlin/operations",
        json=run_request,
        headers=auth_headers(),
    )
    assert run_response.status_code == 200
    run_payload = run_response.json()["payload"]["report"]
    assert run_payload["schema_name"] == "AAS.Discovery.RunReport"
    assert run_payload["counts"]["items_collected"] >= 1

    status_response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.discovery.queue.status",
            payload={"out": str(out_root)},
        ),
        headers=auth_headers(),
    )
    assert status_response.status_code == 200
    status_payload = status_response.json()["payload"]["status"]
    assert status_payload["schema_name"] == "AAS.Discovery.QueueStatus"

    pause_request = operation_envelope(
        operation_name="merlin.discovery.queue.pause",
        payload={"out": str(out_root)},
    )
    pause_request["operation"][
        "idempotency_key"
    ] = "merlin-discovery-queue-pause-contract-fixture-2026-02-24-0001"
    pause_response = client.post(
        "/merlin/operations",
        json=pause_request,
        headers=auth_headers(),
    )
    assert pause_response.status_code == 200
    assert pause_response.json()["payload"]["pause"]["status"]["paused"] is True

    resume_request = operation_envelope(
        operation_name="merlin.discovery.queue.resume",
        payload={"out": str(out_root)},
    )
    resume_request["operation"][
        "idempotency_key"
    ] = "merlin-discovery-queue-resume-contract-fixture-2026-02-24-0001"
    resume_response = client.post(
        "/merlin/operations",
        json=resume_request,
        headers=auth_headers(),
    )
    assert resume_response.status_code == 200
    assert resume_response.json()["payload"]["resume"]["status"]["paused"] is False

    drain_request = operation_envelope(
        operation_name="merlin.discovery.queue.drain",
        payload={"out": str(out_root)},
    )
    drain_request["operation"][
        "idempotency_key"
    ] = "merlin-discovery-queue-drain-contract-fixture-2026-02-24-0001"
    drain_response = client.post(
        "/merlin/operations",
        json=drain_request,
        headers=auth_headers(),
    )
    assert drain_response.status_code == 200
    assert (
        drain_response.json()["payload"]["drain"]["schema_name"]
        == "AAS.Discovery.QueueDrain"
    )

    purge_request = operation_envelope(
        operation_name="merlin.discovery.queue.purge_deadletter",
        payload={"out": str(out_root)},
    )
    purge_request["operation"][
        "idempotency_key"
    ] = "merlin-discovery-queue-purge-contract-fixture-2026-02-24-0001"
    purge_response = client.post(
        "/merlin/operations",
        json=purge_request,
        headers=auth_headers(),
    )
    assert purge_response.status_code == 200
    assert (
        purge_response.json()["payload"]["purge_deadletter"]["schema_name"]
        == "AAS.Discovery.QueuePurgeDeadletter"
    )

    search_response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.knowledge.search",
            payload={"query": "discovery", "out": str(out_root), "limit": 5},
        ),
        headers=auth_headers(),
    )
    assert search_response.status_code == 200
    search_payload = search_response.json()["payload"]["search"]
    assert search_payload["schema_name"] == "AAS.Knowledge.SearchResult"


def test_operation_envelope_seed_status_and_control(monkeypatch):
    class DummySeedAccess:
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
        ):
            return {
                "schema_name": "AAS.Merlin.SeedStatus",
                "schema_version": "1.0.0",
                "process": {"active": True, "count": 1, "rows": [{"pid": 4242}]},
            }

        def control(self, *, action, **kwargs):
            return {
                "schema_name": "AAS.Merlin.SeedControl",
                "schema_version": "1.0.0",
                "action": action,
                "decision": "allowed",
                "status": "started",
                "message": "Seed worker process started",
            }

    monkeypatch.setattr(
        api_server,
        "build_seed_access",
        lambda workspace_root=None: DummySeedAccess(),
    )

    client = TestClient(api_server.app)
    status_response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.seed.status",
            payload={"include_log_tail": False},
        ),
        headers=auth_headers(),
    )
    assert status_response.status_code == 200
    assert (
        status_response.json()["payload"]["seed"]["schema_name"]
        == "AAS.Merlin.SeedStatus"
    )

    control_response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.seed.control",
            payload={"action": "start", "allow_live_automation": True},
        ),
        headers=auth_headers(),
    )
    assert control_response.status_code == 200
    control_payload = control_response.json()["payload"]["control"]
    assert control_payload["schema_name"] == "AAS.Merlin.SeedControl"
    assert control_payload["status"] == "started"


def test_operation_envelope_seed_control_blocked_by_policy():
    client = TestClient(api_server.app)
    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.seed.control",
            payload={"action": "start", "allow_live_automation": False},
        ),
        headers=auth_headers(),
    )
    assert response.status_code == 403
    assert response.json()["payload"]["error"]["code"] == "SEED_CONTROL_BLOCKED"


def test_operation_envelope_seed_control_dry_run_preview(monkeypatch):
    recorded_calls: list[dict[str, object]] = []

    class DummySeedAccess:
        def control(self, *, action, **kwargs):
            recorded_calls.append({"action": action, **kwargs})
            return {
                "schema_name": "AAS.Merlin.SeedControl",
                "schema_version": "1.0.0",
                "action": action,
                "decision": "allowed",
                "dry_run": kwargs.get("dry_run", False),
                "status": "preview",
                "message": "Dry-run preview only; no process started",
            }

    monkeypatch.setattr(
        api_server,
        "build_seed_access",
        lambda workspace_root=None: DummySeedAccess(),
    )

    client = TestClient(api_server.app)
    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.seed.control",
            payload={
                "action": "start",
                "allow_live_automation": True,
                "dry_run": True,
            },
        ),
        headers=auth_headers(),
    )
    assert response.status_code == 200
    control_payload = response.json()["payload"]["control"]
    assert control_payload["status"] == "preview"
    assert control_payload["dry_run"] is True
    assert recorded_calls and recorded_calls[0]["dry_run"] is True


def test_operation_envelope_seed_health(monkeypatch):
    class DummySeedAccess:
        def health(
            self,
            *,
            status_file=None,
            merged_jsonl=None,
            merged_parquet=None,
            log_file=None,
            allow_live_automation=None,
            stale_after_seconds=3600.0,
        ):
            return {
                "schema_name": "AAS.Merlin.SeedHealth",
                "schema_version": "1.0.0",
                "state": "attention",
                "severity": "warn",
                "next_action": "start",
                "recommended_control_action": "start",
                "progress": {
                    "target_rounds": 50000,
                    "completed_rounds": 4641,
                    "remaining_rounds": 45359,
                    "completion_percent": 9.28,
                },
                "staleness": {
                    "status_age_seconds": 1718619.0,
                    "stale_after_seconds": stale_after_seconds,
                    "is_stale": True,
                },
            }

    monkeypatch.setattr(
        api_server,
        "build_seed_access",
        lambda workspace_root=None: DummySeedAccess(),
    )

    client = TestClient(api_server.app)
    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.seed.health",
            payload={"stale_after_seconds": 1200.0},
        ),
        headers=auth_headers(),
    )
    assert response.status_code == 200
    payload = response.json()["payload"]["health"]
    assert payload["schema_name"] == "AAS.Merlin.SeedHealth"
    assert payload["severity"] == "warn"
    assert payload["recommended_control_action"] == "start"


def test_operation_envelope_seed_health_heartbeat(monkeypatch):
    recorded_calls: list[dict[str, object]] = []

    class DummySeedAccess:
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
        ):
            recorded_calls.append(
                {
                    "status_file": status_file,
                    "stale_after_seconds": stale_after_seconds,
                    "heartbeat_file": heartbeat_file,
                    "write_event": write_event,
                    "allow_live_automation": allow_live_automation,
                }
            )
            return {
                "schema_name": "AAS.Merlin.SeedHealthHeartbeat",
                "schema_version": "1.0.0",
                "event_id": "hb_fixture_seed_health_heartbeat_0001",
                "event_type": "merlin.seed.health.heartbeat",
                "workspace_root": "/tmp/seed-workspace",
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
                    "completed_rounds": 5712,
                    "remaining_rounds": 44288,
                    "completion_percent": 11.42,
                },
                "worker": {
                    "active": True,
                    "count": 2,
                },
                "staleness": {
                    "status_age_seconds": 12.0,
                    "stale_after_seconds": stale_after_seconds,
                    "is_stale": False,
                },
                "health_snapshot": {
                    "schema_name": "AAS.Merlin.SeedHealth",
                    "schema_version": "1.0.0",
                    "state": "healthy",
                    "severity": "ok",
                },
                "heartbeat_file": (
                    heartbeat_file
                    or "/tmp/seed-workspace/artifacts/diagnostics/merlin_seed_health_heartbeat.jsonl"
                ),
                "persisted": write_event,
                "emitted_at": "2026-02-25T18:00:00Z",
            }

    monkeypatch.setattr(
        api_server,
        "build_seed_access",
        lambda workspace_root=None: DummySeedAccess(),
    )

    client = TestClient(api_server.app)
    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.seed.health.heartbeat",
            payload={
                "status_file": "artifacts/merlin_seed_status.json",
                "stale_after_seconds": 1200.0,
                "heartbeat_file": "artifacts/diagnostics/custom_heartbeat.jsonl",
                "write_event": False,
                "allow_live_automation": True,
            },
        ),
        headers=auth_headers(),
    )
    assert response.status_code == 200
    payload = response.json()["payload"]["heartbeat"]
    assert payload["schema_name"] == "AAS.Merlin.SeedHealthHeartbeat"
    assert payload["persisted"] is False
    assert payload["event_type"] == "merlin.seed.health.heartbeat"
    assert recorded_calls == [
        {
            "status_file": "artifacts/merlin_seed_status.json",
            "stale_after_seconds": 1200.0,
            "heartbeat_file": "artifacts/diagnostics/custom_heartbeat.jsonl",
            "write_event": False,
            "allow_live_automation": True,
        }
    ]


def test_operation_envelope_seed_health_heartbeat_rejects_invalid_write_event():
    client = TestClient(api_server.app)
    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.seed.health.heartbeat",
            payload={"write_event": "yes"},
        ),
        headers=auth_headers(),
    )
    assert response.status_code == 422
    error = response.json()["payload"]["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["message"] == "payload.write_event must be a boolean when provided"


def test_operation_envelope_seed_watchdog_tick(monkeypatch):
    recorded_calls: list[dict[str, object]] = []

    class DummySeedAccess:
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
        ):
            recorded_calls.append(
                {
                    "status_file": status_file,
                    "stale_after_seconds": stale_after_seconds,
                    "allow_live_automation": allow_live_automation,
                    "apply": apply,
                    "force": force,
                    "dry_run_control": dry_run_control,
                }
            )
            return {
                "schema_name": "AAS.Merlin.SeedWatchdogTick",
                "schema_version": "1.0.0",
                "workspace_root": "/tmp/seed-workspace",
                "health": {
                    "schema_name": "AAS.Merlin.SeedHealth",
                    "schema_version": "1.0.0",
                    "state": "attention",
                    "severity": "warn",
                    "policy_decision": "allowed",
                    "next_action": "start",
                    "recommended_control_action": "start",
                    "checks": {
                        "policy_allowed": True,
                        "status_stale": False,
                        "worker_active": False,
                        "progress_complete": False,
                    },
                    "progress": {
                        "target_rounds": 50000,
                        "completed_rounds": 5712,
                        "remaining_rounds": 44288,
                        "completion_percent": 11.42,
                    },
                    "worker": {"active": False, "count": 0},
                    "staleness": {
                        "status_age_seconds": 45.0,
                        "stale_after_seconds": stale_after_seconds,
                        "is_stale": False,
                    },
                    "guidance": {
                        "schema_name": "AAS.Merlin.SeedGuidance",
                        "schema_version": "1.0.0",
                        "state": "attention",
                        "next_action": "start",
                        "recommendations": [],
                    },
                    "status_snapshot_updated_at": "2026-02-25T18:00:00Z",
                    "updated_at": "2026-02-25T18:00:45Z",
                },
                "decision": {
                    "recommended_control_action": "start",
                    "apply_requested": True,
                    "dry_run_control": False,
                    "force": True,
                    "action_taken": "start",
                    "outcome_status": "executed",
                    "reason": "Control action 'start' executed.",
                },
                "control_result": {
                    "schema_name": "AAS.Merlin.SeedControl",
                    "schema_version": "1.0.0",
                    "action": "start",
                    "decision": "allowed",
                    "status": "started",
                },
                "updated_at": "2026-02-25T18:00:45Z",
            }

    monkeypatch.setattr(
        api_server,
        "build_seed_access",
        lambda workspace_root=None: DummySeedAccess(),
    )

    client = TestClient(api_server.app)
    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.seed.watchdog.tick",
            payload={
                "status_file": "artifacts/merlin_seed_status.json",
                "stale_after_seconds": 900,
                "allow_live_automation": True,
                "apply": True,
                "force": True,
                "dry_run_control": False,
            },
        ),
        headers=auth_headers(),
    )
    assert response.status_code == 200
    payload = response.json()["payload"]["watchdog"]
    assert payload["schema_name"] == "AAS.Merlin.SeedWatchdogTick"
    assert payload["decision"]["outcome_status"] == "executed"
    assert recorded_calls == [
        {
            "status_file": "artifacts/merlin_seed_status.json",
            "stale_after_seconds": 900.0,
            "allow_live_automation": True,
            "apply": True,
            "force": True,
            "dry_run_control": False,
        }
    ]


def test_operation_envelope_seed_watchdog_tick_rejects_invalid_apply():
    client = TestClient(api_server.app)
    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.seed.watchdog.tick",
            payload={"apply": "yes"},
        ),
        headers=auth_headers(),
    )
    assert response.status_code == 422
    error = response.json()["payload"]["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["message"] == "payload.apply must be a boolean when provided"


def test_operation_envelope_seed_watchdog_runtime_status(monkeypatch):
    class DummySeedAccess:
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
        ):
            return {
                "schema_name": "AAS.Merlin.SeedWatchdogRuntimeStatus",
                "schema_version": "1.0.0",
                "workspace_root": "/tmp/seed-workspace",
                "policy": {"decision": "allowed"},
                "paths": {"watchdog_log_file": "logs/merlin_seed_watchdog_runtime.log"},
                "process": {"active": False, "count": 0, "rows": []},
                "telemetry": {"append_jsonl_exists": False},
                "health": {"schema_name": "AAS.Merlin.SeedHealth"},
                "updated_at": "2026-02-25T20:00:00Z",
            }

    monkeypatch.setattr(
        api_server,
        "build_seed_access",
        lambda workspace_root=None: DummySeedAccess(),
    )
    client = TestClient(api_server.app)
    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.seed.watchdog.status",
            payload={"stale_after_seconds": 900},
        ),
        headers=auth_headers(),
    )
    assert response.status_code == 200
    payload = response.json()["payload"]["watchdog_status"]
    assert payload["schema_name"] == "AAS.Merlin.SeedWatchdogRuntimeStatus"
    assert payload["process"]["count"] == 0


def test_operation_envelope_seed_watchdog_runtime_control(monkeypatch):
    recorded_calls: list[dict[str, object]] = []

    class DummySeedAccess:
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
        ):
            recorded_calls.append(
                {
                    "action": action,
                    "allow_live_automation": allow_live_automation,
                    "dry_run": dry_run,
                    "force": force,
                    "stale_after_seconds": stale_after_seconds,
                    "apply": apply,
                    "dry_run_control": dry_run_control,
                    "interval_seconds": interval_seconds,
                    "max_iterations": max_iterations,
                    "emit_heartbeat": emit_heartbeat,
                }
            )
            return {
                "schema_name": "AAS.Merlin.SeedWatchdogRuntimeControl",
                "schema_version": "1.0.0",
                "action": action,
                "decision": "allowed",
                "status": "preview",
                "message": "Dry-run preview only; no watchdog runtime process started",
            }

    monkeypatch.setattr(
        api_server,
        "build_seed_access",
        lambda workspace_root=None: DummySeedAccess(),
    )
    client = TestClient(api_server.app)
    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.seed.watchdog.control",
            payload={
                "action": "start",
                "allow_live_automation": True,
                "dry_run": True,
                "force": True,
                "stale_after_seconds": 900,
                "apply": True,
                "dry_run_control": True,
                "interval_seconds": 5.0,
                "max_iterations": 0,
                "emit_heartbeat": False,
            },
        ),
        headers=auth_headers(),
    )
    assert response.status_code == 200
    payload = response.json()["payload"]["watchdog_control"]
    assert payload["schema_name"] == "AAS.Merlin.SeedWatchdogRuntimeControl"
    assert payload["status"] == "preview"
    assert recorded_calls == [
        {
            "action": "start",
            "allow_live_automation": True,
            "dry_run": True,
            "force": True,
            "stale_after_seconds": 900.0,
            "apply": True,
            "dry_run_control": True,
            "interval_seconds": 5.0,
            "max_iterations": 0,
            "emit_heartbeat": False,
        }
    ]


def test_operation_envelope_seed_watchdog_runtime_control_blocked_by_policy():
    client = TestClient(api_server.app)
    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.seed.watchdog.control",
            payload={"action": "start", "allow_live_automation": False},
        ),
        headers=auth_headers(),
    )
    assert response.status_code == 403
    assert response.json()["payload"]["error"]["code"] == "SEED_WATCHDOG_CONTROL_BLOCKED"


def test_operation_envelope_seed_watchdog_runtime_control_rejects_invalid_max_iterations():
    client = TestClient(api_server.app)
    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.seed.watchdog.control",
            payload={"action": "start", "max_iterations": -1},
        ),
        headers=auth_headers(),
    )
    assert response.status_code == 422
    error = response.json()["payload"]["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert (
        error["message"]
        == "payload.max_iterations must be an integer greater than or equal to zero"
    )


def test_operation_envelope_seed_health_rejects_invalid_stale_after_seconds():
    client = TestClient(api_server.app)
    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.seed.health",
            payload={"stale_after_seconds": 0},
        ),
        headers=auth_headers(),
    )
    assert response.status_code == 422
    assert response.json()["payload"]["error"]["code"] == "VALIDATION_ERROR"


def test_operation_envelope_rag_query(monkeypatch):
    monkeypatch.setattr(
        api_server.merlin_rag,
        "search",
        lambda query, limit=5: [
            {"text": "doc", "metadata": {"path": "docs/readme.md"}},
            {"text": f"q={query},limit={limit}", "metadata": {}},
        ],
    )
    client = TestClient(api_server.app)

    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.rag.query",
            payload={"query": "policy", "limit": 2},
        ),
        headers=auth_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["operation"]["name"] == "merlin.rag.query.result"
    assert body["payload"]["count"] == 2
    assert body["payload"]["results"][0].startswith("docs/readme.md")
    assert "q=policy,limit=2" in body["payload"]["results"][1]
    assert body["payload"]["citations"][0]["path"] == "docs/readme.md"
    assert body["payload"]["citations"][0]["source_id"].startswith("src_")


def test_operation_envelope_tasks_create_and_list(monkeypatch):
    monkeypatch.setattr(
        api_server.task_manager,
        "add_task",
        lambda title, description, priority: {
            "id": 2,
            "title": title,
            "description": description,
            "priority": priority,
        },
    )
    monkeypatch.setattr(
        api_server.task_manager,
        "list_tasks",
        lambda: [{"id": 1, "title": "existing"}],
    )
    client = TestClient(api_server.app)

    create = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.tasks.create",
            payload={"title": "new task", "description": "desc", "priority": "High"},
        ),
        headers=auth_headers(),
    )

    assert create.status_code == 200
    assert create.json()["payload"]["task"]["title"] == "new task"

    list_tasks = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="merlin.tasks.list",
            payload={},
        ),
        headers=auth_headers(),
    )

    assert list_tasks.status_code == 200
    assert list_tasks.json()["payload"]["tasks"][0]["title"] == "existing"


def test_history_and_tasks(monkeypatch):
    monkeypatch.setattr(
        api_server, "load_chat", lambda user_id: [{"user": "u", "merlin": "m"}]
    )
    monkeypatch.setattr(
        api_server.task_manager, "list_tasks", lambda: [{"id": 1, "title": "t"}]
    )
    monkeypatch.setattr(
        api_server.task_manager,
        "add_task",
        lambda title, description, priority: {
            "id": 2,
            "title": title,
            "priority": priority,
        },
    )
    client = TestClient(api_server.app)

    history = client.get("/merlin/history/u1", headers=auth_headers())
    assert history.status_code == 200
    assert history.json()["history"][0]["merlin"] == "m"

    tasks = client.get("/merlin/tasks", headers=auth_headers())
    assert tasks.status_code == 200
    assert tasks.json()["tasks"][0]["title"] == "t"

    created = client.post(
        "/merlin/tasks",
        json={"title": "new", "description": "d", "priority": "Low"},
        headers=auth_headers(),
    )
    assert created.status_code == 200
    assert created.json()["task"]["title"] == "new"


def test_chat_multipart(monkeypatch):
    monkeypatch.setattr(
        api_server, "merlin_emotion_chat", lambda user_input, user_id: "ok"
    )
    client = TestClient(api_server.app)

    resp = client.post(
        "/merlin/chat",
        data={"user_input": "hi", "user_id": "u1"},
        files={"image": ("note.txt", b"data", "text/plain")},
        headers=auth_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["reply"] == "ok"


def test_execute_search_and_manifest(monkeypatch):
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
            {"text": "doc", "metadata": {"path": "docs/readme.md"}}
        ],
    )
    monkeypatch.setattr(api_server, "append_manifest_entry", lambda entry: None)
    monkeypatch.setattr(api_server, "get_recent_logs", lambda: [{"message": "log"}])
    client = TestClient(api_server.app)

    execute = client.post(
        "/merlin/execute", json={"command": "echo ok"}, headers=auth_headers()
    )
    assert execute.status_code == 200
    assert execute.json()["output"].startswith("ok")

    search = client.post(
        "/merlin/search", json={"query": "doc"}, headers=auth_headers()
    )
    assert search.status_code == 200
    assert search.json()["results"][0].startswith("docs/readme.md")
    assert search.json()["citations"][0]["path"] == "docs/readme.md"
    assert search.json()["citations"][0]["source_id"].startswith("src_")

    manifest = client.post(
        "/merlin/genesis/manifest",
        json={"filename": "file.txt", "code": "content"},
        headers=auth_headers(),
    )
    assert manifest.status_code == 200
    assert manifest.json()["status"] == "queued"

    logs = client.get("/merlin/genesis/logs", headers=auth_headers())
    assert logs.status_code == 200
    assert logs.json()["logs"][0]["message"] == "log"


def test_plugins_dynamic_components_and_aas(monkeypatch):
    monkeypatch.setattr(
        api_server.plugin_manager,
        "list_plugin_info",
        lambda: {"demo": {"name": "Demo", "description": "d", "category": "general"}},
    )
    monkeypatch.setattr(
        api_server.hub_client, "create_aas_task", lambda *args, **kwargs: "42"
    )
    client = TestClient(api_server.app)

    plugins = client.get("/merlin/plugins", headers=auth_headers())
    assert plugins.status_code == 200
    assert plugins.json()[0]["name"] == "Demo"

    components = client.get("/merlin/dynamic_components/u1", headers=auth_headers())
    assert components.status_code == 200
    assert components.json()[0]["actionCommand"] == "demo"

    aas_task = client.post(
        "/merlin/aas/create_task",
        json={"title": "t", "description": "d", "priority": "High"},
        headers=auth_headers(),
    )
    assert aas_task.status_code == 200
    assert aas_task.json()["task_id"] == "42"


def test_rest_plugins_endpoint_filters_by_capability_and_health_state(monkeypatch):
    monkeypatch.setattr(
        api_server.plugin_manager,
        "list_plugin_info",
        lambda: {
            "healthy_demo": {
                "name": "Healthy Demo",
                "capabilities": ["merlin.demo.run"],
                "health_state": "healthy",
            },
            "isolated_demo": {
                "name": "Isolated Demo",
                "capabilities": ["merlin.demo.run"],
                "health_state": "isolated",
            },
        },
    )
    client = TestClient(api_server.app)

    response = client.get(
        "/merlin/plugins",
        params={
            "format": "list",
            "capability": "merlin.demo.run",
            "health_state": "isolated",
        },
        headers=auth_headers(),
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["name"] == "Isolated Demo"

    invalid = client.get(
        "/merlin/plugins",
        params={"health_state": "invalid"},
        headers=auth_headers(),
    )
    assert invalid.status_code == 422


def test_voice_endpoints(monkeypatch):
    class DummyVoice:
        def speak(self, text, engine=None):
            return True

        def listen(self, engine=None):
            return "hi"

    monkeypatch.setattr(api_server, "get_voice", lambda: DummyVoice())
    client = TestClient(api_server.app)

    speak = client.post("/merlin/speak", json={"text": "hello"}, headers=auth_headers())
    assert speak.status_code == 200
    assert speak.json()["ok"] is True

    listen = client.post("/merlin/listen", headers=auth_headers())
    assert listen.status_code == 200
    assert listen.json()["text"] == "hi"


def test_voice_status_and_transcribe(monkeypatch):
    class DummyVoice:
        def status(self):
            return {"tts": {"primary": "pyttsx3"}, "stt": {"primary": "google"}}

        def transcribe_file(self, path, engine=None):
            return "transcribed"

    monkeypatch.setattr(api_server, "get_voice", lambda: DummyVoice())
    client = TestClient(api_server.app)

    status = client.get("/merlin/voice/status", headers=auth_headers())
    assert status.status_code == 200
    assert "tts" in status.json()

    transcribe = client.post(
        "/merlin/voice/transcribe",
        files={"file": ("sample.wav", b"RIFFDATA", "audio/wav")},
        headers=auth_headers(),
    )
    assert transcribe.status_code == 200
    assert transcribe.json()["text"] == "transcribed"


def test_research_manager_endpoints(monkeypatch, tmp_path):
    manager = ResearchManager(tmp_path / "research_manager", allow_writes=True)
    monkeypatch.setattr(api_server, "research_manager", manager)
    client = TestClient(api_server.app)

    create = client.post(
        "/merlin/research/manager/session",
        json={
            "objective": "Build a local probabilistic research orchestrator",
            "constraints": ["repo-local-only"],
            "horizon_days": 10,
            "tags": ["cp4a", "telemetry"],
            "linked_task_ids": [5],
            "planner_artifacts": [
                "docs/research/CHIMERA_V2_CP2_PLANNER_RELIABILITY_PACKET_2026-02-15.md"
            ],
        },
        headers=auth_headers(),
    )
    assert create.status_code == 200
    create_payload = create.json()
    session_id = create_payload["session"]["session_id"]
    assert create_payload["session"]["objective"].startswith("Build a local")
    assert create_payload["session"]["tags"] == ["cp4a", "telemetry"]
    assert create_payload["session"]["linked_task_ids"] == [5]
    assert create_payload["session"]["planner_artifacts"] == [
        "docs/research/CHIMERA_V2_CP2_PLANNER_RELIABILITY_PACKET_2026-02-15.md"
    ]
    assert "risk_rubric" in create_payload["session"]
    assert (
        create_payload["session"]["created_by"]
        == "AaroneousAutomationSuite/Merlin:merlin_api_server"
    )
    assert (
        create_payload["session"]["source_operation"]
        == "http.post:/merlin/research/manager/session"
    )
    assert (
        create_payload["session"]["policy_version"]
        == api_server.RESEARCH_SESSION_PROVENANCE_POLICY_VERSION
    )
    assert len(create_payload["next_actions"]) == 3

    listing = client.get(
        "/merlin/research/manager/sessions?tag=cp4a",
        headers=auth_headers(),
    )
    assert listing.status_code == 200
    listing_payload = listing.json()
    assert listing_payload["sessions"][0]["session_id"] == session_id
    assert listing_payload["next_cursor"] is None

    signal = client.post(
        f"/merlin/research/manager/session/{session_id}/signal",
        json={
            "source": "routing-smoke",
            "claim": "CP4A routing and fallback telemetry checks are green.",
            "confidence": 0.9,
            "supports": ["h_execution_success"],
        },
        headers=auth_headers(),
    )
    assert signal.status_code == 200
    assert signal.json()["session_id"] == session_id

    session = client.get(
        f"/merlin/research/manager/session/{session_id}", headers=auth_headers()
    )
    assert session.status_code == 200
    assert len(session.json()["session"]["signals"]) == 1

    brief = client.get(
        f"/merlin/research/manager/session/{session_id}/brief",
        headers=auth_headers(),
    )
    assert brief.status_code == 200
    brief_payload = brief.json()["brief"]
    assert brief_payload["session_id"] == session_id
    assert brief_payload["brief_template_id"] == "research_manager.default"
    assert brief_payload["brief_template_version"] == "1.0.0"
    assert "risk_rubric" in brief_payload
    assert brief_payload["contradicting_signal_count"] == 0
    assert brief_payload["conflict_count"] == 0
    assert len(brief_payload["causal_chains"]) == 3
    assert len(brief_payload["foresight"]) == 3

    missing = client.get(
        "/merlin/research/manager/session/missing-session-id", headers=auth_headers()
    )
    assert missing.status_code == 404


def test_research_manager_sessions_endpoint_cursor(monkeypatch, tmp_path):
    manager = ResearchManager(tmp_path / "research_manager", allow_writes=True)
    first = manager.create_session("First paged session")
    second = manager.create_session("Second paged session")
    monkeypatch.setattr(api_server, "research_manager", manager)
    client = TestClient(api_server.app)

    first_page = client.get(
        "/merlin/research/manager/sessions?limit=1",
        headers=auth_headers(),
    )
    assert first_page.status_code == 200
    first_page_payload = first_page.json()
    assert first_page_payload["sessions"][0]["session_id"] == second["session_id"]
    assert first_page_payload["next_cursor"] == "1"

    second_page = client.get(
        f"/merlin/research/manager/sessions?limit=1&cursor={first_page_payload['next_cursor']}",
        headers=auth_headers(),
    )
    assert second_page.status_code == 200
    second_page_payload = second_page.json()
    assert second_page_payload["sessions"][0]["session_id"] == first["session_id"]
    assert second_page_payload["next_cursor"] is None


def test_research_manager_search_endpoint(monkeypatch, tmp_path):
    manager = ResearchManager(tmp_path / "research_manager", allow_writes=True)
    manager.create_session("Planner readiness baseline")
    voice = manager.create_session("Voice latency readiness")
    monkeypatch.setattr(api_server, "research_manager", manager)
    client = TestClient(api_server.app)

    search = client.get(
        "/merlin/research/manager/search?q=voice&limit=10",
        headers=auth_headers(),
    )
    assert search.status_code == 200
    payload = search.json()
    assert payload["query"] == "voice"
    assert len(payload["sessions"]) == 1
    assert payload["sessions"][0]["session_id"] == voice["session_id"]
    assert payload["next_cursor"] is None

    invalid = client.get(
        "/merlin/research/manager/search?q=%20%20",
        headers=auth_headers(),
    )
    assert invalid.status_code == 422
    assert "query must be non-empty" in invalid.json()["error"]


def test_research_manager_endpoints_read_only(monkeypatch, tmp_path):
    manager = ResearchManager(tmp_path / "research_manager", allow_writes=True)
    seeded = manager.create_session("Read-only test objective")
    manager.allow_writes = False
    monkeypatch.setattr(api_server, "research_manager", manager)
    client = TestClient(api_server.app)

    create = client.post(
        "/merlin/research/manager/session",
        json={"objective": "Attempt blocked write"},
        headers=auth_headers(),
    )
    assert create.status_code == 403
    assert create.json()["error"] == "Research manager is read-only"

    signal = client.post(
        f"/merlin/research/manager/session/{seeded['session_id']}/signal",
        json={"source": "test", "claim": "blocked", "confidence": 0.9},
        headers=auth_headers(),
    )
    assert signal.status_code == 403
    assert signal.json()["error"] == "Research manager is read-only"


def test_research_manager_endpoints_invalid_session_id(monkeypatch, tmp_path):
    manager = ResearchManager(tmp_path / "research_manager", allow_writes=True)
    monkeypatch.setattr(api_server, "research_manager", manager)
    client = TestClient(api_server.app)

    get_response = client.get(
        "/merlin/research/manager/session/..bad",
        headers=auth_headers(),
    )
    assert get_response.status_code == 422
    assert "session_id contains invalid characters" in get_response.json()["error"]

    brief_response = client.get(
        "/merlin/research/manager/session/..bad/brief",
        headers=auth_headers(),
    )
    assert brief_response.status_code == 422
    assert "session_id contains invalid characters" in brief_response.json()["error"]
