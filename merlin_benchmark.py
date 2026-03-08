from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

import merlin_settings as settings


def benchmark_llm(
    *,
    prompt: str = "Explain the importance of modular software architecture.",
    iterations: int = 3,
    target_url: str | None = None,
    timeout_s: float = 30.0,
    emit_console: bool = True,
) -> dict[str, Any]:
    resolved_target_url = target_url or settings.LM_STUDIO_URL
    resolved_iterations = max(1, int(iterations))

    if emit_console:
        print("=" * 40)
        print("Merlin Merlin - LLM Benchmark")
        print("=" * 40)
        print(f"Prompt: {prompt}")
        print(f"Iterations: {resolved_iterations}")
        print(f"Target URL: {resolved_target_url}")
        print("=" * 40)

    latencies: list[float] = []
    tokens_per_sec: list[float] = []
    runs: list[dict[str, Any]] = []

    for i in range(resolved_iterations):
        if emit_console:
            print(f"Running iteration {i + 1}...")
        start_time = time.time()

        payload = {
            "model": settings.OPENAI_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 200,
        }

        try:
            response = requests.post(
                resolved_target_url,
                json=payload,
                timeout=timeout_s,
            )
            response.raise_for_status()
            end_time = time.time()
            duration = end_time - start_time
            data = response.json()
            content = (
                data.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
            )
            token_count = len(content) / 4 if content else 0.0
            tps = (token_count / duration) if duration > 0 else 0.0
            latencies.append(duration)
            tokens_per_sec.append(tps)
            runs.append(
                {
                    "iteration": i + 1,
                    "ok": True,
                    "duration_s": duration,
                    "estimated_tokens_per_s": tps,
                    "status_code": response.status_code,
                }
            )
            if emit_console:
                print(f"  Duration: {duration:.2f}s | Est. TPS: {tps:.2f}")
        except Exception as exc:
            runs.append(
                {
                    "iteration": i + 1,
                    "ok": False,
                    "error": str(exc),
                }
            )
            if emit_console:
                print(f"  Error: {exc}")

    summary = {
        "successful_runs": len(latencies),
        "failed_runs": len(runs) - len(latencies),
        "avg_latency_s": statistics.mean(latencies) if latencies else None,
        "min_latency_s": min(latencies) if latencies else None,
        "max_latency_s": max(latencies) if latencies else None,
        "avg_tokens_per_s": statistics.mean(tokens_per_sec) if tokens_per_sec else None,
    }
    result = {
        "schema_name": "AAS.Benchmark.LLMResult",
        "schema_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target_url": resolved_target_url,
        "prompt": prompt,
        "iterations_requested": resolved_iterations,
        "runs": runs,
        "summary": summary,
    }

    if emit_console:
        if latencies:
            print("=" * 40)
            print("Benchmark Results:")
            print(f"  Avg Latency: {summary['avg_latency_s']:.2f}s")
            print(f"  Min Latency: {summary['min_latency_s']:.2f}s")
            print(f"  Max Latency: {summary['max_latency_s']:.2f}s")
            print(f"  Avg Tokens/Sec: {summary['avg_tokens_per_s']:.2f}")
            print("=" * 40)
        else:
            print("Benchmark failed to collect data.")

    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Merlin LLM benchmark runner")
    parser.add_argument(
        "--prompt",
        default="Explain the importance of modular software architecture.",
        help="Prompt sent for each benchmark iteration",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=3,
        help="Number of benchmark iterations",
    )
    parser.add_argument(
        "--target-url",
        default=None,
        help="Override target chat completion endpoint URL",
    )
    parser.add_argument(
        "--timeout-s",
        type=float,
        default=30.0,
        help="Request timeout per iteration in seconds",
    )
    parser.add_argument(
        "--output-json",
        default=None,
        help="Optional path to write benchmark result JSON",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    result = benchmark_llm(
        prompt=args.prompt,
        iterations=args.iterations,
        target_url=args.target_url,
        timeout_s=args.timeout_s,
        emit_console=True,
    )

    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(f"Saved benchmark JSON: {output_path}")

    return 0 if result["summary"]["successful_runs"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
