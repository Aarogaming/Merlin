from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "check_vector_memory_integrity.py"
)


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(SCRIPT_PATH), *args]
    return subprocess.run(command, check=False, text=True, capture_output=True)


def _write_memory_file(path: Path, entries: list[dict]) -> None:
    path.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def test_check_vector_memory_integrity_passes_for_valid_file(tmp_path: Path):
    storage_file = tmp_path / "memory.json"
    _write_memory_file(
        storage_file,
        [
            {"text": "alpha", "metadata": {"path": "a"}, "timestamp": 10.0},
            {"text": "beta", "metadata": {"path": "b"}, "timestamp": 20.0},
        ],
    )

    result = _run_script("--storage-file", str(storage_file))

    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report["invalid_entries"] == 0
    assert report["duplicate_entries"] == 0


def test_check_vector_memory_integrity_fails_when_duplicates_exceed_budget(
    tmp_path: Path,
):
    storage_file = tmp_path / "memory.json"
    _write_memory_file(
        storage_file,
        [
            {"text": "alpha", "metadata": {"path": "a"}, "timestamp": 10.0},
            {"text": "alpha", "metadata": {"path": "a"}, "timestamp": 11.0},
        ],
    )

    result = _run_script("--storage-file", str(storage_file))

    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["duplicate_entries"] == 1


def test_check_vector_memory_integrity_compact_mode_clears_duplicates(
    tmp_path: Path,
):
    storage_file = tmp_path / "memory.json"
    _write_memory_file(
        storage_file,
        [
            {"text": "alpha", "metadata": {"path": "a"}, "timestamp": 10.0},
            {"text": "alpha", "metadata": {"path": "a"}, "timestamp": 11.0},
        ],
    )

    result = _run_script("--storage-file", str(storage_file), "--compact")

    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report["duplicate_entries"] == 0
