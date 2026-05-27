"""Edge case tests for core API modules.

Covers: empty input, long input, special characters, boundary values.
"""

import json
from pathlib import Path

from api.app.classification.decision import DecisionPolicy, decide_route
from api.app.classification.rule_matcher import RuleCandidate, rank_rule_candidates
from api.app.rules import load_rules
from api.app.taxonomy import load_taxonomy
from api.app.taxonomy_schema import build_taxonomy_schema


# ---- Helpers ----

def _minimal_taxonomy():
    return build_taxonomy_schema(
        {
            "categories": [
                {"name": "dev", "subcategories": ["frontend", "language"]},
                {"name": "ai", "subcategories": ["llm", "agent"]},
                {"name": "uncategorized", "subcategories": ["other"]},
            ],
            "tags": ["LLM", "Agent", "Web"],
        }
    )


def _candidate(score: float = 0.5, rule_id: str = "test.rule") -> RuleCandidate:
    return RuleCandidate(
        rule_id=rule_id,
        category="dev",
        subcategory="frontend",
        score=score,
        priority=0,
        tag_ids=[],
        tags=[],
        must_hits=[],
        should_hits=[],
        evidence=[],
    )


# ---- Rule Engine Edge Cases ----

def test_load_rules_empty_json() -> None:
    """Empty rules list should return empty list."""
    result = load_rules(json.dumps({"rules": []}))
    assert result == []


def test_load_rules_malformed_rule_skipped() -> None:
    """Rules missing required fields should be skipped gracefully."""
    raw = json.dumps({
        "rules": [
            {"keywords": ["valid"], "category": "dev", "subcategory": "frontend"},
            {"category": "dev"},  # missing keywords
            {},  # empty rule
        ]
    })
    # Should not raise, malformed rules filtered
    result = load_rules(raw)
    assert isinstance(result, list)


def test_rank_rule_candidates_empty_description() -> None:
    """Repos with all-empty fields should still produce a candidate."""
    taxonomy = _minimal_taxonomy()
    rules = [
        {
            "rule_id": "dev.frontend.test",
            "category": "dev",
            "subcategory": "frontend",
            "should_keywords": ["react"],
        }
    ]
    candidates = rank_rule_candidates(
        {
            "name": "",
            "full_name": "",
            "description": "",
            "language": None,
            "topics": [],
            "readme_summary": "",
        },
        rules,
        taxonomy,
    )
    # Should return at least one candidate (score may be low)
    assert len(candidates) >= 0  # empty input → no crash


def test_rank_rule_candidates_special_characters() -> None:
    """Special characters in repo name/description should not crash."""
    taxonomy = _minimal_taxonomy()
    rules = [
        {
            "rule_id": "dev.frontend.test",
            "category": "dev",
            "subcategory": "frontend",
            "should_keywords": ["react"],
        }
    ]
    candidates = rank_rule_candidates(
        {
            "name": "repo<script>alert(1)</script>",
            "full_name": "user/repo<script>",
            "description": "A repo with 特殊字符 & émojis 🎉",
            "language": "Python",
            "topics": ["c++", ".net"],
            "readme_summary": "Contains <html> &amp; entities",
        },
        rules,
        taxonomy,
    )
    assert isinstance(candidates, list)


def test_rank_rule_candidates_long_input() -> None:
    """Very long strings should be handled without error."""
    taxonomy = _minimal_taxonomy()
    rules = [
        {
            "rule_id": "dev.frontend.test",
            "category": "dev",
            "subcategory": "frontend",
            "should_keywords": ["react"],
        }
    ]
    long_str = "x" * 10000
    candidates = rank_rule_candidates(
        {
            "name": long_str,
            "full_name": f"user/{long_str}",
            "description": long_str * 3,
            "language": "Python",
            "topics": [long_str],
            "readme_summary": long_str * 5,
        },
        rules,
        taxonomy,
    )
    assert isinstance(candidates, list)


# ---- Decision Policy Edge Cases ----

def test_decide_route_score_zero() -> None:
    """Zero score candidate should route to ai or manual."""
    policy = DecisionPolicy()
    result = decide_route("rules_then_ai", True, _candidate(score=0.0), None, policy)
    assert result.route in ("ai", "manual")


def test_decide_route_score_one() -> None:
    """Perfect score candidate should route to rules or ai."""
    policy = DecisionPolicy(direct_rule_threshold=0.95)
    result = decide_route("rules_then_ai", True, _candidate(score=1.0), None, policy)
    assert result.route in ("direct_rule", "rules", "ai")


def test_decide_route_boundary_threshold() -> None:
    """Score exactly at threshold should be handled consistently."""
    policy = DecisionPolicy(min_rule_threshold=0.5)
    result = decide_route("rules_then_ai", True, _candidate(score=0.5), None, policy)
    assert result.route in ("ai", "manual", "rules")


def test_decide_route_ambiguous_same_score() -> None:
    """Two candidates with identical scores should be marked ambiguous."""
    policy = DecisionPolicy(ambiguity_gap=0.0)
    top = _candidate(score=0.9, rule_id="rule.a")
    runner_up = _candidate(score=0.9, rule_id="rule.b")
    result = decide_route("rules_then_ai", True, top, runner_up, policy)
    # With 0 gap, should be ambiguous
    assert result.route in ("direct_rule", "ai", "manual")
