"""Rule base and verdict models.

The rule base is data (``rules.yaml``); the engine is code. A rule never
contains an expression to evaluate - it declares a *field*, a *comparison
operator* and a *threshold*, and ``rule_engine`` applies it with plain Python.
That keeps the legal benchmarks auditable and free of eval/exec risk.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    ClauseCategory,
    FindingStatus,
    RiskLevel,
    RuleOperator,
    Severity,
    StatuteVerification,
)


class StatuteInfo(BaseModel):
    """Metadata about the statute the benchmarks were derived from."""

    act: str
    short_name: str
    act_number: str
    jurisdiction: str = "Tamil Nadu, India"
    year: int
    source_url: str | None = None
    as_at: str | None = None
    note: str | None = None


class StatuteReference(BaseModel):
    """A precise pointer into the statute for a single rule."""

    act: str
    section: str
    heading: str
    quote: str
    url: str | None = None
    verification: StatuteVerification = StatuteVerification.INDICATIVE

    def label(self) -> str:
        """Human readable citation, e.g. ``S.11(1) - Security deposit``."""
        return f"S.{self.section} - {self.heading}"


class RuleDefinition(BaseModel):
    """A single legal benchmark loaded from YAML."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Z]{3}-\d{3}$")
    category: ClauseCategory
    title: str
    severity: Severity

    # -- deterministic comparison ------------------------------------------
    field: str
    operator: RuleOperator
    value: Any | None = None
    value_max: float | None = None
    unit: str | None = None
    penalty_group: str | None = None
    applies_to: list[ClauseCategory] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    # -- tenant-facing copy -------------------------------------------------
    explanation: str
    tamil: str
    counter_clause: str
    negotiation_tip: str | None = None

    # -- legal provenance ---------------------------------------------------
    statute: StatuteReference

    @property
    def effective_group(self) -> str:
        """Group used to avoid double-penalising the same fact."""
        return self.penalty_group or self.field

    @property
    def categories(self) -> list[ClauseCategory]:
        return self.applies_to or [self.category]


class RuleEvaluation(BaseModel):
    """Outcome of applying one rule to one clause."""

    rule_id: str
    clause_id: str
    category: ClauseCategory
    status: FindingStatus
    severity: Severity
    observed_value: Any | None = None
    threshold: Any | None = None
    message: str = ""
    penalty_group: str = ""
    penalty_points: int = 0
    is_violation: bool = False

    @classmethod
    def not_applicable(
        cls,
        rule: RuleDefinition,
        clause_id: str,
        *,
        message: str = "Clause does not state the fact this rule checks.",
    ) -> RuleEvaluation:
        return cls(
            rule_id=rule.id,
            clause_id=clause_id,
            category=rule.category,
            status=FindingStatus.NOT_APPLICABLE,
            severity=rule.severity,
            message=message,
            penalty_group=rule.effective_group,
        )


class CategoryRisk(BaseModel):
    """Risk contributed by one tenancy domain."""

    category: ClauseCategory
    score: int = Field(ge=0, le=100)
    weight: float = 1.0
    contribution: float = 0.0
    violation_count: int = 0
    highest_severity: Severity | None = None
    weight_note: str | None = None


class RiskBand(BaseModel):
    """Mapping from a score range to a human risk level."""

    level: RiskLevel
    min_score: int = Field(ge=0, le=100)
    max_score: int = Field(ge=0, le=100)
    label: str


class ScoringConfig(BaseModel):
    """Scoring parameters, kept in YAML so weights are tunable without code.

    The model is severity-led: the worst violation sets the base score, extra
    distinct violations add a capped breadth bonus, and the base is scaled by the
    dollar/control importance of the domain. A flat weighted average was
    deliberately rejected - it let a clean maintenance clause dilute a critical
    eviction term down to "low risk".
    """

    version: str
    severity_points: dict[Severity, int]
    category_importance: dict[ClauseCategory, float]
    breadth_bonus_per_violation: int = 4
    breadth_bonus_cap: int = 12
    risk_bands: list[RiskBand]

    def band_for(self, score: int) -> RiskBand:
        for band in self.risk_bands:
            if band.min_score <= score <= band.max_score:
                return band
        ordered = sorted(self.risk_bands, key=lambda band: band.min_score)
        return ordered[-1] if ordered else RiskBand(
            level=RiskLevel.MODERATE, min_score=0, max_score=100, label="Moderate risk"
        )


class RiskAssessment(BaseModel):
    """Aggregate 0-100 risk score with a full, explainable breakdown."""

    overall_score: int = Field(ge=0, le=100)
    risk_level: RiskLevel
    band_label: str
    headline: str
    category_scores: list[CategoryRisk] = Field(default_factory=list)
    violation_count: int = 0
    compliant_count: int = 0
    analysed_category_count: int = 0
    top_drivers: list[str] = Field(default_factory=list)
    scoring_version: str = "1.0"
    methodology: str = ""


class RuleBase(BaseModel):
    """The fully loaded rule base."""

    statute: StatuteInfo
    scoring: ScoringConfig
    rules: list[RuleDefinition]

    def by_id(self, rule_id: str) -> RuleDefinition | None:
        for rule in self.rules:
            if rule.id == rule_id:
                return rule
        return None

    def by_category(self, category: ClauseCategory) -> list[RuleDefinition]:
        return [rule for rule in self.rules if category in rule.categories]

    def rule_ids(self) -> list[str]:
        return [rule.id for rule in self.rules]
