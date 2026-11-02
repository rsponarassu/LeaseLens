"""Request/response models that exist only for the HTTP surface.

The domain models in ``app.models.analysis`` describe an analysis; these describe
how the API wraps one (parse-only output, annotation requests, health, errors).
Keeping them separate means the domain layer never grows transport concerns.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.clause import ClauseOutline
from app.models.document import ExtractionSummary, PageLayout
from app.models.rules import RiskBand, RuleDefinition, StatuteInfo


class ParseLeaseResponse(BaseModel):
    """Output of ``POST /parse-lease``: structure only, no legal verdicts."""

    file_name: str
    extraction: ExtractionSummary
    clauses: list[ClauseOutline] = Field(default_factory=list)
    clause_count: int = 0
    strategy: str
    warnings: list[str] = Field(default_factory=list)
    text_preview: str = Field(
        default="",
        description="First 2,000 characters of the normalised text (truncated for privacy).",
    )
    coordinates: list[PageLayout] | None = Field(
        default=None,
        description="Per-page line and word boxes, returned only when requested.",
    )


class AnnotateRequest(BaseModel):
    """Either a live session or one of the demo leases can be annotated."""

    model_config = ConfigDict(extra="forbid")

    session_id: str | None = Field(
        default=None, description="Session id returned by /analyze."
    )
    sample_id: str | None = Field(
        default=None, description="Demo lease id, e.g. ``sample-high-deposit``."
    )
    include_summary_page: bool = Field(
        default=True,
        description="Prepend a cover page with the risk score, drivers and legend.",
    )

    @model_validator(mode="after")
    def _exactly_one_target(self) -> AnnotateRequest:
        provided = [value for value in (self.session_id, self.sample_id) if value]
        if len(provided) != 1:
            raise ValueError("Provide exactly one of 'session_id' or 'sample_id'.")
        return self

    @property
    def target_id(self) -> str:
        """The id to look up in the session cache."""
        return self.session_id or self.sample_id or ""


class RuleCatalogue(BaseModel):
    """Everything needed to audit the benchmarks behind a verdict."""

    statute: StatuteInfo
    scoring_version: str
    severity_points: dict[str, int] = Field(default_factory=dict)
    category_importance: dict[str, float] = Field(default_factory=dict)
    breadth_bonus_per_violation: int = 0
    breadth_bonus_cap: int = 0
    risk_bands: list[RiskBand] = Field(default_factory=list)
    rule_count: int = 0
    rules: list[RuleDefinition] = Field(default_factory=list)


class ComponentHealth(BaseModel):
    """Status of one dependency."""

    status: str = "ok"
    detail: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    """Liveness plus enough diagnostics to trust a demo."""

    status: str
    version: str
    environment: str
    uptime_seconds: float
    statute: str
    components: dict[str, ComponentHealth] = Field(default_factory=dict)


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None
    request_id: str | None = None


class ErrorResponse(BaseModel):
    """The single error shape every endpoint returns."""

    error: ErrorBody
