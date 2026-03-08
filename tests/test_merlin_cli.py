import json
import subprocess
import sys

import pytest

import merlin_cli
from merlin_research_manager import ResearchManager


def _set_argv(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["merlin_cli.py", *args])


def test_plugin_list_loads_packaged_plugins_without_core_import_skip():
    result = subprocess.run(
        [sys.executable, "merlin_cli.py", "plugin", "list"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "No module named 'core'" not in result.stderr
    assert "strict packaged plugin load failed" not in result.stderr
    assert "No module named 'core.integrations'" not in result.stderr

    payload = json.loads(result.stdout)
    assert "discovery_engine" in payload
    assert "kernel" in payload
    assert "file_manager" in payload
    assert "session_builder" in payload
    assert "session_streamer" in payload


def test_research_cli_create_signal_brief_and_list(monkeypatch, tmp_path, capsys):
    manager = ResearchManager(tmp_path / "research_manager", allow_writes=True)
    monkeypatch.setattr(merlin_cli, "ResearchManager", lambda: manager)

    _set_argv(
        monkeypatch,
        "research",
        "create",
        "Build local orchestration research flow",
        "--constraint",
        "repo-local-only",
        "--horizon-days",
        "10",
        "--task-id",
        "21",
        "--planner-artifact",
        "docs/research/CHIMERA_V2_CP4A_PLANNER_READINESS_STATUS_2026-02-15.md",
    )
    merlin_cli.main()
    created = json.loads(capsys.readouterr().out)
    session_id = created["session"]["session_id"]
    assert created["session"]["objective"].startswith("Build local")
    assert created["session"]["linked_task_ids"] == [21]
    assert created["session"]["planner_artifacts"] == [
        "docs/research/CHIMERA_V2_CP4A_PLANNER_READINESS_STATUS_2026-02-15.md"
    ]

    _set_argv(
        monkeypatch,
        "research",
        "signal",
        session_id,
        "--source",
        "routing-suite",
        "--claim",
        "Planner fallback tests are green",
        "--confidence",
        "0.9",
        "--supports",
        "h_execution_success",
    )
    merlin_cli.main()
    signal_result = json.loads(capsys.readouterr().out)
    assert signal_result["session_id"] == session_id

    _set_argv(monkeypatch, "research", "brief", session_id)
    merlin_cli.main()
    brief = json.loads(capsys.readouterr().out)
    assert brief["brief"]["session_id"] == session_id

    _set_argv(monkeypatch, "research", "list", "--limit", "5")
    merlin_cli.main()
    listing = json.loads(capsys.readouterr().out)
    assert listing["sessions"][0]["session_id"] == session_id


def test_research_cli_brief_causal_render(monkeypatch, tmp_path, capsys):
    manager = ResearchManager(tmp_path / "research_manager", allow_writes=True)
    monkeypatch.setattr(merlin_cli, "ResearchManager", lambda: manager)

    session = manager.create_session("CLI causal render")
    session_id = session["session_id"]
    manager.add_signal(
        session_id=session_id,
        source="cli-causal-source",
        claim="Evidence linked for causal rendering",
        confidence=0.9,
        supports=["h_execution_success"],
    )

    _set_argv(monkeypatch, "research", "brief", session_id, "--render", "causal")
    merlin_cli.main()
    output = capsys.readouterr().out
    assert "causal_chains:" in output
    assert "h_execution_success" in output
    assert "support: cli-causal-source" in output


def test_research_cli_export_and_import_snapshot(monkeypatch, tmp_path, capsys):
    manager = ResearchManager(tmp_path / "research_manager", allow_writes=True)
    monkeypatch.setattr(merlin_cli, "ResearchManager", lambda: manager)

    session = manager.create_session("CLI export/import snapshot")
    session_id = session["session_id"]
    output_path = tmp_path / "snapshots" / "session_snapshot.json"

    _set_argv(
        monkeypatch,
        "research",
        "export",
        session_id,
        str(output_path),
    )
    merlin_cli.main()
    export_payload = json.loads(capsys.readouterr().out)
    assert export_payload["status"] == "exported"
    assert output_path.exists()

    manager._session_path(session_id).unlink()
    with pytest.raises(FileNotFoundError):
        manager.get_session(session_id)

    _set_argv(
        monkeypatch,
        "research",
        "import",
        str(output_path),
    )
    merlin_cli.main()
    import_payload = json.loads(capsys.readouterr().out)
    assert import_payload["status"] == "imported"
    assert import_payload["session"]["session_id"] == session_id
    assert manager.get_session(session_id)["session_id"] == session_id


def test_research_cli_packet_generates_cp_markdown(monkeypatch, tmp_path, capsys):
    manager = ResearchManager(tmp_path / "research_manager", allow_writes=True)
    monkeypatch.setattr(merlin_cli, "ResearchManager", lambda: manager)

    session = manager.create_session(
        "Generate CP packet from session brief",
        linked_task_ids=[9],
        planner_artifacts=["docs/research/CP_PACKET_EXAMPLE.md"],
    )
    session_id = session["session_id"]
    manager.add_signal(
        session_id=session_id,
        source="cli-packet",
        claim="Fallback telemetry trend is stable for packet generation",
        confidence=0.85,
        supports=["h_execution_success"],
    )
    output_path = tmp_path / "docs" / "research" / "cp_packet.md"

    _set_argv(
        monkeypatch,
        "research",
        "packet",
        session_id,
        "--output",
        str(output_path),
        "--cycle-id",
        "CHIMERA-V2-RESEARCH-AND-EXECUTION-2026-02-15",
        "--phase",
        "CP4-A",
    )
    merlin_cli.main()
    result = json.loads(capsys.readouterr().out)

    assert result["status"] == "generated"
    assert result["session_id"] == session_id
    assert output_path.exists()
    packet_text = output_path.read_text(encoding="utf-8")
    assert "FUNCTION_STATEMENT" in packet_text
    assert "EVIDENCE_REFERENCES" in packet_text
    assert "VERIFICATION_COMMANDS_RUN" in packet_text
    assert session_id in packet_text
    assert "CP4-A" in packet_text


def test_research_cli_create_with_tags_and_filtered_list(monkeypatch, tmp_path, capsys):
    manager = ResearchManager(tmp_path / "research_manager", allow_writes=True)
    monkeypatch.setattr(merlin_cli, "ResearchManager", lambda: manager)

    _set_argv(
        monkeypatch,
        "research",
        "create",
        "Planner fallback readiness",
        "--tag",
        "cp2",
        "--tag",
        "routing",
    )
    merlin_cli.main()
    first = json.loads(capsys.readouterr().out)
    first_session_id = first["session"]["session_id"]

    _set_argv(
        monkeypatch,
        "research",
        "create",
        "Voice latency baseline",
        "--tag",
        "voice",
    )
    merlin_cli.main()
    second = json.loads(capsys.readouterr().out)
    second_session_id = second["session"]["session_id"]

    _set_argv(monkeypatch, "research", "list", "--tag", "cp2")
    merlin_cli.main()
    filtered_by_tag = json.loads(capsys.readouterr().out)
    assert [item["session_id"] for item in filtered_by_tag["sessions"]] == [
        first_session_id
    ]

    _set_argv(monkeypatch, "research", "list", "--topic", "voice")
    merlin_cli.main()
    filtered_by_topic = json.loads(capsys.readouterr().out)
    assert [item["session_id"] for item in filtered_by_topic["sessions"]] == [
        second_session_id
    ]


def test_research_cli_batch_executes_repeated_operations(monkeypatch, tmp_path, capsys):
    manager = ResearchManager(tmp_path / "research_manager", allow_writes=True)
    monkeypatch.setattr(merlin_cli, "ResearchManager", lambda: manager)

    batch_file = tmp_path / "batch" / "research_batch.json"
    batch_file.parent.mkdir(parents=True, exist_ok=True)
    batch_file.write_text(
        json.dumps(
            [
                {
                    "action": "create",
                    "objective": "Batch-mode research setup",
                    "tags": ["batch"],
                    "linked_task_ids": [8, 8],
                    "planner_artifacts": [
                        "docs/research/CHIMERA_V2_CP2_PLANNER_RELIABILITY_PACKET_2026-02-15.md"
                    ],
                },
                {
                    "action": "signal",
                    "session_id": "$last_session_id",
                    "source": "batch-source",
                    "claim": "Batch signal linked to last session id",
                    "confidence": 0.85,
                    "supports": ["h_execution_success"],
                },
                {
                    "action": "brief",
                    "session_id": "$last_session_id",
                },
            ]
        ),
        encoding="utf-8",
    )

    _set_argv(monkeypatch, "research", "batch", "--file", str(batch_file))
    merlin_cli.main()
    summary = json.loads(capsys.readouterr().out)

    assert summary["schema_name"] == "AAS.ResearchBatchResult"
    assert summary["step_count"] == 3
    assert summary["success_count"] == 3
    assert summary["failure_count"] == 0
    assert summary["last_session_id"]
    assert summary["results"][0]["result"]["session"]["linked_task_ids"] == [8]
    assert summary["results"][0]["result"]["session"]["planner_artifacts"] == [
        "docs/research/CHIMERA_V2_CP2_PLANNER_RELIABILITY_PACKET_2026-02-15.md"
    ]
    assert (
        summary["results"][2]["result"]["brief"]["session_id"]
        == summary["last_session_id"]
    )


def test_research_cli_read_only_returns_exit_1(monkeypatch, tmp_path, capsys):
    manager = ResearchManager(tmp_path / "research_manager", allow_writes=False)
    monkeypatch.setattr(merlin_cli, "ResearchManager", lambda: manager)

    _set_argv(monkeypatch, "research", "create", "Should fail")
    with pytest.raises(SystemExit) as exc_info:
        merlin_cli.main()

    assert exc_info.value.code == 1
    error_output = capsys.readouterr().err
    assert "read-only" in error_output


def test_research_cli_missing_session_returns_exit_1(monkeypatch, tmp_path, capsys):
    manager = ResearchManager(tmp_path / "research_manager", allow_writes=True)
    monkeypatch.setattr(merlin_cli, "ResearchManager", lambda: manager)

    _set_argv(monkeypatch, "research", "brief", "missing-session")
    with pytest.raises(SystemExit) as exc_info:
        merlin_cli.main()

    assert exc_info.value.code == 1
    error_output = capsys.readouterr().err
    assert "not found" in error_output


def test_backup_cli_create_emits_created_payload(monkeypatch, tmp_path, capsys):
    expected_backup_path = str(tmp_path / "backups" / "merlin_backup.zip")
    monkeypatch.setattr(
        merlin_cli, "create_backup", lambda backup_dir: expected_backup_path
    )

    _set_argv(
        monkeypatch, "backup", "create", "--backup-dir", str(tmp_path / "backups")
    )
    merlin_cli.main()
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "created"
    assert payload["backup_path"] == expected_backup_path


def test_backup_cli_verify_non_ok_exits_1(monkeypatch):
    monkeypatch.setattr(
        merlin_cli,
        "verify_backup_integrity",
        lambda backup_path, manifest_path=None, expected_sha256=None: {
            "ok": False,
            "backup_path": backup_path,
        },
    )

    _set_argv(monkeypatch, "backup", "verify", "missing.zip")
    with pytest.raises(SystemExit) as exc_info:
        merlin_cli.main()

    assert exc_info.value.code == 1


def test_backup_cli_smoke_test_and_restore_db(monkeypatch, capsys):
    monkeypatch.setattr(
        merlin_cli,
        "run_restore_smoke_test",
        lambda backup_path: {"ok": True, "backup_path": backup_path},
    )
    monkeypatch.setattr(
        merlin_cli,
        "restore_database_snapshot",
        lambda backup_path, db_path="merlin.db": {
            "ok": True,
            "backup_path": backup_path,
            "db_path": db_path,
        },
    )

    _set_argv(monkeypatch, "backup", "smoke-test", "backups/demo.zip")
    merlin_cli.main()
    smoke_payload = json.loads(capsys.readouterr().out)
    assert smoke_payload["ok"] is True

    _set_argv(
        monkeypatch,
        "backup",
        "restore-db",
        "backups/demo.sqlite",
        "--db-path",
        "runtime/merlin.db",
    )
    merlin_cli.main()
    restore_payload = json.loads(capsys.readouterr().out)
    assert restore_payload["ok"] is True
    assert restore_payload["db_path"] == "runtime/merlin.db"
