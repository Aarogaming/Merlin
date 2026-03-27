from __future__ import annotations

from pathlib import Path

import pytest

import merlin_ab_testing as ab_testing


def _make_manager(tmp_path: Path) -> ab_testing.ABTestingManager:
    manager = ab_testing.ABTestingManager()
    manager.tests_file = str(tmp_path / "ab_tests.json")
    manager.active_tests = {}
    manager.test_history = []
    return manager


def test_get_variant_for_request_uses_weights(monkeypatch):
    test = ab_testing.ABTest(
        test_id="test_weights",
        name="weights",
        variants=["v1", "v2"],
        weights=[0.2, 0.8],
        start_time="2026-02-13T00:00:00",
        status="active",
    )

    monkeypatch.setattr(ab_testing.random, "random", lambda: 0.1)
    assert test.get_variant_for_request() == "v1"

    monkeypatch.setattr(ab_testing.random, "random", lambda: 0.9)
    assert test.get_variant_for_request() == "v2"


def test_create_test_validates_weights(tmp_path):
    manager = _make_manager(tmp_path)

    test_id = manager.create_test(
        name="strategy test", variants=["routing", "voting"], weights=[0.6, 0.4]
    )
    assert test_id in manager.active_tests

    with pytest.raises(ValueError, match="Weights must match variants count"):
        manager.create_test(name="bad count", variants=["a", "b"], weights=[1.0])

    with pytest.raises(ValueError, match="Weights must sum to 1.0"):
        manager.create_test(name="bad sum", variants=["a", "b"], weights=[0.2, 0.2])


def test_get_winner_uses_aggregated_variant_stats():
    test = ab_testing.ABTest(
        test_id="test_winner",
        name="winner selection",
        variants=["routing", "cascade"],
        weights=[0.5, 0.5],
        start_time="2026-02-13T00:00:00",
        status="completed",
    )

    for _ in range(12):
        test.add_metric("routing", user_rating=5, latency=1.0, success=True)

    for _ in range(12):
        test.add_metric("cascade", user_rating=2, latency=4.0, success=False)

    winner = test.get_winner()
    assert winner is not None
    assert winner["variant"] == "routing"
    assert winner["stats"]["requests"] == 12


def test_complete_test_updates_history_and_summary(tmp_path):
    manager = _make_manager(tmp_path)
    test_id = manager.create_test(
        name="completion flow", variants=["routing", "cascade"], weights=[0.5, 0.5]
    )

    for _ in range(12):
        manager.record_result(
            test_id=test_id,
            variant="routing",
            user_rating=5,
            latency=1.0,
            success=True,
        )

    for _ in range(12):
        manager.record_result(
            test_id=test_id,
            variant="cascade",
            user_rating=2,
            latency=4.0,
            success=False,
        )

    winner = manager.complete_test(test_id)
    assert winner is not None
    assert winner["variant"] == "routing"
    assert test_id not in manager.active_tests
    assert len(manager.test_history) == 1

    summary = manager.get_summary()
    assert summary["total_tests"] == 1
    assert summary["active_tests"] == 0
    assert summary["completed_tests"] == 1
    assert summary["variant_winners"] == {"routing": 1}


def test_create_retrieval_profile_test_uses_even_split(tmp_path):
    manager = _make_manager(tmp_path)

    test_id = manager.create_retrieval_profile_test(
        profile_a="hybrid", profile_b="vector", test_name="retrieval-profile"
    )

    assert test_id in manager.active_tests
    test = manager.active_tests[test_id]
    assert test.name == "retrieval-profile"
    assert test.variants == ["hybrid", "vector"]
    assert test.weights == [0.5, 0.5]


def test_recommend_variant_falls_back_to_default(tmp_path):
    manager = _make_manager(tmp_path)

    assert (
        manager.recommend_variant("missing-test", default_variant="hybrid")
        == "hybrid"
    )
