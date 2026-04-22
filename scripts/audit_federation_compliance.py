import argparse
import json
from datetime import datetime, UTC
from pathlib import Path

from validate_agent_artifacts import validate_repo


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = ROOT.parent
DEFAULT_REPOS = [
    "AaroneousAutomationSuite",
    "Guild",
    "Library",
    "Maelstrom",
    "Merlin",
    "MyFortress",
    "Workbench",
]


def _discover_repos() -> list[Path]:
    repos: list[Path] = []
    for name in DEFAULT_REPOS:
        path = WORKSPACE_ROOT / name
        if path.exists() and path.is_dir():
            repos.append(path)
    return repos


def _resolve_repo_paths(workspace_root: Path, repo_names: list[str]) -> tuple[list[Path], list[str]]:
    found: list[Path] = []
    missing: list[str] = []
    for name in repo_names:
        path = workspace_root / name
        if path.exists() and path.is_dir():
            found.append(path)
        else:
            missing.append(name)
    return found, missing


def _status_from_errors(errors: list[str]) -> str:
    return "pass" if not errors else "fail"


def _write_markdown_report(report_path: Path, rows: list[dict], generated_at: str):
    lines = []
    lines.append("# Federation Compliance Report")
    lines.append("")
    lines.append(f"Generated at: `{generated_at}`")
    lines.append("")
    lines.append("| Repo | Status | Error Count |")
    lines.append("| --- | --- | ---: |")
    for row in rows:
        lines.append(f"| {row['repo']} | {row['status']} | {len(row['errors'])} |")

    lines.append("")
    lines.append("## Details")
    lines.append("")
    for row in rows:
        lines.append(f"### {row['repo']}")
        lines.append(f"- Status: `{row['status']}`")
        if row["errors"]:
            lines.append("- Errors:")
            for err in row["errors"]:
                lines.append(f"  - {err}")
        else:
            lines.append("- Errors: none")
        lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")


def run_audit(
    output_dir: Path,
    workspace_root: Path,
    repo_names: list[str],
    strict_repo_presence: bool,
) -> tuple[Path, Path, int]:
    repos, missing_repos = _resolve_repo_paths(workspace_root, repo_names)
    generated_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    rows = []
    failure_count = 0
    for repo_path in repos:
        errors = validate_repo(repo_path)
        status = _status_from_errors(errors)
        if status == "fail":
            failure_count += 1
        rows.append(
            {
                "repo": repo_path.name,
                "path": str(repo_path),
                "status": status,
                "errors": errors,
            }
        )

    if strict_repo_presence:
        for name in missing_repos:
            failure_count += 1
            rows.append(
                {
                    "repo": name,
                    "path": str((workspace_root / name).resolve()),
                    "status": "fail",
                    "errors": [f"Repository directory not found: {name}"],
                }
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"federation_compliance_{stamp}.json"
    md_path = output_dir / f"federation_compliance_{stamp}.md"

    payload = {
        "generated_at_utc": generated_at,
        "workspace_root": str(workspace_root),
        "repos_checked": [r["repo"] for r in rows],
        "strict_repo_presence": strict_repo_presence,
        "summary": {
            "total": len(rows),
            "passed": len([r for r in rows if r["status"] == "pass"]),
            "failed": len([r for r in rows if r["status"] == "fail"]),
        },
        "results": rows,
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    _write_markdown_report(md_path, rows, generated_at)
    return json_path, md_path, failure_count


def main():
    parser = argparse.ArgumentParser(description="Run federation artifact compliance audit.")
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "artifacts" / "compliance"),
        help="Directory to write compliance reports",
    )
    parser.add_argument(
        "--workspace-root",
        default=str(WORKSPACE_ROOT),
        help="Workspace root containing federation repos",
    )
    parser.add_argument(
        "--repos",
        default=",".join(DEFAULT_REPOS),
        help="Comma-separated repo names to audit",
    )
    parser.add_argument(
        "--strict-repo-presence",
        action="store_true",
        help="Fail when requested repo directories are missing",
    )
    parser.add_argument(
        "--no-fail-on-issues",
        action="store_true",
        help="Always exit 0 even if compliance issues are found",
    )
    args = parser.parse_args()

    repo_names = [name.strip() for name in args.repos.split(",") if name.strip()]
    json_path, md_path, failures = run_audit(
        output_dir=Path(args.output_dir).resolve(),
        workspace_root=Path(args.workspace_root).resolve(),
        repo_names=repo_names,
        strict_repo_presence=args.strict_repo_presence,
    )
    print(f"Compliance JSON: {json_path}")
    print(f"Compliance MD: {md_path}")
    if failures > 0 and not args.no_fail_on_issues:
        print(f"Federation compliance failures: {failures}")
        raise SystemExit(1)
    if failures > 0:
        print(f"Federation compliance issues found (non-blocking): {failures}")
    else:
        print("Federation compliance audit passed.")


if __name__ == "__main__":
    main()
