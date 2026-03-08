from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "generate_frontend_operation_contracts.py"
)


def test_generate_frontend_operation_contracts_writes_typed_mapping(tmp_path: Path):
    output_path = tmp_path / "operationContracts.generated.ts"
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--output", str(output_path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    generated = output_path.read_text(encoding="utf-8")
    assert "export type OperationName" in generated
    assert "'merlin.research.manager.session.create'" in generated
    assert "tests/fixtures/contracts/assistant.chat.request.json" in generated


def test_generate_frontend_operation_contracts_check_mode_detects_drift(tmp_path: Path):
    output_path = tmp_path / "operationContracts.generated.ts"
    subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--output", str(output_path)],
        check=True,
        capture_output=True,
        text=True,
    )

    up_to_date = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--output", str(output_path), "--check"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert up_to_date.returncode == 0

    output_path.write_text("// stale\n", encoding="utf-8")
    stale_result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--output", str(output_path), "--check"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert stale_result.returncode == 1
