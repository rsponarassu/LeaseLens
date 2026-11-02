"""``POST /analyze`` - the full pipeline in one call."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, File, Query, UploadFile, status

from app.api.deps import PipelineDep, SessionsDep, SettingsDep, read_pdf_upload
from app.models.analysis import AnalysisReport
from app.models.api import ErrorResponse
from app.services.fix_generator import PartyContext
from app.services.pipeline import AnalysisOptions

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analysis"])


@router.post(
    "/analyze",
    response_model=AnalysisReport,
    status_code=status.HTTP_200_OK,
    summary="Analyse a rental agreement",
    description=(
        "Runs the whole pipeline on one uploaded PDF:\n\n"
        "1. **Extraction** - PyMuPDF text layer, with an automatic Tesseract OCR "
        "fallback for scanned pages.\n"
        "2. **Segmentation** - the document is split into numbered or headed clauses, "
        "keeping each clause's page and bounding box.\n"
        "3. **Classification** - an LLM (when configured) labels each clause and "
        "extracts typed entities; a deterministic extractor runs in parallel as a "
        "cross-check and takes precedence for literal numbers.\n"
        "4. **Rule engine** - `rules.yaml` benchmarks are applied by plain Python "
        "comparisons and the 0-100 score is computed here, never by the model.\n"
        "5. **Fix-it Kit** - each violation gets a bilingual explanation, a "
        "counter-clause and an email draft.\n\n"
        "The response contains everything the UI needs; the source PDF is kept in "
        "memory for one hour so that it can be downloaded with annotations."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "Upload rejected"},
        413: {"model": ErrorResponse, "description": "File too large"},
        415: {"model": ErrorResponse, "description": "Not a PDF"},
        422: {"model": ErrorResponse, "description": "Unreadable or unstructured document"},
        502: {"model": ErrorResponse, "description": "Classification model failed"},
        504: {"model": ErrorResponse, "description": "Classification model timed out"},
    },
)
async def analyze_lease(
    file: Annotated[
        UploadFile,
        File(description="The rental agreement to analyse (PDF, text layer or scanned)."),
    ],
    pipeline: PipelineDep,
    sessions: SessionsDep,
    settings: SettingsDep,
    use_llm: Annotated[
        bool,
        Query(description="Use the configured LLM for classification. Falls back to the "
                          "deterministic extractor when no provider is configured."),
    ] = True,
    tenant_name: Annotated[
        str | None, Query(max_length=120, description="Optional; only used in email drafts.")
    ] = None,
    landlord_name: Annotated[
        str | None, Query(max_length=120, description="Optional; only used in email drafts.")
    ] = None,
    monthly_rent_inr: Annotated[
        float | None,
        Query(ge=0, le=100_000_000, description="Optional; lets the Fix-it Kit convert "
                                                "deposit months into an amount."),
    ] = None,
) -> AnalysisReport:
    upload = await read_pdf_upload(file, settings)

    parties = None
    if tenant_name or landlord_name or monthly_rent_inr is not None:
        parties = PartyContext(
            tenant_name=tenant_name,
            landlord_name=landlord_name,
            monthly_rent_inr=monthly_rent_inr,
        )

    options = AnalysisOptions(
        use_llm=use_llm and settings.llm_enabled,
        parties=parties,
    )
    result = await pipeline.analyze(upload.data, upload.file_name, options)

    session = sessions.save(result)
    logger.info(
        "analyzed %s: session=%s score=%s level=%s findings=%s",
        upload.file_name,
        session.session_id,
        session.report.risk.overall_score,
        session.report.risk.risk_level.value,
        len(session.report.findings),
    )
    return session.report
