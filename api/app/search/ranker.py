import math
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple


def _tokenize_query(query: str) -> List[str]:
    if not query:
        return []
    tokens = [
        token.strip().lower()
        for token in re.split(r"[^\w\u4e00-\u9fff]+", query)
        if token and token.strip()
    ]
    return tokens[:10]


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _term_hit(term: str, text: str) -> bool:
    if not term:
        return False
    return term in text


def rank_repo_matches(row: Dict[str, Any], query: str) -> Tuple[float, List[str]]:
    tokens = _tokenize_query(query)
    if not tokens:
        return (0.0, [])

    name = str(row.get("name") or "").lower()
    full_name = str(row.get("full_name") or "").lower()
    description = str(row.get("description") or "").lower()
    readme_summary = str(row.get("readme_summary") or "").lower()
    summary_zh = str(row.get("summary_zh") or "").lower()
    topics = str(row.get("topics") or "").lower()
    ai_tags = str(row.get("ai_tags") or "").lower()
    override_tags = str(row.get("override_tags") or "").lower()
    ai_keywords = str(row.get("ai_keywords") or "").lower()
    override_keywords = str(row.get("override_keywords") or "").lower()

    score = 0.0
    reasons: List[str] = []
    unique_reasons: set[str] = set()

    for term in tokens:
        if _term_hit(term, name):
            score += 4.0
            unique_reasons.add("name")
        if _term_hit(term, full_name):
            score += 3.0
            unique_reasons.add("full_name")
        if _term_hit(term, topics):
            score += 2.5
            unique_reasons.add("topics")
        if _term_hit(term, override_tags) or _term_hit(term, ai_tags):
            score += 2.0
            unique_reasons.add("tags")
        if _term_hit(term, override_keywords) or _term_hit(term, ai_keywords):
            score += 1.8
            unique_reasons.add("keywords")
        if _term_hit(term, description):
            score += 1.4
            unique_reasons.add("description")
        if _term_hit(term, readme_summary):
            score += 1.2
            unique_reasons.add("readme_summary")
        if _term_hit(term, summary_zh):
            score += 1.0
            unique_reasons.add("summary_zh")

    confidence = row.get("ai_confidence")
    try:
        confidence_value = float(confidence or 0.0)
    except (TypeError, ValueError):
        confidence_value = 0.0
    score += max(0.0, min(1.0, confidence_value)) * 0.9

    stars = row.get("stargazers_count")
    try:
        stars_value = int(stars or 0)
    except (TypeError, ValueError):
        stars_value = 0
    score += min(1.2, math.log10(max(1, stars_value + 1)) * 0.5)

    updated_at = _parse_datetime(str(row.get("updated_at") or ""))
    if updated_at is not None:
        age_days = (datetime.now(timezone.utc) - updated_at).days
        freshness = max(0.0, 1.0 - (age_days / 3650))
        score += freshness * 0.6
        if freshness >= 0.75:
            unique_reasons.add("recently_updated")

    reasons.extend(sorted(unique_reasons))
    return (score, reasons)
