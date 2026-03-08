from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "chimera_v2_cp6_gate_rescore.py"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        text=True,
        capture_output=True,
    )


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _base_matrix() -> dict[str, object]:
    return {
        "cycle_id": "CHIMERA-V2-RESEARCH-AND-EXECUTION-2026-02-15",
        "phase": "CP6 Cross-Repo Orchestration Wave",
        "generated_on": "2026-02-18",
        "repos": [
            {
                "repo": "ANDROIDAPP",
                "six_block": True,
                "success_flow": True,
                "expected_failure_branch": True,
                "artifact_present": True,
                "live_probe": False,
                "live_chain_proof": False,
                "gate_verdict": "CONDITIONAL_PASS",
                "blocking_reasons": ["missing live proof"],
            }
        ],
        "summary": {
            "pass": 0,
            "conditional_pass": 1,
            "fail": 0,
            "total": 1,
        },
    }


def test_rescore_upgrades_conditional_to_pass_when_live_proof_arrives(tmp_path: Path):
    matrix_path = tmp_path / "matrix.json"
    intake_path = tmp_path / "intake.json"

    _write_json(matrix_path, _base_matrix())
    _write_json(
        intake_path,
        {
            "repos": [
                {
                    "repo": "ANDROIDAPP",
                    "live_probe": True,
                    "live_chain_proof": True,
                    "notes": ["live chain completed"],
                }
            ]
        },
    )

    result = _run("--matrix", str(matrix_path), "--intake", str(intake_path))

    assert result.returncode == 0
    payload = json.loads(matrix_path.read_text(encoding="utf-8"))
    entry = payload["repos"][0]
    assert entry["gate_verdict"] == "PASS"
    assert entry["blocking_reasons"] == []
    assert payload["summary"] == {
        "pass": 1,
        "conditional_pass": 0,
        "fail": 0,
        "total": 1,
    }


def test_rescore_yields_conditional_when_base_ready_but_live_missing(tmp_path: Path):
    matrix_path = tmp_path / "matrix.json"
    intake_path = tmp_path / "intake.json"

    _write_json(
        matrix_path,
        {
            "cycle_id": "id",
            "phase": "phase",
            "generated_on": "2026-02-18",
            "repos": [
                {
                    "repo": "MYFORTRESS",
                    "six_block": False,
                    "success_flow": False,
                    "expected_failure_branch": False,
                    "artifact_present": False,
                    "live_probe": False,
                    "live_chain_proof": False,
                    "gate_verdict": "FAIL",
                    "blocking_reasons": [],
                }
            ],
        },
    )

    _write_json(
        intake_path,
        {
            "repo": "MYFORTRESS",
            "six_block": True,
            "success_flow": True,
            "expected_failure_branch": True,
            "artifact_present": True,
            "live_probe": False,
            "live_chain_proof": False,
        },
    )

    result = _run("--matrix", str(matrix_path), "--intake", str(intake_path))

    assert result.returncode == 0
    payload = json.loads(matrix_path.read_text(encoding="utf-8"))
    entry = payload["repos"][0]
    assert entry["gate_verdict"] == "CONDITIONAL_PASS"
    assert "Live Merlin capability probe has not passed yet." in entry["blocking_reasons"]
    assert "Live create->signal->brief proof is missing." in entry["blocking_reasons"]
    assert payload["summary"] == {
        "pass": 0,
        "conditional_pass": 1,
        "fail": 0,
        "total": 1,
    }


def test_rescore_keeps_fail_when_required_base_criteria_missing(tmp_path: Path):
    matrix_path = tmp_path / "matrix.json"
    intake_path = tmp_path / "intake.json"

    _write_json(matrix_path, _base_matrix())
    _write_json(
        intake_path,
        [
            {
                "repo": "ANDROIDAPP",
                "artifact_present": False,
                "live_probe": True,
                "live_chain_proof": True,
            }
        ],
    )

    result = _run("--matrix", str(matrix_path), "--intake", str(intake_path))

    assert result.returncode == 0
    payload = json.loads(matrix_path.read_text(encoding="utf-8"))
    entry = payload["repos"][0]
    assert entry["gate_verdict"] == "FAIL"
    assert "Missing required CP6 artifact in repo-local docs/research path." in entry[
        "blocking_reasons"
    ]
    assert payload["summary"] == {
        "pass": 0,
        "conditional_pass": 0,
        "fail": 1,
        "total": 1,
    }
