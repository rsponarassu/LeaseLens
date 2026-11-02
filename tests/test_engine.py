"""Deterministic core: rule base, extractor, splitter, scorer and caches.

These tests deliberately avoid the API. The division of labour that makes the
product defensible - the model extracts, this code decides - is only meaningful
if the deciding half can be tested without a network or a document upload.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from app.cache.sessions import AnalysisSession, SessionCache
from app.cache.ttl_cache import TTLCache
from app.core.config import Settings
from app.core.errors import SessionExpiredError, SessionNotFoundError
from app.models.clause import Clause
from app.models.enums import ClauseCategory, RuleOperator, Severity
from app.rules.loader import get_rule_base
from app.services.heuristic_extractor import HeuristicExtractor
from app.services.pipeline import AnalysisOptions, AnalysisPipeline


# ---------------------------------------------------------------------------
# Rule base
# ---------------------------------------------------------------------------
def test_rule_base_pins_the_tamil_nadu_act():
    statute = get_rule_base().statute

    assert statute.act_number == "Act 42 of 2017"
    assert statute.year == 2017
    assert "Tamil Nadu" in statute.jurisdiction


def test_every_tenancy_domain_has_benchmarks():
    base = get_rule_base()
    covered = {rule.category for rule in base.rules}

    assert covered >= {
        ClauseCategory.DEPOSIT,
        ClauseCategory.LOCK_IN,
        ClauseCategory.EVICTION,
        ClauseCategory.RENT_HIKE,
        ClauseCategory.ENTRY_RIGHTS,
        ClauseCategory.MAINTENANCE,
    }


def test_default_deposit_limit_is_three_months():
    rule = get_rule_base().by_id("DEP-001")

    assert rule is not None
    assert rule.field == "deposit_months"
    assert rule.operator is RuleOperator.GREATER_THAN
    assert rule.value == 3
    assert rule.severity is Severity.HIGH
    assert rule.statute.section


def test_every_rule_carries_bilingual_copy_and_a_citation():
    for rule in get_rule_base().rules:
        assert rule.explanation.strip()
        assert rule.tamil.strip()
        assert rule.counter_clause.strip()
        assert rule.statute.quote.strip()


# ---------------------------------------------------------------------------
# Deterministic extraction
# ---------------------------------------------------------------------------
def clause(text: str, heading: str = "7. Security deposit") -> Clause:
    return Clause(
        clause_id="c001",
        order=1,
        heading=heading,
        raw_text=f"{heading}: {text}",
        page_number=1,
    )


DEPOSIT_TEXT = (
    "The Tenant shall pay an interest free security deposit of 10 months rent "
    "amounting to Rs. 4,80,000 to the Landlord before taking possession."
)


def test_extractor_reads_the_deposit_in_months():
    result = HeuristicExtractor().extract(clause(DEPOSIT_TEXT))

    assert result.category is ClauseCategory.DEPOSIT
    assert result.entities.deposit_months == 10
    assert result.entities.field_sources.get("deposit_months") == "heuristic"


def test_extractor_ignores_months_that_are_not_a_deposit():
    result = HeuristicExtractor().extract(
        clause("The rent shall be increased by 10 percent after the first 12 months.")
    )

    assert result.entities.deposit_months is None


def test_extractor_respects_a_negated_lockout():
    result = HeuristicExtractor().extract(
        clause(
            "The Landlord shall not cut off water or electricity supply on any ground "
            "whatsoever.",
            heading="10. Essential services",
        )
    )

    assert result.entities.essential_services_cutoff_allowed is not True


def test_extractor_does_not_blame_the_tenant_for_the_landlord_repairs():
    result = HeuristicExtractor().extract(
        clause(
            "The Landlord shall carry out all structural repairs to the roof and walls.",
            heading="8. Repairs",
        )
    )

    assert result.entities.tenant_pays_structural_repairs is not True


# ---------------------------------------------------------------------------
# End-to-end determinism
# ---------------------------------------------------------------------------
def _score_twice(pdf: bytes) -> tuple[int, int]:
    pipeline = AnalysisPipeline(Settings(llm_provider="offline"))
    options = AnalysisOptions(use_llm=False)

    async def run() -> tuple[int, int]:
        first = await pipeline.analyze(pdf, "lease.pdf", options)
        second = await pipeline.analyze(pdf, "lease.pdf", options)
        return first.report.risk.overall_score, second.report.risk.overall_score

    try:
        return asyncio.run(run())
    finally:
        asyncio.run(pipeline.aclose())


def test_the_same_document_always_gets_the_same_score(high_risk_pdf):
    first, second = _score_twice(high_risk_pdf)

    assert first == second
    assert first >= 80


# ---------------------------------------------------------------------------
# Caches
# ---------------------------------------------------------------------------
def test_ttl_cache_expires_entries():
    cache: TTLCache[str, str] = TTLCache(max_entries=4, ttl_seconds=0.01)
    cache.set("a", "value")

    assert cache.get("a") == "value"
    # Generous margin: the Windows clock granularity is coarser than the TTL.
    time.sleep(0.2)
    assert cache.get("a") is None
    assert len(cache) == 0


def test_ttl_cache_evicts_the_least_recently_used_entry():
    cache: TTLCache[str, int] = TTLCache(max_entries=2, ttl_seconds=60)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.get("a")  # 'b' becomes the least recently used
    cache.set("c", 3)

    assert cache.get("a") == 1
    assert cache.get("b") is None
    assert cache.get("c") == 3
    assert cache.evictions == 1


def test_ttl_cache_enforces_the_byte_budget():
    cache: TTLCache[str, str] = TTLCache(max_entries=10, ttl_seconds=60, max_bytes=100)
    cache.set("big", "x" * 80, size=80)
    cache.set("also-big", "y" * 80, size=80)

    assert len(cache) == 1
    assert cache.total_bytes <= 100


def test_ttl_cache_zero_ttl_means_never_expires():
    cache: TTLCache[str, int] = TTLCache(max_entries=2, ttl_seconds=0)
    cache.set("pinned", 1)

    time.sleep(0.02)
    assert cache.get("pinned") == 1


def test_session_cache_distinguishes_unknown_from_expired():
    sessions = SessionCache(Settings(llm_provider="offline"))
    session = AnalysisSession(
        session_id="abc",
        report=None,  # type: ignore[arg-type]
        clauses=[],
        highlights=[],
        summary_spec=None,  # type: ignore[arg-type]
        source_pdf=b"%PDF",
    )
    sessions.put(session, ttl_seconds=60)

    assert sessions.get("abc") is session

    sessions._cache.delete("abc")  # simulate the TTL lapsing
    with pytest.raises(SessionExpiredError):
        sessions.get("abc")

    with pytest.raises(SessionNotFoundError):
        sessions.get("never-seen")


def test_invalidate_forgets_the_session_and_its_tombstone():
    sessions = SessionCache(Settings(llm_provider="offline"))
    session = AnalysisSession(
        session_id="def",
        report=None,  # type: ignore[arg-type]
        clauses=[],
        highlights=[],
        summary_spec=None,  # type: ignore[arg-type]
        source_pdf=b"%PDF",
    )
    sessions.put(session, ttl_seconds=60)

    assert sessions.invalidate("def") is True
    with pytest.raises(SessionNotFoundError):
        sessions.get("def")
