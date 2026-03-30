from dataclasses import dataclass
from typing import Literal, Optional

from .rule_matcher import RuleCandidate


DecisionRoute = Literal["direct_rule", "ai", "rule_fallback", "manual", "skip"]


@dataclass(frozen=True)
class DecisionPolicy:
    direct_rule_threshold: float = 0.88
    ai_required_threshold: float = 0.45
    min_rule_threshold: float = 0.42
    ambiguity_gap: float = 0.08


@dataclass(frozen=True)
class Decision:
    route: DecisionRoute
    reason: str
    candidate: Optional[RuleCandidate]
    include_rule_candidates: bool = False
    allow_rule_fallback: bool = False


def _is_ambiguous(
    top_candidate: RuleCandidate,
    runner_up: Optional[RuleCandidate],
    policy: DecisionPolicy,
) -> bool:
    if runner_up is None:
        return False
    if (top_candidate.category, top_candidate.subcategory) == (
        runner_up.category,
        runner_up.subcategory,
    ):
        return False
    return (top_candidate.score - runner_up.score) < policy.ambiguity_gap


def decide_route(
    classify_mode: str,
    use_ai: bool,
    top_candidate: Optional[RuleCandidate],
    runner_up: Optional[RuleCandidate],
    policy: DecisionPolicy,
) -> Decision:
    if classify_mode == "ai_only":
        if use_ai:
            return Decision("ai", "classify_mode=ai_only", None)
        return Decision("manual", "AI disabled", None)

    if classify_mode == "rules_only":
        if not top_candidate:
            return Decision("manual", "No matched rule", None)
        if top_candidate.score < policy.min_rule_threshold:
            return Decision(
                "manual",
                (
                    f"Top rule score {top_candidate.score:.2f} "
                    f"below minimum {policy.min_rule_threshold:.2f}"
                ),
                top_candidate,
            )
        if _is_ambiguous(top_candidate, runner_up, policy):
            gap = top_candidate.score - float(runner_up.score if runner_up else 0.0)
            return Decision(
                "manual",
                (
                    f"Top rules too close ({top_candidate.score:.2f} vs "
                    f"{runner_up.score:.2f}, gap {gap:.2f})"
                ),
                top_candidate,
            )
        return Decision("direct_rule", "classify_mode=rules_only", top_candidate)

    if not top_candidate:
        if use_ai:
            return Decision("ai", "No rule candidate", None)
        return Decision("manual", "No rule and AI unavailable", None)

    if top_candidate.score < policy.min_rule_threshold:
        if use_ai:
            return Decision(
                "ai",
                (
                    f"Rule score {top_candidate.score:.2f} below minimum "
                    f"{policy.min_rule_threshold:.2f}; AI classifies independently"
                ),
                None,
                include_rule_candidates=False,
                allow_rule_fallback=False,
            )
        return Decision(
            "manual",
            (
                f"Rule score {top_candidate.score:.2f} below minimum "
                f"{policy.min_rule_threshold:.2f}"
            ),
            top_candidate,
        )

    if _is_ambiguous(top_candidate, runner_up, policy):
        gap = top_candidate.score - float(runner_up.score if runner_up else 0.0)
        if use_ai:
            return Decision(
                "ai",
                (
                    f"Top rules too close ({top_candidate.score:.2f} vs "
                    f"{runner_up.score:.2f}, gap {gap:.2f}); AI arbitration required"
                ),
                top_candidate,
                include_rule_candidates=True,
                allow_rule_fallback=False,
            )
        return Decision(
            "manual",
            (
                f"Top rules too close ({top_candidate.score:.2f} vs "
                f"{runner_up.score:.2f}, gap {gap:.2f})"
            ),
            top_candidate,
        )

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
            include_rule_candidates=True,
            allow_rule_fallback=True,
        )

    if use_ai:
        return Decision(
            "ai",
            (
                f"Rule score {top_candidate.score:.2f} below AI hint threshold "
                f"{policy.ai_required_threshold:.2f}; AI classifies independently"
            ),
            None,
            include_rule_candidates=False,
            allow_rule_fallback=False,
        )

    return Decision(
        "rule_fallback",
        "AI unavailable; fallback to top rule candidate",
        top_candidate,
    )
