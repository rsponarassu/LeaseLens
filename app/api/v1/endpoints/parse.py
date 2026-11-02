"""``POST /parse-lease`` - extraction and segmentation without any legal verdict."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, File, Query, UploadFile
from fastapi.concurrency import run_in_threadpool

from app.api.deps import PipelineDep, SettingsDep, read_pdf_upload
from app.models.api import ErrorResponse, ParseLeaseResponse
from app.models.document import ExtractionSummary

logger = logging.getLogger(__name__)

router = APIRouter(tags=["documents"])

TEXT_PREVIEW_CHARS = 2000


@router.post(
    "/parse-lease",
    response_model=ParseLeaseResponse,
    summary="Extract text, coordinates and clauses",
    description=(
        "Debug and integration endpoint. Returns the raw extraction (pages, "
        "character counts, OCR usage), the clause outline with page numbers and "
        "bounding boxes, and - when `include_coordinates=true` - the full "
        "line/word coordinate map that the annotator uses.\n\n"
        "No model is called and no legal benchmark is applied."
    ),
    responses={
        415: {"model": ErrorResponse, "description": "Not a PDF"},
        422: {"model": ErrorResponse, "description": "Unreadable or unstructured document"},
    },
)
async def parse_lease(
    file: Annotated[UploadFile, File(description="The rental agreement to parse (PDF).")],
    pipeline: PipelineDep,
    settings: SettingsDep,
    include_coordinates: Annotated[
        bool,
        Query(description="Include per-line and per-word bounding boxes in the response."),
    ] = False,
) -> ParseLeaseResponse:
    upload = await read_pdf_upload(file, settings)

    # Parsing is CPU-bound, so it runs off the event loop.
    parsed = await run_in_threadpool(pipeline.parse_document, upload.data, upload.file_name)
    document = parsed.document

    logger.info(
        "parsed %s: pages=%s clauses=%s strategy=%s method=%s",
        document.file_name,
        document.page_count,
        len(parsed.clauses),
        parsed.strategy,
        document.extraction_method.value,
    )

    return ParseLeaseResponse(
        file_name=document.file_name,
        extraction=ExtractionSummary.from_document(document),
        clauses=parsed.outline,
        clause_count=len(parsed.clauses),
        strategy=parsed.strategy,
        warnings=parsed.warnings,
        text_preview=document.full_text[:TEXT_PREVIEW_CHARS],
        coordinates=document.pages if include_coordinates else None,
    )
