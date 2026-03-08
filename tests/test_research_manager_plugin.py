from __future__ import annotations

import importlib.util
from pathlib import Path

from merlin_research_manager import ResearchManager


def _load_plugin_class():
    plugin_path = Path(__file__).resolve().parents[1] / "plugins" / "research_manager.py"
    spec = importlib.util.spec_from_file_location("research_manager_plugin", plugin_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ResearchManagerPlugin


def test_research_manager_plugin_create_signal_and_brief(tmp_path: Path):
    plugin = _load_plugin_class()()
    plugin.manager = ResearchManager(tmp_path / "research_manager", allow_writes=True)

    created = plugin.execute(
        action="create",
        objective="Stand up a local research manager workflow",
        constraints=["repo-local-only"],
    )
    assert created["ok"] is True
    session_id = created["session"]["session_id"]
    assert len(created["next_actions"]) == 3

    signaled = plugin.execute(
        action="signal",
        session_id=session_id,
        source="local-smoke",
        claim="Core tests are green for planner fallback and schema checks.",
        confidence=0.85,
        supports=["h_execution_success"],
    )
    assert signaled["ok"] is True
    assert signaled["session_id"] == session_id

    brief = plugin.execute(action="brief", session_id=session_id)
    assert brief["ok"] is True
    assert brief["brief"]["session_id"] == session_id
    assert len(brief["brief"]["foresight"]) == 3

    listing = plugin.execute(action="list")
    assert listing["ok"] is True
    assert listing["sessions"][0]["session_id"] == session_id


def test_research_manager_plugin_validation_and_missing_session(tmp_path: Path):
    plugin = _load_plugin_class()()
    plugin.manager = ResearchManager(tmp_path / "research_manager", allow_writes=True)

    invalid = plugin.execute(action="create", objective="")
    assert invalid["ok"] is False
    assert invalid["error"] == "validation_error"

    missing = plugin.execute(action="brief", session_id="does-not-exist")
    assert missing["ok"] is False
    assert missing["error"] == "session_not_found"


def test_research_manager_plugin_read_only(tmp_path: Path):
    plugin = _load_plugin_class()()
    plugin.manager = ResearchManager(tmp_path / "research_manager", allow_writes=False)

    read_only = plugin.execute(
        action="create",
        objective="Attempt mutation while read-only",
    )
    assert read_only["ok"] is False
    assert read_only["error"] == "read_only"
