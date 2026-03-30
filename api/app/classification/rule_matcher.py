import re
from dataclasses import dataclass
from typing import Any, Dict, List

from ..taxonomy_schema import normalize_tag_ids


@dataclass(frozen=True)
class RuleCandidate:
    rule_id: str
    category: str
    subcategory: str
    score: float
    priority: int
    tag_ids: List[str]
    tags: List[str]
    must_hits: List[str]
    should_hits: List[str]
    evidence: List[str]


FIELD_WEIGHTS = {
    "name": 1.0,
    "full_name": 0.95,
    "topics": 0.9,
    "description": 0.7,
    "readme_summary": 0.45,
    "language": 0.35,
}


@dataclass(frozen=True)
class KeywordHit:
    keyword: str
    fields: List[str]
    best_weight: float


def _build_field_texts(repo: Dict[str, Any]) -> Dict[str, str]:
    return {
        "name": str(repo.get("name") or "").lower(),
        "full_name": str(repo.get("full_name") or "").lower(),
        "topics": " ".join(repo.get("topics") or []).lower(),
        "description": str(repo.get("description") or "").lower(),
        "readme_summary": str(repo.get("readme_summary") or "").lower(),
        "language": str(repo.get("language") or "").lower(),
    }


def _keyword_match(keyword: str, haystack: str) -> bool:
    token = str(keyword or "").strip().lower()
    if not token:
        return False
    if re.fullmatch(r"[a-z0-9_\- ./+]+", token):
        pattern = r"(?<![a-z0-9])" + re.escape(token) + r"(?![a-z0-9])"
        return bool(re.search(pattern, haystack))
    return token in haystack


def _find_keyword_fields(keyword: str, field_texts: Dict[str, str]) -> List[str]:
    matched_fields: List[str] = []
    for field_name, haystack in field_texts.items():
        if haystack and _keyword_match(keyword, haystack):
            matched_fields.append(field_name)
    return matched_fields


def _collect_keyword_hits(keywords: List[str], field_texts: Dict[str, str]) -> List[KeywordHit]:
    hits: List[KeywordHit] = []
    for keyword in keywords:
        matched_fields = _find_keyword_fields(keyword, field_texts)
        if not matched_fields:
            continue
        best_weight = max(FIELD_WEIGHTS.get(field_name, 0.0) for field_name in matched_fields)
        hits.append(
            KeywordHit(
                keyword=keyword,
                fields=matched_fields,
                best_weight=best_weight,
            )
        )
    return hits


def _average_weight(hits: List[KeywordHit]) -> float:
    if not hits:
        return 0.0
    return sum(hit.best_weight for hit in hits) / len(hits)


def _format_evidence(label: str, hits: List[KeywordHit]) -> str:
    parts: List[str] = []
    for hit in hits[:4]:
        parts.append(f"{hit.keyword}@{'/'.join(hit.fields[:2])}")
    return f"{label}={';'.join(parts)}"


def rank_rule_candidates(
    repo: Dict[str, Any],
    rules: List[Dict[str, Any]],
    taxonomy: Dict[str, Any],
) -> List[RuleCandidate]:
    if not rules:
        return []
    field_texts = _build_field_texts(repo)
    candidates: List[RuleCandidate] = []

    for rule in rules:
        rule_id = str(rule.get("rule_id") or "").strip() or "rule"
        must_keywords = [str(k).strip() for k in (rule.get("must_keywords") or []) if str(k).strip()]
        should_keywords = [str(k).strip() for k in (rule.get("should_keywords") or []) if str(k).strip()]
        exclude_keywords = [str(k).strip() for k in (rule.get("exclude_keywords") or []) if str(k).strip()]
        category = str(
            rule.get("candidate_category") or rule.get("category") or "uncategorized"
        ).strip() or "uncategorized"
        subcategory = str(
            rule.get("candidate_subcategory") or rule.get("subcategory") or "other"
        ).strip() or "other"
        try:
            priority = int(rule.get("priority", 0))
        except (TypeError, ValueError):
            priority = 0

        exclude_hits = _collect_keyword_hits(exclude_keywords, field_texts)
        if exclude_hits:
            continue

        must_hit_details = _collect_keyword_hits(must_keywords, field_texts)
        if must_keywords and len(must_hit_details) != len(must_keywords):
            continue
        should_hit_details = _collect_keyword_hits(should_keywords, field_texts)
        if not must_keywords and not should_hit_details:
            continue

        score = 0.0
        if must_keywords:
            must_avg_weight = _average_weight(must_hit_details)
            strong_must_hit = any(hit.best_weight >= 0.9 for hit in must_hit_details)
            score += 0.45
            score += 0.15 * must_avg_weight
            score += 0.1
            if strong_must_hit:
                score += 0.1
        if should_keywords:
            should_best_weight = max(
                (hit.best_weight for hit in should_hit_details),
                default=0.0,
            )
            should_avg_weight = _average_weight(should_hit_details)
            should_coverage = min(1.0, len(should_hit_details) / 2.0)
            strong_should_field_bonus = 0.0
            if should_best_weight >= 0.9:
                strong_should_field_bonus = 0.15
            elif should_best_weight >= 0.7:
                strong_should_field_bonus = 0.08
            score += 0.25 * should_coverage
            score += 0.2 * should_best_weight
            score += 0.1 * should_avg_weight
            score += strong_should_field_bonus
            score += min(0.1, max(0, len(should_hit_details) - 1) * 0.05)
        else:
            score += 0.1
        score += min(0.1, max(0, priority) * 0.02)
        score = max(0.0, min(1.0, score))

        raw_tag_ids = [str(v).strip() for v in (rule.get("tag_ids") or []) if str(v).strip()]
        raw_tags = [str(v).strip() for v in (rule.get("tags") or []) if str(v).strip()]
        normalized_tag_ids, _ = normalize_tag_ids(raw_tag_ids + raw_tags, taxonomy)

        evidence = []
        if must_hit_details:
            evidence.append(_format_evidence("must", must_hit_details))
        if should_hit_details:
            evidence.append(_format_evidence("should", should_hit_details))

        candidates.append(
            RuleCandidate(
                rule_id=rule_id,
                category=category,
                subcategory=subcategory,
                score=score,
                priority=priority,
                tag_ids=normalized_tag_ids,
                tags=raw_tags,
                must_hits=[hit.keyword for hit in must_hit_details],
                should_hits=[hit.keyword for hit in should_hit_details],
                evidence=evidence,
            )
        )

    candidates.sort(
        key=lambda item: (
            item.score,
            item.priority,
            len(item.must_hits),
            len(item.should_hits),
            item.rule_id,
        ),
        reverse=True,
    )
    return candidates
