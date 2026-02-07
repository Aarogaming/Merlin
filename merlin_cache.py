import os
import json
import redis
from typing import Any, Optional
from merlin_logger import merlin_logger


class MerlinCache:
    def __init__(self):
        self.redis_host = os.getenv("REDIS_HOST", "localhost")
        self.redis_port = int(os.getenv("REDIS_PORT", 6379))
        self.client = None
        self._connect()

    def _connect(self):
        try:
            self.client = redis.Redis(
                host=self.redis_host, port=self.redis_port, decode_responses=True
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
            self._memory_cache = {}

    def get(self, key: str) -> Optional[Any]:
        if self.client:
            try:
                value = self.client.get(key)
                return json.loads(value) if value else None
            except Exception as e:
                merlin_logger.error(f"Redis get error: {e}")
                return None
        return self._memory_cache.get(key)

    def set(self, key: str, value: Any, expire: int = 3600):
        if self.client:
            try:
                self.client.set(key, json.dumps(value), ex=expire)
            except Exception as e:
                merlin_logger.error(f"Redis set error: {e}")
        else:
            self._memory_cache[key] = value

    def delete(self, key: str):
        if self.client:
            try:
                self.client.delete(key)
            except Exception as e:
                merlin_logger.error(f"Redis delete error: {e}")
        else:
            self._memory_cache.pop(key, None)


merlin_cache = MerlinCache()
