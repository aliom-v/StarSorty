import json
import os
import time
from typing import Any

from .db.pool import get_connection

_CACHE_VERSION_PREFIX = "cache_version:"
SHARED_CACHE_MAX_ENTRIES_PER_NAMESPACE = 500
SHARED_CACHE_MAX_BYTES_PER_NAMESPACE = 5 * 1024 * 1024
SHARED_CACHE_CLEANUP_BATCH_SIZE = 100


def _env_int(name: str, default: int, minimum: int = 0) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    if value < minimum:
        return default
    return value


SHARED_CACHE_MAX_ENTRIES_PER_NAMESPACE = _env_int(
    "SHARED_CACHE_MAX_ENTRIES_PER_NAMESPACE",
    SHARED_CACHE_MAX_ENTRIES_PER_NAMESPACE,
    minimum=1,
)
SHARED_CACHE_MAX_BYTES_PER_NAMESPACE = _env_int(
    "SHARED_CACHE_MAX_BYTES_PER_NAMESPACE",
    SHARED_CACHE_MAX_BYTES_PER_NAMESPACE,
    minimum=1,
)
SHARED_CACHE_CLEANUP_BATCH_SIZE = _env_int(
    "SHARED_CACHE_CLEANUP_BATCH_SIZE",
    SHARED_CACHE_CLEANUP_BATCH_SIZE,
    minimum=1,
)


def _cache_version_key(namespace: str) -> str:
    return f"{_CACHE_VERSION_PREFIX}{namespace}"


def _normalize_namespace(namespace: str) -> str:
    return str(namespace or "").strip().lower()


def _parse_version(value: Any) -> int:
    if value is None:
        return 0
    parsed = value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            parsed = value
    try:
        return int(parsed)
    except (TypeError, ValueError):
        return 0


def _normalize_limit(limit: int | None) -> int:
    try:
        parsed = int(limit or SHARED_CACHE_CLEANUP_BATCH_SIZE)
    except (TypeError, ValueError):
        return SHARED_CACHE_CLEANUP_BATCH_SIZE
    return max(1, parsed)


def _metrics_from_row(row: Any) -> dict[str, Any]:
    return {
        "entry_count": int(row["entry_count"] or 0),
        "expired_count": int(row["expired_count"] or 0),
        "approx_payload_bytes": int(row["approx_payload_bytes"] or 0),
        "oldest_expires_at": row["oldest_expires_at"],
        "newest_expires_at": row["newest_expires_at"],
        "last_updated_at": row["last_updated_at"],
    }


async def get_cache_namespace_version(namespace: str) -> int:
    normalized = _normalize_namespace(namespace)
    if not normalized:
        return 0
    async with get_connection() as conn:
        row = await (
            await conn.execute(
                "SELECT value FROM app_settings WHERE key = ?",
                (_cache_version_key(normalized),),
            )
        ).fetchone()
    if not row:
        return 0
    return _parse_version(row["value"])


