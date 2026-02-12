import json
import math
from typing import Any, Dict, List, Optional, Tuple

from ..models import RepoBase
from ..search.ranker import rank_repo_matches
from .helpers import (
    _build_fts_query,
    _escape_like,
    _interest_boost,
    _load_json_list,
    _parse_sort_timestamp,
    _row_to_repo,
)
from .pool import get_connection
from .schema import is_fts_enabled


async def list_repos(
    q: Optional[str] = None,
    language: Optional[str] = None,
    min_stars: Optional[int] = None,
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    tag: Optional[str] = None,
    tags: Optional[List[str]] = None,
    tag_mode: str = "or",
    sort: str = "stars",
    topic_scores: Optional[Dict[str, float]] = None,
    star_user: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[int, List[RepoBase]]:
    clauses = []
    params: List[Any] = []

    if q:
        fts_query = _build_fts_query(q) if is_fts_enabled() else None
        if fts_query:
            clauses.append("id IN (SELECT rowid FROM repos_fts WHERE repos_fts MATCH ?)")
            params.append(fts_query)
        else:
            escaped_q = _escape_like(q)
            like = f"%{escaped_q}%"
            clauses.append(
                "("
                "name LIKE ? ESCAPE '\\' OR full_name LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\' "
                "OR topics LIKE ? ESCAPE '\\' OR ai_tags LIKE ? ESCAPE '\\' OR override_tags LIKE ? ESCAPE '\\' "
                "OR ai_tag_ids LIKE ? ESCAPE '\\' OR override_tag_ids LIKE ? ESCAPE '\\' "
                "OR readme_summary LIKE ? ESCAPE '\\' OR star_users LIKE ? ESCAPE '\\' OR summary_zh LIKE ? ESCAPE '\\' "
                "OR override_summary_zh LIKE ? ESCAPE '\\' OR ai_keywords LIKE ? ESCAPE '\\' "
                "OR override_keywords LIKE ? ESCAPE '\\'"
                ")"
            )
            params.extend([like] * 14)

    if language:
        clauses.append("language = ?")
        params.append(language)

    if min_stars is not None:
        clauses.append("stargazers_count >= ?")
        params.append(min_stars)

    if category:
        clauses.append("COALESCE(NULLIF(override_category, ''), category) = ?")
        params.append(category)

    if subcategory:
        clauses.append("COALESCE(NULLIF(override_subcategory, ''), subcategory) = ?")
        params.append(subcategory)

    if tag:
        clauses.append(
            "("
            "COALESCE(NULLIF(override_tag_ids, ''), ai_tag_ids, '') LIKE ? "
            "OR COALESCE(NULLIF(override_tags, ''), ai_tags, '') LIKE ?"
            ")"
        )
        params.append(f"%\"{tag}\"%")
        params.append(f"%\"{tag}\"%")

    if tags:
        tag_clauses = []
        for t in tags:
            tag_clauses.append(
                "("
                "COALESCE(NULLIF(override_tag_ids, ''), ai_tag_ids, '') LIKE ? "
                "OR COALESCE(NULLIF(override_tags, ''), ai_tags, '') LIKE ?"
                ")"
            )
            params.append(f'%"{t}"%')
            params.append(f'%"{t}"%')
        joiner = " AND " if str(tag_mode).lower() == "and" else " OR "
        clauses.append("(" + joiner.join(tag_clauses) + ")")

    if star_user:
        clauses.append("star_users LIKE ?")
        params.append(f"%\"{star_user}\"%")

    where_sql = ""
    if clauses:
        where_sql = "WHERE " + " AND ".join(clauses)

    select_sql = f"""
        SELECT
            full_name, name, owner, html_url, description, language,
            stargazers_count, forks_count, topics, pushed_at, updated_at, starred_at,
            star_users,
            category, subcategory, ai_confidence, ai_tags, ai_tag_ids, ai_provider, ai_model,
            ai_reason, ai_decision_source, ai_rule_candidates, ai_updated_at,
            override_category, override_subcategory, override_tags, override_tag_ids,
            override_note, readme_summary, readme_fetched_at,
            summary_zh, ai_keywords, override_summary_zh, override_keywords
        FROM repos
        {where_sql}
    """
    normalized_sort = str(sort or "stars").strip().lower()
    if normalized_sort not in ("relevance", "stars", "updated"):
        normalized_sort = "stars"

    async with get_connection() as conn:
        total = (await (await conn.execute(
            f"SELECT COUNT(*) FROM repos {where_sql}", params
        )).fetchone())[0]
        if normalized_sort == "updated":
            rows = await (await conn.execute(
                f"""
                {select_sql}
                ORDER BY updated_at DESC, stargazers_count DESC, full_name ASC
                LIMIT ? OFFSET ?
                """,
                params + [limit, offset],
            )).fetchall()
            return total, [_row_to_repo(row) for row in rows]

        if normalized_sort != "relevance" or not q:
            rows = await (await conn.execute(
                f"""
                {select_sql}
                ORDER BY stargazers_count DESC, full_name ASC
                LIMIT ? OFFSET ?
                """,
                params + [limit, offset],
            )).fetchall()
            return total, [_row_to_repo(row) for row in rows]

        rows = await (await conn.execute(
            f"""
            {select_sql}
            ORDER BY stargazers_count DESC, full_name ASC
            """,
            params,
        )).fetchall()

    ranked_rows: List[Dict[str, Any]] = []
    for row in rows:
        row_dict: Dict[str, Any] = dict(row)
        score, reasons = rank_repo_matches(row_dict, q or "")
        personalization = _interest_boost(row_dict, topic_scores or {})
        if personalization > 0:
            score += personalization
            reasons.append("interest_profile")
        row_dict["search_score"] = score
        row_dict["match_reasons"] = json.dumps(reasons, ensure_ascii=False)
        ranked_rows.append(row_dict)

    ranked_rows.sort(
        key=lambda item: (
            -float(item.get("search_score") or 0.0),
            -int(item.get("stargazers_count") or 0),
            -(math.floor(_parse_sort_timestamp(item.get("updated_at")))),
            str(item.get("full_name") or ""),
        )
    )
    paged_rows = ranked_rows[offset : offset + limit]
    return total, [_row_to_repo(row) for row in paged_rows]


async def iter_repos_for_export(
    language: Optional[str] = None,
    tags: Optional[List[str]] = None,
    batch_size: int = 500,
):
    clauses = []
    params: List[Any] = []

    if language:
        clauses.append("language = ?")
        params.append(language)

    if tags:
        tag_clauses = []
        for t in tags:
            tag_clauses.append(
                "("
                "COALESCE(NULLIF(override_tag_ids, ''), ai_tag_ids, '') LIKE ? "
                "OR COALESCE(NULLIF(override_tags, ''), ai_tags, '') LIKE ?"
                ")"
            )
            params.append(f'%"{t}"%')
            params.append(f'%"{t}"%')
        clauses.append("(" + " OR ".join(tag_clauses) + ")")

    cursor_stars: Optional[int] = None
    cursor_full_name: Optional[str] = None

    while True:
        page_clauses = list(clauses)
        page_params = list(params)

        if cursor_full_name is not None and cursor_stars is not None:
            page_clauses.append(
                "("
                "COALESCE(stargazers_count, -1) < ? "
                "OR (COALESCE(stargazers_count, -1) = ? AND full_name > ?)"
                ")"
            )
            page_params.extend([cursor_stars, cursor_stars, cursor_full_name])

        page_where_sql = ""
        if page_clauses:
            page_where_sql = "WHERE " + " AND ".join(page_clauses)

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
                    override_note, readme_summary, readme_fetched_at,
                    summary_zh, ai_keywords, override_summary_zh, override_keywords
                FROM repos
                {page_where_sql}
                ORDER BY stargazers_count DESC, full_name ASC
                LIMIT ?
                """,
                page_params + [batch_size],
            )).fetchall()

        if not rows:
            break

        for row in rows:
            yield _row_to_repo(row)

        if len(rows) < batch_size:
            break

        last = rows[-1]
        cursor_stars = int(last["stargazers_count"] or -1)
        cursor_full_name = str(last["full_name"])
