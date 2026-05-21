import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger("starsorty.cache")


async def _record_cache_metric(source: str) -> None:
    try:
        from .state import _add_quality_metrics
    except Exception:
        return
    normalized = str(source or "miss").strip().lower()
    if normalized == "local":
        await _add_quality_metrics(cache_hit_total=1, cache_local_hit_total=1)
    elif normalized == "shared":
        await _add_quality_metrics(cache_hit_total=1, cache_shared_hit_total=1)
    else:
        await _add_quality_metrics(cache_miss_total=1)


class SimpleCache:
    """Process-local cache for repo list responses with TTL support."""

    def __init__(self):
        self._cache: dict[str, "_CacheEntry"] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        source = "miss"
        value: Optional[Any] = None
        entry: _CacheEntry | None = None
        namespace = _cache_namespace_for_key(key)
        namespace_version: int | None = None
        async with self._lock:
            entry = self._cache.get(key)
            if entry is not None and time.time() >= entry.expires_at:
                self._cache.pop(key, None)
                entry = None
        if entry is not None and entry.namespace is not None:
            namespace_version = await _try_get_shared_cache_namespace_version(
                entry.namespace
            )
            if namespace_version is None or namespace_version != entry.namespace_version:
                async with self._lock:
                    if self._cache.get(key) is entry:
                        self._cache.pop(key, None)
                entry = None
        if entry is not None:
            value = entry.value
            source = "local"
        elif namespace is not None:
            if namespace_version is None:
                namespace_version = await _try_get_shared_cache_namespace_version(
                    namespace
                )
            if namespace_version is not None:
                shared_entry = await _try_load_shared_cache_entry(key)
                if shared_entry is not None:
                    shared_namespace = str(shared_entry.get("namespace") or "")
                    shared_version = int(shared_entry.get("namespace_version") or 0)
                    shared_value = shared_entry.get("payload")
                    shared_expires_at = float(shared_entry.get("expires_at") or 0.0)
                    if (
                        shared_namespace == namespace
                        and shared_version == namespace_version
                        and time.time() < shared_expires_at
                    ):
                        entry = _CacheEntry(
                            value=shared_value,
                            expires_at=shared_expires_at,
                            namespace=namespace,
                            namespace_version=shared_version,
                        )
                        async with self._lock:
                            self._cache[key] = entry
                        value = shared_value
                        source = "shared"
                    else:
                        await _try_delete_shared_cache_entry(key)
        await _record_cache_metric(source)
        return value

    async def set(self, key: str, value: Any, ttl: int = 60) -> None:
        namespace = _cache_namespace_for_key(key)
        namespace_version: int | None = None
        if namespace is not None:
            namespace_version = await _try_get_shared_cache_namespace_version(namespace)
        expires_at = time.time() + ttl
        entry_namespace = namespace if namespace_version is not None else None
        entry_namespace_version = int(namespace_version or 0)
        async with self._lock:
            self._cache[key] = _CacheEntry(
                value=value,
                expires_at=expires_at,
                namespace=entry_namespace,
                namespace_version=entry_namespace_version,
            )
        if namespace is not None and namespace_version is not None:
            await _try_store_shared_cache_entry(
                key,
                namespace=namespace,
                namespace_version=namespace_version,
                value=value,
                expires_at=expires_at,
            )

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._cache.pop(key, None)
        namespace = _cache_namespace_for_key(key)
        if namespace is not None:
            await _try_delete_shared_cache_entry(key)

    async def clear(self) -> None:
        async with self._lock:
            self._cache.clear()

    async def invalidate_prefix(self, prefix: str) -> None:
        async with self._lock:
            keys_to_delete = [k for k in self._cache if k.startswith(prefix)]
            for key in keys_to_delete:
                del self._cache[key]
        namespace = _cache_namespace_for_prefix(prefix)
        if namespace is not None:
            await _try_delete_shared_cache_namespace(namespace)
            await _try_bump_shared_cache_namespace_version(namespace)


@dataclass(slots=True)
class _CacheEntry:
    value: Any
    expires_at: float
    namespace: str | None
    namespace_version: int


def _cache_namespace_for_key(key: str) -> str | None:
    if key == "repos" or key.startswith("repos:"):
        return "repos"
    return None


def _cache_namespace_for_prefix(prefix: str) -> str | None:
    normalized = str(prefix or "").strip().lower()
    if normalized == "repos":
        return normalized
    return None


async def _try_get_shared_cache_namespace_version(namespace: str) -> int | None:
    from .cache_store import get_cache_namespace_version

    try:
        return await get_cache_namespace_version(namespace)
    except Exception as exc:
        logger.warning(
            "Shared cache namespace version lookup failed for %s: %s",
            namespace,
            exc,
        )
        return None


async def _try_bump_shared_cache_namespace_version(namespace: str) -> None:
    from .cache_store import bump_cache_namespace_version

    try:
        await bump_cache_namespace_version(namespace)
    except Exception as exc:
        logger.warning("Shared cache namespace bump failed for %s: %s", namespace, exc)


async def _try_load_shared_cache_entry(key: str) -> dict[str, Any] | None:
    from .cache_store import load_shared_cache_entry

    try:
        return await load_shared_cache_entry(key)
    except Exception as exc:
        logger.warning("Shared cache load failed for %s: %s", key, exc)
        return None


async def _try_store_shared_cache_entry(
    key: str,
    *,
    namespace: str,
    namespace_version: int,
    value: Any,
    expires_at: float,
) -> None:
    from .cache_store import store_shared_cache_entry

    try:
        await store_shared_cache_entry(
            key,
            namespace=namespace,
            namespace_version=namespace_version,
            payload=value,
            expires_at=expires_at,
        )
    except Exception as exc:
        logger.warning("Shared cache store failed for %s: %s", key, exc)


async def _try_delete_shared_cache_entry(key: str) -> None:
    from .cache_store import delete_shared_cache_entry

    try:
        await delete_shared_cache_entry(key)
    except Exception as exc:
        logger.warning("Shared cache delete failed for %s: %s", key, exc)


async def _try_delete_shared_cache_namespace(namespace: str) -> None:
    from .cache_store import delete_shared_cache_namespace

    try:
        await delete_shared_cache_namespace(namespace)
    except Exception as exc:
        logger.warning(
            "Shared cache namespace delete failed for %s: %s",
            namespace,
            exc,
        )


cache = SimpleCache()

CACHE_TTL_REPOS = 15
