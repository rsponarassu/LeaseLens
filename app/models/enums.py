"""Enumerations shared across models, services and API schemas."""

from __future__ import annotations

from enum import Enum


class ClauseCategory(str, Enum):
    """The tenancy domains LeaseLens classifies clauses into."""

    DEPOSIT = "deposit"
    LOCK_IN = "lock_in"
    EVICTION = "eviction"
    RENT_HIKE = "rent_hike"
    ENTRY_RIGHTS = "entry_rights"
    MAINTENANCE = "maintenance"
    GENERAL = "general"

    @classmethod
    def analysable(cls) -> tuple[ClauseCategory, ...]:
        """Categories that carry legal benchmarks (i.e. excluding ``general``)."""
        return tuple(c for c in cls if c is not cls.GENERAL)


class Severity(str, Enum):
    """Severity of a rule violation, ordered from worst to informational."""

    CRITICAL = "critical"
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    INFO = "info"

    @property
    def rank(self) -> int:
        return _SEVERITY_RANK[self]


_SEVERITY_RANK: dict[Severity, int] = {
    Severity.CRITICAL: 5,
    Severity.HIGH: 4,
    Severity.MODERATE: 3,
    Severity.LOW: 2,
    Severity.INFO: 1,
}


def max_severity(values: list[Severity]) -> Severity:
    """Return the highest severity in ``values`` (``INFO`` when empty)."""
    if not values:
        return Severity.INFO
    return max(values, key=lambda item: item.rank)


class RiskLevel(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    ELEVATED = "elevated"
    HIGH = "high"
    CRITICAL = "critical"


class RiskColor(str, Enum):
    """Colour used for PDF highlighting and UI badges."""

    RED = "red"
    AMBER = "amber"
    GREEN = "green"
    GREY = "grey"


class FindingStatus(str, Enum):
    VIOLATION = "violation"
    COMPLIANT = "compliant"
    NOT_APPLICABLE = "not_applicable"
    INFORMATIONAL = "informational"


class RuleOperator(str, Enum):
    """Deterministic comparison operators supported by the rule engine."""

    GREATER_THAN = "greater_than"
    GREATER_OR_EQUAL = "greater_or_equal"
    LESS_THAN = "less_than"
    LESS_OR_EQUAL = "less_or_equal"
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    IS_TRUE = "is_true"
    IS_FALSE = "is_false"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"
    CONTAINS_ANY = "contains_any"
    NOT_CONTAINS_ANY = "not_contains_any"
    WITHIN_RANGE = "within_range"


class ExtractionMethod(str, Enum):
    TEXT_LAYER = "text_layer"
    OCR = "ocr"
    HYBRID = "hybrid"


class ExtractionSource(str, Enum):
    """Where a classified clause / entity value came from."""

    LLM = "llm"
    HEURISTIC = "heuristic"
    HYBRID = "hybrid"
    MANUAL = "manual"


class AnalysisMode(str, Enum):
    """How the document was understood end to end."""

    LLM_ASSISTED = "llm_assisted"
    OFFLINE_HEURISTIC = "offline_heuristic"
    LLM_DEGRADED = "llm_degraded"


class StatuteVerification(str, Enum):
    """How confident we are that a citation matches the current statute text."""

    VERIFIED = "verified"
    INDICATIVE = "indicative"


class Language(str, Enum):
    ENGLISH = "en"
    TAMIL = "ta"
