import json
import sys

import pytest

import merlin_cli


def _set_argv(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["merlin_cli.py", *args])


def test_seed_cli_status_uses_native_seed_access(monkeypatch, capsys):
    workspace_roots: list[str | None] = []

    class DummySeedAccess:
        def __init__(self):
            self.status_calls = []

        def status(self, **kwargs):
            self.status_calls.append(kwargs)
            return {
                "schema_name": "AAS.Merlin.SeedStatus",
                "status": {"current_total": 4641},
            }

    dummy = DummySeedAccess()
    monkeypatch.setattr(
        merlin_cli,
        "build_seed_access",
        lambda workspace_root=None: workspace_roots.append(workspace_root) or dummy,
    )

    _set_argv(
        monkeypatch,
        "seed",
        "status",
        "--workspace-root",
        "/tmp/seed-workspace",
        "--status-file",
        "artifacts/custom_seed_status.json",
        "--tail-lines",
        "5",
        "--no-log-tail",
        "--no-live-automation",
    )
    merlin_cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_name"] == "AAS.Merlin.SeedStatus"
    assert payload["status"]["current_total"] == 4641
    assert workspace_roots == ["/tmp/seed-workspace"]
    assert len(dummy.status_calls) == 1
    call = dummy.status_calls[0]
    assert call["status_file"] == "artifacts/custom_seed_status.json"
    assert call["tail_lines"] == 5
    assert call["include_log_tail"] is False
    assert call["allow_live_automation"] is False


def test_seed_cli_control_uses_native_seed_access(monkeypatch, capsys):
    workspace_roots: list[str | None] = []

    class DummySeedAccess:
        def __init__(self):
            self.control_calls = []

        def control(self, **kwargs):
            self.control_calls.append(kwargs)
            return {
                "schema_name": "AAS.Merlin.SeedControl",
                "decision": "allowed",
                "status": "started",
            }

    dummy = DummySeedAccess()
    monkeypatch.setattr(
        merlin_cli,
        "build_seed_access",
        lambda workspace_root=None: workspace_roots.append(workspace_root) or dummy,
    )

    _set_argv(
        monkeypatch,
        "seed",
        "control",
        "start",
        "--workspace-root",
        "/tmp/seed-workspace",
        "--dry-run",
        "--force",
        "--target",
        "60000",
        "--increment",
        "1000",
        "--repeat",
        "7",
        "--eta-window",
        "3",
        "--sleep-seconds",
        "0.2",
        "--delay-seconds",
        "1.5",
        "--cpu-max",
        "90",
        "--mem-max",
        "91",
        "--resource-wait",
        "2.5",
        "--allow-live-automation",
        "--teachers",
        "qwen/qwen3-vl-4b",
    )
    merlin_cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_name"] == "AAS.Merlin.SeedControl"
    assert payload["status"] == "started"
    assert workspace_roots == ["/tmp/seed-workspace"]
    assert len(dummy.control_calls) == 1
    call = dummy.control_calls[0]
    assert call["action"] == "start"
    assert call["dry_run"] is True
    assert call["force"] is True
    assert call["target"] == 60000
    assert call["increment"] == 1000
    assert call["repeat"] == 7
    assert call["eta_window"] == 3
    assert call["sleep_seconds"] == 0.2
    assert call["delay_seconds"] == 1.5
    assert call["cpu_max"] == 90.0
    assert call["mem_max"] == 91.0
    assert call["resource_wait"] == 2.5
    assert call["allow_live_automation"] is True
    assert call["teachers"] == "qwen/qwen3-vl-4b"


def test_seed_cli_control_value_error_returns_exit_1(monkeypatch, capsys):
    class DummySeedAccess:
        def control(self, **kwargs):
            raise ValueError("bad seed action")

    monkeypatch.setattr(
        merlin_cli, "build_seed_access", lambda workspace_root=None: DummySeedAccess()
    )

    _set_argv(monkeypatch, "seed", "control", "start")
    with pytest.raises(SystemExit) as exc_info:
        merlin_cli.main()

    assert exc_info.value.code == 1
    assert "bad seed action" in capsys.readouterr().err


