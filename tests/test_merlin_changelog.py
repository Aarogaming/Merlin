from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from merlin_changelog import CommitEntry, generate_changelog_markdown


def test_generate_changelog_markdown_renders_commit_rows():
    markdown = generate_changelog_markdown(
        from_tag="v0.1.0",
        to_ref="HEAD",
        commits=[
            CommitEntry(
                commit_hash="abcdef1234567890",
                date="2026-02-19",
                subject="Add release checklist automation",
            )
        ],
    )

    assert "# Changelog (Generated from Git Tags)" in markdown
    assert "`2026-02-19` `abcdef12` Add release checklist automation" in markdown


def test_merlin_changelog_cli_writes_output(tmp_path: Path):
    output_path = tmp_path / "changelog.md"
    result = subprocess.run(
        [
            sys.executable,
            "merlin_changelog.py",
            "--max-count",
            "3",
            "--output",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert output_path.exists()
    assert "# Changelog (Generated from Git Tags)" in output_path.read_text(
        encoding="utf-8"
    )
