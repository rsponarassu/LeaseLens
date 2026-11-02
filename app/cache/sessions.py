"""Session store: analysis results and their PDF artefacts, in memory only.

Privacy by design means the tenant's document never touches the disk. A session
lives for ``CACHE_TTL_SECONDS`` (default one hour), is bounded by an entry count
*and* a byte budget, and is dropped wholesale when the TTL lapses. The annotated
PDF is rendered lazily on first download and then kept for the rest of the
session.

Nothing here is durable: a process restart forgets every upload, which is the
intended trade-off for a document that may contain personal data.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.cache.ttl_cache import TTLCache
from app.core.config import Settings, get_settings
from app.core.errors import SessionExpiredError, SessionNotFoundError
from app.models.analysis import AnalysisReport, AnalysisSummary
from app.models.clause import Clause
from app.services.pdf_annotator import AnnotationSummary, HighlightSpec, PdfAnnotator
from app.services.pipeline import AnalysisResult

logger = logging.getLogger(__name__)


@dataclass
class AnalysisSession:
    """One analysed document and everything needed to render or re-download it."""

    session_id: str
    report: AnalysisReport
    clauses: list[Clause]
    highlights: list[HighlightSpec]
    summary_spec: AnnotationSummary
    source_pdf: bytes
    annotated_pdf: bytes | None = None
    sample_id: str | None = None
    report_bytes: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))

    @classmethod
    def from_result(cls, result: AnalysisResult) -> AnalysisSession:
        report = result.report
        return cls(
            session_id=report.session_id,
            report=report,
            clauses=result.clauses,
            highlights=result.highlights,
            summary_spec=result.summary_spec,
            source_pdf=result.source_pdf,
            sample_id=report.sample_id,
            report_bytes=len(report.model_dump_json()),
        )

    @property
    def file_name(self) -> str:
        return self.report.file_name

    @property
    def is_sample(self) -> bool:
        return self.sample_id is not None

    @property
    def size_bytes(self) -> int:
        """Approximate heap footprint, used for the cache byte budget."""
        return len(self.source_pdf) + len(self.annotated_pdf or b"") + self.report_bytes


class SessionCache:
    """Thread-safe TTL cache of :class:`AnalysisSession` objects."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        annotator: PdfAnnotator | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._cache: TTLCache[str, AnalysisSession] = TTLCache(
            max_entries=self.settings.cache_max_entries,
            ttl_seconds=self.settings.cache_ttl_seconds,
            max_bytes=self.settings.cache_max_bytes,
        )
        # Tombstones let us answer "expired" (410) instead of "unknown" (404)
        # for sessions the caller has genuinely used before.
        self._ledger: TTLCache[str, bool] = TTLCache(
            max_entries=self.settings.cache_max_entries * 4,
            ttl_seconds=max(self.settings.cache_ttl_seconds * 3, 900),
            max_bytes=None,
        )
        self._annotator = annotator or PdfAnnotator()
        self._annotate_lock = threading.RLock()

    # -- writes -------------------------------------------------------------
    def save(self, result: AnalysisResult, *, ttl_seconds: float | None = None) -> AnalysisSession:
        """Persist one analysis run and return the stored session."""
        session = AnalysisSession.from_result(result)
        return self.put(session, ttl_seconds=ttl_seconds)

    def put(self, session: AnalysisSession, *, ttl_seconds: float | None = None) -> AnalysisSession:
        self._cache.set(
            session.session_id,
            session,
            size=session.size_bytes,
            ttl_seconds=ttl_seconds,
        )
        self._ledger.set(session.session_id, True, ttl_seconds=ttl_seconds)
        logger.debug(
            "session stored: id=%s sample=%s bytes=%s entries=%s",
            session.session_id,
            session.sample_id,
            session.size_bytes,
            len(self._cache),
        )
        return session

    def store_annotated(self, session_id: str, pdf_bytes: bytes) -> None:
        """Attach the rendered annotated PDF to an existing session."""
        session = self._cache.get(session_id)
        if session is None:
            return
        session.annotated_pdf = pdf_bytes
        # Re-insert so the byte budget accounts for the new artefact.
        self._cache.set(session_id, session, size=session.size_bytes)

    # -- reads --------------------------------------------------------------
    def find(self, session_id: str) -> AnalysisSession | None:
        """Return the session, or ``None`` when it is unknown or expired."""
        return self._cache.get(session_id)

    def get(self, session_id: str) -> AnalysisSession:
        """Return the session or raise a typed 404/410 domain error."""
        session = self._cache.get(session_id)
        if session is not None:
            return session
        if self._ledger.get(session_id):
            raise SessionExpiredError(
                details={"session_id": session_id, "ttl_seconds": self.settings.cache_ttl_seconds}
            )
        raise SessionNotFoundError(details={"session_id": session_id})

    def report(self, session_id: str, *, cache_hit: bool = True) -> AnalysisReport:
        session = self.get(session_id)
        report = session.report
        if report.cache_hit != cache_hit:
            report.cache_hit = cache_hit
        return report

    def annotated_pdf(self, session_id: str, *, include_summary: bool = True) -> bytes:
        """Return the highlighted PDF, rendering it on first use."""
        session = self.get(session_id)
        if include_summary and session.annotated_pdf is not None:
            return session.annotated_pdf

        with self._annotate_lock:
            if include_summary and session.annotated_pdf is not None:
                return session.annotated_pdf
            pdf_bytes = self._annotator.annotate(
                session.source_pdf,
                session.highlights,
                session.summary_spec if include_summary else None,
            )
            if include_summary:
                self.store_annotated(session_id, pdf_bytes)
        return pdf_bytes

    def summaries(self) -> list[AnalysisSummary]:
        """Card views of every live session, newest first."""
        summaries = [
            AnalysisSummary.from_report(self._cache.get(key).report)
            for key in list(self._cache)
            if self._cache.get(key) is not None
        ]
        summaries.sort(key=lambda summary: summary.created_at, reverse=True)
        return summaries

    # -- maintenance --------------------------------------------------------
    def invalidate(self, session_id: str) -> bool:
        """Drop a session (e.g. the client asked to forget the document).

        The tombstone goes too: an explicit deletion means the server should not
        even remember that the id existed, so a later lookup is a plain 404
        rather than a 410 "expired".
        """
        removed = self._cache.delete(session_id)
        self._ledger.delete(session_id)
        if removed:
            logger.info("session purged on request: id=%s", session_id)
        return removed

    def purge_expired(self) -> int:
        return self._cache.purge_expired()

    def clear(self) -> None:
        self._cache.clear()
        self._ledger.clear()

    def stats(self) -> dict[str, object]:
        return self._cache.stats()


def session_size_bytes(session: AnalysisSession) -> int:
    """Public helper so tests can assert the byte accounting."""
    return session.size_bytes
