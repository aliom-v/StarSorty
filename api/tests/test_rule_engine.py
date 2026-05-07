import json
from pathlib import Path

from api.app.classification.decision import DecisionPolicy, decide_route
from api.app.classification.engine import ClassificationEngine
from api.app.classification.rule_matcher import RuleCandidate, rank_rule_candidates
from api.app.routes import classify as classify_routes
from api.app.rules import load_rules
from api.app.taxonomy import load_taxonomy
from api.app.taxonomy_schema import build_taxonomy_schema


def _candidate(
    *,
    rule_id: str = "rule.demo",
    category: str = "dev",
    subcategory: str = "frontend",
    score: float = 0.5,
) -> RuleCandidate:
    return RuleCandidate(
        rule_id=rule_id,
        category=category,
        subcategory=subcategory,
        score=score,
        priority=0,
        tag_ids=[],
        tags=[],
        must_hits=[],
        should_hits=[],
        evidence=[],
    )


def _minimal_taxonomy():
    return build_taxonomy_schema(
        {
            "categories": [
                {"name": "dev", "subcategories": ["frontend", "language"]},
                {"name": "ai", "subcategories": ["llm", "agent"]},
                {"name": "network", "subcategories": ["vpn"]},
                {"name": "uncategorized", "subcategories": ["other"]},
            ],
            "tags": ["LLM", "Agent", "VPN", "Web应用", "ChatGPT", "RAG", "向量数据库"],
        }
    )


def test_load_rules_generates_stable_rule_ids_for_rules_without_explicit_ids() -> None:
    rule = {
        "keywords": ["warp", "wireguard"],
        "category": "network",
        "subcategory": "vpn",
        "tags": ["VPN"],
    }
    raw_a = json.dumps({"rules": [rule, {"keywords": ["react"], "category": "dev", "subcategory": "frontend"}]})
    raw_b = json.dumps({"rules": [{"keywords": ["react"], "category": "dev", "subcategory": "frontend"}, rule]})

    parsed_a = load_rules(raw_a)
    parsed_b = load_rules(raw_b)

    vpn_id_a = next(item["rule_id"] for item in parsed_a if item["candidate_subcategory"] == "vpn")
    vpn_id_b = next(item["rule_id"] for item in parsed_b if item["candidate_subcategory"] == "vpn")

    assert vpn_id_a == vpn_id_b
    assert vpn_id_a.startswith("network.vpn.")


def test_rule_matcher_prioritizes_name_matches_over_description_and_language() -> None:
    taxonomy = _minimal_taxonomy()
    rules = [
        {
            "rule_id": "dev.language.python",
            "category": "dev",
            "subcategory": "language",
            "should_keywords": ["python", "typescript"],
            "tags": ["LLM"],
        }
    ]

    name_match = rank_rule_candidates(
        {
            "name": "python-tool",
            "full_name": "demo/python-tool",
            "description": "",
            "language": "Go",
            "topics": [],
            "readme_summary": "",
        },
        rules,
        taxonomy,
    )[0]
    description_match = rank_rule_candidates(
        {
            "name": "tool",
            "full_name": "demo/tool",
            "description": "python automation framework",
            "language": "Go",
            "topics": [],
            "readme_summary": "",
        },
        rules,
        taxonomy,
    )[0]
    language_match = rank_rule_candidates(
        {
            "name": "tool",
            "full_name": "demo/tool",
            "description": "",
            "language": "Python",
            "topics": [],
            "readme_summary": "",
        },
        rules,
        taxonomy,
    )[0]

    assert name_match.score > description_match.score > language_match.score
    assert name_match.score >= 0.55
    assert language_match.score < 0.3
    assert "name/full_name" in name_match.evidence[0]
    assert "@language" in language_match.evidence[0]


def test_decide_route_respects_minimum_and_ai_hint_thresholds() -> None:
    policy = DecisionPolicy(
        direct_rule_threshold=0.88,
        ai_required_threshold=0.45,
        min_rule_threshold=0.42,
        ambiguity_gap=0.08,
    )

    weak = decide_route("rules_then_ai", True, _candidate(score=0.3), None, policy)
    assert weak.route == "ai"
    assert weak.candidate is None
    assert weak.include_rule_candidates is False
    assert weak.allow_rule_fallback is False

    arbitration = decide_route("rules_then_ai", True, _candidate(score=0.6), None, policy)
    assert arbitration.route == "ai"
    assert arbitration.candidate is not None
    assert arbitration.include_rule_candidates is True
    assert arbitration.allow_rule_fallback is True

    manual = decide_route("rules_then_ai", False, _candidate(score=0.3), None, policy)
    assert manual.route == "manual"


def test_decide_route_marks_close_distinct_candidates_as_ambiguous() -> None:
    policy = DecisionPolicy(
        direct_rule_threshold=0.88,
        ai_required_threshold=0.45,
        min_rule_threshold=0.42,
        ambiguity_gap=0.08,
    )
    top = _candidate(rule_id="dev.front", category="dev", subcategory="frontend", score=0.91)
    runner_up = _candidate(rule_id="ai.llm", category="ai", subcategory="llm", score=0.86)

    ai_decision = decide_route("rules_then_ai", True, top, runner_up, policy)
    assert ai_decision.route == "ai"
    assert ai_decision.include_rule_candidates is True
    assert ai_decision.allow_rule_fallback is False
    assert "too close" in ai_decision.reason

    manual_decision = decide_route("rules_then_ai", False, top, runner_up, policy)
    assert manual_decision.route == "manual"
    assert "too close" in manual_decision.reason


