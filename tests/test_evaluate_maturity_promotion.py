from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "evaluate_maturity_promotion.py"
)


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        check=False,
        text=True,
        capture_output=True,
    )


def test_maturity_evaluator_recommends_promotion_when_gates_pass(tmp_path: Path):
    release_report = tmp_path / "release_checklist.json"
    smoke_report = tmp_path / "smoke_evidence.json"
    output_path = tmp_path / "maturity_eval.json"

    release_report.write_text(
        json.dumps({"summary": {"ok": True}}, indent=2) + "\n",
        encoding="utf-8",
    )
    smoke_report.write_text(
        json.dumps({"status": "pass"}, indent=2) + "\n",
        encoding="utf-8",
    )

    result = _run(
        "--current-tier",
        "M1",
        "--contract-suite-status",
        "pass",
        "--release-checklist-report",
        str(release_report),
        "--smoke-evidence-report",
        str(smoke_report),
        "--fallback-error-rate",
        "0.01",
        "--max-fallback-error-rate",
        "0.05",
        "--strict",
        "--output-json",
        str(output_path),
    )

    assert result.returncode == 0
    assert "recommended_action: promote" in result.stdout
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["recommended_action"] == "promote"
    assert payload["recommended_tier"] == "M2"
    assert payload["summary"]["promotion_ready"] is True
    assert payload["summary"]["demotion_required"] is False


def test_maturity_evaluator_recommends_demotion_on_error_budget_breach(tmp_path: Path):
    release_report = tmp_path / "release_checklist.json"
    smoke_report = tmp_path / "smoke_evidence.json"
    output_path = tmp_path / "maturity_eval_demotion.json"

    release_report.write_text(
        json.dumps({"summary": {"ok": True}}, indent=2) + "\n",
        encoding="utf-8",
    )
    smoke_report.write_text(
        json.dumps({"status": "pass"}, indent=2) + "\n",
        encoding="utf-8",
    )

    result = _run(
        "--current-tier",
        "M3",
        "--contract-suite-status",
        "pass",
        "--release-checklist-report",
        str(release_report),
        "--smoke-evidence-report",
        str(smoke_report),
        "--error-budget-breached",
        "--strict",
        "--output-json",
        str(output_path),
    )

    assert result.returncode == 1
    assert "recommended_action: demote" in result.stdout
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["recommended_action"] == "demote"
    assert payload["recommended_tier"] == "M2"
    assert payload["summary"]["demotion_required"] is True
    assert "error budget breached" in payload["rationale"]


def test_maturity_evaluator_holds_when_required_evidence_missing(tmp_path: Path):
    output_path = tmp_path / "maturity_eval_hold.json"

    result = _run(
        "--current-tier",
        "M1",
        "--contract-suite-status",
        "unknown",
        "--output-json",
        str(output_path),
    )

    assert result.returncode == 0
    assert "recommended_action: hold" in result.stdout
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["recommended_action"] == "hold"
    assert payload["recommended_tier"] == "M1"
    assert payload["summary"]["promotion_ready"] is False
    assert payload["summary"]["demotion_required"] is False
