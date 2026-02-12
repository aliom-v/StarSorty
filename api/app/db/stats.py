from typing import Any, Dict

from .pool import get_connection


async def get_repo_stats() -> Dict[str, Any]:
    async with get_connection() as conn:
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
