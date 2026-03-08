from __future__ import annotations

import importlib
import types

import pytest


class _FailingRedisClient:
    def ping(self):
        raise RuntimeError("redis unavailable")


def test_memory_cache_namespace_metrics_with_eviction(monkeypatch):
    module = importlib.import_module("merlin_cache")
    monkeypatch.setenv("MERLIN_CACHE_MAX_ENTRIES", "2")
    if module.redis is None:
        monkeypatch.setattr(
            module,
            "redis",
            types.SimpleNamespace(Redis=lambda *args, **kwargs: _FailingRedisClient()),
        )
    else:
        monkeypatch.setattr(
            module.redis,
            "Redis",
            lambda *args, **kwargs: _FailingRedisClient(),
        )
    cache = module.MerlinCache()

    cache.set("alpha:item_1", {"v": 1})
    cache.set("alpha:item_2", {"v": 2})
    assert cache.get("alpha:item_1") == {"v": 1}
    assert cache.get("alpha:missing") is None
    cache.set("beta:item_3", {"v": 3})  # Evicts alpha:item_2 by LRU ordering.
    cache.delete("alpha:item_1")

    metrics = cache.get_metrics()
    alpha = metrics["namespaces"]["alpha"]
    beta = metrics["namespaces"]["beta"]

    assert metrics["backend"] == "memory"
    assert alpha["hits"] == 1
    assert alpha["misses"] == 1
    assert alpha["sets"] == 2
    assert alpha["deletes"] == 1
    assert alpha["evictions"] == 1
    assert beta["sets"] == 1
    assert metrics["overall"]["hit_rate"] == pytest.approx(0.5)
