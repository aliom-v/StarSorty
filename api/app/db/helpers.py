import asyncio
import functools
import json
import logging
import random
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import aiosqlite

from ..models import RepoBase

logger = logging.getLogger("starsorty.db")


def _env_int(name: str, default: int, minimum: int | None = None) -> int:
    import os
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        logger.warning("Invalid %s=%r, fallback to %s", name, raw, default)
        return default
    if minimum is not None and value < minimum:
        logger.warning("Out-of-range %s=%r, fallback to %s", name, raw, default)
        return default
    return value


FTS_MAX_TERMS = _env_int("FTS_MAX_TERMS", 8, minimum=1)


def _retry_on_lock(
    max_attempts: int = 5,
    base_delay: float = 0.05,
    max_delay: float = 0.5,
) -> Callable:
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            attempt = 0
            while True:
                try:
                    return await func(*args, **kwargs)
                except sqlite3.OperationalError as exc:
                    message = str(exc).lower()
                    if "database is locked" not in message and "database table is locked" not in message:
                        raise
                    if attempt >= max_attempts - 1:
                        raise
                    delay = min(max_delay, base_delay * (2**attempt))
                    jitter = random.uniform(0, delay)
                    logger.warning("SQLite locked, retrying in %.2fs", delay + jitter)
                    await asyncio.sleep(delay + jitter)
                    attempt += 1
        return wrapper
    return decorator


def _sqlite_path(database_url: str) -> str:
    if database_url.startswith("sqlite:////"):
        return "/" + database_url[len("sqlite:////"):]
    if database_url.startswith("sqlite:///"):
        return database_url[len("sqlite:///"):]
    raise ValueError("Only sqlite is supported in the skeleton")


def _ensure_parent_dir(path: str) -> None:
    import os
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def _build_fts_query(raw_query: str) -> str | None:
    terms = [
        term.strip().lower()
        for term in re.split(r"[^\w\u4e00-\u9fff]+", raw_query)
        if term and term.strip()
    ]
    if not terms:
        return None
    normalized: List[str] = []
    for term in terms[:FTS_MAX_TERMS]:
        escaped = term[:64].replace('"', '""')
        if escaped:
            normalized.append(f'"{escaped}"')
    if not normalized:
        return None
    return " AND ".join(normalized)


def _load_json_list(value: Optional[str]) -> List[str]:
    if not value:
        return []
    try:
        loaded = json.loads(value)
        if isinstance(loaded, list):
            return [str(item) for item in loaded if item]
    except json.JSONDecodeError:
        return []
    return []


def _load_json_list_optional(value: Optional[str]) -> Optional[List[str]]:
    if value is None or value == "":
        return None
    return _load_json_list(value)


def _load_json_dict_list(value: Optional[str]) -> List[Dict[str, Any]]:
    if not value:
        return []
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(loaded, list):
        return []
    result: List[Dict[str, Any]] = []
    for item in loaded:
        if isinstance(item, dict):
            result.append(item)
    return result


def _load_json_object(value: Optional[str]) -> Optional[Dict[str, Any]]:
    if not value:
        return None
    try:
        loaded = json.loads(value)
        if isinstance(loaded, dict):
            return loaded
    except json.JSONDecodeError:
        return None
    return None


def _safe_json_dict(value: Optional[str]) -> Dict[str, Any]:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    if isinstance(loaded, dict):
        return loaded
    return {}


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _parse_sort_timestamp(value: Any) -> float:
    if not value:
        return 0.0
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _interest_boost(row: Dict[str, Any], topic_scores: Dict[str, float]) -> float:
    if not topic_scores:
        return 0.0
    candidates: List[str] = []
    for key in ("category", "subcategory"):
        token = str(row.get(key) or "").strip().lower()
        if token:
            candidates.append(token)
    for field in ("ai_tags", "override_tags", "ai_keywords", "override_keywords"):
        for token in _load_json_list(row.get(field)):
            normalized = str(token).strip().lower()
            if normalized:
                candidates.append(normalized)
    total = 0.0
    for token in candidates:
        total += float(topic_scores.get(token, 0.0))
    return min(3.0, total * 0.12)


