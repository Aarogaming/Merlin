from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "generate_dependency_audit_report.py"
)


def test_generate_dependency_audit_report_with_findings(tmp_path: Path):
    audit_json = tmp_path / "audit.json"
    report_md = tmp_path / "report.md"
    audit_json.write_text(
        json.dumps(
            [
                {
                    "name": "example-lib",
                    "version": "1.0.0",
                    "vulns": [
                        {
                            "id": "PYSEC-2026-0001",
                            "fix_versions": ["1.0.1"],
                            "description": "sample vulnerability",
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--audit-json",
            str(audit_json),
            "--output",
            str(report_md),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    text = report_md.read_text(encoding="utf-8")
    assert "PYSEC-2026-0001" in text
    assert "`example-lib`" in text


def test_generate_dependency_audit_report_strict_mode_fails_on_findings(tmp_path: Path):
    audit_json = tmp_path / "audit.json"
    report_md = tmp_path / "report.md"
    audit_json.write_text(
        json.dumps(
            [
                {
                    "name": "example-lib",
                    "version": "1.0.0",
                    "vulns": [{"id": "PYSEC-2026-0001", "fix_versions": []}],
                }
            ]
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--audit-json",
            str(audit_json),
            "--output",
            str(report_md),
            "--strict",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1


def test_generate_dependency_audit_report_strict_mode_passes_without_findings(
    tmp_path: Path,
):
    audit_json = tmp_path / "audit.json"
    report_md = tmp_path / "report.md"
    audit_json.write_text(json.dumps([]), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--audit-json",
            str(audit_json),
            "--output",
            str(report_md),
            "--strict",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "No vulnerabilities reported" in report_md.read_text(encoding="utf-8")
