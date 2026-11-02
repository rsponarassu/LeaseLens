"""Session management: list live analyses, fetch one, forget one.

A session is the only handle a client needs after ``POST /analyze``: it addresses
the full report, the annotated PDF and the cached source document. Listing exists
so a dashboard can restore itself after a page reload; ``DELETE`` exists so a
tenant can tell the server to drop their document immediately instead of waiting
for the TTL.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query, Response, status

from app.api.deps import SamplesDep, SessionsDep
from app.models.analysis import AnalysisReport, AnalysisSummary
from app.models.api import ErrorResponse

router = APIRouter(tags=["sessions"])

SessionId = Annotated[
    str,
    Path(
        description="Session id returned by ``POST /analyze``.",
        examples=["8f14e45fceea167a5a36dedd4bea2543"],
    ),
]


@router.get(
    "/sessions",
    response_model=list[AnalysisSummary],
    summary="List the analyses still held in memory",
    description=(
        "One card per live session: score, band, violation count and the top "
        "drivers, newest first.\n\n"
        "Nothing here survives a restart - documents are never written to disk, so "
        "a redeploy starts with an empty list. Set `include_samples=false` to hide "
        "the three demo leases."
    ),
)
async def list_sessions(
    sessions: SessionsDep,
    samples: SamplesDep,
    include_samples: Annotated[
        bool,
        Query(description="Include the three demo leases in the listing."),
    ] = True,
) -> list[AnalysisSummary]:
    if include_samples:
        await samples.ensure_ready()
        samples.sessions_for_samples()
    return sessions.summaries()


@router.get(
    "/sessions/{session_id}",
    response_model=AnalysisReport,
    summary="Re-fetch the full analysis for a session",
    description=(
        "Returns exactly the payload `POST /analyze` produced, including the "
        "per-clause verdicts, the bilingual Fix-it Kit and the statute citations. "
        "`cache_hit` is set to true because no work is repeated."
    ),
    responses={
        404: {"model": ErrorResponse, "description": "Unknown session"},
        410: {"model": ErrorResponse, "description": "Session expired"},
    },
)
async def get_session(session_id: SessionId, sessions: SessionsDep) -> AnalysisReport:
    return sessions.report(session_id, cache_hit=True)


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Forget a session and its artefacts",
    description=(
        "Drops the extracted text, the report and the annotated PDF straight away. "
        "Idempotent: deleting an already-gone session still returns 204, because the "
        "caller's intent - the document is not retained - is already satisfied."
    ),
    responses={204: {"description": "Session dropped or already absent"}},
)
async def delete_session(session_id: SessionId, sessions: SessionsDep) -> Response:
    sessions.invalidate(session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
