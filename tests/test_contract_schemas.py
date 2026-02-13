import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker

import merlin_api_server as api_server

ROOT_DIR = Path(__file__).resolve().parents[1]
CONTRACTS_DIR = ROOT_DIR / "contracts"
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "contracts"


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


def test_operation_request_fixtures_match_operation_envelope_schema():
    request_files = sorted(FIXTURES_DIR.glob("*.request.json"))
    assert request_files, "No request fixtures found in tests/fixtures/contracts"

    for request_file in request_files:
        payload = load_json(request_file)
        errors = _schema_errors(OPERATION_ENVELOPE_VALIDATOR, payload)
        assert not errors, f"{request_file.name} failed schema validation: {errors}"


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
