import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker

import merlin_api_server as api_server
from merlin_research_manager import ResearchManager

ROOT_DIR = Path(__file__).resolve().parents[1]
CONTRACTS_DIR = ROOT_DIR / "contracts"
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "contracts"

OPERATION_ENVELOPE_VALIDATOR = Draft202012Validator(
    json.loads((CONTRACTS_DIR / "aas.operation-envelope.v1.schema.json").read_text()),
    format_checker=FormatChecker(),
)

SPECIFIC_ERROR_CASES = json.loads(
    (FIXTURES_DIR / "operation_error_specific.cases.json").read_text(encoding="utf-8")
)["cases"]


def auth_headers():
    return {"X-Merlin-Key": "merlin-secret-key"}


def load_contract_fixture(filename: str):
    with (FIXTURES_DIR / filename).open("r", encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def _schema_errors(validator: Draft202012Validator, data: dict):
    return [error.message for error in validator.iter_errors(data)]


def _apply_case_setup(monkeypatch, setup_name: str | None, tmp_path: Path):
    if not setup_name:
        return

    if setup_name == "assistant_tools_not_found":
        monkeypatch.setattr(
            api_server.plugin_manager,
            "execute_plugin",
            lambda name, *args, **kwargs: {"error": "Plugin missing_tool not found"},
        )
        return

    if setup_name == "assistant_tools_exception":

        def _raise_tool_error(name, *args, **kwargs):
            raise RuntimeError("tool boom")

        monkeypatch.setattr(
            api_server.plugin_manager, "execute_plugin", _raise_tool_error
        )
        return

    if setup_name == "command_blocked":
        monkeypatch.setattr(
            api_server.policy_manager, "is_command_allowed", lambda command: False
        )
        return

    if setup_name == "command_execution_failed":
        monkeypatch.setattr(
            api_server.policy_manager, "is_command_allowed", lambda command: True
        )
        monkeypatch.setattr(
            api_server, "execute_command", lambda command: {"error": "boom"}
        )
        return

    if setup_name == "command_execution_exception":
        monkeypatch.setattr(
            api_server.policy_manager, "is_command_allowed", lambda command: True
        )

        def _raise_command_exception(command):
            raise RuntimeError("command crash")

        monkeypatch.setattr(api_server, "execute_command", _raise_command_exception)
        return

    if setup_name == "plugins_execute_not_found":
        monkeypatch.setattr(
            api_server.plugin_manager,
            "execute_plugin",
            lambda name, *args, **kwargs: {"error": "Plugin missing not found"},
        )
        return

    if setup_name == "plugins_execute_failed_generic":
        monkeypatch.setattr(
            api_server.plugin_manager,
            "execute_plugin",
            lambda name, *args, **kwargs: {"error": "Plugin demo failed"},
        )
        return

    if setup_name == "plugins_execute_exception":

        def _raise_plugin_error(name, *args, **kwargs):
            raise RuntimeError("plugin crash")

        monkeypatch.setattr(
            api_server.plugin_manager, "execute_plugin", _raise_plugin_error
        )
        return

    if setup_name == "voice_unavailable":
        monkeypatch.setattr(api_server, "get_voice", lambda: None)
        return

    if setup_name == "voice_synthesize_failed":

        class DummyVoice:
            def synthesize_to_file(self, text, engine=None):
                return None

        monkeypatch.setattr(api_server, "get_voice", lambda: DummyVoice())
        return

    if setup_name == "voice_synthesize_output_missing":
        missing_output_path = tmp_path / "missing-output.wav"
        if missing_output_path.exists():
            missing_output_path.unlink()

        class DummyVoice:
            def synthesize_to_file(self, text, engine=None):
                return str(missing_output_path)

        monkeypatch.setattr(api_server, "get_voice", lambda: DummyVoice())
        return

    if setup_name == "voice_listen_failed":

        class DummyVoice:
            def listen(self, engine=None):
                return ""

        monkeypatch.setattr(api_server, "get_voice", lambda: DummyVoice())
        return

    if setup_name == "voice_transcribe_failed":

        class DummyVoice:
            def transcribe_file(self, file_path, engine=None):
                return ""

        monkeypatch.setattr(api_server, "get_voice", lambda: DummyVoice())
        return

    if setup_name == "user_create_exists":

        def _raise_exists(username, password, role="user"):
            raise ValueError("User already exists")

        monkeypatch.setattr(api_server.user_manager, "create_user", _raise_exists)
        return

    if setup_name == "user_auth_failed":
        monkeypatch.setattr(
            api_server.user_manager,
            "authenticate_user",
            lambda username, password: None,
        )
        return

    if setup_name == "aas_create_task_failed":
        monkeypatch.setattr(
            api_server.hub_client,
            "create_aas_task",
            lambda title, description, priority: None,
        )
        return

    if setup_name == "research_manager_read_only":
        manager = ResearchManager(tmp_path / "research_manager")
        manager.allow_writes = False
        monkeypatch.setattr(api_server, "research_manager", manager)
        return

    raise AssertionError(f"Unknown case setup: {setup_name}")


def test_specific_error_case_ids_are_unique():
    case_ids = [case["case_id"] for case in SPECIFIC_ERROR_CASES]
    assert len(case_ids) == len(set(case_ids))


def test_specific_error_cases_reference_supported_operations():
    supported = set(api_server.SUPPORTED_ENVELOPE_OPERATIONS)
    for case in SPECIFIC_ERROR_CASES:
        assert case["operation_name"] in supported


@pytest.mark.parametrize(
    "case",
    SPECIFIC_ERROR_CASES,
    ids=[case["case_id"] for case in SPECIFIC_ERROR_CASES],
)
def test_specific_error_responses_match_fixture_cases(
    monkeypatch, tmp_path: Path, case: dict
):
    _apply_case_setup(monkeypatch, case.get("setup"), tmp_path)

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
    assert body["payload"]["error"]["message"] == expected_error["message"]
    assert body["payload"]["error"]["retryable"] == expected_error["retryable"]
