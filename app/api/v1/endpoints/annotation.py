"""Annotated PDF endpoints: render highlights, then serve them."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Body, Path
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from app.api.deps import SamplesDep, SessionsDep
from app.api.responses import download_name, pdf_response
from app.models.api import AnnotateRequest, ErrorResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["annotation"])


@router.post(
    "/annotate-pdf",
    summary="Render a highlighted PDF and stream it back",
    response_class=Response,
    description=(
        "Draws colour-coded highlights over the original clause coordinates "
        "(red = high risk, amber = moderate, green = compliant) and, by default, "
        "prepends a cover page with the risk score, the top drivers and a legend.\n\n"
        "Pass either a `session_id` from `/analyze` or a demo `sample_id`. The "
        "rendered file is cached for the session, so a second download is free."
    ),
    responses={
        200: {"content": {"application/pdf": {}}},
        404: {"model": ErrorResponse, "description": "Unknown session or sample"},
        410: {"model": ErrorResponse, "description": "Session expired"},
        422: {"model": ErrorResponse, "description": "Neither or both ids supplied"},
    },
)
async def annotate_pdf(
    request: Annotated[AnnotateRequest, Body(...)],
    sessions: SessionsDep,
    samples: SamplesDep,
) -> Response:
    if request.sample_id:
        # Guarantees the sample session exists even after a cache eviction.
        await samples.ensure_ready()
        samples.sessions_for_samples()

    # Rendering is CPU-bound (PyMuPDF), so it runs off the event loop.
    content = await run_in_threadpool(
        sessions.annotated_pdf,
        request.target_id,
        include_summary=request.include_summary_page,
    )
    session = sessions.get(request.target_id)
    logger.info(
        "annotated session=%s highlights=%s bytes=%s",
        session.session_id,
        len(session.highlights),
        len(content),
    )
    return pdf_response(content, download_name(session.file_name))


@router.get(
    "/download-annotated/{session_id}",
    summary="Download the annotated PDF for a session",
    response_class=Response,
    description=(
        "Streams the highlighted PDF for a previously analysed document. The file is "
        "rendered on first request and then kept in memory until the session expires."
    ),
    responses={
        200: {"content": {"application/pdf": {}}},
        404: {"model": ErrorResponse, "description": "Unknown session"},
        410: {"model": ErrorResponse, "description": "Session expired"},
    },
)
async def download_annotated(
    session_id: Annotated[str, Path(description="Session id returned by /analyze.")],
    sessions: SessionsDep,
) -> Response:
    content = await run_in_threadpool(sessions.annotated_pdf, session_id)
    session = sessions.get(session_id)
    logger.info("served annotated PDF: session=%s bytes=%s", session_id, len(content))
    return pdf_response(content, download_name(session.file_name))