async def bump_cache_namespace_version(namespace: str) -> None:
    normalized = _normalize_namespace(namespace)
    if not normalized:
        return
    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, '1', CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = CAST(COALESCE(CAST(app_settings.value AS INTEGER), 0) + 1 AS TEXT),
                updated_at = CURRENT_TIMESTAMP
            """,
            (_cache_version_key(normalized),),
        )
        await conn.commit()


async def load_shared_cache_entry(cache_key: str) -> dict[str, Any] | None:
    normalized_key = str(cache_key or "").strip()
    if not normalized_key:
        return None
    async with get_connection() as conn:
        row = await (
            await conn.execute(
                """
                SELECT namespace, namespace_version, payload, expires_at
                FROM cache_entries
                WHERE cache_key = ?
                """,
                (normalized_key,),
            )
        ).fetchone()
        if not row:
            return None
        expires_at = float(row["expires_at"] or 0.0)
        if time.time() >= expires_at:
            await conn.execute(
                "DELETE FROM cache_entries WHERE cache_key = ?",
                (normalized_key,),
            )
            await conn.commit()
            return None
    try:
        payload = json.loads(row["payload"])
    except Exception:
        await delete_shared_cache_entry(normalized_key)
        return None
    return {
        "namespace": _normalize_namespace(row["namespace"]),
        "namespace_version": _parse_version(row["namespace_version"]),
        "payload": payload,
        "expires_at": expires_at,
    }


async def store_shared_cache_entry(
    cache_key: str,
    *,
    namespace: str,
    namespace_version: int,
    payload: Any,
    expires_at: float,
    enforce_limits: bool = True,
) -> None:
    normalized_key = str(cache_key or "").strip()
    normalized_namespace = _normalize_namespace(namespace)
    if not normalized_key or not normalized_namespace:
        return
    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO cache_entries (
                cache_key,
                namespace,
                namespace_version,
                payload,
                expires_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(cache_key) DO UPDATE SET
                namespace = excluded.namespace,
                namespace_version = excluded.namespace_version,
                payload = excluded.payload,
                expires_at = excluded.expires_at,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                normalized_key,
                normalized_namespace,
                int(namespace_version),
                json.dumps(payload, ensure_ascii=False),
                float(expires_at),
            ),
        )
        await conn.commit()
    if enforce_limits:
        await enforce_shared_cache_limits(normalized_namespace)


async def delete_shared_cache_entry(cache_key: str) -> None:
    normalized_key = str(cache_key or "").strip()
    if not normalized_key:
        return
    async with get_connection() as conn:
        await conn.execute(
            "DELETE FROM cache_entries WHERE cache_key = ?",
            (normalized_key,),
        )
        await conn.commit()


async def delete_shared_cache_namespace(namespace: str) -> None:
    normalized = _normalize_namespace(namespace)
    if not normalized:
        return
    async with get_connection() as conn:
        await conn.execute(
            "DELETE FROM cache_entries WHERE namespace = ?",
            (normalized,),
        )
        await conn.commit()


async def cleanup_expired_shared_cache_entries(
    *,
    namespace: str | None = None,
    now: float | None = None,
    limit: int | None = None,
) -> int:
    normalized = _normalize_namespace(namespace) if namespace is not None else None
    current_time = time.time() if now is None else float(now)
    batch_limit = _normalize_limit(limit)
    clauses = ["expires_at <= ?"]
    params: list[Any] = [current_time]
    if normalized:
        clauses.append("namespace = ?")
        params.append(normalized)
    where_sql = " AND ".join(clauses)
    async with get_connection() as conn:
        before = conn.total_changes
        await conn.execute(
            f"""
            DELETE FROM cache_entries
            WHERE rowid IN (
                SELECT rowid
                FROM cache_entries
                WHERE {where_sql}
                ORDER BY expires_at ASC, updated_at ASC, cache_key ASC
                LIMIT ?
            )
            """,
            (*params, batch_limit),
        )
        await conn.commit()
        return max(0, conn.total_changes - before)


async def enforce_shared_cache_limits(
    namespace: str,
    *,
    max_entries: int = SHARED_CACHE_MAX_ENTRIES_PER_NAMESPACE,
    max_bytes: int = SHARED_CACHE_MAX_BYTES_PER_NAMESPACE,
    now: float | None = None,
) -> int:
    normalized = _normalize_namespace(namespace)
    if not normalized:
        return 0
    deleted = await cleanup_expired_shared_cache_entries(
        namespace=normalized,
        now=now,
        limit=SHARED_CACHE_CLEANUP_BATCH_SIZE,
    )
    max_entry_count = max(1, int(max_entries))
    max_byte_count = max(1, int(max_bytes))
    current_time = time.time() if now is None else float(now)
    async with get_connection() as conn:
        while True:
            row = await (
                await conn.execute(
                    """
                    SELECT
                        COUNT(*) AS entry_count,
                        COALESCE(SUM(LENGTH(payload)), 0) AS approx_payload_bytes,
                        COALESCE(SUM(CASE WHEN expires_at <= ? THEN 1 ELSE 0 END), 0)
                            AS expired_count,
                        MIN(expires_at) AS oldest_expires_at,
                        MAX(expires_at) AS newest_expires_at,
                        MAX(updated_at) AS last_updated_at
                    FROM cache_entries
                    WHERE namespace = ?
                    """,
                    (current_time, normalized),
                )
            ).fetchone()
            if not row:
                break
            entry_count = int(row["entry_count"] or 0)
            approx_payload_bytes = int(row["approx_payload_bytes"] or 0)
            over_entries = max(0, entry_count - max_entry_count)
            over_bytes = approx_payload_bytes > max_byte_count
            if over_entries == 0 and not over_bytes:
                break
            batch_limit = over_entries if over_entries > 0 else 1
            batch_limit = max(1, min(batch_limit, SHARED_CACHE_CLEANUP_BATCH_SIZE))
            before = conn.total_changes
            await conn.execute(
                """
                DELETE FROM cache_entries
                WHERE rowid IN (
                    SELECT rowid
                    FROM cache_entries
                    WHERE namespace = ?
                    ORDER BY updated_at ASC, expires_at ASC, cache_key ASC
                    LIMIT ?
                )
                """,
                (normalized, batch_limit),
            )
            removed = max(0, conn.total_changes - before)
            deleted += removed
            if removed == 0:
                break
        await conn.commit()
    return deleted


async def get_shared_cache_metrics(
    *,
    namespace: str | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    normalized = _normalize_namespace(namespace) if namespace is not None else None
    current_time = time.time() if now is None else float(now)
    where_sql = "WHERE namespace = ?" if normalized else ""
    params: tuple[Any, ...] = (normalized,) if normalized else ()
    async with get_connection() as conn:
        total = await (
            await conn.execute(
                f"""
                SELECT
                    COUNT(*) AS entry_count,
                    COALESCE(SUM(LENGTH(payload)), 0) AS approx_payload_bytes,
                    COALESCE(SUM(CASE WHEN expires_at <= ? THEN 1 ELSE 0 END), 0)
                        AS expired_count,
                    MIN(expires_at) AS oldest_expires_at,
                    MAX(expires_at) AS newest_expires_at,
                    MAX(updated_at) AS last_updated_at
                FROM cache_entries
                {where_sql}
                """,
                (current_time, *params),
            )
        ).fetchone()
        rows = await (
            await conn.execute(
                f"""
                SELECT
                    namespace,
                    COUNT(*) AS entry_count,
                    COALESCE(SUM(LENGTH(payload)), 0) AS approx_payload_bytes,
                    COALESCE(SUM(CASE WHEN expires_at <= ? THEN 1 ELSE 0 END), 0)
                        AS expired_count,
                    MIN(expires_at) AS oldest_expires_at,
                    MAX(expires_at) AS newest_expires_at,
                    MAX(updated_at) AS last_updated_at
                FROM cache_entries
                {where_sql}
                GROUP BY namespace
                ORDER BY namespace
                """,
                (current_time, *params),
            )
        ).fetchall()

    namespaces: list[dict[str, Any]] = []
    for row in rows:
        item = _metrics_from_row(row)
        item["namespace"] = _normalize_namespace(row["namespace"])
        item["namespace_version"] = await get_cache_namespace_version(item["namespace"])
        namespaces.append(item)
    metrics = _metrics_from_row(total)
    metrics["namespaces"] = namespaces
    return metrics
