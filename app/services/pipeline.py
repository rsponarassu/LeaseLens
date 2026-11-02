"""End-to-end orchestration.

    PDF bytes
      -> parse (text layer / OCR)          [pdf_parser]
      -> split into clauses                [clause_splitter]
      -> classify + extract typed entities [ai_classifier]
      -> apply YAML benchmarks             [rule_engine]
      -> build findings + risk assessment  [this module + fix_generator]
      -> render highlights                 [pdf_annotator]

Only the third stage can call a model, and it may only return labels and typed
values. Verdicts, severities and the 0-100 score are produced by code.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field

from app.core.config import Settings, get_settings
from app.core.errors import NoClausesFoundError
from app.llm.base import LLMClient
from app.llm.factory import build_llm_client
from app.models.analysis import (
    AnalysisReport,
    ClauseFinding,
    EngineMetadata,
)
from app.models.clause import Clause, ClauseOutline
from app.models.document import ExtractedDocument, ExtractionSummary
from app.models.enums import (
    ClauseCategory,
    FindingStatus,
    RiskColor,
    Severity,
)
from app.models.rules import RuleBase, RuleEvaluation, StatuteReference
from app.rules.loader import get_rule_base
from app.services.ai_classifier import ClauseClassifier
from app.services.clause_splitter import ClauseSplitter
from app.services.fix_generator import FixItKitBuilder, PartyContext
from app.services.pdf_annotator import AnnotationSummary, HighlightSpec, PdfAnnotator
from app.services.pdf_parser import PdfParser
from app.services.rule_engine import CATEGORY_LABELS, RuleEngine, RuleEngineResult

logger = logging.getLogger(__name__)

MAX_FINDING_TEXT = 2400


@dataclass
class AnalysisOptions:
    """Per-request switches."""

    use_llm: bool = True
    parties: PartyContext | None = None
    sample_id: str | None = None
    session_id: str | None = None


@dataclass
class ParseResult:
    """Output of the parse + split stages (no model, no rules)."""

    document: ExtractedDocument
    clauses: list[Clause]
    strategy: str
    warnings: list[str] = field(default_factory=list)

    @property
    def outline(self) -> list[ClauseOutline]:
        return [ClauseOutline.from_clause(clause) for clause in self.clauses]


@dataclass
class AnalysisResult:
    """Everything the API needs from one analysis run."""

    report: AnalysisReport
    clauses: list[Clause]
    highlights: list[HighlightSpec]
    summary_spec: AnnotationSummary
    source_pdf: bytes


class AnalysisPipeline:
    """Stateless service that runs the full analysis for one document."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        rule_base: RuleBase | None = None,
        llm_client: LLMClient | None = None,
        llm_client_factory: bool = True,
    ) -> None:
        self.settings = settings or get_settings()
        self.rule_base = rule_base or get_rule_base()
        self.parser = PdfParser(self.settings)
        self.splitter = ClauseSplitter()
        self.engine = RuleEngine(self.rule_base)
        self.fix_builder = FixItKitBuilder(self.rule_base, self.settings)
        self.annotator = PdfAnnotator()
        self._llm_client = llm_client
        self._owns_llm_client = llm_client is None and llm_client_factory
        self._llm_resolved = llm_client is not None or not llm_client_factory

    # -- LLM lifecycle ------------------------------------------------------
    def _client(self) -> LLMClient | None:
        if not self._llm_resolved:
            self._llm_client = build_llm_client(self.settings)
            self._llm_resolved = True
        return self._llm_client

    async def aclose(self) -> None:
        if self._owns_llm_client and self._llm_client is not None:
            await self._llm_client.aclose()
        self._llm_client = None
        self._llm_resolved = not self._owns_llm_client

    # -- stage 1 + 2 --------------------------------------------------------
    def parse_document(self, pdf_bytes: bytes, file_name: str) -> ParseResult:
        document = self.parser.parse(pdf_bytes, file_name)
        split = self.splitter.split(document)
        if not split.clauses:
            raise NoClausesFoundError()
        return ParseResult(
            document=document,
            clauses=split.clauses,
            strategy=split.strategy,
            warnings=[*document.warnings, *split.warnings],
        )

    # -- full run -----------------------------------------------------------
    async def analyze(
        self,
        pdf_bytes: bytes,
        file_name: str,
        options: AnalysisOptions | None = None,
    ) -> AnalysisResult:
        opts = options or AnalysisOptions()
        started = time.perf_counter()

        parsed = await asyncio.to_thread(self.parse_document, pdf_bytes, file_name)

        client = self._client() if opts.use_llm else None
        classifier = ClauseClassifier(self.settings, llm_client=client)
        classification = await classifier.classify(parsed.clauses)

        engine_result = self.engine.evaluate(classification.clauses)
        assert engine_result.risk is not None

        findings, highlights = self._build_findings(
            classification.clauses, engine_result, opts.parties
        )
        summary_email = self.fix_builder.build_summary_email(
            [
                (clause, evaluation)
                for clause in classification.clauses
                for evaluation in engine_result.evaluations_for(clause.clause_id)
                if evaluation.is_violation
            ],
            opts.parties,
        )

        duration_ms = int((time.perf_counter() - started) * 1000)
        session_id = opts.session_id or uuid.uuid4().hex

        report = AnalysisReport(
            session_id=session_id,
            sample_id=opts.sample_id,
            file_name=file_name,
            file_size_bytes=len(pdf_bytes),
            page_count=parsed.document.page_count,
            statute=self.rule_base.statute,
            risk=engine_result.risk,
            findings=findings,
            extraction=ExtractionSummary.from_document(parsed.document),
            engine=EngineMetadata(
                analysis_mode=classification.mode,
                llm_provider=self.settings.resolved_llm_provider if opts.use_llm else "offline",
                llm_model=self.settings._active_model() if opts.use_llm else None,
                llm_calls=classification.stats.llm_calls,
                llm_failures=classification.stats.llm_failures,
                llm_latency_ms=classification.stats.llm_latency_ms,
                classification_source_breakdown=classification.source_breakdown,
                clause_count=len(classification.clauses),
                duration_ms=duration_ms,
                warnings=[*parsed.warnings, *classification.warnings],
            ),
            annotated_pdf_url=f"{self.settings.api_prefix}/download-annotated/{session_id}",
            disclaimer=self.settings.disclaimer,
            summary_email=summary_email,
            clauses=classification.clauses,
        )

        summary_spec = self._summary_spec(report)
        logger.info(
            "analysis complete: session=%s clauses=%s violations=%s score=%s mode=%s in %sms",
            session_id,
            len(classification.clauses),
            engine_result.risk.violation_count,
            engine_result.risk.overall_score,
            classification.mode.value,
            duration_ms,
        )
        return AnalysisResult(
            report=report,
            clauses=classification.clauses,
            highlights=highlights,
            summary_spec=summary_spec,
            source_pdf=pdf_bytes,
        )

    # -- findings -----------------------------------------------------------
    def _build_findings(
        self,
        clauses: Sequence[Clause],
        engine_result: RuleEngineResult,
        parties: PartyContext | None,
    ) -> tuple[list[ClauseFinding], list[HighlightSpec]]:
        findings: list[ClauseFinding] = []
        highlights: list[HighlightSpec] = []

        for clause in clauses:
            evaluations = engine_result.evaluations_for(clause.clause_id)
            violations = [e for e in evaluations if e.is_violation]
            applicable = [e for e in evaluations if e.status is FindingStatus.COMPLIANT]

            if violations:
                primary = max(violations, key=lambda e: (e.penalty_points, e.severity.rank))
                severity = max((e.severity for e in violations), key=lambda s: s.rank)
                color = _colour_for(severity)
                status = FindingStatus.VIOLATION
                fix = self.fix_builder.build(clause, evaluations, parties)
                headline = primary.message
                references = self._statute_references(violations)
                compliant_rules: list[str] = []
            elif applicable:
                status = FindingStatus.COMPLIANT
                severity = Severity.INFO
                color = RiskColor.GREEN
                fix = None
                headline = (
                    f"Compliant - {len(applicable)} statutory check(s) passed "
                    f"for {CATEGORY_LABELS[clause.category]}."
                )
                references = self._statute_references(applicable)
                compliant_rules = [evaluation.rule_id for evaluation in applicable]
            else:
                status = FindingStatus.NOT_APPLICABLE
                severity = Severity.INFO
                color = RiskColor.GREY
                fix = None
                headline = "No statutory benchmark applies to this clause."
                references = []
                compliant_rules = []

            findings.append(
                ClauseFinding(
                    clause_id=clause.clause_id,
                    heading=clause.heading,
                    category=clause.category,
                    page_number=clause.page_number,
                    bbox=clause.bbox.as_list() if clause.bbox else None,
                    raw_text=clause.raw_text[:MAX_FINDING_TEXT],
                    status=status,
                    severity=severity,
                    risk_color=color,
                    headline=headline,
                    category_confidence=clause.category_confidence,
                    extracted=clause.entities,
                    violations=violations,
                    compliant_rules=compliant_rules,
                    statute_references=references,
                    fix=fix,
                )
            )

            if status is not FindingStatus.NOT_APPLICABLE:
                note = _annotation_note(clause, findings[-1])
                for page_number, bbox in clause.annotation_boxes():
                    highlights.append(
                        HighlightSpec(
                            page_number=page_number,
                            bbox=(bbox.x0, bbox.y0, bbox.x1, bbox.y1),
                            color=color,
                            title=f"{category_title(clause.category)} - {color.value}",
                            note=note,
                            clause_id=clause.clause_id,
                        )
                    )

        findings.sort(key=_finding_sort_key)
        return findings, highlights

    # -- annotation ---------------------------------------------------------
    def _statute_references(
        self, evaluations: list[RuleEvaluation]
    ) -> list[StatuteReference]:
        """Resolve rule ids to their statutory citations, de-duplicated."""
        references: list[StatuteReference] = []
        seen: set[tuple[str, str]] = set()
        for evaluation in evaluations:
            rule = self.rule_base.by_id(evaluation.rule_id)
            if rule is None:
                continue
            key = (rule.statute.section, rule.statute.heading)
            if key in seen:
                continue
            seen.add(key)
            references.append(rule.statute)
        return references

    def _summary_spec(self, report: AnalysisReport) -> AnnotationSummary:
        return AnnotationSummary(
            file_name=report.file_name,
            risk_score=report.risk.overall_score,
            risk_level=report.risk.risk_level.value,
            band_label=report.risk.band_label,
            headline=report.risk.headline,
            violation_count=report.risk.violation_count,
            compliant_count=report.risk.compliant_count,
            top_drivers=tuple(report.risk.top_drivers),
            statute_name=self.rule_base.statute.act,
            disclaimer=report.disclaimer,
        )

    def annotate_result(self, result: AnalysisResult, *, include_summary: bool = True) -> bytes:
        return self.annotator.annotate(
            result.source_pdf,
            result.highlights,
            result.summary_spec if include_summary else None,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _colour_for(severity: Severity) -> RiskColor:
    if severity in (Severity.CRITICAL, Severity.HIGH):
        return RiskColor.RED
    if severity is Severity.MODERATE:
        return RiskColor.AMBER
    if severity is Severity.LOW:
        return RiskColor.GREY
    return RiskColor.GREY


def category_title(category: ClauseCategory) -> str:
    return CATEGORY_LABELS.get(category, category.value).title()


def _annotation_note(clause: Clause, finding: ClauseFinding) -> str:
    parts = [finding.headline]
    if finding.status is FindingStatus.VIOLATION and finding.fix:
        parts.append(finding.fix.explanation_en.split("\n\n")[0])
    extracted = clause.entities.known_values()
    if extracted:
        rendered = ", ".join(
            f"{key}={value}" for key, value in list(extracted.items())[:6]
        )
        parts.append(f"Extracted: {rendered}")
    return "\n\n".join(part for part in parts if part)[:1800]


def _finding_sort_key(finding: ClauseFinding) -> tuple[int, int, int]:
    if finding.status is FindingStatus.VIOLATION:
        group = 0
    elif finding.status is FindingStatus.COMPLIANT:
        group = 1
    else:
        group = 2
    return (group, -finding.severity.rank, finding.page_number)
