from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from core.plugin_manifest import get_hive_metadata
from loguru import logger

MERLIN_ROOT = Path(__file__).resolve().parents[2]
if str(MERLIN_ROOT) not in sys.path:
    sys.path.insert(0, str(MERLIN_ROOT))

try:
    from merlin_voice_source_eval import DEFAULT_SOURCES_FILE, load_sources, resolve_reference, select_sources
except Exception as exc:  # pragma: no cover - import guard
    DEFAULT_SOURCES_FILE = MERLIN_ROOT / "merlin_voice_sources.json"
    load_sources = None
    resolve_reference = None
    select_sources = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


def _parse_ids(value: str | Iterable[str] | None) -> Optional[List[str]]:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = [item.strip() for item in value.split(",") if item.strip()]
    else:
        cleaned = [str(item).strip() for item in value if str(item).strip()]
    return cleaned or None


def _benchmark_cmd(
    benchmark_script: Path,
    engines: str,
    runs: int,
    prompts: str | None,
    output_dir: Path,
) -> List[str]:
    cmd = [
        sys.executable,
        str(benchmark_script),
        "--engines",
        engines,
        "--runs",
        str(runs),
        "--output-dir",
        str(output_dir),
    ]
    if prompts:
        cmd.extend(["--prompts", prompts])
    return cmd


def _normalize_engines(value: str | Iterable[str]) -> str:
    if isinstance(value, str):
        return value
    cleaned = [str(item).strip() for item in value if str(item).strip()]
    return ",".join(cleaned)


class Plugin:
    def __init__(self, hub: Any = None, manifest: Dict[str, Any] | None = None):
        self.hub = hub
        self.manifest = manifest or {}
        hive_meta = get_hive_metadata(self.manifest)
        self.hive = str(hive_meta.get("hive") or "merlin").lower()

    def commands(self) -> Dict[str, Any]:
        return {
            "merlin.voice.source_eval": self.source_eval,
        }

    def source_eval(
        self,
        sources: str | Iterable[str] | None = None,
        engines: str | Iterable[str] = "xtts",
        runs: int = 1,
        prompts: str | None = None,
        sources_file: str = "",
        output_dir: str = "",
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        if load_sources is None or select_sources is None or resolve_reference is None:
            return {
                "ok": False,
                "error": f"merlin_voice_source_eval import failed: {_IMPORT_ERROR}",
            }

        sources_path = Path(sources_file) if sources_file else Path(DEFAULT_SOURCES_FILE)
        if not sources_path.exists():
            return {
                "ok": False,
                "error": f"Sources file not found: {sources_path}",
            }

        benchmark_script = MERLIN_ROOT / "merlin_voice_benchmark.py"
        if not benchmark_script.exists():
            return {
                "ok": False,
                "error": f"Benchmark script not found: {benchmark_script}",
            }

        try:
            all_sources = load_sources(sources_path)
        except Exception as exc:
            return {"ok": False, "error": f"Failed to load sources: {exc}"}

        selected = select_sources(all_sources, _parse_ids(sources))
        if not selected:
            return {"ok": False, "error": "No sources selected."}

        try:
            run_count = max(1, int(runs))
        except (TypeError, ValueError):
            return {"ok": False, "error": "Runs must be an integer."}

        engines_value = _normalize_engines(engines)
        if not engines_value.strip():
            return {"ok": False, "error": "No engines requested."}

        output_root = Path(
            output_dir
            or Path(os.getenv("MERLIN_VOICE_CACHE_DIR", "artifacts/voice")) / "benchmarks"
        )
        output_root.mkdir(parents=True, exist_ok=True)

        summary: Dict[str, Any] = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "sources_file": str(sources_path),
            "engines": engines_value,
            "runs": run_count,
            "prompt_file": prompts,
            "output_root": str(output_root),
            "sources": [],
        }

        commands: List[str] = []
        for source in selected:
            ref_path = resolve_reference(source)
            entry = {
                "id": source.get("id"),
                "label": source.get("label"),
                "reference_wav": source.get("reference_wav"),
                "reference_exists": bool(ref_path),
            }
            summary["sources"].append(entry)
            if not ref_path:
                logger.warning(f"[SKIP] {source.get('id')}: missing reference_wav")
                continue

            output_dir_path = output_root / str(source.get("id"))
            output_dir_path.mkdir(parents=True, exist_ok=True)
            cmd = _benchmark_cmd(
                benchmark_script, engines_value, run_count, prompts, output_dir_path
            )

            if dry_run:
                commands.append(" ".join(cmd))
                continue

            env = os.environ.copy()
            env["MERLIN_VOICE_REFERENCE_WAV"] = str(ref_path)
            subprocess.run(cmd, env=env, check=False)

        summary_path = output_root / "voice_source_eval_summary.json"
        try:
            summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        except Exception as exc:
            return {"ok": False, "error": f"Failed to write summary: {exc}"}

        response: Dict[str, Any] = {
            "ok": True,
            "summary_path": str(summary_path),
            "summary": summary,
        }
        if commands:
            response["commands"] = commands
        return response
