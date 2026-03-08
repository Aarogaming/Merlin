from __future__ import annotations

import json
import os
from collections import OrderedDict
from typing import Any, Optional

try:
    import redis
except Exception:  # pragma: no cover - optional dependency.
    redis = None

from merlin_logger import merlin_logger


class MerlinCache:
    def __init__(self):
        self.redis_host = os.getenv("REDIS_HOST", "localhost")
        self.redis_port = int(os.getenv("REDIS_PORT", 6379))
        self.max_memory_entries = max(
            1, int(os.getenv("MERLIN_CACHE_MAX_ENTRIES", "1024"))
        )
        self.client = None
        self._memory_cache: OrderedDict[str, Any] = OrderedDict()
        self._namespace_metrics: dict[str, dict[str, int]] = {}
        self._connect()

    @staticmethod
    def _namespace_from_key(key: str) -> str:
        if ":" not in key:
            return "default"
        namespace, _rest = key.split(":", 1)
        return namespace.strip() or "default"

    def _metrics_for_namespace(self, namespace: str) -> dict[str, int]:
        metrics = self._namespace_metrics.get(namespace)
        if metrics is None:
            metrics = {
                "hits": 0,
                "misses": 0,
                "sets": 0,
                "deletes": 0,
                "evictions": 0,
            }
            self._namespace_metrics[namespace] = metrics
        return metrics

    def _record_metric(self, namespace: str, metric: str) -> None:
        self._metrics_for_namespace(namespace)[metric] += 1

    def _connect(self):
        if redis is None:
            merlin_logger.warning(
                "Redis package unavailable. Falling back to in-memory cache."
            )
            self.client = None
            self._memory_cache = OrderedDict()
            return

        try:
            self.client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                decode_responses=True,
            )
            self.client.ping()
            merlin_logger.info(
                f"Connected to Redis at {self.redis_host}:{self.redis_port}"
            )
        except Exception as e:
            merlin_logger.warning(
                f"Redis connection failed: {e}. Falling back to in-memory cache."
            )
            self.client = None
            self._memory_cache = OrderedDict()

    def get(self, key: str) -> Optional[Any]:
        namespace = self._namespace_from_key(key)
        if self.client:
            try:
                value = self.client.get(key)
                if value is None:
                    self._record_metric(namespace, "misses")
                    return None
                self._record_metric(namespace, "hits")
                return json.loads(value)
            except Exception as e:
                merlin_logger.error(f"Redis get error: {e}")
                self._record_metric(namespace, "misses")
                return None

        if key in self._memory_cache:
            self._memory_cache.move_to_end(key)
            self._record_metric(namespace, "hits")
            return self._memory_cache[key]
        self._record_metric(namespace, "misses")
        return None

    def set(self, key: str, value: Any, expire: int = 3600):
        namespace = self._namespace_from_key(key)
        if self.client:
            try:
                self.client.set(key, json.dumps(value), ex=expire)
                self._record_metric(namespace, "sets")
            except Exception as e:
                merlin_logger.error(f"Redis set error: {e}")
            return

        if key in self._memory_cache:
            self._memory_cache.move_to_end(key)
        else:
            if len(self._memory_cache) >= self.max_memory_entries:
                evicted_key, _evicted_value = self._memory_cache.popitem(last=False)
                evicted_namespace = self._namespace_from_key(evicted_key)
                self._record_metric(evicted_namespace, "evictions")
        self._memory_cache[key] = value
        self._record_metric(namespace, "sets")

    def delete(self, key: str):
        namespace = self._namespace_from_key(key)
        if self.client:
            try:
                deleted = int(self.client.delete(key))
                if deleted > 0:
                    self._record_metric(namespace, "deletes")
            except Exception as e:
                merlin_logger.error(f"Redis delete error: {e}")
            return

        if key in self._memory_cache:
            self._memory_cache.pop(key, None)
            self._record_metric(namespace, "deletes")

    def get_metrics(self) -> dict[str, Any]:
        namespaces: dict[str, dict[str, Any]] = {}
        total_hits = 0
        total_misses = 0
        total_evictions = 0
        total_sets = 0
        total_deletes = 0

        for namespace, metrics in self._namespace_metrics.items():
            hits = int(metrics.get("hits", 0))
            misses = int(metrics.get("misses", 0))
            requests = hits + misses
            sets = int(metrics.get("sets", 0))
            deletes = int(metrics.get("deletes", 0))
            evictions = int(metrics.get("evictions", 0))

            total_hits += hits
            total_misses += misses
            total_evictions += evictions
            total_sets += sets
            total_deletes += deletes

            namespaces[namespace] = {
                "hits": hits,
                "misses": misses,
                "requests": requests,
                "hit_rate": (hits / requests) if requests > 0 else 0.0,
                "sets": sets,
                "deletes": deletes,
                "evictions": evictions,
            }

        total_requests = total_hits + total_misses
        return {
            "backend": "redis" if self.client else "memory",
            "max_memory_entries": self.max_memory_entries,
            "namespaces": namespaces,
            "overall": {
                "hits": total_hits,
                "misses": total_misses,
                "requests": total_requests,
                "hit_rate": (total_hits / total_requests) if total_requests > 0 else 0.0,
                "sets": total_sets,
                "deletes": total_deletes,
                "evictions": total_evictions,
            },
        }

    def reset_metrics(self) -> None:
        self._namespace_metrics.clear()


merlin_cache = MerlinCache()
