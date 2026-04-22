from __future__ import annotations

import glob
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
        return {"merlin.voice.benchmark": self.voice_benchmark}

    def voice_benchmark(
        self,
        engines: str = "xtts,piper,pyttsx3",
        runs: int = 1,
        prompts: str = "",
        output_dir: str = "",
        source_catalog_path: str = "",
        source_ids: str = "",
        dataset_version: str = "",
    ) -> Dict[str, Any]:
        script = self.repo_root / "scripts" / "merlin_voice_benchmark.py"
        target_output = Path(output_dir) if output_dir else (self.repo_root / "artifacts" / "voice" / "benchmarks")
        target_output.mkdir(parents=True, exist_ok=True)

        cmd = [
            sys.executable,
            str(script),
            "--engines",
            str(engines),
            "--runs",
            str(max(1, int(runs))),
            "--output-dir",
            str(target_output),
        ]
        if prompts:
            cmd.extend(["--prompts", str(prompts)])
        if source_catalog_path:
            cmd.extend(["--source-catalog", str(source_catalog_path)])
        if source_ids:
            cmd.extend(["--source-ids", str(source_ids)])
        if dataset_version:
            cmd.extend(["--dataset-version", str(dataset_version)])

        result = subprocess.run(cmd, cwd=str(self.repo_root), check=False, capture_output=True, text=True)

        reports = sorted(glob.glob(str(target_output / "voice_benchmark_*.json")))
        report_path = reports[-1] if reports else ""
        return {
            "ok": result.returncode == 0,
            "command": cmd,
            "returncode": result.returncode,
            "report_path": report_path,
            "stdout_tail": (result.stdout or "")[-1200:],
            "stderr_tail": (result.stderr or "")[-1200:],
        }
