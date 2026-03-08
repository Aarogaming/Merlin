import json
import sys
from pathlib import Path

import merlin_seed_access as seed_access
import pytest


def test_seed_status_reads_workspace_artifacts(tmp_path: Path):
    (tmp_path / "artifacts").mkdir(parents=True)
    (tmp_path / "guild" / "data").mkdir(parents=True)
    (tmp_path / "logs").mkdir(parents=True)

    (tmp_path / "artifacts" / "merlin_seed_status.json").write_text(
        json.dumps(
            {
                "status": "running",
                "target": 50000,
                "current_total": 4641,
                "updated_at": "2026-02-24T12:30:00Z",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "guild" / "data" / "merlin_distill_merged.jsonl").write_text(
        '{"row": 1}\n{"row": 2}\n',
        encoding="utf-8",
    )
    (tmp_path / "logs" / "merlin_seed_task.log").write_text(
        "line-1\nline-2\n",
        encoding="utf-8",
    )

    access = seed_access.MerlinSeedAccess(workspace_root=tmp_path)
    payload = access.status(include_log_tail=True, tail_lines=1)

    assert payload["schema_name"] == "AAS.Merlin.SeedStatus"
    assert payload["status"]["current_total"] == 4641
    assert payload["dataset"]["line_count"] == 2
    assert payload["log_tail"]["lines"] == ["line-2"]


def test_seed_control_blocked_when_live_automation_disabled(tmp_path: Path):
    access = seed_access.MerlinSeedAccess(workspace_root=tmp_path)
    blocked = access.control(action="start", allow_live_automation=False)

    assert blocked["schema_name"] == "AAS.Merlin.SeedControl"
    assert blocked["decision"] == "stubbed"
    assert blocked["status"] == "blocked"


def test_seed_control_start_uses_start_path(monkeypatch, tmp_path: Path):
    access = seed_access.MerlinSeedAccess(workspace_root=tmp_path)

    monkeypatch.setattr(access, "_list_processes", lambda **kwargs: [])
    monkeypatch.setattr(
        access,
        "_build_start_command",
        lambda **kwargs: [
            "python",
            "scripts/run_merlin_seed_until.py",
            "--target",
            "50000",
        ],
    )
    monkeypatch.setattr(
        access,
        "_start_process",
        lambda **kwargs: {
            "pid": 12345,
            "command": [
                "python",
                "scripts/run_merlin_seed_until.py",
                "--target",
                "50000",
            ],
        },
    )
    monkeypatch.setattr(
        access,
        "status",
        lambda **kwargs: {
            "schema_name": "AAS.Merlin.SeedStatus",
            "process": {"active": True, "count": 1},
        },
    )

    started = access.control(action="start", allow_live_automation=True)

    assert started["decision"] == "allowed"
    assert started["status"] == "started"
    assert started["start"]["pid"] == 12345
    assert "run_merlin_seed_until.py" in started["start"]["command"]


def test_seed_control_dry_run_previews_start_without_launch(
    monkeypatch, tmp_path: Path
):
    access = seed_access.MerlinSeedAccess(workspace_root=tmp_path)

    monkeypatch.setattr(access, "_list_processes", lambda **kwargs: [])
    monkeypatch.setattr(
        access,
        "_build_start_command",
        lambda **kwargs: [
            "python",
            "scripts/run_merlin_seed_until.py",
            "--target",
            "50000",
        ],
    )

    def _unexpected_start(**kwargs):
        raise AssertionError("start process should not run during dry-run preview")

    monkeypatch.setattr(access, "_start_process", _unexpected_start)
    monkeypatch.setattr(
        access,
        "status",
        lambda **kwargs: {
            "schema_name": "AAS.Merlin.SeedStatus",
            "process": {"active": False, "count": 0},
        },
    )

    preview = access.control(
        action="start",
        allow_live_automation=True,
        dry_run=True,
    )

    assert preview["decision"] == "allowed"
    assert preview["dry_run"] is True
    assert preview["status"] == "preview"
    assert preview["preview"]["would_launch"] is True
    assert "run_merlin_seed_until.py" in preview["preview"]["command"]


def test_seed_status_includes_progress_and_guidance_when_incomplete(tmp_path: Path):
    (tmp_path / "artifacts").mkdir(parents=True)
    (tmp_path / "guild" / "data").mkdir(parents=True)
    (tmp_path / "logs").mkdir(parents=True)

    (tmp_path / "artifacts" / "merlin_seed_status.json").write_text(
        json.dumps(
            {
                "status": "running",
                "target": 50000,
                "current_total": 4250,
                "throughput_per_min": 41.2,
                "updated_at": "2026-02-25T05:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "guild" / "data" / "merlin_distill_merged.jsonl").write_text(
        '{"row": 1}\n',
        encoding="utf-8",
    )

    access = seed_access.MerlinSeedAccess(workspace_root=tmp_path)
    payload = access.status(include_log_tail=False, allow_live_automation=True)

    assert payload["progress"]["target_rounds"] == 50000
    assert payload["progress"]["completed_rounds"] == 4250
    assert payload["progress"]["remaining_rounds"] == 45750
    assert payload["guidance"]["schema_name"] == "AAS.Merlin.SeedGuidance"
    assert payload["guidance"]["state"] == "attention"
    assert payload["guidance"]["next_action"] == "start"
    recommendation_ids = {item["id"] for item in payload["guidance"]["recommendations"]}
    assert "start_worker" in recommendation_ids


def test_seed_status_guidance_blocked_when_live_automation_disabled(tmp_path: Path):
    access = seed_access.MerlinSeedAccess(workspace_root=tmp_path)
    payload = access.status(include_log_tail=False, allow_live_automation=False)

    assert payload["policy"]["decision"] == "stubbed"
    assert payload["guidance"]["state"] == "blocked"
    assert payload["guidance"]["next_action"] == "unblock_policy"
    recommendation_ids = {item["id"] for item in payload["guidance"]["recommendations"]}
    assert "enable_live_automation" in recommendation_ids


def test_resolve_seed_workspace_root_prefers_status_file_candidate(
    monkeypatch, tmp_path: Path
):
    repo_root = tmp_path / "Merlin"
    repo_root.mkdir()
    (repo_root / "scripts").mkdir()
    (repo_root / "scripts" / "run_merlin_seed_until.py").write_text(
        "#!/usr/bin/env python\n",
        encoding="utf-8",
    )

    parent_status = tmp_path / "artifacts"
    parent_status.mkdir()
    (parent_status / "merlin_seed_status.json").write_text(
        json.dumps({"current_total": 4641, "target": 50000}),
        encoding="utf-8",
    )

    monkeypatch.chdir(repo_root)
    resolved = seed_access.resolve_seed_workspace_root()

    assert resolved == tmp_path.resolve()


def test_seed_health_reports_attention_with_start_recommendation(tmp_path: Path):
    (tmp_path / "artifacts").mkdir(parents=True)
    (tmp_path / "guild" / "data").mkdir(parents=True)

    (tmp_path / "artifacts" / "merlin_seed_status.json").write_text(
        json.dumps(
            {
                "status": "running",
                "target": 50000,
                "current_total": 4641,
                "updated_at": "2026-02-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "guild" / "data" / "merlin_distill_merged.jsonl").write_text(
        '{"row": 1}\n',
        encoding="utf-8",
    )

    access = seed_access.MerlinSeedAccess(workspace_root=tmp_path)
    payload = access.health(
        allow_live_automation=True,
        stale_after_seconds=1200.0,
    )

    assert payload["schema_name"] == "AAS.Merlin.SeedHealth"
    assert payload["state"] == "attention"
    assert payload["severity"] == "warn"
    assert payload["next_action"] == "start"
    assert payload["recommended_control_action"] == "start"
    assert payload["checks"]["status_stale"] is True
    assert payload["checks"]["worker_active"] is False


def test_seed_health_reports_blocked_when_live_automation_disabled(tmp_path: Path):
    access = seed_access.MerlinSeedAccess(workspace_root=tmp_path)
    payload = access.health(allow_live_automation=False)

    assert payload["policy_decision"] == "stubbed"
    assert payload["state"] == "blocked"
    assert payload["severity"] == "critical"
    assert payload["recommended_control_action"] == "none"


def test_seed_control_start_prefers_endpoint_from_status_file_when_default(
    monkeypatch, tmp_path: Path
):
    (tmp_path / "artifacts").mkdir(parents=True)
    (tmp_path / "artifacts" / "merlin_seed_status.json").write_text(
        json.dumps({"endpoint": "http://100.110.74.113:1234"}),
        encoding="utf-8",
    )

    access = seed_access.MerlinSeedAccess(workspace_root=tmp_path)
    monkeypatch.setattr(access, "_list_processes", lambda **kwargs: [])

    captured: dict[str, object] = {}

    def _capture_build_start_command(**kwargs):
        captured.update(kwargs)
        return ["python", "scripts/run_merlin_seed_until.py"]

    monkeypatch.setattr(access, "_build_start_command", _capture_build_start_command)
    monkeypatch.setattr(
        access,
        "_start_process",
        lambda **kwargs: {
            "pid": 99999,
            "command": kwargs["command_override"],
        },
    )
    monkeypatch.setattr(
        access,
        "status",
        lambda **kwargs: {
            "schema_name": "AAS.Merlin.SeedStatus",
            "process": {"active": True, "count": 1},
        },
    )

    started = access.control(action="start", allow_live_automation=True)

    assert started["status"] == "started"
    assert captured["endpoint"] == "http://100.110.74.113:1234"


def test_resolve_python_executable_skips_windows_python_on_posix(tmp_path: Path):
    if seed_access.os.name == "nt":
        pytest.skip("POSIX-only assertion")

    windows_python = tmp_path / ".venv" / "Scripts" / "python.exe"
    windows_python.parent.mkdir(parents=True)
    windows_python.write_text("", encoding="utf-8")

    access = seed_access.MerlinSeedAccess(workspace_root=tmp_path)
    assert access._resolve_python_executable() == sys.executable


def test_seed_status_prefers_mtime_age_when_active_process_has_clock_skew(
    monkeypatch, tmp_path: Path
):
    (tmp_path / "artifacts").mkdir(parents=True)
    (tmp_path / "guild" / "data").mkdir(parents=True)
    (tmp_path / "artifacts" / "merlin_seed_status.json").write_text(
        json.dumps(
            {
                "status": "running",
                "target": 50000,
                "current_total": 5000,
                "updated_at": "2026-02-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    access = seed_access.MerlinSeedAccess(workspace_root=tmp_path)
    monkeypatch.setattr(
        access,
        "_list_processes",
        lambda **kwargs: [{"pid": 123, "command": "python run_merlin_seed_until.py"}],
    )

    payload = access.status(include_log_tail=False, allow_live_automation=True)

    assert payload["process"]["active"] is True
    assert isinstance(payload["status_file"]["status_age_seconds"], float)
    assert payload["status_file"]["status_age_seconds"] < 300.0
    assert payload["status_file"]["stale"] is False


def test_seed_heartbeat_writes_event_file(tmp_path: Path):
    (tmp_path / "artifacts").mkdir(parents=True)
    (tmp_path / "guild" / "data").mkdir(parents=True)
    (tmp_path / "logs").mkdir(parents=True)

    (tmp_path / "artifacts" / "merlin_seed_status.json").write_text(
        json.dumps(
            {
                "status": "running",
                "target": 50000,
                "current_total": 5712,
                "updated_at": "2026-02-25T18:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "guild" / "data" / "merlin_distill_merged.jsonl").write_text(
        '{"row": 1}\n{"row": 2}\n',
        encoding="utf-8",
    )

    heartbeat_path = (
        tmp_path / "artifacts" / "diagnostics" / "merlin_seed_health_heartbeat.jsonl"
    )
    access = seed_access.MerlinSeedAccess(workspace_root=tmp_path)
    payload = access.heartbeat(
        allow_live_automation=True,
        write_event=True,
        heartbeat_file=str(heartbeat_path),
    )

    assert payload["schema_name"] == "AAS.Merlin.SeedHealthHeartbeat"
    assert payload["persisted"] is True
    assert payload["heartbeat_file"] == str(heartbeat_path)
    assert heartbeat_path.exists()

    lines = heartbeat_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["schema_name"] == "AAS.Merlin.SeedHealthHeartbeat"
    assert event["event_id"] == payload["event_id"]
    assert event["persisted"] is True


def test_seed_heartbeat_no_write_returns_event_only(tmp_path: Path):
    heartbeat_path = tmp_path / "artifacts" / "diagnostics" / "custom_hb.jsonl"
    access = seed_access.MerlinSeedAccess(workspace_root=tmp_path)

    payload = access.heartbeat(
        allow_live_automation=True,
        write_event=False,
        heartbeat_file=str(heartbeat_path),
    )

    assert payload["schema_name"] == "AAS.Merlin.SeedHealthHeartbeat"
    assert payload["persisted"] is False
    assert payload["heartbeat_file"] == str(heartbeat_path)
    assert heartbeat_path.exists() is False


def test_seed_watchdog_preview_recommended_action_without_apply(tmp_path: Path):
    access = seed_access.MerlinSeedAccess(workspace_root=tmp_path)
    payload = access.watchdog(
        allow_live_automation=True,
        apply=False,
    )

    assert payload["schema_name"] == "AAS.Merlin.SeedWatchdogTick"
    assert payload["decision"]["recommended_control_action"] == "start"
    assert payload["decision"]["outcome_status"] == "preview"
    assert payload["decision"]["action_taken"] == "none"
    assert payload["control_result"] is None


def test_seed_watchdog_apply_executes_control(monkeypatch, tmp_path: Path):
    access = seed_access.MerlinSeedAccess(workspace_root=tmp_path)

    captured: dict[str, object] = {}

    def _control_stub(*, action, **kwargs):
        captured["action"] = action
        captured.update(kwargs)
        return {
            "schema_name": "AAS.Merlin.SeedControl",
            "schema_version": "1.0.0",
            "action": action,
            "decision": "allowed",
            "status": "started",
        }

    monkeypatch.setattr(access, "control", _control_stub)

    payload = access.watchdog(
        allow_live_automation=True,
        apply=True,
        force=True,
        dry_run_control=False,
    )

    assert payload["decision"]["recommended_control_action"] == "start"
    assert payload["decision"]["action_taken"] == "start"
    assert payload["decision"]["outcome_status"] == "executed"
    assert payload["control_result"]["status"] == "started"
    assert captured["action"] == "start"
    assert captured["force"] is True
    assert captured["dry_run"] is False


def test_seed_watchdog_apply_blocked_when_policy_disallows(tmp_path: Path):
    access = seed_access.MerlinSeedAccess(workspace_root=tmp_path)
    payload = access.watchdog(
        allow_live_automation=False,
        apply=True,
    )

    assert payload["health"]["policy_decision"] == "stubbed"
    assert payload["decision"]["recommended_control_action"] == "none"
    assert payload["decision"]["outcome_status"] == "blocked"
    assert payload["control_result"] is None


def test_seed_watchdog_runtime_status_reports_process_and_telemetry(
    monkeypatch, tmp_path: Path
):
    (tmp_path / "artifacts" / "diagnostics").mkdir(parents=True)
    (tmp_path / "logs").mkdir(parents=True)
    (tmp_path / "artifacts" / "merlin_seed_status.json").write_text(
        json.dumps({"status": "idle", "updated_at": "2026-02-25T21:00:00Z"}),
        encoding="utf-8",
    )
    append_jsonl = (
        tmp_path / "artifacts" / "diagnostics" / "merlin_seed_watchdog_runtime_ticks.jsonl"
    )
    append_jsonl.write_text(
        json.dumps(
            {
                "iteration": 1,
                "watchdog": {
                    "schema_name": "AAS.Merlin.SeedWatchdogTick",
                    "decision": {"outcome_status": "preview"},
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    output_json = (
        tmp_path / "artifacts" / "diagnostics" / "merlin_seed_watchdog_runtime_latest.json"
    )
    output_json.write_text(
        json.dumps({"summary": {"total_ticks": 1, "preview": 1}}),
        encoding="utf-8",
    )

    access = seed_access.MerlinSeedAccess(workspace_root=tmp_path)
    monkeypatch.setattr(
        access,
        "_list_processes",
        lambda **kwargs: [
            {"pid": 7777, "command": "python scripts/run_merlin_seed_watchdog.py"}
        ],
    )

    payload = access.watchdog_runtime_status(
        allow_live_automation=True,
    )

    assert payload["schema_name"] == "AAS.Merlin.SeedWatchdogRuntimeStatus"
    assert payload["process"]["active"] is True
    assert payload["process"]["count"] == 1
    assert payload["telemetry"]["append_jsonl_exists"] is True
    assert payload["telemetry"]["append_jsonl_line_count"] == 1
    assert payload["telemetry"]["last_tick"]["iteration"] == 1
    assert payload["telemetry"]["last_report_summary"]["total_ticks"] == 1


def test_seed_watchdog_runtime_control_blocked_when_live_automation_disabled(
    tmp_path: Path,
):
    access = seed_access.MerlinSeedAccess(workspace_root=tmp_path)
    payload = access.watchdog_runtime_control(
        action="start",
        allow_live_automation=False,
    )

    assert payload["schema_name"] == "AAS.Merlin.SeedWatchdogRuntimeControl"
    assert payload["decision"] == "stubbed"
    assert payload["status"] == "blocked"


def test_seed_watchdog_runtime_control_dry_run_preview_start(tmp_path: Path):
    access = seed_access.MerlinSeedAccess(workspace_root=tmp_path)
    payload = access.watchdog_runtime_control(
        action="start",
        allow_live_automation=True,
        dry_run=True,
        apply=True,
        dry_run_control=True,
        interval_seconds=5.0,
        max_iterations=0,
        emit_heartbeat=False,
    )

    assert payload["schema_name"] == "AAS.Merlin.SeedWatchdogRuntimeControl"
    assert payload["decision"] == "allowed"
    assert payload["status"] == "preview"
    assert payload["preview"]["would_launch"] is True
    assert payload["runtime"]["max_iterations"] == 0
    assert payload["runtime"]["emit_heartbeat"] is False
    assert "run_merlin_seed_watchdog.py" in payload["preview"]["command"]
