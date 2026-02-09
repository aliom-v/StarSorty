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


def _build_haystack(repo: Dict[str, Any]) -> str:
    return " ".join(
        [
            str(repo.get("name") or ""),
            str(repo.get("full_name") or ""),
            str(repo.get("description") or ""),
            str(repo.get("language") or ""),
            " ".join(repo.get("topics") or []),
            str(repo.get("readme_summary") or ""),
        ]
    ).lower()


def _keyword_match(keyword: str, haystack: str) -> bool:
    token = str(keyword or "").strip().lower()
    if not token:
        return False
    if re.fullmatch(r"[a-z0-9_\- ./+]+", token):
        pattern = r"(?<![a-z0-9])" + re.escape(token) + r"(?![a-z0-9])"
        return bool(re.search(pattern, haystack))
    return token in haystack


def rank_rule_candidates(
    repo: Dict[str, Any],
    rules: List[Dict[str, Any]],
    taxonomy: Dict[str, Any],
) -> List[RuleCandidate]:
    if not rules:
        return []
    haystack = _build_haystack(repo)
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

        if any(_keyword_match(keyword, haystack) for keyword in exclude_keywords):
            continue

        must_hits = [keyword for keyword in must_keywords if _keyword_match(keyword, haystack)]
        if must_keywords and len(must_hits) != len(must_keywords):
            continue
        should_hits = [keyword for keyword in should_keywords if _keyword_match(keyword, haystack)]
        if not must_keywords and not should_hits:
            continue

        score = 0.0
        if must_keywords:
            score += 0.55
        if should_keywords:
            score += min(0.35, 0.35 * (len(should_hits) / max(1, len(should_keywords))))
        else:
            score += 0.2
        score += min(0.1, max(0, priority) * 0.02)
        score = max(0.0, min(1.0, score))

        raw_tag_ids = [str(v).strip() for v in (rule.get("tag_ids") or []) if str(v).strip()]
        raw_tags = [str(v).strip() for v in (rule.get("tags") or []) if str(v).strip()]
        normalized_tag_ids, _ = normalize_tag_ids(raw_tag_ids + raw_tags, taxonomy)

        evidence = []
        if must_hits:
            evidence.append(f"must={','.join(must_hits[:4])}")
        if should_hits:
            evidence.append(f"should={','.join(should_hits[:4])}")

        candidates.append(
            RuleCandidate(
                rule_id=rule_id,
                category=category,
                subcategory=subcategory,
                score=score,
                priority=priority,
                tag_ids=normalized_tag_ids,
                tags=raw_tags,
                must_hits=must_hits,
                should_hits=should_hits,
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
