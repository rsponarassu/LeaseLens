"""Deterministic rule engine.

Division of labour, restated because it is the safety property that makes this
product defensible:

* The LLM only *extracts*: it labels a clause and fills typed entity fields.
* This module *decides*: it compares those values to thresholds in YAML using
  ordinary Python operators and produces the verdict, the severity and the score.

Nothing here calls a model, and no model output can bypass these checks. Given
the same entities and the same ``rules.yaml`` the output is bit-for-bit stable.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from app.models.clause import Clause
from app.models.enums import (
    ClauseCategory,
    FindingStatus,
    RuleOperator,
    Severity,
)
from app.models.rules import (
    CategoryRisk,
    RiskAssessment,
    RuleBase,
    RuleDefinition,
    RuleEvaluation,
)
from app.rules.loader import get_rule_base

logger = logging.getLogger(__name__)

CATEGORY_LABELS: dict[ClauseCategory, str] = {
    ClauseCategory.DEPOSIT: "security deposit",
    ClauseCategory.LOCK_IN: "lock-in and exit penalties",
    ClauseCategory.EVICTION: "eviction and notice",
    ClauseCategory.RENT_HIKE: "rent revision",
    ClauseCategory.ENTRY_RIGHTS: "landlord entry rights",
    ClauseCategory.MAINTENANCE: "repairs and maintenance",
    ClauseCategory.GENERAL: "formal requirements",
}

_OPERATOR_PHRASE: dict[RuleOperator, str] = {
    RuleOperator.GREATER_THAN: "must not exceed",
    RuleOperator.GREATER_OR_EQUAL: "must not exceed",
    RuleOperator.LESS_THAN: "must be at least",
    RuleOperator.LESS_OR_EQUAL: "must be at least",
    RuleOperator.EQUALS: "must be",
    RuleOperator.NOT_EQUALS: "must not be",
    RuleOperator.WITHIN_RANGE: "must be within",
}


@dataclass
class RuleEngineResult:
    """Everything the report builder needs from the engine."""

    evaluations: dict[str, list[RuleEvaluation]] = field(default_factory=dict)
    risk: RiskAssessment | None = None

    def evaluations_for(self, clause_id: str) -> list[RuleEvaluation]:
        return self.evaluations.get(clause_id, [])

    @property
    def violations(self) -> list[RuleEvaluation]:
        return [
            evaluation
            for evaluations in self.evaluations.values()
            for evaluation in evaluations
            if evaluation.is_violation
        ]

    @property
    def compliant(self) -> list[RuleEvaluation]:
        return [
            evaluation
            for evaluations in self.evaluations.values()
            for evaluation in evaluations
            if evaluation.status is FindingStatus.COMPLIANT
        ]


class RuleEngine:
    """Applies the YAML benchmarks to classified clauses."""

    def __init__(self, rule_base: RuleBase | None = None) -> None:
        self.rule_base = rule_base or get_rule_base()

    # -- public API ---------------------------------------------------------
    def evaluate(self, clauses: Iterable[Clause]) -> RuleEngineResult:
        clause_list = list(clauses)
        result = RuleEngineResult()

        for clause in clause_list:
            result.evaluations[clause.clause_id] = [
                self._apply(rule, clause)
                for rule in self._rules_for(clause.category)
            ]

        result.risk = self._score(clause_list, result)
        logger.info(
            "rule engine: %s clauses, %s violations, score %s",
            len(clause_list),
            len(result.violations),
            result.risk.overall_score,
        )
        return result

    def _rules_for(self, category: ClauseCategory) -> list[RuleDefinition]:
        return self.rule_base.by_category(category)

    # -- single rule --------------------------------------------------------
    def _apply(self, rule: RuleDefinition, clause: Clause) -> RuleEvaluation:
        observed = getattr(clause.entities, rule.field, None)

        # Unary presence checks must run before the "unknown" short-circuit.
        if rule.operator is RuleOperator.IS_NULL:
            violated = observed is None
        elif rule.operator is RuleOperator.IS_NOT_NULL:
            violated = observed is not None
        elif observed is None:
            return RuleEvaluation.not_applicable(rule, clause.clause_id)
        elif isinstance(observed, list) and not observed:
            return RuleEvaluation.not_applicable(
                rule, clause.clause_id, message="No values were extracted for this clause."
            )
        else:
            violated = self._is_violation(rule, observed)

        if not violated:
            return RuleEvaluation(
                rule_id=rule.id,
                clause_id=clause.clause_id,
                category=rule.category,
                status=FindingStatus.COMPLIANT,
                severity=rule.severity,
                observed_value=observed,
                threshold=rule.value,
                message=self._compliance_message(rule, observed),
                penalty_group=rule.effective_group,
            )

        return RuleEvaluation(
            rule_id=rule.id,
            clause_id=clause.clause_id,
            category=rule.category,
            status=FindingStatus.VIOLATION,
            severity=rule.severity,
            observed_value=observed,
            threshold=rule.value,
            message=self._violation_message(rule, observed),
            penalty_group=rule.effective_group,
            penalty_points=self.rule_base.scoring.severity_points.get(rule.severity, 0),
            is_violation=True,
        )

    @staticmethod
    def _is_violation(rule: RuleDefinition, observed: Any) -> bool:
        """Return True when ``observed`` breaches the rule's benchmark."""
        operator = rule.operator

        if operator is RuleOperator.IS_TRUE:
            return observed is True
        if operator is RuleOperator.IS_FALSE:
            return observed is False
        if operator is RuleOperator.CONTAINS_ANY:
            expected = rule.value if isinstance(rule.value, list) else [rule.value]
            if not isinstance(observed, list):
                return False
            return any(str(item).lower() in {str(v).lower() for v in expected} for item in observed)
        if operator is RuleOperator.NOT_CONTAINS_ANY:
            expected_list = rule.value if isinstance(rule.value, list) else [rule.value]
            if not isinstance(observed, list):
                return False
            return not any(
                str(item).lower() in {str(v).lower() for v in expected_list} for item in observed
            )

        if isinstance(observed, bool):  # avoid True == 1 surprises
            if operator is RuleOperator.EQUALS:
                return observed is not bool(rule.value)
            if operator is RuleOperator.NOT_EQUALS:
                return observed is bool(rule.value)
            return False

        if operator is RuleOperator.EQUALS:
            return observed != rule.value
        if operator is RuleOperator.NOT_EQUALS:
            return observed == rule.value

        try:
            actual = float(observed)
            threshold = float(rule.value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            logger.warning("rule %s: non-numeric comparison skipped", rule.id)
            return False

        if operator is RuleOperator.GREATER_THAN:
            return actual > threshold
        if operator is RuleOperator.GREATER_OR_EQUAL:
            return actual >= threshold
        if operator is RuleOperator.LESS_THAN:
            return actual < threshold
        if operator is RuleOperator.LESS_OR_EQUAL:
            return actual <= threshold
        if operator is RuleOperator.WITHIN_RANGE:
            upper = float(rule.value_max if rule.value_max is not None else threshold)
            return not (threshold <= actual <= upper)
        return False

    # -- messages -----------------------------------------------------------
    @staticmethod
    def _format_value(value: Any, unit: str | None) -> str:
        if isinstance(value, bool):
            return "yes" if value else "no"
        rendered = f"{value:g}" if isinstance(value, float) else str(value)
        return f"{rendered} {unit}" if unit else rendered

    def _violation_message(self, rule: RuleDefinition, observed: Any) -> str:
        if rule.operator is RuleOperator.IS_TRUE:
            return rule.title
        if rule.operator is RuleOperator.IS_FALSE:
            return rule.title
        if rule.operator is RuleOperator.IS_NOT_NULL:
            return rule.title
        phrase = _OPERATOR_PHRASE.get(rule.operator, "must satisfy")
        observed_text = self._format_value(observed, rule.unit)
        if rule.operator is RuleOperator.WITHIN_RANGE:
            return f"{rule.title}. Agreement states {observed_text}; {phrase} {rule.value}-{rule.value_max}."
        expected = self._format_value(rule.value, rule.unit)
        return f"{rule.title}. Agreement states {observed_text}; {phrase} {expected}."

    def _compliance_message(self, rule: RuleDefinition, observed: Any) -> str:
        if isinstance(observed, bool):
            return f"{rule.title} - compliant."
        return (
            f"{rule.title} - compliant "
            f"({self._format_value(observed, rule.unit)} within the statutory benchmark)."
        )

    # -- scoring ------------------------------------------------------------
    def _score(self, clauses: list[Clause], result: RuleEngineResult) -> RiskAssessment:
        scoring = self.rule_base.scoring

        # One representative violation per penalty group: the most severe one.
        grouped: dict[str, RuleEvaluation] = {}
        for evaluation in result.violations:
            existing = grouped.get(evaluation.penalty_group)
            if existing is None or evaluation.penalty_points > existing.penalty_points:
                grouped[evaluation.penalty_group] = evaluation

        # Map penalty group -> clause category so importance lookup is accurate.
        group_category: dict[str, ClauseCategory] = {
            group: evaluation.category for group, evaluation in grouped.items()
        }

        present_categories = {
            clause.category
            for clause in clauses
            if clause.category is not ClauseCategory.GENERAL
        } or {clause.category for clause in clauses}

        per_category: dict[ClauseCategory, list[RuleEvaluation]] = {}
        for group, evaluation in grouped.items():
            per_category.setdefault(group_category[group], []).append(evaluation)

        category_scores: list[CategoryRisk] = []
        for category in sorted(present_categories, key=lambda c: c.value):
            evaluations = sorted(
                per_category.get(category, []), key=lambda e: e.penalty_points, reverse=True
            )
            importance = scoring.category_importance.get(category, 1.0)
            if not evaluations:
                category_scores.append(
                    CategoryRisk(
                        category=category,
                        score=0,
                        weight=importance,
                        violation_count=0,
                        weight_note=f"No unfavourable {CATEGORY_LABELS[category]} terms found.",
                    )
                )
                continue
            base = evaluations[0].penalty_points
            breadth = min(
                scoring.breadth_bonus_cap,
                scoring.breadth_bonus_per_violation * (len(evaluations) - 1),
            )
            score = min(100, round(base * importance + breadth))
            category_scores.append(
                CategoryRisk(
                    category=category,
                    score=score,
                    weight=importance,
                    contribution=round(score / max(1, len(present_categories)), 1),
                    violation_count=len(evaluations),
                    highest_severity=max(
                        (e.severity for e in evaluations), key=lambda s: s.rank
                    ),
                )
            )

        overall = 0
        if grouped:
            strongest = max(grouped.values(), key=lambda e: e.penalty_points)
            importance = scoring.category_importance.get(strongest.category, 1.0)
            breadth = min(
                scoring.breadth_bonus_cap,
                scoring.breadth_bonus_per_violation * (len(grouped) - 1),
            )
            overall = min(100, round(strongest.penalty_points * importance + breadth))

        band = scoring.band_for(overall)
        violations = len(grouped)
        compliant_count = len(result.compliant)

        return RiskAssessment(
            overall_score=overall,
            risk_level=band.level,
            band_label=band.label,
            headline=self._headline(overall, violations, grouped, band.label),
            category_scores=category_scores,
            violation_count=violations,
            compliant_count=compliant_count,
            analysed_category_count=len(present_categories),
            top_drivers=[
                evaluation.message
                for evaluation in sorted(
                    grouped.values(), key=lambda e: e.penalty_points, reverse=True
                )[:3]
            ],
            scoring_version=scoring.version,
            methodology=(
                "Severity-led scoring: the worst violation sets the base points, each "
                "additional distinct violation adds a capped breadth bonus, and the base "
                "is scaled by the importance of its domain. Only code computes this - the "
                "language model never sees or produces the score."
            ),
        )

    @staticmethod
    def _headline(
        score: int,
        violations: int,
        grouped: dict[str, RuleEvaluation],
        band_label: str,
    ) -> str:
        if not violations or score == 0:
            return "No statutory red flags detected in the clauses we could read."
        worst = max(grouped.values(), key=lambda e: e.penalty_points)
        severity_word = {
            Severity.CRITICAL: "a critical",
            Severity.HIGH: "a high-risk",
            Severity.MODERATE: "a moderate",
            Severity.LOW: "a minor",
            Severity.INFO: "an informational",
        }.get(worst.severity, "a")
        noun = "clause" if violations == 1 else "clauses"
        return (
            f"{violations} {noun} need attention, led by {severity_word} "
            f"{CATEGORY_LABELS[worst.category]} term. {band_label} ({score}/100)."
        )
