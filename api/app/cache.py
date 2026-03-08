import asyncio
import time
from typing import Any, Optional


async def _record_cache_metric(hit: bool) -> None:
    try:
        from .state import _add_quality_metrics
    except Exception:
        return
    await _add_quality_metrics(
        cache_hit_total=1 if hit else 0,
        cache_miss_total=0 if hit else 1,
    )


class SimpleCache:
    """Simple in-memory cache with TTL support."""

    def __init__(self):
        self._cache: dict[str, tuple[Any, float]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        hit = False
        value: Optional[Any] = None
        async with self._lock:
            if key in self._cache:
                cached_value, expires_at = self._cache[key]
                if time.time() < expires_at:
                    value = cached_value
                    hit = True
                else:
                    del self._cache[key]
            if not hit:
                value = None
        await _record_cache_metric(hit)
        return value

    async def set(self, key: str, value: Any, ttl: int = 60) -> None:
        async with self._lock:
            self._cache[key] = (value, time.time() + ttl)

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._cache.pop(key, None)

    async def clear(self) -> None:
        async with self._lock:
            self._cache.clear()

    async def invalidate_prefix(self, prefix: str) -> None:
        async with self._lock:
            keys_to_delete = [k for k in self._cache if k.startswith(prefix)]
            for key in keys_to_delete:
                del self._cache[key]


cache = SimpleCache()

CACHE_TTL_STATS = 30
CACHE_TTL_REPOS = 15
