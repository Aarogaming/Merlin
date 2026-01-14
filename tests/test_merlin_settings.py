import importlib
from pathlib import Path


def test_parse_list_and_env_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("MERLIN_CHAT_HISTORY_DIR", str(tmp_path / "history"))
    settings = importlib.import_module("merlin_settings")
    settings = importlib.reload(settings)

    assert settings._parse_list("a, b, ,c") == ["a", "b", "c"]
    assert settings._parse_list("") == []
    assert settings._parse_list(None) == []

    assert settings.MERLIN_CHAT_HISTORY_DIR == Path(tmp_path / "history")
    assert settings.MERLIN_CHAT_HISTORY_DIR.exists()
