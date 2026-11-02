"""Clause models: the structural unit of analysis plus its typed entities.

Design note ("LLM extracts, code decides"): the LLM may only populate
``ClauseCategory`` and ``ClauseEntities``. It never produces a verdict, a
severity or a score. Every numeric comparison happens in ``rule_engine`` against
typed values validated here.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import BoundingBox
from app.models.enums import ClauseCategory, ExtractionSource


class ClauseEntities(BaseModel):
    """Typed facts extracted from a clause.

    A single flat model (rather than one model per category) keeps the rule base
    declarative: a YAML rule simply names the field it reads, e.g.
    ``field: deposit_months``. Fields are ``None`` when the clause does not state
    them - *unknown* is deliberately distinct from *zero*/*false*.
    """

    model_config = ConfigDict(extra="ignore")

    # -- deposit ------------------------------------------------------------
    deposit_months: float | None = Field(default=None, ge=0, le=120)
    deposit_amount_inr: float | None = Field(default=None, ge=0)
    deposit_refund_days: int | None = Field(default=None, ge=0, le=3650)
    deposit_non_refundable: bool | None = None
    deposit_forfeiture_on_early_exit: bool | None = None

    # -- lock-in ------------------------------------------------------------
    lock_in_months: float | None = Field(default=None, ge=0, le=120)
    lock_in_penalty_months: float | None = Field(default=None, ge=0, le=120)
    lock_in_penalty_inr: float | None = Field(default=None, ge=0)

    # -- eviction / notice --------------------------------------------------
    notice_period_days: int | None = Field(default=None, ge=0, le=3650)
    landlord_eviction_notice_days: int | None = Field(default=None, ge=0, le=3650)
    allows_immediate_eviction: bool | None = None
    eviction_grounds: list[str] = Field(default_factory=list)
    double_rent_penalty: bool | None = None

    # -- rent revision ------------------------------------------------------
    rent_increase_percent: float | None = Field(default=None, ge=0, le=1000)
    rent_increase_frequency_months: int | None = Field(default=None, ge=0, le=600)
    rent_increase_notice_days: int | None = Field(default=None, ge=0, le=3650)
    rent_increase_unilateral: bool | None = None
    rent_increase_during_fixed_term: bool | None = None

    # -- entry rights -------------------------------------------------------
    entry_notice_hours: float | None = Field(default=None, ge=0, le=8760)
    unrestricted_entry: bool | None = None
    landlord_retains_keys: bool | None = None
    entry_outside_allowed_hours: bool | None = None

    # -- maintenance --------------------------------------------------------
    tenant_pays_structural_repairs: bool | None = None
    tenant_pays_all_repairs: bool | None = None
    landlord_repair_duty_waived: bool | None = None
    repair_deduction_allowed: bool | None = None
    essential_services_cutoff_allowed: bool | None = None

    # -- general / formalities ---------------------------------------------
    mentions_rent_authority: bool | None = None
    agreement_unregistered: bool | None = None
    original_agreement_withheld: bool | None = None

    # -- provenance ---------------------------------------------------------
    field_sources: dict[str, str] = Field(
        default_factory=dict,
        description="field name -> 'llm' | 'heuristic', for auditability",
    )

    def known_values(self) -> dict[str, Any]:
        """Only the non-empty fields, useful for reporting and logs."""
        return {
            key: value
            for key, value in self.model_dump(exclude={"field_sources"}).items()
            if value not in (None, [])
        }

    def merge_missing(self, other: ClauseEntities) -> None:
        """Fill fields that are ``None`` here with values from ``other``."""
        for key, value in other.model_dump(exclude={"field_sources"}).items():
            if value in (None, []) or key == "field_sources":
                continue
            current = getattr(self, key)
            if current in (None, []):
                setattr(self, key, value)
                source = other.field_sources.get(key)
                if source:
                    self.field_sources[key] = source


class Clause(BaseModel):
    """A logical clause detected in the agreement, enriched in place.

    ``category``/``entities`` start empty and are populated by the classifier;
    the object is passed through the pipeline as a single mutable record.
    """

    clause_id: str = Field(description="Stable identifier, e.g. 'c007'")
    order: int = Field(ge=0, description="1-based position in the document")
    heading: str
    raw_text: str
    page_number: int = Field(ge=1)
    bbox: BoundingBox | None = None
    spans: list[ClauseSpan] = Field(default_factory=list)

    # Enrichment (filled by ai_classifier)
    category: ClauseCategory = ClauseCategory.GENERAL
    category_confidence: float = Field(default=0.0, ge=0, le=1)
    entities: ClauseEntities = Field(default_factory=ClauseEntities)
    extraction_source: ExtractionSource = ExtractionSource.HEURISTIC
    classification_notes: list[str] = Field(default_factory=list)

    @property
    def text_for_prompt(self) -> str:
        """Clause text with the heading removed, trimmed for token efficiency."""
        body = self.raw_text
        if self.heading and body.lower().startswith(self.heading.lower()):
            body = body[len(self.heading) :]
        return body.strip()

    def annotation_boxes(self) -> list[tuple[int, BoundingBox]]:
        """Per-page rectangles to highlight for this clause."""
        if self.spans:
            return [(span.page_number, span.bbox) for span in self.spans if span.bbox]
        if self.bbox is not None:
            return [(self.page_number, self.bbox)]
        return []


class ClauseSpan(BaseModel):
    """The portion of a clause that lives on one page."""

    page_number: int = Field(ge=1)
    bbox: BoundingBox
    line_count: int = 1


Clause.model_rebuild()


class ClauseOutline(BaseModel):
    """A clause as the parse-only endpoint reports it.

    Mirrors the documented contract - id, heading, text, page and box - and adds
    the per-page spans, so a caller can highlight a clause that straddles a page
    break without re-parsing the PDF.
    """

    clause_id: str
    order: int
    heading: str
    raw_text: str
    page_number: int
    char_count: int
    bbox: list[float] | None = Field(
        default=None,
        description="Page-space rectangle [x0, y0, x1, y1] of the clause's first box.",
    )
    spans: list[ClauseSpan] = Field(
        default_factory=list,
        description="One entry per page the clause touches, in reading order.",
    )

    @classmethod
    def from_clause(cls, clause: Clause) -> ClauseOutline:
        return cls(
            clause_id=clause.clause_id,
            order=clause.order,
            heading=clause.heading,
            raw_text=clause.raw_text,
            page_number=clause.page_number,
            char_count=len(clause.raw_text),
            bbox=clause.bbox.as_list() if clause.bbox else None,
            spans=clause.spans,
        )


class ClauseSplitResult(BaseModel):
    """Result of the splitter, including diagnostics used by tests and UI."""

    clauses: list[Clause] = Field(default_factory=list)
    strategy: str = "numbered_headings"
    dropped_boilerplate_lines: int = 0
    warnings: list[str] = Field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.clauses)
