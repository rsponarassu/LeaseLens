"""Demo leases: pre-analysed, deterministic and always available."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path
from fastapi.responses import Response

from app.api.deps import SamplesDep, SessionsDep
from app.api.responses import download_name, pdf_response
from app.models.analysis import AnalysisReport, SampleLease
from app.models.api import ErrorResponse

router = APIRouter(tags=["samples"])

SampleId = Annotated[
    str,
    Path(
        description="Demo lease id: ``sample-high-deposit``, ``sample-moderate-rent`` "
        "or ``sample-tenant-friendly``.",
        examples=["sample-high-deposit"],
    ),
]


@router.get(
    "/sample-leases",
    response_model=list[SampleLease],
    summary="List the three demo leases with their analyses",
    description=(
        "Guarantees a working demo without an upload, an API key or a network call. "
        "Each lease is rendered from text at startup and analysed with the "
        "deterministic extractor, so the numbers are reproducible.\n\n"
        "Every entry embeds the full analysis report and the URL of its source PDF."
    ),
)
async def list_sample_leases(samples: SamplesDep) -> list[SampleLease]:
    await samples.ensure_ready()
    return samples.list_models()


@router.get(
    "/sample-leases/{sample_id}",
    response_model=SampleLease,
    summary="One demo lease and its analysis",
    responses={404: {"model": ErrorResponse, "description": "Unknown sample"}},
)
async def get_sample_lease(sample_id: SampleId, samples: SamplesDep) -> SampleLease:
    await samples.ensure_ready()
    return samples.get(sample_id).to_model(samples.settings.api_prefix)


@router.get(
    "/sample-leases/{sample_id}/analysis",
    response_model=AnalysisReport,
    summary="Analysis report for a demo lease",
    responses={404: {"model": ErrorResponse, "description": "Unknown sample"}},
)
async def get_sample_analysis(sample_id: SampleId, samples: SamplesDep) -> AnalysisReport:
    await samples.ensure_ready()
    # The report was already marked as a cache hit when the sample was prepared.
    return samples.get(sample_id).report


@router.get(
    "/sample-leases/{sample_id}/pdf",
    summary="Download the source PDF of a demo lease",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}, 404: {"model": ErrorResponse}},
)
async def get_sample_pdf(sample_id: SampleId, samples: SamplesDep) -> Response:
    await samples.ensure_ready()
    sample = samples.get(sample_id)
    return pdf_response(
        sample.pdf_bytes,
        download_name(f"{sample_id}.pdf", suffix=""),
        inline=True,
    )


@router.get(
    "/sample-leases/{sample_id}/annotated-pdf",
    summary="Download a demo lease with its highlights",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}, 404: {"model": ErrorResponse}},
)
async def get_sample_annotated_pdf(
    sample_id: SampleId,
    samples: SamplesDep,
    sessions: SessionsDep,
) -> Response:
    await samples.ensure_ready()
    # Re-registers the session if it was evicted, then renders on first use.
    samples.sessions_for_samples()
    annotated = sessions.annotated_pdf(sample_id)
    return pdf_response(annotated, download_name(f"{sample_id}.pdf"))
