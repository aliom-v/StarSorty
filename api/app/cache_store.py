import json
import time
from typing import Any

from .db.pool import get_connection

_CACHE_VERSION_PREFIX = "cache_version:"


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
