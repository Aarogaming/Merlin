from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "run_merlin_seed_watchdog.py"
)


def test_seed_watchdog_script_preview_mode_writes_report(tmp_path: Path):
    output_path = tmp_path / "seed_watchdog_report.json"
    append_path = tmp_path / "seed_watchdog_ticks.jsonl"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--workspace-root",
            str(tmp_path),
            "--allow-live-automation",
            "--max-iterations",
            "1",
            "--interval-seconds",
            "0",
            "--no-heartbeat",
            "--append-jsonl",
            str(append_path),
            "--output-json",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["schema_name"] == "AAS.Merlin.SeedWatchdogLoopResult"
    assert payload["summary"]["total_ticks"] == 1
    assert payload["summary"]["error"] == 0
    assert append_path.exists()
    assert len(append_path.read_text(encoding="utf-8").strip().splitlines()) == 1


def test_seed_watchdog_script_apply_mode_returns_nonzero_when_policy_blocked(
    tmp_path: Path,
):
    output_path = tmp_path / "seed_watchdog_report_blocked.json"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--workspace-root",
            str(tmp_path),
            "--apply",
            "--no-live-automation",
            "--max-iterations",
            "1",
            "--interval-seconds",
            "0",
            "--no-heartbeat",
            "--output-json",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 3
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["mode"]["apply"] is True
    assert payload["summary"]["blocked"] >= 1
