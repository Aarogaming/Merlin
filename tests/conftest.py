from __future__ import annotations

from typing import Any, Callable

import pytest

from merlin_routing_contract import FALLBACK_REASON_CODES

_ROUTER_VARIANTS = ("dms", "control", "disabled")


def _zero_fallback_reason_counts() -> dict[str, int]:
    return {reason_code: 0 for reason_code in sorted(FALLBACK_REASON_CODES)}


def _reset_router_metrics_state(backend: Any) -> None:
    routing_metrics = getattr(backend, "routing_metrics", None)
    if not isinstance(routing_metrics, dict):
        return

    routing_metrics["total_requests"] = 0
    routing_metrics["dms_attempted"] = 0
    routing_metrics["dms_selected"] = 0
    routing_metrics["dms_fallbacks"] = 0
    routing_metrics["throughput_rpm"] = 0.0

    fallback_counts = routing_metrics.get("fallback_reason_counts")
    if not isinstance(fallback_counts, dict):
        fallback_counts = {}
        routing_metrics["fallback_reason_counts"] = fallback_counts
    fallback_counts.clear()
    fallback_counts.update(_zero_fallback_reason_counts())

    stream_latency = routing_metrics.get("stream_latency")
    if isinstance(stream_latency, dict):
        stream_latency["requests"] = 0
        stream_latency["ttft_sum_seconds"] = 0.0
        stream_latency["completion_sum_seconds"] = 0.0
        stream_latency["ttft_samples"] = 0
        stream_latency["completion_samples"] = 0

    usage_economics = routing_metrics.get("usage_economics")
    if isinstance(usage_economics, dict):
        usage_economics["selected_samples"] = 0
        usage_economics["selected_prompt_tokens"] = 0
        usage_economics["selected_completion_tokens"] = 0
        usage_economics["selected_total_tokens"] = 0
        usage_economics["selected_cached_tokens"] = 0
        usage_economics["selected_reasoning_tokens"] = 0

        by_prompt_bucket = usage_economics.get("by_prompt_bucket")
        if isinstance(by_prompt_bucket, dict):
            for bucket in ("short", "medium", "long", "other"):
                bucket_metrics = by_prompt_bucket.get(bucket)
                if not isinstance(bucket_metrics, dict):
                    bucket_metrics = {}
                    by_prompt_bucket[bucket] = bucket_metrics
                bucket_metrics["samples"] = 0
                bucket_metrics["prompt_tokens"] = 0
                bucket_metrics["completion_tokens"] = 0
                bucket_metrics["total_tokens"] = 0
                bucket_metrics["cached_tokens"] = 0
                bucket_metrics["reasoning_tokens"] = 0

        by_ab_variant = usage_economics.get("by_ab_variant")
        if isinstance(by_ab_variant, dict):
            for variant in _ROUTER_VARIANTS:
                variant_metrics = by_ab_variant.get(variant)
                if not isinstance(variant_metrics, dict):
                    variant_metrics = {}
                    by_ab_variant[variant] = variant_metrics
                variant_metrics["samples"] = 0
                variant_metrics["prompt_tokens"] = 0
                variant_metrics["completion_tokens"] = 0
                variant_metrics["total_tokens"] = 0
                variant_metrics["cached_tokens"] = 0
                variant_metrics["reasoning_tokens"] = 0

    ab_variants = routing_metrics.get("ab_variants")
    if not isinstance(ab_variants, dict):
        ab_variants = {}
        routing_metrics["ab_variants"] = ab_variants

    for variant in _ROUTER_VARIANTS:
        variant_metrics = ab_variants.get(variant)
        if not isinstance(variant_metrics, dict):
            variant_metrics = {}
            ab_variants[variant] = variant_metrics
        variant_metrics["requests"] = 0
        variant_metrics["successes"] = 0
        variant_metrics["latency_sum"] = 0.0
        variant_metrics["quality_sum"] = 0.0

    request_timestamps = getattr(backend, "_request_timestamps", None)
    if hasattr(request_timestamps, "clear"):
        request_timestamps.clear()


@pytest.fixture
def reset_router_metrics() -> Callable[[Any], None]:
    return _reset_router_metrics_state


@pytest.fixture
def assert_zero_fallback_reason_counts() -> Callable[[Any], None]:
    def _assert(backend: Any) -> None:
        routing_metrics = getattr(backend, "routing_metrics", {})
        fallback_counts = routing_metrics.get("fallback_reason_counts", {})
        assert isinstance(fallback_counts, dict)
        assert fallback_counts == _zero_fallback_reason_counts()

    return _assert


@pytest.fixture(autouse=True)
def reset_operation_request_state() -> None:
    """Keep API operation tests isolated from prior request cache state."""
    try:
        import merlin_api_server as api_server
    except Exception:
        return

    idempotency_lock = getattr(api_server, "_IDEMPOTENCY_LOCK", None)
    idempotency_cache = getattr(api_server, "_IDEMPOTENCY_RESPONSE_CACHE", None)
    if hasattr(idempotency_lock, "__enter__") and isinstance(idempotency_cache, dict):
        with idempotency_lock:
            idempotency_cache.clear()
    elif isinstance(idempotency_cache, dict):
        idempotency_cache.clear()

    rate_lock = getattr(api_server, "_OPERATION_RATE_LIMIT_LOCK", None)
    rate_windows = getattr(api_server, "_OPERATION_RATE_WINDOWS", None)
    if hasattr(rate_lock, "__enter__") and isinstance(rate_windows, dict):
        with rate_lock:
            rate_windows.clear()
    elif isinstance(rate_windows, dict):
        rate_windows.clear()

    dependency_breaker = getattr(api_server, "_DEPENDENCY_CIRCUIT_BREAKER", None)
    if dependency_breaker is not None and hasattr(dependency_breaker, "clear"):
        dependency_breaker.clear()
