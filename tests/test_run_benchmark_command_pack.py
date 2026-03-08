from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "run_benchmark_command_pack.py"
)


def test_benchmark_command_pack_dry_run_writes_plan(tmp_path: Path):
    output_path = tmp_path / "benchmark_plan.json"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--dry-run",
            "--output-json",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["mode"] == "dry_run"
    assert payload["summary"]["total"] >= 2
    assert payload["results"][0]["executed"] is False
    assert any(item["command_id"] == "python_version" for item in payload["results"])


def test_benchmark_command_pack_execute_single_command(tmp_path: Path):
    output_path = tmp_path / "benchmark_exec.json"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--execute",
            "--only",
            "python_version",
            "--output-json",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["mode"] == "execute"
    assert payload["summary"]["executed"] == 1
    assert payload["summary"]["failed"] == 0
    assert payload["results"][0]["command_id"] == "python_version"
    assert payload["results"][0]["ok"] is True
