import json
from pathlib import Path

from fastapi.testclient import TestClient

import merlin_api_server as api_server

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
