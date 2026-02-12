import json
from datetime import datetime, timezone
from typing import Any, Dict, List

from .helpers import _load_json_list, _retry_on_lock
from .pool import get_connection


@_retry_on_lock()
async def update_override(full_name: str, updates: Dict[str, Any]) -> bool:
    if not updates:
        return False

    mapping = {
        "category": "override_category",
        "subcategory": "override_subcategory",
        "tags": "override_tags",
        "tag_ids": "override_tag_ids",
        "note": "override_note",
    }
    sets = []
    params: List[Any] = []

    for key, value in updates.items():
        column = mapping.get(key)
        if not column:
            continue
        if key in ("tags", "tag_ids"):
            params.append(json.dumps(value, ensure_ascii=False) if value is not None else None)
        else:
            params.append(value)
        sets.append(f"{column} = ?")

    if not sets:
        return False

    params.append(full_name)
    async with get_connection() as conn:
        before = await (await conn.execute(
            """
            SELECT
                COALESCE(NULLIF(override_category, ''), category) AS category,
                COALESCE(NULLIF(override_subcategory, ''), subcategory) AS subcategory,
                COALESCE(NULLIF(override_tag_ids, ''), ai_tag_ids) AS tag_ids
            FROM repos
            WHERE full_name = ?
            """,
            (full_name,),
        )).fetchone()
        cur = await conn.execute(
            f"UPDATE repos SET {', '.join(sets)} WHERE full_name = ?",
            params,
        )
        if cur.rowcount > 0:
            timestamp = datetime.now(timezone.utc).isoformat()
            row = await (await conn.execute(
                """
                SELECT
                    override_category, override_subcategory, override_tags, override_tag_ids, override_note,
                    COALESCE(NULLIF(override_category, ''), category) AS effective_category,
                    COALESCE(NULLIF(override_subcategory, ''), subcategory) AS effective_subcategory,
                    COALESCE(NULLIF(override_tag_ids, ''), ai_tag_ids) AS effective_tag_ids
                FROM repos
                WHERE full_name = ?
                """,
                (full_name,),
            )).fetchone()
            if row:
                await conn.execute(
                    """
                    INSERT INTO override_history
                        (full_name, category, subcategory, tags, note, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        full_name,
                        row["override_category"],
                        row["override_subcategory"],
                        row["override_tags"],
                        row["override_note"],
                        timestamp,
                    ),
                )
                await conn.execute(
                    """
                    INSERT INTO training_samples (
                        user_id,
                        full_name,
                        before_category,
                        before_subcategory,
                        before_tag_ids,
                        after_category,
                        after_subcategory,
                        after_tag_ids,
                        note,
                        source,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "global",
                        full_name,
                        before["category"] if before else None,
                        before["subcategory"] if before else None,
                        before["tag_ids"] if before else None,
                        row["effective_category"],
                        row["effective_subcategory"],
                        row["effective_tag_ids"],
                        row["override_note"],
                        "manual_override",
                        timestamp,
                    ),
                )
        await conn.commit()
        return cur.rowcount > 0


async def list_override_history(full_name: str) -> List[Dict[str, Any]]:
    async with get_connection() as conn:
        rows = await (await conn.execute(
            """
            SELECT category, subcategory, tags, note, updated_at
            FROM override_history
            WHERE full_name = ?
            ORDER BY updated_at DESC, id DESC
            """,
            (full_name,),
        )).fetchall()
    results: List[Dict[str, Any]] = []
    for row in rows:
        results.append(
            {
                "category": row["category"],
                "subcategory": row["subcategory"],
                "tags": _load_json_list(row["tags"]),
                "note": row["note"],
                "updated_at": row["updated_at"],
            }
        )
    return results
