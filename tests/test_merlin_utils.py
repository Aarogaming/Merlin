from __future__ import annotations

import requests
import pytest

from merlin_utils import (
    RetryBackoffPolicy,
    compute_retry_backoff_seconds,
    retry_with_backoff,
    stable_claim_hash,
)


def test_compute_retry_backoff_seconds_applies_cap_and_jitter():
    policy = RetryBackoffPolicy(
        max_attempts=3,
        initial_backoff_seconds=0.1,
        max_backoff_seconds=0.2,
        jitter_ratio=0.5,
        retry_budget_seconds=1.0,
    )

    delay = compute_retry_backoff_seconds(
        2,
        policy=policy,
        random_fn=lambda: 1.0,
    )

    assert delay == pytest.approx(0.3)


def test_retry_with_backoff_retries_until_success():
    attempts = {"count": 0}
    sleep_calls: list[float] = []
    policy = RetryBackoffPolicy(
        max_attempts=3,
        initial_backoff_seconds=0.1,
        max_backoff_seconds=0.1,
        jitter_ratio=0.0,
        retry_budget_seconds=2.0,
    )

    def operation():
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise requests.exceptions.Timeout("temporary")
        return "ok"

    result = retry_with_backoff(
        operation,
        policy=policy,
        should_retry=lambda err: isinstance(err, requests.exceptions.Timeout),
        sleep_fn=lambda delay: sleep_calls.append(delay),
        random_fn=lambda: 0.0,
    )

    assert result == "ok"
    assert attempts["count"] == 2
    assert sleep_calls == [0.1]


def test_retry_with_backoff_stops_when_budget_is_exhausted():
    attempts = {"count": 0}
    clock = {"now": 0.0}
    policy = RetryBackoffPolicy(
        max_attempts=5,
        initial_backoff_seconds=1.0,
        max_backoff_seconds=1.0,
        jitter_ratio=0.0,
        retry_budget_seconds=0.3,
    )

    def operation():
        attempts["count"] += 1
        raise requests.exceptions.Timeout("still down")

    def fake_sleep(delay: float) -> None:
        clock["now"] += delay

    with pytest.raises(requests.exceptions.Timeout):
        retry_with_backoff(
            operation,
            policy=policy,
            should_retry=lambda err: isinstance(err, requests.exceptions.Timeout),
            sleep_fn=fake_sleep,
            monotonic_fn=lambda: clock["now"],
            random_fn=lambda: 0.0,
        )

    assert attempts["count"] == 2
    assert clock["now"] == pytest.approx(0.3)


def test_retry_with_backoff_skips_non_retryable_errors():
    attempts = {"count": 0}
    policy = RetryBackoffPolicy(max_attempts=4)

    def operation():
        attempts["count"] += 1
        raise ValueError("hard failure")

    with pytest.raises(ValueError):
        retry_with_backoff(
            operation,
            policy=policy,
            should_retry=lambda _err: False,
        )

    assert attempts["count"] == 1


def test_stable_claim_hash_is_normalized_and_deterministic():
    hash_a = stable_claim_hash("  Duplicate   Claim Example ")
    hash_b = stable_claim_hash("duplicate claim example")
    hash_c = stable_claim_hash("different claim example")

    assert hash_a == hash_b
    assert hash_a != hash_c
