from dataclasses import dataclass
from typing import Literal, Optional

from .rule_matcher import RuleCandidate


DecisionRoute = Literal["direct_rule", "ai", "rule_fallback", "manual", "skip"]


@dataclass(frozen=True)
class DecisionPolicy:
    direct_rule_threshold: float = 0.88
    ai_required_threshold: float = 0.45


@dataclass(frozen=True)
class Decision:
    route: DecisionRoute
    reason: str
    candidate: Optional[RuleCandidate]


def decide_route(
    classify_mode: str,
    use_ai: bool,
    top_candidate: Optional[RuleCandidate],
    policy: DecisionPolicy,
) -> Decision:
    if classify_mode == "ai_only":
        if use_ai:
            return Decision("ai", "classify_mode=ai_only", None)
        return Decision("skip", "AI disabled", None)

    if classify_mode == "rules_only":
        if top_candidate:
            return Decision("direct_rule", "classify_mode=rules_only", top_candidate)
        return Decision("skip", "No matched rule", None)

    if not top_candidate:
        if use_ai:
            return Decision("ai", "No rule candidate", None)
        return Decision("manual", "No rule and AI unavailable", None)

    if top_candidate.score >= policy.direct_rule_threshold:
        return Decision(
            "direct_rule",
            f"Rule score {top_candidate.score:.2f} >= {policy.direct_rule_threshold:.2f}",
            top_candidate,
        )

    if use_ai and top_candidate.score >= policy.ai_required_threshold:
        return Decision(
            "ai",
            f"Rule score {top_candidate.score:.2f} in AI arbitration band",
            top_candidate,
        )

    if use_ai:
        return Decision(
            "ai",
            f"Rule score {top_candidate.score:.2f} below threshold; still try AI",
            top_candidate,
        )

    return Decision(
        "rule_fallback",
        "AI unavailable; fallback to top rule candidate",
        top_candidate,
    )
