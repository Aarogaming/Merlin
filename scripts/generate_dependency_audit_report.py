#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _normalize_findings(payload: Any) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if not isinstance(payload, list):
        return findings
    for dependency in payload:
        if not isinstance(dependency, dict):
            continue
        name = str(dependency.get("name", "unknown"))
        version = str(dependency.get("version", "unknown"))
        vulnerabilities = dependency.get("vulns") or dependency.get("vulnerabilities") or []
        if not isinstance(vulnerabilities, list):
            continue
        for vuln in vulnerabilities:
            if not isinstance(vuln, dict):
                continue
            findings.append(
                {
                    "dependency": name,
                    "version": version,
                    "id": vuln.get("id", "unknown"),
                    "fix_versions": vuln.get("fix_versions", []),
                    "description": vuln.get("description", ""),
                }
            )
    return findings


def _render_markdown(
    *,
    audit_json_path: Path,
    findings: list[dict[str, Any]],
) -> str:
    lines = [
        "# Dependency Vulnerability Audit Report",
        "",
        f"- generated_at_utc: {datetime.now(timezone.utc).isoformat()}",
        f"- source_json: `{audit_json_path}`",
        f"- finding_count: `{len(findings)}`",
        "",
    ]
    if not findings:
        lines.append("No vulnerabilities reported by `pip-audit`.")
        lines.append("")
        return "\n".join(lines)

    lines.extend(
        [
            "## Findings",
            "",
            "| Dependency | Version | Vulnerability | Fix Versions |",
            "| --- | --- | --- | --- |",
        ]
    )
    for finding in findings:
        fix_versions = ", ".join(str(item) for item in finding.get("fix_versions", []))
        lines.append(
            f"| `{finding['dependency']}` | `{finding['version']}` | `{finding['id']}` | `{fix_versions}` |"
        )
    lines.append("")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate markdown summary from pip-audit JSON output."
    )
    parser.add_argument(
        "--audit-json",
        required=True,
        help="Path to pip-audit JSON output file.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Markdown report output path.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any vulnerabilities are found.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    audit_json_path = Path(args.audit_json)
    output_path = Path(args.output)

    payload = _load_json(audit_json_path)
    findings = _normalize_findings(payload)
    markdown = _render_markdown(audit_json_path=audit_json_path, findings=findings)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    print(f"wrote dependency audit report: {output_path}")
    print(f"findings: {len(findings)}")

    if args.strict and findings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
