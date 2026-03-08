from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]


def _run_smoke(*, env_overrides: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()

    def _to_bash_path(value: str) -> str:
        normalized = value.replace("\\", "/")
        if len(normalized) >= 3 and normalized[1:3] == ":/" and normalized[0].isalpha():
            drive = normalized[0].lower()
            return f"/mnt/{drive}/{normalized[3:]}"
        return normalized

    normalized_overrides = {
        key: _to_bash_path(value)
        if key.endswith("_PATH") or key.endswith("_DIR") or key.endswith("_XML")
        else value
        for key, value in env_overrides.items()
    }

    env_assignments = " ".join(
        f"{key}={shlex.quote(value)}" for key, value in normalized_overrides.items()
    )
    command = f"{env_assignments} bash scripts/smoke_planner_fallback_runbook.sh".strip()
    return subprocess.run(
        ["bash", "-lc", command],
        cwd=ROOT_DIR,
        env=env,
        check=False,
        text=True,
        capture_output=True,
    )


def test_smoke_runbook_fails_fast_on_malformed_baseline(tmp_path: Path):
    baseline_path = tmp_path / "bad-baseline.json"
    baseline_path.write_text('{"planner_expected_tests":"bad"}\n', encoding="utf-8")
    artifact_dir = tmp_path / "artifacts"

    result = _run_smoke(
        env_overrides={
            "CP4A_SMOKE_BASELINE_PATH": str(baseline_path),
            "PLANNER_FALLBACK_ARTIFACT_DIR": str(artifact_dir),
        }
    )

    assert result.returncode == 1
    assert "baseline field 'planner_expected_tests' must be an integer" in result.stderr
    assert "test session starts" not in result.stdout
    assert not (artifact_dir / "planner-fallback-junit.xml").exists()
    assert not (artifact_dir / "cp4a-schema-junit.xml").exists()


def test_smoke_runbook_fails_fast_when_baseline_file_is_missing(tmp_path: Path):
    missing_baseline = tmp_path / "missing-baseline.json"
    artifact_dir = tmp_path / "artifacts"

    result = _run_smoke(
        env_overrides={
            "CP4A_SMOKE_BASELINE_PATH": str(missing_baseline),
            "PLANNER_FALLBACK_ARTIFACT_DIR": str(artifact_dir),
        }
    )

    assert result.returncode == 1
    assert "baseline file not found:" in result.stderr
    assert "missing-baseline.json" in result.stderr
    assert "test session starts" not in result.stdout
    assert not (artifact_dir / "planner-fallback-junit.xml").exists()
    assert not (artifact_dir / "cp4a-schema-junit.xml").exists()


def test_smoke_runbook_fails_on_planner_expected_total_mismatch(tmp_path: Path):
    artifact_dir = tmp_path / "artifacts"

    result = _run_smoke(
        env_overrides={
            "PLANNER_EXPECTED_TESTS": "999",
            "PLANNER_FALLBACK_ARTIFACT_DIR": str(artifact_dir),
        }
    )

    assert result.returncode == 1
    assert "planner: tests=" in result.stdout
    assert "planner: expected exactly 999 tests, got " in result.stdout
    assert "schema: tests=" not in result.stdout
    assert "smoke log signatures verified" not in result.stdout


def test_smoke_runbook_fails_on_missing_taxonomy_signature(tmp_path: Path):
    artifact_dir = tmp_path / "artifacts"

    result = _run_smoke(
        env_overrides={
            "TAXONOMY_EXPECTED_SUMMARY": "__missing_taxonomy_signature__",
            "PLANNER_FALLBACK_ARTIFACT_DIR": str(artifact_dir),
        }
    )

    assert result.returncode == 1
    assert "planner: tests=" in result.stdout
    assert "schema: tests=" in result.stdout
    assert "smoke log signature check failed:" in result.stdout
    assert "missing summary signature: __missing_taxonomy_signature__" in result.stdout
    assert "cp4a smoke evidence status: pass" not in result.stdout
