"""Liveness and readiness in one call.

The payload answers the questions that actually matter during a demo: is the rule
base loaded, did the three sample leases analyse to the risk levels they claim,
how much is the cache holding, and which model - if any - will classify clauses.

A degraded component does not change the status code (an orchestrator's liveness
probe should not flap because a demo sample drifted); the ``status`` field carries
the verdict instead, and every component reports its own detail.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.api.deps import PipelineDep, RuntimeDep, SamplesDep, SessionsDep, SettingsDep
from app.data.sample_repository import SampleLeaseRepository
from app.models.api import ComponentHealth, HealthResponse
from app.models.enums import ClauseCategory
from app.services.pdf_parser import ocr_diagnostics

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

STATUS_OK = "ok"
STATUS_DEGRADED = "degraded"
STATUS_WARMING = "warming"
# A missing OCR engine only limits scanned leases; text PDFs are unaffected, so it
# must not drag the whole service into "degraded".
STATUS_LIMITED = "limited"


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness plus demo-readiness diagnostics",
    description=(
        "Reports the loaded rule base, the self-check result for each demo lease, "
        "cache occupancy and the active LLM provider.\n\n"
        "`samples.detail.diagnostics` compares what each demo is *supposed* to "
        "demonstrate with what it actually produced, so a drifting benchmark shows "
        "up here before it embarrasses anyone in a live review."
    ),
)
async def health(
    runtime: RuntimeDep,
    settings: SettingsDep,
    pipeline: PipelineDep,
    sessions: SessionsDep,
    samples: SamplesDep,
) -> HealthResponse:
    rule_base = pipeline.rule_base
    components: dict[str, ComponentHealth] = {
        "rules": ComponentHealth(
            status=STATUS_OK,
            detail={
                "rule_count": len(rule_base.rules),
                "scoring_version": rule_base.scoring.version,
                "statute": rule_base.statute.short_name,
                "act_number": rule_base.statute.act_number,
                "categories": sorted({c.value for c in ClauseCategory}),
            },
        ),
        "samples": _samples_component(samples),
        "cache": ComponentHealth(
            status=STATUS_OK,
            detail={
                **sessions.stats(),
                "ttl_seconds": settings.cache_ttl_seconds,
                "max_entries": settings.cache_max_entries,
                "max_bytes_mb": settings.cache_max_bytes_mb,
            },
        ),
        "llm": ComponentHealth(
            status=STATUS_OK,
            detail={
                "enabled": settings.llm_enabled,
                "provider_setting": settings.llm_provider,
                "provider_resolved": settings.resolved_llm_provider,
                "model": settings._active_model(),
                "timeout_seconds": settings.llm_timeout_seconds,
                "note": (
                    "Clauses are classified by the model, verdicts are computed by code."
                    if settings.llm_enabled
                    else "Offline mode: deterministic keyword classifier only."
                ),
            },
        ),
        "ocr": _ocr_component(settings),
        "extraction": ComponentHealth(
            status=STATUS_OK,
            detail={
                "max_upload_mb": settings.max_upload_mb,
                "max_pages": settings.max_pages,
                "coordinates": "PyMuPDF line and word boxes",
            },
        ),
    }

    overall = STATUS_OK
    statuses = {component.status for component in components.values()}
    if STATUS_DEGRADED in statuses:
        overall = STATUS_DEGRADED
    elif STATUS_WARMING in statuses:
        overall = STATUS_WARMING

    return HealthResponse(
        status=overall,
        version=settings.app_version,
        environment=settings.environment,
        uptime_seconds=round(runtime.uptime_seconds, 3),
        statute=rule_base.statute.act,
        components=components,
    )


def _ocr_component(settings: SettingsDep) -> ComponentHealth:
    diagnostics = ocr_diagnostics(settings)
    healthy = diagnostics["available"] or not settings.ocr_enabled
    return ComponentHealth(
        status=STATUS_OK if healthy else STATUS_LIMITED,
        detail={
            **diagnostics,
            "languages": settings.ocr_languages,
            "fallback_threshold_chars_per_page": settings.ocr_min_chars_per_page,
            "dpi": settings.ocr_dpi,
        },
    )


def _samples_component(samples: SampleLeaseRepository) -> ComponentHealth:
    detail = dict(samples.status())
    if not samples.ready:
        detail["note"] = "Demo leases are prepared on the first demo request."
        return ComponentHealth(status=STATUS_WARMING, detail=detail)

    diagnostics = samples.diagnostics()
    detail["diagnostics"] = diagnostics
    failed = [entry["sample_id"] for entry in diagnostics if not entry["ok"]]
    if failed:
        logger.warning("sample self-check failed for: %s", ", ".join(map(str, failed)))
        detail["failed"] = failed
        return ComponentHealth(status=STATUS_DEGRADED, detail=detail)
    return ComponentHealth(status=STATUS_OK, detail=detail)
