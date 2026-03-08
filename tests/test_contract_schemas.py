import json
from copy import deepcopy
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker

import merlin_api_server as api_server

ROOT_DIR = Path(__file__).resolve().parents[1]
CONTRACTS_DIR = ROOT_DIR / "contracts"
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "contracts"
SMOKE_BASELINE_PATH = (
    ROOT_DIR / "docs" / "research" / "CP4A_SMOKE_BASELINE_2026-02-15.json"
)


def auth_headers():
    return {"X-Merlin-Key": "merlin-secret-key"}


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


OPERATION_ENVELOPE_VALIDATOR = Draft202012Validator(
    load_json(CONTRACTS_DIR / "aas.operation-envelope.v1.schema.json"),
    format_checker=FormatChecker(),
)
CAPABILITY_MANIFEST_VALIDATOR = Draft202012Validator(
    load_json(CONTRACTS_DIR / "aas.repo-capability-manifest.v1.schema.json"),
    format_checker=FormatChecker(),
)
CP4A_SMOKE_EVIDENCE_VALIDATOR = Draft202012Validator(
    load_json(CONTRACTS_DIR / "cp4a.smoke-evidence.v1.schema.json"),
    format_checker=FormatChecker(),
)


def operation_envelope(operation_name: str, payload: dict):
    return {
        "schema_name": "AAS.OperationEnvelope",
        "schema_version": "1.0.0",
        "message_id": "4f5976db-f731-447a-953e-cd9ed820f647",
        "correlation_id": "73e112e7-9deb-41f0-bdc4-d2cb15725116",
        "trace_id": "572f83a0-d80f-4ce2-b4be-793437978f24",
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
            "idempotency_key": "contract-test-2026-02-13-0001",
            "expects_ack": True,
            "retry": {"max_attempts": 1},
        },
        "payload": payload,
    }


def _schema_errors(validator: Draft202012Validator, data: dict):
    return [error.message for error in validator.iter_errors(data)]


def _normalized_routing_metadata_schema(schema: dict) -> dict:
    normalized = dict(schema)
    normalized.pop("$schema", None)
    normalized.pop("$id", None)
    normalized.pop("title", None)
    normalized.pop("description", None)
    return normalized


def _merge_subset(base, subset):
    if isinstance(base, dict) and isinstance(subset, dict):
        merged = deepcopy(base)
        for key, value in subset.items():
            if key in merged:
                merged[key] = _merge_subset(merged[key], value)
            else:
                merged[key] = deepcopy(value)
        return merged
    return deepcopy(subset)


def test_operation_request_fixtures_match_operation_envelope_schema():
    request_files = sorted(FIXTURES_DIR.glob("*.request.json"))
    assert request_files, "No request fixtures found in tests/fixtures/contracts"

    for request_file in request_files:
        payload = load_json(request_file)
        errors = _schema_errors(OPERATION_ENVELOPE_VALIDATOR, payload)
        assert not errors, f"{request_file.name} failed schema validation: {errors}"


def test_routing_metadata_schema_fragment_matches_embedded_envelope_definition():
    standalone_schema = load_json(
        CONTRACTS_DIR / "assistant.chat.routing-metadata.v1.schema.json"
    )
    envelope_schema = load_json(CONTRACTS_DIR / "aas.operation-envelope.v1.schema.json")
    embedded_schema = envelope_schema["$defs"]["assistant_chat_routing_metadata"]

    assert _normalized_routing_metadata_schema(standalone_schema) == embedded_schema


def test_cp4a_smoke_baseline_is_well_formed():
    baseline = load_json(SMOKE_BASELINE_PATH)

    assert isinstance(baseline.get("planner_expected_tests"), int)
    assert baseline["planner_expected_tests"] > 0
    assert isinstance(baseline.get("schema_expected_tests"), int)
    assert baseline["schema_expected_tests"] > 0
    assert isinstance(baseline.get("planner_min_tests"), int)
    assert baseline["planner_min_tests"] >= 0
    assert isinstance(baseline.get("schema_min_tests"), int)
    assert baseline["schema_min_tests"] >= 0
    assert isinstance(baseline.get("sync_expected_summary"), str)
    assert baseline["sync_expected_summary"].strip()


def test_cp4a_smoke_evidence_fixture_matches_schema_contract():
    evidence = load_json(FIXTURES_DIR / "cp4a.smoke_evidence.contract.json")
    errors = _schema_errors(CP4A_SMOKE_EVIDENCE_VALIDATOR, evidence)

    assert not errors, f"cp4a smoke evidence fixture failed schema validation: {errors}"


