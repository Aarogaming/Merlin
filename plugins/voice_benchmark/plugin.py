from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

from core.plugin_manifest import get_hive_metadata
from loguru import logger

MERLIN_ROOT = Path(__file__).resolve().parents[2]
if str(MERLIN_ROOT) not in sys.path:
    sys.path.insert(0, str(MERLIN_ROOT))

try:
    import merlin_settings as settings
    from merlin_logger import merlin_logger
    from merlin_voice_benchmark import ENGINE_MAP, _load_prompts, _run_engine, _summarize
except Exception as exc:  # pragma: no cover - import guard
    settings = None
    merlin_logger = None
    ENGINE_MAP = {}
    _load_prompts = None
    _run_engine = None
    _summarize = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


def _parse_engines(value: str | Iterable[str]) -> List[str]:
    if isinstance(value, str):
        tokens = [item.strip().lower() for item in value.split(",") if item.strip()]
    else:
        tokens = [str(item).strip().lower() for item in value if str(item).strip()]
    return tokens


def _resolve_prompts(prompts: Any) -> List[str]:
    if _load_prompts is None:
        return []
    if prompts is None or prompts == "":
        return _load_prompts(None)
    if isinstance(prompts, (list, tuple)):
        cleaned = [str(item).strip() for item in prompts if str(item).strip()]
        return cleaned or _load_prompts(None)
    return _load_prompts(Path(str(prompts)))


class Plugin:
    def __init__(self, hub: Any = None, manifest: Dict[str, Any] | None = None):
        self.hub = hub
        self.manifest = manifest or {}
        hive_meta = get_hive_metadata(self.manifest)
        self.hive = str(hive_meta.get("hive") or "merlin").lower()

    def commands(self) -> Dict[str, Any]:
        return {
            "merlin.voice.benchmark": self.benchmark,
        }

    def benchmark(
        self,
        engines: str | Iterable[str] = "xtts,piper,pyttsx3",
        runs: int = 1,
        prompts: Any = None,
        output_dir: str = "",
    ) -> Dict[str, Any]:
        if _load_prompts is None or _run_engine is None or _summarize is None:
            return {
                "ok": False,
                "error": f"merlin_voice_benchmark import failed: {_IMPORT_ERROR}",
            }

        try:
            prompts_list = _resolve_prompts(prompts)
        except Exception as exc:
            return {"ok": False, "error": f"Failed to load prompts: {exc}"}

        if not prompts_list:
            return {"ok": False, "error": "No prompts available to benchmark."}

        if settings is None:
            return {"ok": False, "error": "Merlin settings unavailable."}

        output_path = (
            Path(output_dir)
            if output_dir
            else Path(settings.MERLIN_VOICE_CACHE_DIR or "artifacts/voice") / "benchmarks"
        )
        output_path.mkdir(parents=True, exist_ok=True)

        engine_names = _parse_engines(engines)
        if not engine_names:
            return {"ok": False, "error": "No engines requested."}

        results = []
        errors: List[str] = []
        try:
            run_count = max(1, int(runs))
        except (TypeError, ValueError):
            return {"ok": False, "error": "Runs must be an integer."}

        for engine_name in engine_names:
            engine_cls = ENGINE_MAP.get(engine_name)
            if not engine_cls:
                errors.append(f"Unknown engine: {engine_name}")
                continue
            try:
                engine = engine_cls()
            except Exception as exc:
                errors.append(f"Failed to init engine {engine_name}: {exc}")
                continue
            try:
                if not engine.is_available():
                    errors.append(f"Engine unavailable: {engine_name}")
                    continue
            except Exception as exc:
                errors.append(f"Engine check failed {engine_name}: {exc}")
                continue

            for prompt in prompts_list:
                for run_index in range(1, run_count + 1):
                    if merlin_logger:
                        merlin_logger.info(
                            f"Benchmarking {engine_name} run {run_index}/{run_count}"
                        )
                    try:
                        results.append(
                            _run_engine(engine_name, engine, prompt, output_path, run_index)
                        )
                    except Exception as exc:
                        errors.append(
                            f"Benchmark run failed {engine_name} run {run_index}: {exc}"
                        )

        summary = _summarize(results)
        report = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "engines": engine_names,
            "prompts": prompts_list,
            "runs_per_prompt": run_count,
            "results": [result.__dict__ for result in results],
            "summary": summary,
        }

        report_path = (
            output_path / f"voice_benchmark_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        )
        try:
            report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning(f"Failed to write benchmark report: {exc}")
            return {"ok": False, "error": f"Failed to write report: {exc}"}

        ok = bool(results)
        response: Dict[str, Any] = {
            "ok": ok,
            "report_path": str(report_path),
            "summary": summary,
            "results_count": len(results),
            "errors": errors,
        }
        if not ok:
            response["error"] = "No benchmarks executed."
        return response
