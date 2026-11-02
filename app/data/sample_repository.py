"""Demo leases, analysed once and cached.

The three samples exist so a demo never depends on the network, an API key or a
particular upload. They are rendered from text at startup (no binary fixtures),
analysed with the deterministic path (``use_llm=False``) so the result is
reproducible, and then stored in the session cache under a stable id
(``sample-high-deposit`` and friends) so that
``GET /api/v1/download-annotated/sample-high-deposit`` works on a cold cache.

Each sample also declares the outcome it is supposed to demonstrate. If the rule
base or the extractor drifts, the self-check records a warning in the health
payload instead of silently serving a misleading demo.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass, field

from app.cache.sessions import AnalysisSession, SessionCache
from app.core.config import Settings, get_settings
from app.core.errors import SampleDataError, SampleNotFoundError
from app.data.sample_leases import SAMPLE_SPECS, SampleLeaseSpec, get_spec
from app.models.analysis import AnalysisReport, SampleLease
from app.services.fix_generator import PartyContext
from app.services.pipeline import AnalysisOptions, AnalysisPipeline, AnalysisResult
from app.services.sample_pdf import build_lease_pdf

logger = logging.getLogger(__name__)

CLOSING = (
    "Signed by the Landlord and the Tenant on the date first written above in the "
    "presence of the witnesses named below."
)

# Samples are pinned in the cache: their TTL is effectively infinite so a demo can
# be resumed at any point during the session.
SAMPLE_TTL_SECONDS = 0


@dataclass
class PreparedSample:
    """A rendered sample PDF plus its cached analysis."""

    spec: SampleLeaseSpec
    pdf_bytes: bytes
    result: AnalysisResult
    warnings: list[str] = field(default_factory=list)

    @property
    def sample_id(self) -> str:
        return self.spec.sample_id

    @property
    def report(self) -> AnalysisReport:
        return self.result.report

    def to_model(self, api_prefix: str) -> SampleLease:
        return SampleLease(
            sample_id=self.spec.sample_id,
            title=self.spec.title,
            tenant_persona=self.spec.tenant_persona,
            property_description=self.spec.property_description,
            scenario=self.spec.scenario,
            expected_risk_level=self.spec.expected_risk_level,
            pdf_url=f"{api_prefix}/sample-leases/{self.spec.sample_id}/pdf",
            analysis=self.report,
        )


class SampleLeaseRepository:
    """Owns the three demo leases for the lifetime of the process."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        pipeline: AnalysisPipeline | None = None,
        sessions: SessionCache | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.pipeline = pipeline or AnalysisPipeline(self.settings)
        self.sessions = sessions or SessionCache(self.settings)
        self._samples: dict[str, PreparedSample] = {}
        self._lock = threading.RLock()
        self._prepare_lock = asyncio.Lock()
        self._ready = False

    # -- lifecycle ----------------------------------------------------------
    @property
    def ready(self) -> bool:
        return self._ready

    async def ensure_ready(self) -> None:
        """Build the samples once, on first use or during startup."""
        if self._ready:
            return
        async with self._prepare_lock:
            if self._ready:
                return
            prepared: dict[str, PreparedSample] = {}
            for spec in SAMPLE_SPECS:
                prepared[spec.sample_id] = await self._prepare(spec)
            with self._lock:
                self._samples = prepared
                self._ready = True
            logger.info(
                "sample leases ready: %s",
                ", ".join(f"{s.sample_id}={s.report.risk.risk_level.value}" for s in prepared.values()),
            )

    async def _prepare(self, spec: SampleLeaseSpec) -> PreparedSample:
        pdf_bytes = build_lease_pdf(
            title=spec.title,
            subtitle=f"{spec.property_description} | synthetic demo lease",
            parties=list(spec.parties),
            preamble=list(spec.preamble),
            clauses=list(spec.clauses),
            closing=CLOSING,
            header=f"{spec.sample_id} | Rental Agreement",
        )
        options = AnalysisOptions(
            use_llm=False,  # deterministic: a demo must not depend on the network
            parties=_party_context(spec),
            sample_id=spec.sample_id,
            session_id=spec.sample_id,
        )
        try:
            result = await self.pipeline.analyze(pdf_bytes, f"{spec.sample_id}.pdf", options)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("failed to analyse sample %s", spec.sample_id)
            raise SampleDataError(
                f"Sample lease '{spec.sample_id}' could not be prepared.",
                details={"sample_id": spec.sample_id, "reason": type(exc).__name__},
            ) from exc

        # The report is served from the pinned session from now on, so it is
        # honest to say so: every sample response is a cache hit.
        result.report.cache_hit = True

        self.sessions.put(
            AnalysisSession.from_result(result),
            ttl_seconds=SAMPLE_TTL_SECONDS,
        )

        warnings = _self_check(spec, result)
        for warning in warnings:
            logger.warning("sample %s: %s", spec.sample_id, warning)
        return PreparedSample(spec=spec, pdf_bytes=pdf_bytes, result=result, warnings=warnings)

    # -- access -------------------------------------------------------------
    def get(self, sample_id: str) -> PreparedSample:
        sample = self._samples.get(sample_id)
        if sample is None:
            raise SampleNotFoundError(
                details={"sample_id": sample_id, "available": self.sample_ids()}
            )
        return sample

    def find(self, sample_id: str) -> PreparedSample | None:
        return self._samples.get(sample_id)

    def sample_ids(self) -> list[str]:
        return [spec.sample_id for spec in SAMPLE_SPECS]

    @property
    def samples(self) -> list[PreparedSample]:
        """Prepared samples in the order they are declared."""
        return self._ordered()

    def list_models(self) -> list[SampleLease]:
        return [sample.to_model(self.settings.api_prefix) for sample in self._ordered()]

    def pdf_bytes(self, sample_id: str) -> bytes:
        return self.get(sample_id).pdf_bytes

    def sessions_for_samples(self) -> list[AnalysisSession]:
        """Re-register any sample whose session was evicted, then return them."""
        sessions: list[AnalysisSession] = []
        for sample in self._ordered():
            session = self.sessions.find(sample.spec.sample_id)
            if session is None:
                session = self.sessions.put(
                    AnalysisSession.from_result(sample.result),
                    ttl_seconds=SAMPLE_TTL_SECONDS,
                )
            sessions.append(session)
        return sessions

    def diagnostics(self) -> list[dict[str, object]]:
        """Expected-versus-actual check, surfaced by ``/health``."""
        return [
            {
                "sample_id": sample.spec.sample_id,
                "expected_risk_level": sample.spec.expected_risk_level.value,
                "actual_risk_level": sample.report.risk.risk_level.value,
                "overall_score": sample.report.risk.overall_score,
                "violation_count": sample.report.risk.violation_count,
                "expected_min_violations": sample.spec.expected_min_violations,
                "clause_count": sample.report.engine.clause_count,
                "ok": not sample.warnings,
                "warnings": list(sample.warnings),
            }
            for sample in self._ordered()
        ]

    def status(self) -> dict[str, object]:
        return {
            "ready": self._ready,
            "count": len(self._samples),
            "sample_ids": list(self._samples) or self.sample_ids(),
        }

    # -- internals ----------------------------------------------------------
    def _ordered(self) -> list[PreparedSample]:
        with self._lock:
            return [self._samples[sid] for sid in (s.sample_id for s in SAMPLE_SPECS) if sid in self._samples]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _party_context(spec: SampleLeaseSpec) -> PartyContext:
    values = {label.lower(): value for label, value in spec.parties}
    return PartyContext(
        tenant_name=_short_name(values.get("tenant")),
        landlord_name=_short_name(values.get("landlord")),
        premises=values.get("premises"),
        monthly_rent_inr=float(spec.monthly_rent_inr),
    )


