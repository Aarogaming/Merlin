import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker

import merlin_api_server as api_server

ROOT_DIR = Path(__file__).resolve().parents[1]
CONTRACTS_DIR = ROOT_DIR / "contracts"
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "contracts"

OPERATION_ENVELOPE_VALIDATOR = Draft202012Validator(
    json.loads((CONTRACTS_DIR / "aas.operation-envelope.v1.schema.json").read_text()),
    format_checker=FormatChecker(),
)

ERROR_CASES = json.loads(
    (FIXTURES_DIR / "operation_error_invalid_payload.cases.json").read_text(
        encoding="utf-8"
    )
)["cases"]


def auth_headers():
    return {"X-Merlin-Key": "merlin-secret-key"}


def load_contract_fixture(filename: str):
    with (FIXTURES_DIR / filename).open("r", encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def _schema_errors(validator: Draft202012Validator, data: dict):
    return [error.message for error in validator.iter_errors(data)]


def test_invalid_payload_error_fixtures_cover_supported_operations():
    covered = {case["operation_name"] for case in ERROR_CASES}
    assert covered == set(api_server.SUPPORTED_ENVELOPE_OPERATIONS)


@pytest.mark.parametrize(
    "case", ERROR_CASES, ids=[case["operation_name"] for case in ERROR_CASES]
)
def test_invalid_payload_error_responses_match_fixture(case: dict):
    client = TestClient(api_server.app)
    request_fixture = load_contract_fixture(case["request_fixture"])

    # Force deterministic INVALID_PAYLOAD branch across all operation handlers.
    request_fixture["payload"] = "not-an-object"

    response = client.post(
        "/merlin/operations",
        json=request_fixture,
        headers=auth_headers(),
    )

    assert response.status_code == case["expected_status"]
    body = response.json()

    errors = _schema_errors(OPERATION_ENVELOPE_VALIDATOR, body)
    assert not errors, f"Response failed schema validation: {errors}"

    expected_error = case["expected_error"]
    assert body["operation"]["name"] == api_server._response_operation_name(
        case["operation_name"]
    )
    assert body["payload"]["error"]["code"] == expected_error["code"]
    assert body["payload"]["error"]["message"] == expected_error["message"]
    assert body["payload"]["error"]["retryable"] == expected_error["retryable"]
