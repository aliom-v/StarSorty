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


@dataclass(frozen=True)
class PendingAIClassification:
    reason: str
    top_candidate: Optional[RuleCandidate]
    rule_candidates: List[RuleCandidate]
    ai_input: Dict[str, Any]


@dataclass(frozen=True)
class PreparedClassification:
    outcome: Optional[ClassificationOutcome] = None
    pending_ai: Optional[PendingAIClassification] = None


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

    def _rule_candidates_to_ai_input(
        self,
        repo: Dict[str, Any],
        candidates: List[RuleCandidate],
    ) -> Dict[str, Any]:
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
        return ai_input

    def _build_outcome(
        self,
        result: Dict[str, Any],
        source: str,
        reason: str,
        rule_candidates: List[RuleCandidate],
    ) -> ClassificationOutcome:
        return ClassificationOutcome(
            result=result,
            source=source,
            reason=reason,
            rule_candidates=rule_candidates,
        )

    def _fallback_outcome(
        self,
        top_candidate: Optional[RuleCandidate],
        rule_candidates: List[RuleCandidate],
        reason: str = "AI failed; fallback to top rule candidate",
    ) -> ClassificationOutcome:
        if top_candidate is None:
            raise ValueError("No rule fallback candidate available")
        fallback = self._candidate_to_result(top_candidate)
        return self._build_outcome(fallback, "rules_fallback", reason, rule_candidates)

    def fallback_outcome(
        self,
        top_candidate: Optional[RuleCandidate],
        rule_candidates: List[RuleCandidate],
        reason: str = "AI failed; fallback to top rule candidate",
    ) -> ClassificationOutcome:
        return self._fallback_outcome(top_candidate, rule_candidates, reason)

    def prepare_classification(self, repo: Dict[str, Any]) -> PreparedClassification:
        candidates = self.candidates_for_repo(repo)
        top_candidate = candidates[0] if candidates else None
        decision = decide_route(self._classify_mode, self._use_ai, top_candidate, self._policy)

        if decision.route in ("direct_rule", "rule_fallback"):
            if not decision.candidate:
                raise ValueError("Rule route selected without candidate")
            result = self._candidate_to_result(decision.candidate)
            return PreparedClassification(
                outcome=self._build_outcome(result, "rules", decision.reason, candidates)
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
            return PreparedClassification(
                outcome=self._build_outcome(result, "manual_review", decision.reason, candidates)
            )

        return PreparedClassification(
            pending_ai=PendingAIClassification(
                reason=decision.reason,
                top_candidate=top_candidate,
                rule_candidates=candidates,
                ai_input=self._rule_candidates_to_ai_input(repo, candidates),
            )
        )

    def outcome_from_ai_result(
        self,
        ai_result: Dict[str, Any],
        reason: str,
        rule_candidates: List[RuleCandidate],
    ) -> ClassificationOutcome:
        return self._build_outcome(ai_result, "ai", reason, rule_candidates)

    async def classify_repo(
        self,
        repo: Dict[str, Any],
        ai_client: Any,
        ai_retries: int = 2,
    ) -> ClassificationOutcome:
        prepared = self.prepare_classification(repo)
        if prepared.outcome is not None:
            return prepared.outcome

        if prepared.pending_ai is None:
            raise ValueError("Classification preparation did not produce an outcome")

        try:
            ai_result = await ai_client.classify_repo_with_retry(
                prepared.pending_ai.ai_input,
                self._taxonomy,
                retries=ai_retries,
            )
            return self.outcome_from_ai_result(
                ai_result,
                prepared.pending_ai.reason,
                prepared.pending_ai.rule_candidates,
            )
        except Exception:
            if prepared.pending_ai.top_candidate is None:
                raise
            return self._fallback_outcome(
                prepared.pending_ai.top_candidate,
                prepared.pending_ai.rule_candidates,
            )
