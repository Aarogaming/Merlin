from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        check=False,
        text=True,
        capture_output=True,
    )


def test_agent_protocol_startup_handshake_scripts_succeed(tmp_path: Path):
    commands = [
        ["bash", "scripts/workspace/preflight_scope.sh", "-SkipApplyProfile"],
        ["bash", "scripts/agentic_health.sh", "-Quiet"],
        ["bash", "scripts/agentic_runtime_report.sh", "-Quiet"],
        ["bash", "scripts/check_guild_guardrails.sh"],
        [
            "bash",
            "scripts/check_governance_guardrails.sh",
            "--emit-json",
            str(tmp_path / "governance_guardrails_status.json"),
        ],
    ]

    for command in commands:
        result = _run(command)
        assert result.returncode == 0, (
            f"command failed: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}\n"
        )
