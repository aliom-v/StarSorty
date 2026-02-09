import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


def _as_keyword_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    normalized: List[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            normalized.append(text)
    return normalized


def _parse_rules(data: Any) -> List[Dict[str, Any]]:
    rules = data.get("rules") if isinstance(data, dict) else None
    if not isinstance(rules, list):
        return []
    parsed: List[Dict[str, Any]] = []
    for index, raw_rule in enumerate(rules):
        if not isinstance(raw_rule, dict):
            continue
        rule_id = str(raw_rule.get("rule_id") or f"rule_{index + 1}").strip()
        must_keywords = (
            _as_keyword_list(raw_rule.get("must_keywords"))
            or _as_keyword_list(raw_rule.get("must"))
        )
        should_keywords = (
            _as_keyword_list(raw_rule.get("should_keywords"))
            or _as_keyword_list(raw_rule.get("should"))
            or _as_keyword_list(raw_rule.get("keywords"))
        )
        exclude_keywords = (
            _as_keyword_list(raw_rule.get("exclude_keywords"))
            or _as_keyword_list(raw_rule.get("exclude"))
        )
        candidate_category = str(
            raw_rule.get("candidate_category") or raw_rule.get("category") or ""
        ).strip()
        candidate_subcategory = str(
            raw_rule.get("candidate_subcategory") or raw_rule.get("subcategory") or ""
        ).strip()
        tag_ids = _as_keyword_list(raw_rule.get("tag_ids"))
        tags = _as_keyword_list(raw_rule.get("tags"))
        try:
            priority = int(raw_rule.get("priority", 0))
        except (TypeError, ValueError):
            priority = 0

        if not candidate_category:
            candidate_category = "uncategorized"
        if not candidate_subcategory:
            candidate_subcategory = "other"

        parsed.append(
            {
                "rule_id": rule_id,
                "must_keywords": must_keywords,
                "should_keywords": should_keywords,
                "exclude_keywords": exclude_keywords,
                "candidate_category": candidate_category,
                "candidate_subcategory": candidate_subcategory,
                "tag_ids": tag_ids,
                "tags": tags,
                "priority": priority,
            }
        )
    return parsed


def load_rules(raw: str, fallback_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    if raw:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = None
        if data:
            parsed = _parse_rules(data)
            if parsed:
                return parsed

    if fallback_path and fallback_path.exists():
        try:
            data = json.loads(fallback_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return _parse_rules(data)
    return []


def match_rule(repo: Dict[str, Any], rules: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not rules:
        return None
    haystack = " ".join(
        [
            str(repo.get("name") or ""),
            str(repo.get("full_name") or ""),
            str(repo.get("description") or ""),
            str(repo.get("language") or ""),
            " ".join(repo.get("topics") or []),
            str(repo.get("readme_summary") or ""),
        ]
    ).lower()
    best: Optional[Dict[str, Any]] = None
    best_score = -1.0
    for rule in rules:
        must_keywords = rule.get("must_keywords") or []
        should_keywords = rule.get("should_keywords") or []
        exclude_keywords = rule.get("exclude_keywords") or []
        if any(_keyword_in_haystack(keyword, haystack) for keyword in exclude_keywords):
            continue

        if must_keywords and not all(
            _keyword_in_haystack(keyword, haystack) for keyword in must_keywords
        ):
            continue

        should_hits = 0
        for keyword in should_keywords:
            if _keyword_in_haystack(keyword, haystack):
                should_hits += 1

        if not must_keywords and should_hits == 0:
            continue

        try:
            priority = int(rule.get("priority", 0))
        except (TypeError, ValueError):
            priority = 0

        score = 0.0
        if must_keywords:
            score += 0.55
        if should_keywords:
            score += min(0.35, 0.35 * (should_hits / max(1, len(should_keywords))))
        else:
            score += 0.2
        score += min(0.1, max(0, priority) * 0.02)

        if score > best_score:
            best_score = score
            best = rule
    return best


def _keyword_in_haystack(keyword: Any, haystack: str) -> bool:
    token = str(keyword or "").strip().lower()
    if not token:
        return False
    # For mixed English phrases, prefer word-boundary semantics.
    if re.fullmatch(r"[a-z0-9_\- ./+]+", token):
        pattern = r"(?<![a-z0-9])" + re.escape(token) + r"(?![a-z0-9])"
        return bool(re.search(pattern, haystack))
    return token in haystack
