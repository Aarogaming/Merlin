#!/usr/bin/env python3
import argparse
import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import statistics
import wave

import merlin_settings as settings
from merlin_logger import merlin_logger
from merlin_voice_router import PiperEngine, Pyttsx3Engine, XttsEngine

DEFAULT_PROMPTS = [
    "Greetings. I am Merlin, keeper of the tower and watcher of the old roads.",
    "The answer you seek is not in haste, but in careful steps and steady hands.",
    "I can help you plan, build, and test. Tell me your goal, and we will begin.",
]


ENGINE_MAP = {
    "xtts": XttsEngine,
    "piper": PiperEngine,
    "pyttsx3": Pyttsx3Engine,
}


@dataclass
class RunResult:
    engine: str
    prompt: str
    run_index: int
    latency_s: float
    duration_s: float | None
    rtf: float | None
    output_path: str | None
    size_bytes: int | None
    success: bool
    error: str | None


def _load_prompts(path: Path | None) -> list[str]:
    if path is None:
        return DEFAULT_PROMPTS
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    if path.suffix.lower() == ".json":
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, list):
            raise ValueError("Prompt JSON must be a list of strings.")
        return [str(item).strip() for item in data if str(item).strip()]
    lines = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            cleaned = line.strip()
            if cleaned:
                lines.append(cleaned)
    return lines


def _audio_duration(path: Path) -> float | None:
    try:
        with wave.open(str(path), "rb") as wav_file:
            frames = wav_file.getnframes()
            rate = wav_file.getframerate()
            if rate <= 0:
                return None
            return frames / float(rate)
    except Exception:
        return None


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _run_engine(
    engine_name: str, engine, prompt: str, output_dir: Path, run_index: int
) -> RunResult:
    timestamp = int(time.time() * 1000)
    output_path = output_dir / f"{engine_name}_{run_index}_{timestamp}.wav"
    started = time.time()
    error = None
    success = False
    try:
        result = engine.synthesize_to_file(prompt, output_path)
        if result is None or not Path(result).exists():
            error = "synthesis_failed"
        else:
            success = True
            output_path = Path(result)
    except Exception as exc:
        error = str(exc)
    latency = time.time() - started

    duration = _audio_duration(output_path) if success else None
    rtf = (latency / duration) if duration and duration > 0 else None
    size_bytes = output_path.stat().st_size if success else None

    return RunResult(
        engine=engine_name,
        prompt=prompt,
        run_index=run_index,
        latency_s=latency,
        duration_s=duration,
        rtf=rtf,
        output_path=str(output_path) if success else None,
        size_bytes=size_bytes,
        success=success,
        error=error,
    )


def _summarize(results: list[RunResult]) -> dict:
    summary = {}
    engines = sorted({result.engine for result in results})
    for engine in engines:
        runs = [r for r in results if r.engine == engine]
        latencies = [r.latency_s for r in runs if r.success]
        durations = [
            r.duration_s for r in runs if r.success and r.duration_s is not None
        ]
        rtfs = [r.rtf for r in runs if r.success and r.rtf is not None]
        summary[engine] = {
            "runs": len(runs),
            "successes": sum(1 for r in runs if r.success),
            "avg_latency_s": statistics.mean(latencies) if latencies else None,
            "avg_duration_s": statistics.mean(durations) if durations else None,
            "avg_rtf": statistics.mean(rtfs) if rtfs else None,
        }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Merlin voice benchmark harness")
    parser.add_argument(
        "--engines",
        default="xtts,piper,pyttsx3",
        help="Comma-separated list of engines: xtts,piper,pyttsx3",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Number of runs per prompt per engine",
    )
    parser.add_argument(
        "--prompts",
        type=str,
        default=None,
        help="Path to prompts file (.txt lines or .json list)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Directory for generated audio and results JSON",
    )
    args = parser.parse_args()

    prompt_path = Path(args.prompts) if args.prompts else None
    prompts = _load_prompts(prompt_path)

    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else Path(settings.MERLIN_VOICE_CACHE_DIR) / "benchmarks"
    )
    _ensure_dir(output_dir)

    engines = [name.strip().lower() for name in args.engines.split(",") if name.strip()]
    results: list[RunResult] = []

    for engine_name in engines:
        engine_cls = ENGINE_MAP.get(engine_name)
        if not engine_cls:
            merlin_logger.warning(f"Unknown engine: {engine_name}")
            continue
        engine = engine_cls()
        if not engine.is_available():
            merlin_logger.warning(f"Engine unavailable: {engine_name}")
            continue
        for prompt in prompts:
            for run_index in range(1, args.runs + 1):
                merlin_logger.info(
                    f"Benchmarking {engine_name} run {run_index}/{args.runs}"
                )
                results.append(
                    _run_engine(engine_name, engine, prompt, output_dir, run_index)
                )

    summary = _summarize(results)
    report = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "engines": engines,
        "prompts": prompts,
        "runs_per_prompt": args.runs,
        "results": [result.__dict__ for result in results],
        "summary": summary,
    }

    report_path = (
        output_dir
        / f"voice_benchmark_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    )
    with report_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    merlin_logger.info(f"Benchmark report saved to {report_path}")
    for engine_name, metrics in summary.items():
        merlin_logger.info(
            f"{engine_name}: successes={metrics['successes']}/{metrics['runs']} "
            f"avg_latency_s={metrics['avg_latency_s']} avg_rtf={metrics['avg_rtf']}"
        )


if __name__ == "__main__":
    main()
