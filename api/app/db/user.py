import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiosqlite

from .helpers import _load_json_list, _retry_on_lock, _safe_json_dict
from .pool import get_connection


async def get_user_preferences(user_id: str = "global") -> Dict[str, Any]:
    normalized = str(user_id or "global").strip() or "global"
    async with get_connection() as conn:
        row = await (await conn.execute(
            """
            SELECT user_id, tag_mapping_json, rule_priority_json, updated_at
            FROM user_preferences
            WHERE user_id = ?
            """,
            (normalized,),
        )).fetchone()
    if not row:
        return {
            "user_id": normalized,
            "tag_mapping": {},
            "rule_priority": {},
            "updated_at": None,
        }
    return {
        "user_id": row["user_id"],
        "tag_mapping": _safe_json_dict(row["tag_mapping_json"]),
        "rule_priority": _safe_json_dict(row["rule_priority_json"]),
        "updated_at": row["updated_at"],
    }


@_retry_on_lock()
async def update_user_preferences(
    user_id: str,
    tag_mapping: Optional[Dict[str, str]] = None,
    rule_priority: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    normalized = str(user_id or "global").strip() or "global"
    current = await get_user_preferences(normalized)
    merged_tag_mapping = dict(current.get("tag_mapping") or {})
    merged_rule_priority = dict(current.get("rule_priority") or {})
    if tag_mapping is not None:
        merged_tag_mapping = {
            str(k): str(v)
            for k, v in tag_mapping.items()
            if str(k).strip() and str(v).strip()
        }
    if rule_priority is not None:
        filtered: Dict[str, int] = {}
        for key, value in rule_priority.items():
            k = str(key).strip()
            if not k:
                continue
            try:
                filtered[k] = int(value)
            except (TypeError, ValueError):
                continue
        merged_rule_priority = filtered

    timestamp = datetime.now(timezone.utc).isoformat()
    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO user_preferences (user_id, tag_mapping_json, rule_priority_json, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                tag_mapping_json = excluded.tag_mapping_json,
                rule_priority_json = excluded.rule_priority_json,
                updated_at = excluded.updated_at
            """,
            (
                normalized,
                json.dumps(merged_tag_mapping, ensure_ascii=False),
                json.dumps(merged_rule_priority, ensure_ascii=False),
                timestamp,
            ),
        )
        await conn.commit()

    return {
        "user_id": normalized,
        "tag_mapping": merged_tag_mapping,
        "rule_priority": merged_rule_priority,
        "updated_at": timestamp,
    }


def _extract_interest_terms(payload: Dict[str, Any]) -> Dict[str, float]:
    terms: Dict[str, float] = {}
    tags = payload.get("tags")
    if isinstance(tags, list):
        for tag in tags:
            token = str(tag).strip().lower()
            if token:
                terms[token] = terms.get(token, 0.0) + 2.0
    category = str(payload.get("category") or "").strip().lower()
    if category:
        terms[category] = terms.get(category, 0.0) + 1.5
    subcategory = str(payload.get("subcategory") or "").strip().lower()
    if subcategory:
        terms[subcategory] = terms.get(subcategory, 0.0) + 1.2
    keywords = payload.get("keywords")
    if isinstance(keywords, list):
        for item in keywords:
            token = str(item).strip().lower()
            if token:
                terms[token] = terms.get(token, 0.0) + 1.0
    query = str(payload.get("query") or "").strip().lower()
    if query:
        for token in re.split(r"[^\w\u4e00-\u9fff]+", query):
            normalized = token.strip()
            if normalized:
                terms[normalized] = terms.get(normalized, 0.0) + 0.6
    return terms


async def _load_repo_interest_payload(conn: aiosqlite.Connection, full_name: str) -> Dict[str, Any]:
    row = await (await conn.execute(
        """
        SELECT
            COALESCE(NULLIF(override_category, ''), category) AS category,
            COALESCE(NULLIF(override_subcategory, ''), subcategory) AS subcategory,
            COALESCE(NULLIF(override_tags, ''), ai_tags) AS tags,
            COALESCE(NULLIF(override_keywords, ''), ai_keywords) AS keywords
        FROM repos
        WHERE full_name = ?
        """,
        (full_name,),
    )).fetchone()
    if not row:
        return {}
    return {
        "category": row["category"],
        "subcategory": row["subcategory"],
        "tags": _load_json_list(row["tags"]),
        "keywords": _load_json_list(row["keywords"]),
    }


@_retry_on_lock()
async def record_user_feedback_event(
    user_id: str,
    event_type: str,
    query: Optional[str] = None,
    full_name: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    normalized_user = str(user_id or "global").strip() or "global"
    normalized_event = str(event_type or "").strip().lower()
    if normalized_event not in ("search", "click"):
        return
    timestamp = datetime.now(timezone.utc).isoformat()
    payload_obj = dict(payload or {})
    if query and not payload_obj.get("query"):
        payload_obj["query"] = query

    async with get_connection() as conn:
        if normalized_event == "click" and full_name:
            repo_payload = await _load_repo_interest_payload(conn, full_name)
            for key, value in repo_payload.items():
                payload_obj.setdefault(key, value)

        await conn.execute(
            """
            INSERT INTO user_feedback_events (user_id, event_type, query, full_name, payload, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                normalized_user,
                normalized_event,
                query,
                full_name,
                json.dumps(payload_obj, ensure_ascii=False),
                timestamp,
            ),
        )

        current_profile_row = await (await conn.execute(
            """
            SELECT topic_scores
            FROM user_interest_profiles
            WHERE user_id = ?
            """,
            (normalized_user,),
        )).fetchone()
        current_scores = _safe_json_dict(current_profile_row["topic_scores"]) if current_profile_row else {}
        updated_scores: Dict[str, float] = {}
        for key, value in current_scores.items():
            try:
                updated_scores[str(key)] = float(value) * 0.98
            except (TypeError, ValueError):
                continue
        for term, inc in _extract_interest_terms(payload_obj).items():
            updated_scores[term] = updated_scores.get(term, 0.0) + float(inc)
        top_items = sorted(updated_scores.items(), key=lambda item: item[1], reverse=True)[:200]
        compact_scores = {k: round(v, 4) for k, v in top_items if v > 0}

        await conn.execute(
            """
            INSERT INTO user_interest_profiles (user_id, topic_scores, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                topic_scores = excluded.topic_scores,
                updated_at = excluded.updated_at
            """,
            (
                normalized_user,
                json.dumps(compact_scores, ensure_ascii=False),
                timestamp,
            ),
        )
        await conn.commit()


async def get_user_interest_profile(user_id: str = "global") -> Dict[str, Any]:
    normalized = str(user_id or "global").strip() or "global"
    async with get_connection() as conn:
        row = await (await conn.execute(
            """
            SELECT user_id, topic_scores, updated_at
            FROM user_interest_profiles
            WHERE user_id = ?
            """,
            (normalized,),
        )).fetchone()
    if not row:
        return {"user_id": normalized, "topic_scores": {}, "top_topics": [], "updated_at": None}
    scores = _safe_json_dict(row["topic_scores"])
    normalized_scores: Dict[str, float] = {}
    for key, value in scores.items():
        try:
            normalized_scores[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    top_topics = sorted(normalized_scores.items(), key=lambda item: item[1], reverse=True)[:20]
    return {
        "user_id": row["user_id"],
        "topic_scores": normalized_scores,
        "top_topics": [{"topic": key, "score": score} for key, score in top_topics],
        "updated_at": row["updated_at"],
    }


async def list_training_samples(
    user_id: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    clauses = []
    params: List[Any] = []
    if user_id:
        clauses.append("(user_id = ? OR user_id IS NULL)")
        params.append(str(user_id))
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    async with get_connection() as conn:
        rows = await (await conn.execute(
            f"""
            SELECT
                id,
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
            FROM training_samples
            {where_sql}
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            params + [limit],
        )).fetchall()
    output: List[Dict[str, Any]] = []
    for row in rows:
        output.append(
            {
                "id": row["id"],
                "user_id": row["user_id"],
                "full_name": row["full_name"],
                "before_category": row["before_category"],
                "before_subcategory": row["before_subcategory"],
                "before_tag_ids": _load_json_list(row["before_tag_ids"]),
                "after_category": row["after_category"],
                "after_subcategory": row["after_subcategory"],
                "after_tag_ids": _load_json_list(row["after_tag_ids"]),
                "note": row["note"],
                "source": row["source"],
                "created_at": row["created_at"],
            }
        )
    return output
