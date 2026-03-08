from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "check_secret_hygiene.py"
)


def _load_script_module():
    spec = importlib.util.spec_from_file_location("check_secret_hygiene_script", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_main_reports_plugin_dependency_preflight_violations(monkeypatch, capsys):
    module = _load_script_module()
    monkeypatch.setattr(module, "_candidate_paths", lambda include_all: [])
    monkeypatch.setattr(
        module,
        "_plugin_dependency_violations",
        lambda plugin_dir: ["dependent_pkg: missing dependency plugin: core_pkg"],
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["check_secret_hygiene.py", "--plugin-dependency-check"],
    )

    result = module.main()
    captured = capsys.readouterr()

    assert result == 2
    assert "plugin dependency compatibility preflight failed" in captured.err
    assert "dependent_pkg: missing dependency plugin: core_pkg" in captured.err


def test_main_passes_when_no_secret_or_dependency_violations(monkeypatch):
    module = _load_script_module()
    monkeypatch.setattr(module, "_candidate_paths", lambda include_all: [])
    monkeypatch.setattr(module, "_plugin_dependency_violations", lambda plugin_dir: [])
    monkeypatch.setattr(
        sys,
        "argv",
        ["check_secret_hygiene.py", "--plugin-dependency-check"],
    )

    assert module.main() == 0


def test_main_keeps_legacy_git_unavailable_behavior_without_plugin_check(
    monkeypatch,
):
    module = _load_script_module()

    def _raise_git_error(include_all):
        raise RuntimeError("git unavailable")

    monkeypatch.setattr(module, "_candidate_paths", _raise_git_error)
    monkeypatch.setattr(sys, "argv", ["check_secret_hygiene.py"])

    assert module.main() == 0


def test_main_writes_report_json(monkeypatch, tmp_path):
    module = _load_script_module()
    report_path = tmp_path / "secret_hygiene_report.json"
    monkeypatch.setattr(module, "_candidate_paths", lambda include_all: ["logs/app.log"])
    monkeypatch.setattr(module, "_plugin_dependency_violations", lambda plugin_dir: [])
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check_secret_hygiene.py",
            "--all",
            "--report-json",
            str(report_path),
            "--fail-on",
            "none",
        ],
    )

    result = module.main()
    payload = json.loads(report_path.read_text(encoding="utf-8"))

    assert result == 0
    assert payload["violation_count"] == 1
    assert payload["ok"] is False
    assert payload["violations"][0]["value"] == "logs/app.log"


def test_main_fail_on_high_returns_failure(monkeypatch):
    module = _load_script_module()
    monkeypatch.setattr(module, "_candidate_paths", lambda include_all: [".env"])
    monkeypatch.setattr(module, "_plugin_dependency_violations", lambda plugin_dir: [])
    monkeypatch.setattr(
        sys,
        "argv",
        ["check_secret_hygiene.py", "--all", "--fail-on", "high"],
    )

    assert module.main() == 2
