from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "frontend" / "scripts" / "check-dist-size.js"
)
NODE_BIN = shutil.which("node")


@pytest.mark.skipif(NODE_BIN is None, reason="node binary is required for frontend bundle checks")
def test_dist_size_check_passes_for_small_bundle(tmp_path: Path):
    dist_assets = tmp_path / "dist" / "assets"
    dist_assets.mkdir(parents=True, exist_ok=True)
    (dist_assets / "bundle.js").write_bytes(b"x" * 1024)
    (dist_assets / "bundle.css").write_bytes(b"y" * 512)

    report_path = tmp_path / "frontend-dist-size-report.json"
    env = {
        **os.environ,
        "MERLIN_FRONTEND_DIST_SIZE_REPORT": str(report_path),
        "MERLIN_FRONTEND_BUNDLE_MAX_TOTAL_MB": "1",
        "MERLIN_FRONTEND_BUNDLE_MAX_FILE_MB": "1",
        "MERLIN_FRONTEND_BUNDLE_MAX_JS_MB": "1",
        "MERLIN_FRONTEND_BUNDLE_MAX_CSS_MB": "1",
    }
    result = subprocess.run(
        [NODE_BIN, str(SCRIPT_PATH)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["status"] == "passed"
    assert payload["violations"] == []


@pytest.mark.skipif(NODE_BIN is None, reason="node binary is required for frontend bundle checks")
def test_dist_size_check_fails_for_large_bundle(tmp_path: Path):
    dist_assets = tmp_path / "dist" / "assets"
    dist_assets.mkdir(parents=True, exist_ok=True)
    (dist_assets / "bundle.js").write_bytes(b"x" * (2 * 1024 * 1024))
    (dist_assets / "bundle.css").write_bytes(b"y" * 1024)

    report_path = tmp_path / "frontend-dist-size-report.json"
    env = {
        **os.environ,
        "MERLIN_FRONTEND_DIST_SIZE_REPORT": str(report_path),
        "MERLIN_FRONTEND_BUNDLE_MAX_TOTAL_MB": "1",
        "MERLIN_FRONTEND_BUNDLE_MAX_FILE_MB": "1",
        "MERLIN_FRONTEND_BUNDLE_MAX_JS_MB": "1",
        "MERLIN_FRONTEND_BUNDLE_MAX_CSS_MB": "1",
    }
    result = subprocess.run(
        [NODE_BIN, str(SCRIPT_PATH)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["violations"]