def test_seed_cli_health_uses_native_seed_access(monkeypatch, capsys):
    workspace_roots: list[str | None] = []

    class DummySeedAccess:
        def __init__(self):
            self.health_calls = []

        def health(self, **kwargs):
            self.health_calls.append(kwargs)
            return {
                "schema_name": "AAS.Merlin.SeedHealth",
                "state": "attention",
                "recommended_control_action": "start",
            }

    dummy = DummySeedAccess()
    monkeypatch.setattr(
        merlin_cli,
        "build_seed_access",
        lambda workspace_root=None: workspace_roots.append(workspace_root) or dummy,
    )

    _set_argv(
        monkeypatch,
        "seed",
        "health",
        "--workspace-root",
        "/tmp/seed-workspace",
        "--status-file",
        "artifacts/custom_seed_status.json",
        "--stale-after-seconds",
        "1200",
        "--allow-live-automation",
    )
    merlin_cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_name"] == "AAS.Merlin.SeedHealth"
    assert payload["recommended_control_action"] == "start"
    assert workspace_roots == ["/tmp/seed-workspace"]
    assert len(dummy.health_calls) == 1
    call = dummy.health_calls[0]
    assert call["status_file"] == "artifacts/custom_seed_status.json"
    assert call["stale_after_seconds"] == 1200.0
    assert call["allow_live_automation"] is True


def test_seed_cli_heartbeat_uses_native_seed_access(monkeypatch, capsys):
    workspace_roots: list[str | None] = []

    class DummySeedAccess:
        def __init__(self):
            self.heartbeat_calls = []

        def heartbeat(self, **kwargs):
            self.heartbeat_calls.append(kwargs)
            return {
                "schema_name": "AAS.Merlin.SeedHealthHeartbeat",
                "event_type": "merlin.seed.health.heartbeat",
                "persisted": False,
            }

    dummy = DummySeedAccess()
    monkeypatch.setattr(
        merlin_cli,
        "build_seed_access",
        lambda workspace_root=None: workspace_roots.append(workspace_root) or dummy,
    )

    _set_argv(
        monkeypatch,
        "seed",
        "heartbeat",
        "--workspace-root",
        "/tmp/seed-workspace",
        "--status-file",
        "artifacts/custom_seed_status.json",
        "--stale-after-seconds",
        "900",
        "--heartbeat-file",
        "artifacts/diagnostics/custom_heartbeat.jsonl",
        "--no-write-event",
        "--allow-live-automation",
    )
    merlin_cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_name"] == "AAS.Merlin.SeedHealthHeartbeat"
    assert payload["persisted"] is False
    assert workspace_roots == ["/tmp/seed-workspace"]
    assert len(dummy.heartbeat_calls) == 1
    call = dummy.heartbeat_calls[0]
    assert call["status_file"] == "artifacts/custom_seed_status.json"
    assert call["stale_after_seconds"] == 900.0
    assert call["heartbeat_file"] == "artifacts/diagnostics/custom_heartbeat.jsonl"
    assert call["write_event"] is False
    assert call["allow_live_automation"] is True


def test_seed_cli_watchdog_uses_native_seed_access(monkeypatch, capsys):
    workspace_roots: list[str | None] = []

    class DummySeedAccess:
        def __init__(self):
            self.watchdog_calls = []

        def watchdog(self, **kwargs):
            self.watchdog_calls.append(kwargs)
            return {
                "schema_name": "AAS.Merlin.SeedWatchdogTick",
                "decision": {"outcome_status": "preview"},
            }

    dummy = DummySeedAccess()
    monkeypatch.setattr(
        merlin_cli,
        "build_seed_access",
        lambda workspace_root=None: workspace_roots.append(workspace_root) or dummy,
    )

    _set_argv(
        monkeypatch,
        "seed",
        "watchdog",
        "--workspace-root",
        "/tmp/seed-workspace",
        "--status-file",
        "artifacts/custom_seed_status.json",
        "--stale-after-seconds",
        "600",
        "--apply",
        "--force",
        "--dry-run-control",
        "--allow-live-automation",
    )
    merlin_cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_name"] == "AAS.Merlin.SeedWatchdogTick"
    assert payload["decision"]["outcome_status"] == "preview"
    assert workspace_roots == ["/tmp/seed-workspace"]
    assert len(dummy.watchdog_calls) == 1
    call = dummy.watchdog_calls[0]
    assert call["status_file"] == "artifacts/custom_seed_status.json"
    assert call["stale_after_seconds"] == 600.0
    assert call["apply"] is True
    assert call["force"] is True
    assert call["dry_run_control"] is True
    assert call["allow_live_automation"] is True


