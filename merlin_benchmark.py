import time
import requests
import json
import statistics
from typing import List, Dict
import merlin_settings as settings


def benchmark_llm(
    prompt: str = "Explain the importance of modular software architecture.",
    iterations: int = 3,
):
    print("=" * 40)
    print("Merlin Merlin - LLM Benchmark")
    print("=" * 40)
    print(f"Prompt: {prompt}")
    print(f"Iterations: {iterations}")
    print(f"Target URL: {settings.LM_STUDIO_URL}")
    print("=" * 40)

    latencies = []
    tokens_per_sec = []

    for i in range(iterations):
        print(f"Running iteration {i+1}...")
        start_time = time.time()

        payload = {
            "model": settings.OPENAI_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 200,
        }

        try:
            response = requests.post(settings.LM_STUDIO_URL, json=payload, timeout=30)
            response.raise_for_status()
            end_time = time.time()

            duration = end_time - start_time
            latencies.append(duration)

            data = response.json()
            content = data["choices"][0]["message"]["content"]
            # Rough estimate of tokens (4 chars per token)
            token_count = len(content) / 4
            tps = token_count / duration
            tokens_per_sec.append(tps)

            print(f"  Duration: {duration:.2f}s | Est. TPS: {tps:.2f}")
        except Exception as e:
            print(f"  Error: {e}")

    if latencies:
        print("=" * 40)
        print("Benchmark Results:")
        print(f"  Avg Latency: {statistics.mean(latencies):.2f}s")
        print(f"  Min Latency: {min(latencies):.2f}s")
        print(f"  Max Latency: {max(latencies):.2f}s")
        print(f"  Avg Tokens/Sec: {statistics.mean(tokens_per_sec):.2f}")
        print("=" * 40)
    else:
        print("Benchmark failed to collect data.")


if __name__ == "__main__":
    benchmark_llm()
