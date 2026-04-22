from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, Dict


class Plugin:
    def __init__(self, hub: Any = None, manifest: Dict[str, Any] | None = None):
        self.hub = hub
        self.manifest = manifest or {}
        self.repo_root = Path(__file__).resolve().parents[2]

    def commands(self) -> Dict[str, Any]:
        return {"merlin.voice.source_eval": self.voice_source_eval}

    def voice_source_eval(
        self,
        sources: str = "",
        engines: str = "xtts",
        runs: int = 1,
        prompts: str = "",
        sources_file: str = "",
        output_dir: str = "",
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        script = self.repo_root / "scripts" / "merlin_voice_source_eval.py"
        cmd = [
            sys.executable,
            str(script),
            "--engines",
            str(engines),
            "--runs",
            str(max(1, int(runs))),
        ]
        if sources:
            cmd.extend(["--sources", str(sources)])
        if prompts:
            cmd.extend(["--prompts", str(prompts)])
        if sources_file:
            cmd.extend(["--sources-file", str(sources_file)])
        if output_dir:
            cmd.extend(["--output-dir", str(output_dir)])
        if dry_run:
            cmd.append("--dry-run")

        result = subprocess.run(cmd, cwd=str(self.repo_root), check=False, capture_output=True, text=True)
        return {
            "ok": result.returncode == 0,
            "command": cmd,
            "returncode": result.returncode,
            "stdout_tail": (result.stdout or "")[-1200:],
            "stderr_tail": (result.stderr or "")[-1200:],
        }
