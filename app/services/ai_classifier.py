"""Clause classification orchestration.

Reconciliation policy between the LLM and the deterministic extractor is explicit
and testable:

* **Category** - the LLM wins when it is confident (>= 0.35) *unless* it says
  ``general`` while the regex evidence points at a substantive domain.
* **Numbers** - when both sources produce a value and they disagree, the regex
  value wins: it matched a literal number with a unit in the clause text, while a
  model may have paraphrased. The conflict is recorded in ``classification_notes``.
* **Booleans** - the LLM wins (semantics, not arithmetic), then the regex fills gaps.
* **Everything the LLM omits** - the regex fills.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.llm.base import LLMClauseResult, LLMClient
from app.models.clause import Clause, ClauseEntities
from app.models.enums import AnalysisMode, ClauseCategory, ExtractionSource
from app.services.heuristic_extractor import HeuristicExtractor

logger = logging.getLogger(__name__)

# Numeric fields where a literal in the text beats a model's paraphrase.
CODE_DECIDES_FIELDS: tuple[str, ...] = (
    "deposit_months",
    "deposit_amount_inr",
    "deposit_refund_days",
    "lock_in_months",
    "lock_in_penalty_months",
    "lock_in_penalty_inr",
    "notice_period_days",
    "landlord_eviction_notice_days",
    "rent_increase_percent",
    "rent_increase_frequency_months",
    "rent_increase_notice_days",
    "entry_notice_hours",
)


@dataclass
class ClassifierStats:
    """Aggregate LLM behaviour, surfaced in ``EngineMetadata``."""

    llm_calls: int = 0
    llm_failures: int = 0
    llm_latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    batches: int = 0


@dataclass
class ClassifierResult:
    """Classified clauses plus the provenance needed for the report."""

    clauses: list[Clause]
    mode: AnalysisMode
    stats: ClassifierStats = field(default_factory=ClassifierStats)
    warnings: list[str] = field(default_factory=list)
    source_breakdown: dict[str, int] = field(default_factory=dict)


class ClauseClassifier:
    """Runs the heuristic extractor and (optionally) the LLM, then merges."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        llm_client: LLMClient | None = None,
        extractor: HeuristicExtractor | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.client = llm_client
        self.extractor = extractor or HeuristicExtractor()

    # -- public API ---------------------------------------------------------
    async def classify(self, clauses: Sequence[Clause]) -> ClassifierResult:
        clause_list = list(clauses)
        heuristics = {clause.clause_id: self.extractor.extract(clause) for clause in clause_list}

        stats = ClassifierStats()
        warnings: list[str] = []
        llm_results: dict[str, LLMClauseResult] = {}

        if self.client is not None and clause_list:
            llm_results = await self._run_llm(clause_list, stats, warnings)

        for clause in clause_list:
            self._apply(clause, heuristics[clause.clause_id], llm_results.get(clause.clause_id))

        if self.client is None:
            mode = AnalysisMode.OFFLINE_HEURISTIC
        elif stats.llm_failures:
            mode = AnalysisMode.LLM_DEGRADED
        else:
            mode = AnalysisMode.LLM_ASSISTED

        breakdown: dict[str, int] = {}
        for clause in clause_list:
            key = clause.extraction_source.value
            breakdown[key] = breakdown.get(key, 0) + 1

        return ClassifierResult(
            clauses=clause_list,
            mode=mode,
            stats=stats,
            warnings=warnings,
            source_breakdown=breakdown,
        )

    # -- LLM fan-out --------------------------------------------------------
    async def _run_llm(
        self,
        clauses: list[Clause],
        stats: ClassifierStats,
        warnings: list[str],
    ) -> dict[str, LLMClauseResult]:
        assert self.client is not None
        batch_size = max(1, self.settings.llm_batch_size)
        batches = [
            clauses[index : index + batch_size] for index in range(0, len(clauses), batch_size)
        ]
        semaphore = asyncio.Semaphore(max(1, self.settings.llm_max_concurrency))
        stats.batches = len(batches)

        async def run(batch: list[Clause]) -> tuple[list[LLMClauseResult], bool]:
            async with semaphore:
                started = time.perf_counter()
                try:
                    result = await self.client.classify_batch(batch)  # type: ignore[union-attr]
                except Exception as exc:  # noqa: BLE001 - degrade, never fail the request
                    elapsed = int((time.perf_counter() - started) * 1000)
                    stats.llm_failures += 1
                    stats.llm_latency_ms += elapsed
                    logger.warning("LLM batch failed (%s clauses): %s", len(batch), exc)
                    warnings.append(
                        "The language model could not classify part of this document; "
                        "deterministic extraction was used for those clauses."
                    )
                    return [], False
                stats.llm_calls += 1
                stats.llm_latency_ms += result.usage.latency_ms
                stats.input_tokens += result.usage.input_tokens
                stats.output_tokens += result.usage.output_tokens
                return list(result.results), True

        outcomes = await asyncio.gather(*(run(batch) for batch in batches))

        known_ids = {clause.clause_id for clause in clauses}
        merged: dict[str, LLMClauseResult] = {}
        for results, _ok in outcomes:
            for item in results:
                if item.clause_id in known_ids:
                    merged[item.clause_id] = item
                else:
                    logger.debug("ignoring unknown clause_id from LLM: %s", item.clause_id)

        missing = known_ids - merged.keys()
        if missing and not stats.llm_failures:
            warnings.append(
                f"The language model omitted {len(missing)} clause(s); deterministic "
                "extraction was used for them."
            )
        return merged

    # -- merge --------------------------------------------------------------
    def _apply(
        self,
        clause: Clause,
        heuristic: Any,
        llm: LLMClauseResult | None,
    ) -> None:
        entities = ClauseEntities()
        notes: list[str] = []

        if llm is not None:
            llm_entities, problems = _sanitise_llm_entities(llm.entities)
            entities = llm_entities
            notes.extend(problems)

        entities.merge_missing(heuristic.entities)

        # -- category -------------------------------------------------------
        category = heuristic.category
        confidence = heuristic.confidence
        source = ExtractionSource.HEURISTIC

        if llm is not None and llm.confidence >= 0.35:
            if llm.category is ClauseCategory.GENERAL and heuristic.category is not ClauseCategory.GENERAL:
                notes.append(
                    f"LLM labelled this clause 'general' but the text points to "
                    f"'{heuristic.category.value}'; keeping '{heuristic.category.value}'."
                )
            else:
                category = llm.category
                confidence = llm.confidence
                source = (
                    ExtractionSource.HYBRID
                    if heuristic.category is not ClauseCategory.GENERAL
                    and heuristic.category is not llm.category
                    else ExtractionSource.LLM
                )
                if heuristic.category is not ClauseCategory.GENERAL and heuristic.category is not llm.category:
                    notes.append(
                        f"Category disagreement: regex suggested "
                        f"'{heuristic.category.value}', model said '{llm.category.value}'."
                    )
        elif llm is not None:
            notes.append("Low-confidence model label; regex classification kept.")

        # -- numbers: code decides -----------------------------------------
        if llm is not None:
            for field_name in CODE_DECIDES_FIELDS:
                code_value = getattr(heuristic.entities, field_name)
                model_value = getattr(entities, field_name)
                if code_value is None or model_value is None:
                    continue
                if not _close(code_value, model_value):
                    setattr(entities, field_name, code_value)
                    entities.field_sources[field_name] = "heuristic"
                    notes.append(
                        f"{field_name}: model said {model_value}, text says {code_value}; "
                        "the literal text value was used."
                    )
            if source is ExtractionSource.LLM and entities.field_sources:
                source = ExtractionSource.HYBRID

        clause.category = category
        clause.category_confidence = round(confidence, 2)
        clause.entities = entities
        clause.extraction_source = source
        clause.classification_notes = [*clause.classification_notes, *notes][:12]


def _sanitise_llm_entities(payload: dict[str, Any]) -> tuple[ClauseEntities, list[str]]:
    """Validate model output field by field, dropping anything malformed."""
    entities = ClauseEntities()
    problems: list[str] = []
    valid_fields = set(ClauseEntities.model_fields) - {"field_sources"}

    for name, value in payload.items():
        if name not in valid_fields or value in (None, "", []):
            continue
        try:
            probe = ClauseEntities(**{name: value})
        except ValidationError:
            problems.append(f"Ignored invalid model value for '{name}'.")
            continue
        coerced = getattr(probe, name)
        setattr(entities, name, coerced)
        entities.field_sources[name] = "llm"
    return entities, problems


def _close(left: Any, right: Any) -> bool:
    try:
        return abs(float(left) - float(right)) < 1e-6
    except (TypeError, ValueError):
        return left == right
