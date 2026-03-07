import json
from datetime import datetime, timezone
from typing import Any, Dict

from .pool import get_connection


REPO_STATS_VERSION_KEY = "repo_stats_version"
REPO_STATS_SNAPSHOT_KEY = "repo_stats"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


async def _get_repo_stats_version(conn) -> int:
    row = await (
        await conn.execute(
            "SELECT value FROM app_settings WHERE key = ?",
            (REPO_STATS_VERSION_KEY,),
        )
    ).fetchone()
    if not row:
        return 0
    return _parse_version(row["value"])


async def bump_repo_stats_version(conn) -> int:
    next_version = await _get_repo_stats_version(conn) + 1
    await conn.execute(
        """
        INSERT INTO app_settings (key, value, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = CURRENT_TIMESTAMP
        """,
        (REPO_STATS_VERSION_KEY, json.dumps(next_version)),
    )
    return next_version


async def _load_repo_stats_snapshot(conn, version: int) -> Dict[str, Any] | None:
    row = await (
        await conn.execute(
            """
            SELECT version, payload
            FROM stats_snapshots
            WHERE snapshot_key = ?
            """,
            (REPO_STATS_SNAPSHOT_KEY,),
        )
    ).fetchone()
    if not row:
        return None
    row_version = row["version"]
    if row_version is None or int(row_version) != version:
        return None
    try:
        payload = json.loads(row["payload"])
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


async def _store_repo_stats_snapshot(conn, version: int, payload: Dict[str, Any]) -> None:
    await conn.execute(
        """
        INSERT INTO stats_snapshots (snapshot_key, version, payload, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(snapshot_key) DO UPDATE SET
            version = excluded.version,
            payload = excluded.payload,
            updated_at = excluded.updated_at
        """,
        (
            REPO_STATS_SNAPSHOT_KEY,
            version,
            json.dumps(payload, ensure_ascii=False),
            _now_iso(),
        ),
    )


async def _compute_repo_stats(conn) -> Dict[str, Any]:
    total = (await (await conn.execute("SELECT COUNT(*) FROM repos")).fetchone())[0]
    unclassified = (await (await conn.execute(
        """
        SELECT COUNT(*)
        FROM repos
        WHERE NULLIF(override_category, '') IS NULL
          AND NULLIF(category, '') IS NULL
        """
    )).fetchone())[0]
    category_rows = await (await conn.execute(
        """
        SELECT
            COALESCE(NULLIF(override_category, ''), NULLIF(category, ''), 'uncategorized') AS name,
            COUNT(*) AS count
        FROM repos
        GROUP BY
            COALESCE(NULLIF(override_category, ''), NULLIF(category, ''), 'uncategorized')
        ORDER BY count DESC, name ASC
        """
    )).fetchall()
    subcategory_rows = await (await conn.execute(
        """
        SELECT
            COALESCE(NULLIF(override_category, ''), NULLIF(category, ''), 'uncategorized') AS category,
            COALESCE(NULLIF(override_subcategory, ''), NULLIF(subcategory, ''), 'other') AS name,
            COUNT(*) AS count
        FROM repos
        GROUP BY
            COALESCE(NULLIF(override_category, ''), NULLIF(category, ''), 'uncategorized'),
            COALESCE(NULLIF(override_subcategory, ''), NULLIF(subcategory, ''), 'other')
        ORDER BY count DESC, name ASC
        """
    )).fetchall()
    tag_rows = await (await conn.execute(
        """
        SELECT tag.value AS name, COUNT(*) AS count
        FROM repos, json_each(
            CASE
                WHEN override_tags IS NOT NULL AND override_tags != '' AND override_tags != 'null'
                THEN override_tags
                ELSE COALESCE(ai_tags, '[]')
            END
        ) AS tag
        WHERE tag.value IS NOT NULL AND tag.value != ''
        GROUP BY tag.value
        ORDER BY count DESC, name ASC
        """
    )).fetchall()
    user_rows = await (await conn.execute(
        """
        SELECT user.value AS name, COUNT(*) AS count
        FROM repos, json_each(COALESCE(star_users, '[]')) AS user
        WHERE user.value IS NOT NULL AND user.value != ''
        GROUP BY user.value
        ORDER BY count DESC, name ASC
        """
    )).fetchall()

    category_counts = [
        {"name": row["name"], "count": int(row["count"] or 0)}
        for row in category_rows
    ]
    subcategory_counts = [
        {
            "category": row["category"],
            "name": row["name"],
            "count": int(row["count"] or 0),
        }
        for row in subcategory_rows
    ]
    tag_counts = [
        {"name": row["name"], "count": int(row["count"] or 0)}
        for row in tag_rows
    ]
    user_counts = [
        {"name": row["name"], "count": int(row["count"] or 0)}
        for row in user_rows
    ]

    return {
        "total": int(total or 0),
        "unclassified": int(unclassified or 0),
        "categories": category_counts,
        "subcategories": subcategory_counts,
        "tags": tag_counts,
        "users": user_counts,
    }


async def get_repo_stats(refresh: bool = False, use_snapshot: bool = True) -> Dict[str, Any]:
    async with get_connection() as conn:
        version = await _get_repo_stats_version(conn)
        if use_snapshot and not refresh:
            snapshot = await _load_repo_stats_snapshot(conn, version)
            if snapshot is not None:
                return snapshot

        payload = await _compute_repo_stats(conn)
        await _store_repo_stats_snapshot(conn, version, payload)
        await conn.commit()
        return payload
