import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ..models import RepoBase
from .helpers import _retry_on_lock, _row_to_repo
from .pool import get_connection


@_retry_on_lock()
async def update_classification(
    full_name: str,
    category: str,
    subcategory: str,
    confidence: float,
    tags: List[str],
    tag_ids: Optional[List[str]],
    provider: str,
    model: str,
    summary_zh: Optional[str] = None,
    keywords: Optional[List[str]] = None,
    reason: Optional[str] = None,
    decision_source: Optional[str] = None,
    rule_candidates: Optional[List[Dict[str, Any]]] = None,
) -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    serialized_tag_ids = json.dumps(tag_ids or [], ensure_ascii=False)
    serialized_rule_candidates = (
        json.dumps(rule_candidates, ensure_ascii=False) if rule_candidates is not None else None
    )
    async with get_connection() as conn:
        if summary_zh is not None or keywords is not None:
            await conn.execute(
                """
                UPDATE repos
                SET category = ?, subcategory = ?, ai_confidence = ?, ai_tags = ?, ai_tag_ids = ?,
                    ai_provider = ?, ai_model = ?, ai_reason = ?, ai_decision_source = ?,
                    ai_rule_candidates = COALESCE(?, ai_rule_candidates),
                    ai_updated_at = ?, classify_fail_count = 0,
                    summary_zh = ?, ai_keywords = ?
                WHERE full_name = ?
                """,
                (
                    category,
                    subcategory,
                    confidence,
                    json.dumps(tags, ensure_ascii=False),
                    serialized_tag_ids,
                    provider,
                    model,
                    reason,
                    decision_source,
                    serialized_rule_candidates,
                    timestamp,
                    summary_zh,
                    json.dumps(keywords, ensure_ascii=False) if keywords is not None else None,
                    full_name,
                ),
            )
        else:
            await conn.execute(
                """
                UPDATE repos
                SET category = ?, subcategory = ?, ai_confidence = ?, ai_tags = ?, ai_tag_ids = ?,
                    ai_provider = ?, ai_model = ?, ai_reason = ?, ai_decision_source = ?,
                    ai_rule_candidates = COALESCE(?, ai_rule_candidates),
                    ai_updated_at = ?, classify_fail_count = 0
                WHERE full_name = ?
                """,
                (
                    category,
                    subcategory,
                    confidence,
                    json.dumps(tags, ensure_ascii=False),
                    serialized_tag_ids,
                    provider,
                    model,
                    reason,
                    decision_source,
                    serialized_rule_candidates,
                    timestamp,
                    full_name,
                ),
            )
        await conn.commit()


@_retry_on_lock()
async def update_classifications_bulk(items: List[Dict[str, Any]]) -> int:
    if not items:
        return 0
    timestamp = datetime.now(timezone.utc).isoformat()
    rows: List[Tuple[Any, ...]] = []
    for item in items:
        full_name = item.get("full_name")
        if not full_name:
            continue
        keywords = item.get("keywords")
        rule_candidates = item.get("rule_candidates")
        rows.append(
            (
                item.get("category"),
                item.get("subcategory"),
                item.get("confidence", 0.0),
                json.dumps(item.get("tags") or [], ensure_ascii=False),
                json.dumps(item.get("tag_ids") or [], ensure_ascii=False),
                item.get("provider"),
                item.get("model"),
                item.get("reason"),
                item.get("decision_source"),
                json.dumps(rule_candidates, ensure_ascii=False) if rule_candidates is not None else None,
                timestamp,
                item.get("summary_zh"),
                json.dumps(keywords, ensure_ascii=False) if keywords is not None else None,
                full_name,
            )
        )
    if not rows:
        return 0
    async with get_connection() as conn:
        try:
            await conn.executemany(
                """
                UPDATE repos
                SET category = ?, subcategory = ?, ai_confidence = ?, ai_tags = ?, ai_tag_ids = ?,
                    ai_provider = ?, ai_model = ?, ai_reason = ?, ai_decision_source = ?,
                    ai_rule_candidates = COALESCE(?, ai_rule_candidates),
                    ai_updated_at = ?, classify_fail_count = 0,
                    summary_zh = ?, ai_keywords = ?
                WHERE full_name = ?
                """,
                rows,
            )
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
    return len(rows)


