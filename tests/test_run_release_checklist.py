from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_release_checklist.py"


def test_release_checklist_strict_passes_with_path_checks(tmp_path: Path):
    output_path = tmp_path / "release_checklist.json"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--strict",
            "--output-json",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["summary"]["failed_required"] == 0
    assert payload["summary"]["ok"] is True


def test_release_checklist_can_run_optional_commands(tmp_path: Path):
    output_path = tmp_path / "release_checklist_commands.json"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--run-commands",
            "--strict",
            "--output-json",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["run_commands"] is True
    assert payload["summary"]["failed_required"] == 0
    assert payload["command_results"]
    command_labels = [" ".join(entry["command"]) for entry in payload["command_results"]]
    assert any(
        "scripts/evaluate_maturity_promotion.py" in label for label in command_labels
    )
    maturity_reports = list(tmp_path.glob("maturity_evaluator_*.json"))
    assert maturity_reports
    maturity_payload = json.loads(maturity_reports[-1].read_text(encoding="utf-8"))
    assert maturity_payload["schema_name"] == "AAS.MaturityPromotionDemotionReport"
