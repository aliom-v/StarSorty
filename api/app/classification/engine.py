from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..taxonomy import validate_classification
from .decision import DecisionPolicy, decide_route
from .rule_matcher import RuleCandidate, rank_rule_candidates


@dataclass(frozen=True)
class ClassificationOutcome:
    result: Dict[str, Any]
    source: str
    reason: str
    rule_candidates: List[RuleCandidate]


class ClassificationEngine:
    def __init__(
        self,
        taxonomy: Dict[str, Any],
        rules: List[Dict[str, Any]],
        classify_mode: str,
        use_ai: bool,
        policy: Optional[DecisionPolicy] = None,
    ) -> None:
        self._taxonomy = taxonomy
        self._rules = rules
        self._classify_mode = classify_mode
        self._use_ai = use_ai
        self._policy = policy or DecisionPolicy()

    def candidates_for_repo(self, repo: Dict[str, Any]) -> List[RuleCandidate]:
        return rank_rule_candidates(repo, self._rules, self._taxonomy)

    def _candidate_to_result(self, candidate: RuleCandidate) -> Dict[str, Any]:
        return validate_classification(
            {
                "category": candidate.category,
                "subcategory": candidate.subcategory,
                "tag_ids": candidate.tag_ids,
                "tags": candidate.tags,
                "confidence": candidate.score,
                "reason": f"rule:{candidate.rule_id}",
            },
            self._taxonomy,
        )

    async def classify_repo(
        self,
        repo: Dict[str, Any],
        ai_client: Any,
        ai_retries: int = 2,
    ) -> ClassificationOutcome:
        candidates = self.candidates_for_repo(repo)
        top_candidate = candidates[0] if candidates else None
        decision = decide_route(self._classify_mode, self._use_ai, top_candidate, self._policy)

        if decision.route in ("direct_rule", "rule_fallback"):
            if not decision.candidate:
                raise ValueError("Rule route selected without candidate")
            result = self._candidate_to_result(decision.candidate)
            return ClassificationOutcome(
                result=result,
                source="rules",
                reason=decision.reason,
                rule_candidates=candidates,
            )

        if decision.route == "skip":
            raise ValueError(decision.reason)

        if decision.route == "manual":
            result = validate_classification(
                {
                    "category": "uncategorized",
                    "subcategory": "other",
                    "tag_ids": [],
                    "confidence": 0.0,
                    "reason": "manual-review",
                },
                self._taxonomy,
            )
            return ClassificationOutcome(
                result=result,
                source="manual_review",
                reason=decision.reason,
                rule_candidates=candidates,
            )

        # AI arbitration path.
        ai_input = dict(repo)
        ai_input["rule_candidates"] = [
            {
                "rule_id": candidate.rule_id,
                "category": candidate.category,
                "subcategory": candidate.subcategory,
                "score": candidate.score,
                "evidence": candidate.evidence,
                "tag_ids": candidate.tag_ids,
            }
            for candidate in candidates[:3]
        ]
        try:
            ai_result = await ai_client.classify_repo_with_retry(ai_input, self._taxonomy, retries=ai_retries)
            return ClassificationOutcome(
                result=ai_result,
                source="ai",
                reason=decision.reason,
                rule_candidates=candidates,
            )
        except Exception:
            if top_candidate is None:
                raise
            fallback = self._candidate_to_result(top_candidate)
            return ClassificationOutcome(
                result=fallback,
                source="rules_fallback",
                reason="AI failed; fallback to top rule candidate",
                rule_candidates=candidates,
            )
