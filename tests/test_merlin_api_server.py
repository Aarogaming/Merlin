from fastapi.testclient import TestClient

import merlin_api_server as api_server


def auth_headers():
    return {"X-Merlin-Key": "merlin-secret-key"}


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