async def select_repos_for_classification(
    limit: int, force: bool, after_full_name: Optional[str] = None
) -> List[RepoBase]:
    where = "WHERE NULLIF(override_category, '') IS NULL AND (classify_fail_count IS NULL OR classify_fail_count < 5)"
    if not force:
        where += " AND (category IS NULL OR ai_updated_at IS NULL OR ai_updated_at < pushed_at)"
    params: List[Any] = []
    order_by = """
        ORDER BY
            category IS NULL DESC,
            ai_updated_at IS NULL DESC,
            pushed_at IS NULL,
            pushed_at DESC,
            stargazers_count DESC
    """
    if force:
        order_by = "ORDER BY full_name ASC"
        if after_full_name:
            where += " AND full_name > ?"
            params.append(after_full_name)
    effective_limit = limit if limit and limit > 0 else -1
    async with get_connection() as conn:
        rows = await (await conn.execute(
            f"""
            SELECT
                full_name, name, owner, html_url, description, language,
                stargazers_count, forks_count, topics, pushed_at, updated_at, starred_at,
                star_users,
                category, subcategory, ai_confidence, ai_tags, ai_tag_ids, ai_provider, ai_model,
                ai_reason, ai_decision_source, ai_rule_candidates, ai_updated_at,
                override_category, override_subcategory, override_tags, override_tag_ids,
                override_note, readme_summary, readme_fetched_at, readme_last_attempt_at,
                readme_failures, readme_empty,
                summary_zh, ai_keywords, override_summary_zh, override_keywords
            FROM repos
            {where}
            {order_by}
            LIMIT ?
            """,
            params + [effective_limit],
        )).fetchall()
    return [_row_to_repo(row, include_internal=True) for row in rows]


async def count_unclassified_repos() -> int:
    where = (
        "WHERE NULLIF(override_category, '') IS NULL "
        "AND NULLIF(category, '') IS NULL"
    )
    async with get_connection() as conn:
        row = await (await conn.execute(f"SELECT COUNT(*) FROM repos {where}")).fetchone()
    return int(row[0] or 0)


async def count_repos_for_classification(force: bool, after_full_name: Optional[str] = None) -> int:
    where = "WHERE NULLIF(override_category, '') IS NULL AND (classify_fail_count IS NULL OR classify_fail_count < 5)"
    if not force:
        where += " AND (category IS NULL OR ai_updated_at IS NULL OR ai_updated_at < pushed_at)"
    elif after_full_name:
        where += " AND full_name > ?"
    params: List[Any] = []
    if force and after_full_name:
        params.append(after_full_name)
    async with get_connection() as conn:
        row = await (await conn.execute(
            f"SELECT COUNT(*) FROM repos {where}",
            params,
        )).fetchone()
    return int(row[0] or 0)


@_retry_on_lock()
async def increment_classify_fail_count(full_names: List[str]) -> None:
    if not full_names:
        return
    async with get_connection() as conn:
        placeholders = ",".join("?" for _ in full_names)
        await conn.execute(
            f"""
            UPDATE repos
            SET classify_fail_count = COALESCE(classify_fail_count, 0) + 1
            WHERE full_name IN ({placeholders})
            """,
            full_names,
        )
        await conn.commit()


@_retry_on_lock()
async def reset_classify_fail_count(full_names: Optional[List[str]] = None) -> int:
    async with get_connection() as conn:
        if full_names is None:
            result = await conn.execute(
                "UPDATE repos SET classify_fail_count = 0 WHERE classify_fail_count > 0"
            )
        else:
            if not full_names:
                return 0
            placeholders = ",".join("?" for _ in full_names)
            result = await conn.execute(
                f"UPDATE repos SET classify_fail_count = 0 WHERE full_name IN ({placeholders})",
                full_names,
            )
        await conn.commit()
        return result.rowcount


async def get_failed_repos(min_fail_count: int = 5) -> List[Dict[str, Any]]:
    async with get_connection() as conn:
        rows = await (await conn.execute(
            """
            SELECT full_name, name, owner, description, language, classify_fail_count
            FROM repos
            WHERE classify_fail_count >= ?
            ORDER BY classify_fail_count DESC, full_name ASC
            """,
            (min_fail_count,),
        )).fetchall()
    return [
        {
            "full_name": row["full_name"],
            "name": row["name"],
            "owner": row["owner"],
            "description": row["description"],
            "language": row["language"],
            "classify_fail_count": row["classify_fail_count"],
        }
        for row in rows
    ]