def test_chat_with_metadata_expected_fixture_materializes_valid_operation_envelope():
    request_fixture = load_json(
        FIXTURES_DIR / "assistant.chat.request.with_metadata.json"
    )
    expected_response_fixture = load_json(
        FIXTURES_DIR / "assistant.chat.request.with_metadata.expected_response.json"
    )
    materialized_response = _merge_subset(request_fixture, expected_response_fixture)
    errors = _schema_errors(OPERATION_ENVELOPE_VALIDATOR, materialized_response)

    assert (
        not errors
    ), f"assistant.chat with metadata materialized response failed schema: {errors}"


def test_supported_operations_have_request_fixtures():
    request_files = sorted(FIXTURES_DIR.glob("*.request.json"))
    assert request_files, "No request fixtures found in tests/fixtures/contracts"

    operation_names_from_fixtures = set()
    for request_file in request_files:
        payload = load_json(request_file)
        operation = payload.get("operation", {})
        operation_name = operation.get("name")
        if isinstance(operation_name, str) and operation_name:
            operation_names_from_fixtures.add(operation_name)

    missing = sorted(
        set(api_server.SUPPORTED_ENVELOPE_OPERATIONS) - operation_names_from_fixtures
    )
    assert not missing, f"Missing request fixtures for operations: {missing}"


def test_operation_capabilities_matches_manifest_schema():
    client = TestClient(api_server.app)
    response = client.get("/merlin/operations/capabilities", headers=auth_headers())
    assert response.status_code == 200

    body = response.json()
    errors = _schema_errors(CAPABILITY_MANIFEST_VALIDATOR, body)
    assert not errors, f"Capability manifest failed schema validation: {errors}"

    names_from_api = {capability["name"] for capability in body["capabilities"]}
    assert names_from_api == set(api_server.SUPPORTED_ENVELOPE_OPERATIONS)


def test_operation_response_success_matches_operation_envelope_schema(monkeypatch):
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
    errors = _schema_errors(OPERATION_ENVELOPE_VALIDATOR, body)
    assert not errors, f"Success response failed schema validation: {errors}"


def test_operation_response_error_matches_operation_envelope_schema():
    client = TestClient(api_server.app)

    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="assistant.chat.request",
            payload={"user_input": "", "user_id": "u1"},
        ),
        headers=auth_headers(),
    )
    assert response.status_code == 422

    body = response.json()
    errors = _schema_errors(OPERATION_ENVELOPE_VALIDATOR, body)
    assert not errors, f"Error response failed schema validation: {errors}"
    assert body["payload"]["error"]["code"] == "VALIDATION_ERROR"


def test_operation_response_chat_with_metadata_matches_embedded_schema(monkeypatch):
    metadata = load_json(FIXTURES_DIR / "assistant.chat.routing_metadata.contract.json")
    monkeypatch.setattr(
        api_server,
        "merlin_emotion_chat_with_metadata",
        lambda user_input, user_id: ("ok", metadata),
    )
    monkeypatch.setattr(
        api_server, "merlin_emotion_chat", lambda user_input, user_id: "ok"
    )
    client = TestClient(api_server.app)

    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="assistant.chat.request",
            payload={
                "user_input": "hello",
                "user_id": "u1",
                "include_metadata": True,
            },
        ),
        headers=auth_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    errors = _schema_errors(OPERATION_ENVELOPE_VALIDATOR, body)
    assert not errors, f"Metadata response failed schema validation: {errors}"


def test_operation_response_chat_with_invalid_metadata_fails_embedded_schema(
    monkeypatch,
):
    metadata = load_json(FIXTURES_DIR / "assistant.chat.routing_metadata.contract.json")
    metadata["fallback_reason_code"] = "invalid_reason_code"
    metadata["fallback_retryable"] = False
    monkeypatch.setattr(
        api_server,
        "merlin_emotion_chat_with_metadata",
        lambda user_input, user_id: ("ok", metadata),
    )
    monkeypatch.setattr(
        api_server, "merlin_emotion_chat", lambda user_input, user_id: "ok"
    )
    client = TestClient(api_server.app)

    response = client.post(
        "/merlin/operations",
        json=operation_envelope(
            operation_name="assistant.chat.request",
            payload={
                "user_input": "hello",
                "user_id": "u1",
                "include_metadata": True,
            },
        ),
        headers=auth_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    errors = _schema_errors(OPERATION_ENVELOPE_VALIDATOR, body)
    assert errors
