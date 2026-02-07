from pathlib import Path

from fastapi.testclient import TestClient

import merlin_resource_api as resource_api


def test_resource_api_refresh_and_query(tmp_path, monkeypatch):
    index_path = tmp_path / "index.json"
    index_path.write_text(
        "{\n"
        '  "audio": [{"path": "song.mp3", "type": "mp3", "size": 1, "modified": "now"}],\n'
        '  "docs": [{"path": "notes.txt", "type": "txt", "size": 2, "modified": "now"}]\n'
        "}\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(resource_api, "RESOURCE_INDEX_PATH", str(index_path))
    resource_api.RESOURCE_INDEX_MTIME = None
    resource_api.RESOURCE_INDEX = {}

    client = TestClient(resource_api.app)

    refresh = client.post("/resources/refresh")
    assert refresh.status_code == 200
    assert refresh.json()["counts"]["audio"] == 1

    audio = client.get("/resources", params={"type": "audio"})
    assert audio.status_code == 200
    assert audio.json()[0]["path"] == "song.mp3"

    search = client.get("/resources/search", params={"q": "notes"})
    assert search.status_code == 200
    assert search.json()[0]["path"] == "notes.txt"