def _row_to_repo(row: aiosqlite.Row, include_internal: bool = False) -> RepoBase:
    topics = _load_json_list(row["topics"])
    star_users = _load_json_list(row["star_users"])
    ai_tags = _load_json_list(row["ai_tags"])
    ai_tag_ids = _load_json_list(row["ai_tag_ids"]) if "ai_tag_ids" in row.keys() else []
    override_tags = _load_json_list_optional(row["override_tags"])
    override_tag_ids = (
        _load_json_list_optional(row["override_tag_ids"]) if "override_tag_ids" in row.keys() else None
    )
    ai_keywords = _load_json_list(row["ai_keywords"]) if "ai_keywords" in row.keys() else []
    override_keywords = _load_json_list_optional(row["override_keywords"]) if "override_keywords" in row.keys() else None
    ai_rule_candidates = (
        _load_json_dict_list(row["ai_rule_candidates"]) if "ai_rule_candidates" in row.keys() else []
    )
    effective_category = row["override_category"] or row["category"]
    effective_subcategory = row["override_subcategory"] or row["subcategory"]
    effective_tags = ai_tags if override_tags is None else override_tags
    effective_tag_ids = ai_tag_ids if override_tag_ids is None else override_tag_ids
    effective_summary_zh = (row["override_summary_zh"] or row["summary_zh"]) if "summary_zh" in row.keys() else None
    effective_keywords = ai_keywords if override_keywords is None else override_keywords
    search_score = None
    if "search_score" in row.keys():
        try:
            search_score = float(row["search_score"])
        except (TypeError, ValueError):
            search_score = None
    match_reasons = _load_json_list(row["match_reasons"]) if "match_reasons" in row.keys() else []
    repo = RepoBase(
        full_name=row["full_name"],
        name=row["name"],
        owner=row["owner"],
        html_url=row["html_url"],
        description=row["description"],
        language=row["language"],
        stargazers_count=row["stargazers_count"],
        forks_count=row["forks_count"],
        topics=topics,
        star_users=star_users,
        category=effective_category,
        subcategory=effective_subcategory,
        tags=effective_tags,
        tag_ids=effective_tag_ids,
        ai_category=row["category"],
        ai_subcategory=row["subcategory"],
        ai_confidence=row["ai_confidence"],
        ai_tags=ai_tags,
        ai_tag_ids=ai_tag_ids,
        ai_keywords=ai_keywords,
        ai_provider=row["ai_provider"],
        ai_model=row["ai_model"],
        ai_reason=row["ai_reason"] if "ai_reason" in row.keys() else None,
        ai_decision_source=row["ai_decision_source"] if "ai_decision_source" in row.keys() else None,
        ai_rule_candidates=ai_rule_candidates,
        ai_updated_at=row["ai_updated_at"],
        override_category=row["override_category"],
        override_subcategory=row["override_subcategory"],
        override_tags=override_tags or [],
        override_tag_ids=override_tag_ids or [],
        override_note=row["override_note"],
        override_summary_zh=row["override_summary_zh"] if "override_summary_zh" in row.keys() else None,
        override_keywords=override_keywords or [],
        readme_summary=row["readme_summary"],
        readme_fetched_at=row["readme_fetched_at"],
        pushed_at=row["pushed_at"],
        updated_at=row["updated_at"],
        starred_at=row["starred_at"],
        summary_zh=effective_summary_zh,
        keywords=effective_keywords,
        search_score=search_score,
        match_reasons=match_reasons,
        readme_last_attempt_at=row["readme_last_attempt_at"] if include_internal else None,
        readme_failures=(row["readme_failures"] or 0) if include_internal else None,
        readme_empty=bool(row["readme_empty"] or 0) if include_internal else None,
    )
    return repo
