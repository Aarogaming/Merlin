from __future__ import annotations

import argparse
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class CommitEntry:
    commit_hash: str
    date: str
    subject: str


def _run_git(args: list[str]) -> str:
    output = subprocess.check_output(
        ["git", *args],
        text=True,
        stderr=subprocess.DEVNULL,
    )
    return output.strip()


def _latest_tag() -> str | None:
    try:
        tag = _run_git(["describe", "--tags", "--abbrev=0"])
    except Exception:
        return None
    return tag if tag else None


def _read_commits(range_spec: str, max_count: int = 200) -> list[CommitEntry]:
    output = _run_git(
        [
            "log",
            "--date=short",
            f"--max-count={max_count}",
            "--pretty=format:%H%x1f%ad%x1f%s",
            range_spec,
        ]
    )
    if not output:
        return []
    commits: list[CommitEntry] = []
    for line in output.splitlines():
        parts = line.split("\x1f")
        if len(parts) != 3:
            continue
        commits.append(
            CommitEntry(
                commit_hash=parts[0],
                date=parts[1],
                subject=parts[2],
            )
        )
    return commits


def generate_changelog_markdown(
    *,
    from_tag: str | None,
    to_ref: str,
    commits: list[CommitEntry],
) -> str:
    lines = [
        "# Changelog (Generated from Git Tags)",
        "",
        f"- generated_at_utc: {datetime.now(timezone.utc).isoformat()}",
        f"- from: `{from_tag or 'repo_start'}`",
        f"- to: `{to_ref}`",
        f"- commit_count: `{len(commits)}`",
        "",
    ]
    if not commits:
        lines.append("No commits found for selected range.")
        lines.append("")
        return "\n".join(lines)

    lines.extend(["## Commits", ""])
    for entry in commits:
        short_hash = entry.commit_hash[:8]
        lines.append(f"- `{entry.date}` `{short_hash}` {entry.subject}")
    lines.append("")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate markdown changelog from git tags and commit history."
    )
    parser.add_argument(
        "--from-tag",
        default=None,
        help="Optional start tag (defaults to latest reachable tag).",
    )
    parser.add_argument(
        "--to-ref",
        default="HEAD",
        help="End git ref for changelog range (default: HEAD).",
    )
    parser.add_argument(
        "--max-count",
        type=int,
        default=200,
        help="Maximum number of commits to include (default: 200).",
    )
    parser.add_argument(
        "--output",
        default="artifacts/changelog/changelog-from-tags.md",
        help="Output markdown path.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    from_tag = args.from_tag or _latest_tag()
    if from_tag:
        range_spec = f"{from_tag}..{args.to_ref}"
    else:
        range_spec = args.to_ref

    commits = _read_commits(range_spec, max_count=max(1, int(args.max_count)))
    changelog = generate_changelog_markdown(
        from_tag=from_tag,
        to_ref=args.to_ref,
        commits=commits,
    )
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(changelog, encoding="utf-8")
    print(f"wrote changelog: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
