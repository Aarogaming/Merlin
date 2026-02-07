#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_SOURCES_FILE = Path(__file__).with_name("merlin_voice_sources.json")


def load_sources(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload.get("sources", [])


def select_sources(sources: list[dict], ids: list[str] | None) -> list[dict]:
    if not ids:
        return sources
    wanted = {item.strip().lower() for item in ids if item.strip()}
    return [source for source in sources if source.get("id", "").lower() in wanted]


def resolve_reference(source: dict) -> Path | None:
    ref = (source.get("reference_wav") or "").strip()
    if not ref:
        return None
    ref_path = Path(ref)
    return ref_path if ref_path.exists() else None


def run_benchmark(
    source: dict,
    reference_wav: Path,
    engines: str,
    runs: int,
    prompts: str | None,
    output_root: Path,
    dry_run: bool,
) -> None:
    output_dir = output_root / source["id"]
    output_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["MERLIN_VOICE_REFERENCE_WAV"] = str(reference_wav)
    cmd = [
        sys.executable,
        "Merlin/merlin_voice_benchmark.py",
        "--engines",
        engines,
        "--runs",
        str(runs),
        "--output-dir",
        str(output_dir),
    ]
    if prompts:
        cmd.extend(["--prompts", prompts])

    if dry_run:
        print(f"[DRY RUN] {source['id']} -> {' '.join(cmd)}")
        return

    subprocess.run(cmd, env=env, check=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Merlin voice sources.")
    parser.add_argument(
        "--sources", type=str, default="", help="Comma-separated source IDs."
    )
    parser.add_argument(
        "--engines", type=str, default="xtts", help="Engines to benchmark."
    )
    parser.add_argument("--runs", type=int, default=1, help="Runs per prompt.")
    parser.add_argument("--prompts", type=str, default=None, help="Prompt file path.")
    parser.add_argument("--sources-file", type=str, default=str(DEFAULT_SOURCES_FILE))
    parser.add_argument("--output-dir", type=str, default="")
    parser.add_argument("--dry-run", action="store_true", help="Print commands only.")
    args = parser.parse_args()

    sources_file = Path(args.sources_file)
    if not sources_file.exists():
        raise FileNotFoundError(f"Sources file not found: {sources_file}")

    sources = load_sources(sources_file)
    selected = select_sources(
        sources, args.sources.split(",") if args.sources else None
    )

    output_root = Path(
        args.output_dir
        or Path(os.getenv("MERLIN_VOICE_CACHE_DIR", "artifacts/voice")) / "benchmarks"
    )
    output_root.mkdir(parents=True, exist_ok=True)

    summary = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "sources_file": str(sources_file),
        "engines": args.engines,
        "runs": args.runs,
        "prompt_file": args.prompts,
        "output_root": str(output_root),
        "sources": [],
    }

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
            print(f"[SKIP] {source.get('id')}: missing reference_wav")
            continue
        run_benchmark(
            source,
            ref_path,
            args.engines,
            args.runs,
            args.prompts,
            output_root,
            args.dry_run,
        )

    summary_path = output_root / "voice_source_eval_summary.json"
    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
    print(f"Summary saved to {summary_path}")


if __name__ == "__main__":
    main()