def _short_name(value: str | None) -> str | None:
    """``"Mr. S. Rajagopal, No. 12, ..."`` -> ``"Mr. S. Rajagopal"``."""
    if not value:
        return None
    return value.split(",")[0].strip() or None


def _self_check(spec: SampleLeaseSpec, result: AnalysisResult) -> list[str]:
    """Verify the demo still demonstrates what it claims to."""
    warnings: list[str] = []
    risk = result.report.risk
    if risk.risk_level is not spec.expected_risk_level:
        warnings.append(
            f"expected risk level {spec.expected_risk_level.value}, got {risk.risk_level.value}"
        )
    if risk.violation_count < spec.expected_min_violations:
        warnings.append(
            f"expected at least {spec.expected_min_violations} violations, "
            f"got {risk.violation_count}"
        )
    if result.report.engine.clause_count < len(spec.clauses):
        warnings.append(
            f"splitter produced {result.report.engine.clause_count} clauses "
            f"from {len(spec.clauses)} authored clauses"
        )
    return warnings


def get_spec_safe(sample_id: str) -> SampleLeaseSpec:
    """Return a spec by id, translating ``KeyError`` into a domain error."""
    try:
        return get_spec(sample_id)
    except KeyError as exc:
        raise SampleNotFoundError(details={"sample_id": sample_id}) from exc