def test_seed_cli_watchdog_runtime_status_uses_native_seed_access(monkeypatch, capsys):
    workspace_roots: list[str | None] = []

    class DummySeedAccess:
        def __init__(self):
            self.status_calls = []

        def watchdog_runtime_status(self, **kwargs):
            self.status_calls.append(kwargs)
            return {
                "schema_name": "AAS.Merlin.SeedWatchdogRuntimeStatus",
                "process": {"active": False, "count": 0},
            }

    dummy = DummySeedAccess()
    monkeypatch.setattr(
        merlin_cli,
        "build_seed_access",
        lambda workspace_root=None: workspace_roots.append(workspace_root) or dummy,
    )

    _set_argv(
        monkeypatch,
        "seed",
        "watchdog-runtime",
        "status",
        "--workspace-root",
        "/tmp/seed-workspace",
        "--watchdog-log-file",
        "logs/custom_watchdog_runtime.log",
        "--append-jsonl",
        "artifacts/diagnostics/custom_watchdog_ticks.jsonl",
        "--stale-after-seconds",
        "1200",
        "--allow-live-automation",
    )
    merlin_cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_name"] == "AAS.Merlin.SeedWatchdogRuntimeStatus"
    assert workspace_roots == ["/tmp/seed-workspace"]
    assert len(dummy.status_calls) == 1
    call = dummy.status_calls[0]
    assert call["watchdog_log_file"] == "logs/custom_watchdog_runtime.log"
    assert call["append_jsonl"] == "artifacts/diagnostics/custom_watchdog_ticks.jsonl"
    assert call["stale_after_seconds"] == 1200.0
    assert call["allow_live_automation"] is True


def test_seed_cli_watchdog_runtime_control_uses_native_seed_access(
    monkeypatch, capsys
):
    workspace_roots: list[str | None] = []

    class DummySeedAccess:
        def __init__(self):
            self.control_calls = []

        def watchdog_runtime_control(self, **kwargs):
            self.control_calls.append(kwargs)
            return {
                "schema_name": "AAS.Merlin.SeedWatchdogRuntimeControl",
                "decision": "allowed",
                "status": "preview",
            }

    dummy = DummySeedAccess()
    monkeypatch.setattr(
        merlin_cli,
        "build_seed_access",
        lambda workspace_root=None: workspace_roots.append(workspace_root) or dummy,
    )

    _set_argv(
        monkeypatch,
        "seed",
        "watchdog-runtime",
        "control",
        "start",
        "--workspace-root",
        "/tmp/seed-workspace",
        "--dry-run",
        "--force",
        "--apply",
        "--dry-run-control",
        "--interval-seconds",
        "5",
        "--max-iterations",
        "0",
        "--no-heartbeat",
        "--allow-live-automation",
    )
    merlin_cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_name"] == "AAS.Merlin.SeedWatchdogRuntimeControl"
    assert payload["status"] == "preview"
    assert workspace_roots == ["/tmp/seed-workspace"]
    assert len(dummy.control_calls) == 1
    call = dummy.control_calls[0]
    assert call["action"] == "start"
    assert call["dry_run"] is True
    assert call["force"] is True
    assert call["apply"] is True
    assert call["dry_run_control"] is True
    assert call["interval_seconds"] == 5.0
    assert call["max_iterations"] == 0
    assert call["emit_heartbeat"] is False
    assert call["allow_live_automation"] is True
