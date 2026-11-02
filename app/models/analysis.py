"""Analysis report models: what the API actually returns.

A report is self-contained: a frontend can render the risk dashboard, the
clause-by-clause verdicts, the bilingual Fix-it Kit and the statutory citations
without any further calls.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.clause import Clause, ClauseEntities
from app.models.document import ExtractionSummary
from app.models.enums import (
    AnalysisMode,
    ClauseCategory,
    FindingStatus,
    Language,
    RiskColor,
    RiskLevel,
    Severity,
)
from app.models.rules import RiskAssessment, RuleEvaluation, StatuteInfo, StatuteReference


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


class FixItKit(BaseModel):
    """The remediation kit attached to every flagged clause."""

    explanation_en: str
    explanation_ta: str
    counter_clause: str
    email_subject: str
    email_body: str
    negotiation_tips: list[str] = Field(default_factory=list)
    languages: list[Language] = Field(
        default_factory=lambda: [Language.ENGLISH, Language.TAMIL]
    )

    @property
    def explanation(self) -> dict[str, str]:
        return {"en": self.explanation_en, "ta": self.explanation_ta}


class EmailDraft(BaseModel):
    """A ready-to-send message the tenant can copy into email/WhatsApp."""

    subject: str
    body: str
    recipient_hint: str = "landlord"


class ClauseFinding(BaseModel):
    """Verdict for one clause, including its remediation kit."""

    model_config = ConfigDict(extra="ignore")

    clause_id: str
    heading: str
    category: ClauseCategory
    page_number: int
    bbox: list[float] | None = None
    raw_text: str
    status: FindingStatus
    severity: Severity
    risk_color: RiskColor
    headline: str
    category_confidence: float = 0.0

    extracted: ClauseEntities = Field(default_factory=ClauseEntities)
    violations: list[RuleEvaluation] = Field(default_factory=list)
    compliant_rules: list[str] = Field(default_factory=list)
    statute_references: list[StatuteReference] = Field(default_factory=list)

    fix: FixItKit | None = None

    @property
    def is_violation(self) -> bool:
        return self.status in (FindingStatus.VIOLATION, FindingStatus.INFORMATIONAL)


class EngineMetadata(BaseModel):
    """How the report was produced - required for auditability."""

    analysis_mode: AnalysisMode
    llm_provider: str
    llm_model: str | None = None
    llm_calls: int = 0
    llm_failures: int = 0
    llm_latency_ms: int = 0
    classification_source_breakdown: dict[str, int] = Field(default_factory=dict)
    clause_count: int = 0
    duration_ms: int = 0
    warnings: list[str] = Field(default_factory=list)


class AnalysisReport(BaseModel):
    """The complete analysis payload returned by ``POST /analyze``."""

    session_id: str
    sample_id: str | None = None
    file_name: str
    file_size_bytes: int
    page_count: int
    created_at: datetime = Field(default_factory=utc_now)
    cache_hit: bool = False

    statute: StatuteInfo
    risk: RiskAssessment
    findings: list[ClauseFinding] = Field(default_factory=list)
    extraction: ExtractionSummary
    engine: EngineMetadata
    clauses: list[Clause] = Field(default_factory=list, exclude=True)

    annotated_pdf_url: str
    summary_email: EmailDraft | None = None
    disclaimer: str

    @property
    def violations(self) -> list[ClauseFinding]:
        return [f for f in self.findings if f.status is FindingStatus.VIOLATION]

    @property
    def fix_it_kit(self) -> list[ClauseFinding]:
        return [f for f in self.findings if f.fix is not None]


class SampleLease(BaseModel):
    """A demo lease with its pre-computed analysis."""

    model_config = ConfigDict(extra="ignore")

    sample_id: str
    title: str
    tenant_persona: str
    property_description: str
    scenario: str
    expected_risk_level: RiskLevel
    pdf_url: str
    analysis: AnalysisReport


class AnalysisSummary(BaseModel):
    """Compact card view used by list endpoints and dashboards."""

    session_id: str
    sample_id: str | None = None
    file_name: str
    page_count: int
    overall_score: int
    risk_level: RiskLevel
    violation_count: int
    created_at: datetime
    top_drivers: list[str] = Field(default_factory=list)

    @classmethod
    def from_report(cls, report: AnalysisReport) -> AnalysisSummary:
        return cls(
            session_id=report.session_id,
            sample_id=report.sample_id,
            file_name=report.file_name,
            page_count=report.page_count,
            overall_score=report.risk.overall_score,
            risk_level=report.risk.risk_level,
            violation_count=report.risk.violation_count,
            created_at=report.created_at,
            top_drivers=report.risk.top_drivers[:3],
        )


class ReportEnvelope(BaseModel):
    """Wrapper so responses can carry metadata without breaking the schema."""

    report: AnalysisReport
    meta: dict[str, Any] = Field(default_factory=dict)