def test_classification_engine_emits_rules_fallback_when_ai_is_unavailable() -> None:
    taxonomy = _minimal_taxonomy()
    rules = [
        {
            "rule_id": "network.vpn.demo",
            "category": "network",
            "subcategory": "vpn",
            "should_keywords": ["warp", "wireguard"],
            "tags": ["VPN"],
        }
    ]
    engine = ClassificationEngine(
        taxonomy=taxonomy,
        rules=rules,
        classify_mode="rules_then_ai",
        use_ai=False,
        policy=DecisionPolicy(min_rule_threshold=0.42),
    )

    prepared = engine.prepare_classification(
        {
            "name": "warp-client",
            "full_name": "demo/warp-client",
            "description": "Cloudflare Warp VPN client",
            "language": "Rust",
            "topics": ["warp", "vpn"],
            "readme_summary": "",
        }
    )

    assert prepared.outcome is not None
    assert prepared.outcome.source == "rules_fallback"
    assert prepared.outcome.result["category"] == "network"
    assert prepared.outcome.result["subcategory"] == "vpn"


def test_classification_engine_weak_rule_signal_does_not_seed_ai_or_rule_fallback() -> None:
    taxonomy = _minimal_taxonomy()
    rules = [
        {
            "rule_id": "dev.language.demo",
            "category": "dev",
            "subcategory": "language",
            "should_keywords": ["python", "typescript"],
            "tags": ["LLM"],
        }
    ]
    engine = ClassificationEngine(
        taxonomy=taxonomy,
        rules=rules,
        classify_mode="rules_then_ai",
        use_ai=True,
        policy=DecisionPolicy(min_rule_threshold=0.42),
    )

    prepared = engine.prepare_classification(
        {
            "name": "tool",
            "full_name": "demo/tool",
            "description": "",
            "language": "Python",
            "topics": [],
            "readme_summary": "",
        }
    )

    assert prepared.outcome is None
    assert prepared.pending_ai is not None
    assert prepared.pending_ai.top_candidate is None
    assert prepared.pending_ai.allow_rule_fallback is False
    assert "rule_candidates" not in prepared.pending_ai.ai_input


def test_should_fetch_readme_when_repo_context_is_thin(monkeypatch) -> None:
    monkeypatch.setattr(classify_routes, "CLASSIFY_README_DESCRIPTION_MIN_CHARS", 120)
    monkeypatch.setattr(classify_routes, "CLASSIFY_README_MIN_TOPICS", 2)

    assert classify_routes._should_fetch_readme(
        {
            "description": "A GitHub star management application with AI summaries.",
            "topics": ["github"],
        }
    )
    assert not classify_routes._should_fetch_readme(
        {
            "description": "A self-hosted GitHub star management system with API, scheduler, admin UI, "
            "AI-assisted classification, searchable taxonomy, and deployment documentation.",
            "topics": ["github", "stars", "ai"],
        }
    )


def test_manual_override_preference_can_remap_classification_and_tags() -> None:
    taxonomy = _minimal_taxonomy()
    result = {
        "category": "dev",
        "subcategory": "frontend",
        "tag_ids": ["ai.llm"],
        "tags": ["LLM"],
        "confidence": 0.7,
    }

    remapped = classify_routes._apply_tag_mapping_to_result(
        result,
        {
            "classification:dev/frontend": "classification:ai/agent",
            "ai.llm": "ai.agent",
        },
        taxonomy,
    )

    assert remapped["category"] == "ai"
    assert remapped["subcategory"] == "agent"
    assert remapped["tag_ids"] == ["ai.agent"]
    assert remapped["tags"] == ["ai.agent"]


def test_default_rules_avoid_known_false_positives_and_keep_positive_cases() -> None:
    rules_path = Path(__file__).resolve().parents[1] / "config" / "rules.json"
    taxonomy_path = Path(__file__).resolve().parents[1] / "config" / "taxonomy.yaml"
    rules = load_rules("", fallback_path=rules_path)
    taxonomy = load_taxonomy(str(taxonomy_path))

    cloudflare_sdk_candidates = rank_rule_candidates(
        {
            "name": "workers-sdk",
            "full_name": "cloudflare/workers-sdk",
            "description": "SDK for Cloudflare Workers and Pages",
            "language": "TypeScript",
            "topics": ["cloudflare", "workers"],
            "readme_summary": "",
        },
        rules,
        taxonomy,
    )
    assert not any(
        candidate.category == "network" and candidate.subcategory == "vpn"
        for candidate in cloudflare_sdk_candidates[:5]
    )

    vercel_sdk_candidates = rank_rule_candidates(
        {
            "name": "ai",
            "full_name": "vercel/ai",
            "description": "AI SDK for TypeScript and Next.js",
            "language": "TypeScript",
            "topics": ["ai", "nextjs"],
            "readme_summary": "",
        },
        rules,
        taxonomy,
    )
    assert not any(
        candidate.category == "productivity" and candidate.subcategory == "blog"
        for candidate in vercel_sdk_candidates[:5]
    )

    warp_candidates = rank_rule_candidates(
        {
            "name": "warp-client",
            "full_name": "demo/warp-client",
            "description": "Cloudflare Warp VPN client",
            "language": "Rust",
            "topics": ["warp", "vpn"],
            "readme_summary": "",
        },
        rules,
        taxonomy,
    )
    assert any(
        candidate.category == "network" and candidate.subcategory == "vpn"
        for candidate in warp_candidates[:3]
    )
