import json
import re
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

DYNAMIC_ERROR_CASES = json.loads(
    (FIXTURES_DIR / "operation_error_dynamic.cases.json").read_text(encoding="utf-8")
)["cases"]


def auth_headers():
    return {"X-Merlin-Key": "merlin-secret-key"}


def load_contract_fixture(filename: str):
    with (FIXTURES_DIR / filename).open("r", encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def _schema_errors(validator: Draft202012Validator, data: dict):
    return [error.message for error in validator.iter_errors(data)]


def _apply_dynamic_setup(monkeypatch, setup_name: str | None):
    if not setup_name:
        return

    if setup_name == "assistant_tools_not_found_dynamic":
        monkeypatch.setattr(
            api_server.plugin_manager,
            "execute_plugin",
            lambda name, *args, **kwargs: {"error": f"Plugin {name} not found"},
        )
        return

    if setup_name == "plugins_execute_not_found_dynamic":
        monkeypatch.setattr(
            api_server.plugin_manager,
            "execute_plugin",
            lambda name, *args, **kwargs: {"error": f"Plugin {name} not found"},
        )
        return

    if setup_name == "command_execution_failed_dynamic":
        monkeypatch.setattr(
            api_server.policy_manager, "is_command_allowed", lambda command: True
        )
        monkeypatch.setattr(
            api_server,
            "execute_command",
            lambda command: {"error": f"command failed: {command}"},
        )
        return

    if setup_name == "user_create_exists_dynamic":

        def _raise_exists(username, password, role="user"):
            raise ValueError(f"User {username} already exists")

        monkeypatch.setattr(api_server.user_manager, "create_user", _raise_exists)
        return

    raise AssertionError(f"Unknown dynamic case setup: {setup_name}")


def test_dynamic_error_case_ids_are_unique():
    case_ids = [case["case_id"] for case in DYNAMIC_ERROR_CASES]
    assert len(case_ids) == len(set(case_ids))


def test_dynamic_error_cases_reference_supported_operations():
    supported = set(api_server.SUPPORTED_ENVELOPE_OPERATIONS)
    for case in DYNAMIC_ERROR_CASES:
        assert case["operation_name"] in supported


@pytest.mark.parametrize(
    "case",
    DYNAMIC_ERROR_CASES,
    ids=[case["case_id"] for case in DYNAMIC_ERROR_CASES],
)
def test_dynamic_error_responses_match_fixture_cases(monkeypatch, case: dict):
    _apply_dynamic_setup(monkeypatch, case.get("setup"))

    client = TestClient(api_server.app)
    request_fixture = load_contract_fixture(case["request_fixture"])

    if "payload" in case:
        request_fixture["payload"] = case["payload"]

    response = client.post(
        "/merlin/operations",
        json=request_fixture,
        headers=auth_headers(),
    )

    assert response.status_code == case["expected_status"]
    body = response.json()

    errors = _schema_errors(OPERATION_ENVELOPE_VALIDATOR, body)
    assert not errors, f"Response failed schema validation: {errors}"

    assert body["correlation_id"] == request_fixture["correlation_id"]
    assert body["trace_id"] == request_fixture["trace_id"]
    assert body["operation"]["name"] == api_server._response_operation_name(
        request_fixture["operation"]["name"]
    )

    expected_error = case["expected_error"]
    assert body["payload"]["error"]["code"] == expected_error["code"]
    assert body["payload"]["error"]["retryable"] == expected_error["retryable"]

    actual_message = body["payload"]["error"]["message"]
    if "message" in expected_error:
        assert actual_message == expected_error["message"]
    if "message_contains" in expected_error:
        assert expected_error["message_contains"] in actual_message
    if "message_regex" in expected_error:
        assert re.search(expected_error["message_regex"], actual_message)
