"""Colour-coded PDF annotation.

Highlights are written as real PDF annotations (``Highlight``) rather than painted
rectangles, so a reader can click a clause in the returned PDF and read the reason
in the popup. A thin border is added for visibility when printing in greyscale.

The original file is never mutated on disk: the output is produced in memory and
streamed back to the client.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

from app.models.enums import RiskColor

try:  # PyMuPDF >= 1.24
    import pymupdf as fitz
except ImportError:  # pragma: no cover - legacy alias
    import fitz  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

# RGB in 0..1 as required by PyMuPDF annotation colours.
RISK_RGB: dict[RiskColor, tuple[float, float, float]] = {
    RiskColor.RED: (0.83, 0.14, 0.20),
    RiskColor.AMBER: (0.95, 0.62, 0.09),
    RiskColor.GREEN: (0.13, 0.62, 0.35),
    RiskColor.GREY: (0.45, 0.47, 0.50),
}

_HIGHLIGHT_OPACITY = 0.38
_MAX_ANNOTATIONS = 400
_SUMMARY_PAGE_SIZE = (595.0, 842.0)  # A4 portrait in points


@dataclass(frozen=True)
class HighlightSpec:
    """One rectangle to highlight, with its explanation."""

    page_number: int
    bbox: tuple[float, float, float, float]
    color: RiskColor
    title: str
    note: str = ""
    clause_id: str = ""


@dataclass(frozen=True)
class AnnotationSummary:
    """Header data rendered on the cover page."""

    file_name: str
    risk_score: int
    risk_level: str
    band_label: str
    headline: str
    violation_count: int
    compliant_count: int
    top_drivers: tuple[str, ...] = ()
    statute_name: str = ""
    disclaimer: str = ""


class PdfAnnotator:
    """Draws highlights and (optionally) prepends a summary cover page."""

    def annotate(
        self,
        pdf_bytes: bytes,
        highlights: Sequence[HighlightSpec],
        summary: AnnotationSummary | None = None,
    ) -> bytes:
        try:
            document = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as exc:
            logger.warning("annotator could not open PDF: %s", exc)
            raise

        try:
            applied = 0
            for spec in highlights:
                if applied >= _MAX_ANNOTATIONS:
                    logger.warning("annotation cap reached (%s)", _MAX_ANNOTATIONS)
                    break
                if spec.page_number < 1 or spec.page_number > document.page_count:
                    continue
                if self._apply_highlight(document[spec.page_number - 1], spec):
                    applied += 1

            if summary is not None:
                self._prepend_summary_page(document, summary, applied)

            return document.tobytes(garbage=3, deflate=True)
        finally:
            document.close()

    # -- internals ----------------------------------------------------------
    @staticmethod
    def _apply_highlight(page: fitz.Page, spec: HighlightSpec) -> bool:
        rect = fitz.Rect(*spec.bbox)
        rect = rect & page.rect  # clip to the visible page
        if rect.is_empty or rect.width < 2 or rect.height < 2:
            return False

        colour = RISK_RGB[spec.color]
        try:
            annotation = page.add_highlight_annot(rect)
        except Exception:  # covers rects with no text underneath
            annotation = None

        if annotation is not None:
            annotation.set_colors(stroke=colour)
            annotation.set_opacity(_HIGHLIGHT_OPACITY)
            annotation.set_info(
                title=spec.title[:120],
                subject=f"LeaseLens: {spec.color.value}",
                content=spec.note[:2000],
            )
            annotation.update()

        # Thin border so the cue survives greyscale printing.
        try:
            page.draw_rect(rect, color=colour, width=0.9, overlay=True)
        except Exception:  # pragma: no cover - drawing is best effort
            logger.debug("could not draw border on page %s", spec.page_number)
        return True

    def _prepend_summary_page(
        self,
        document: fitz.Document,
        summary: AnnotationSummary,
        annotation_count: int,
    ) -> None:
        page = document.new_page(pno=0, width=_SUMMARY_PAGE_SIZE[0], height=_SUMMARY_PAGE_SIZE[1])
        margin = 56.0
        width = _SUMMARY_PAGE_SIZE[0] - 2 * margin

        page.insert_text(
            fitz.Point(margin, margin + 18),
            "LeaseLens - lease risk report",
            fontsize=20,
            fontname="hebo",
            color=(0.08, 0.10, 0.14),
        )
        page.insert_text(
            fitz.Point(margin, margin + 40),
            _trim(summary.file_name, 78),
            fontsize=9,
            fontname="helv",
            color=(0.35, 0.37, 0.42),
        )

        score_colour = _score_rgb(summary.risk_score)
        page.draw_rect(
            fitz.Rect(margin, margin + 60, margin + width, margin + 138),
            color=score_colour,
            width=1.2,
            fill=None,
        )
        page.insert_text(
            fitz.Point(margin + 16, margin + 96),
            f"{summary.risk_score}",
            fontsize=38,
            fontname="hebo",
            color=score_colour,
        )
        page.insert_text(
            fitz.Point(margin + 16, margin + 120),
            f"/100 - {summary.risk_level.upper()} RISK",
            fontsize=9,
            fontname="hebo",
            color=score_colour,
        )
        page.insert_textbox(
            fitz.Rect(margin + 120, margin + 74, margin + width - 16, margin + 132),
            f"{summary.band_label}\n{summary.headline}",
            fontsize=10,
            fontname="helv",
            color=(0.12, 0.14, 0.18),
        )

        stats = (
            f"{summary.violation_count} clause(s) flagged  |  "
            f"{summary.compliant_count} clause(s) compliant  |  "
            f"{annotation_count} highlight(s) drawn"
        )
        page.insert_text(
            fitz.Point(margin, margin + 160),
            stats,
            fontsize=9,
            fontname="helv",
            color=(0.35, 0.37, 0.42),
        )

        cursor = margin + 186
        page.insert_text(
            fitz.Point(margin, cursor),
            "What to fix first",
            fontsize=11,
            fontname="hebo",
            color=(0.08, 0.10, 0.14),
        )
        cursor += 16
        for index, driver in enumerate(summary.top_drivers[:5], start=1):
            text = f"{index}. {_trim(driver, 150)}"
            page.insert_textbox(
                fitz.Rect(margin, cursor, margin + width, cursor + 70),
                text,
                fontsize=9,
                fontname="helv",
                color=(0.18, 0.20, 0.24),
            )
            cursor += 26

        cursor += 8
        page.insert_text(
            fitz.Point(margin, cursor),
            "Highlight legend",
            fontsize=11,
            fontname="hebo",
            color=(0.08, 0.10, 0.14),
        )
        cursor += 18
        for colour_name, rgb, label in (
            ("Red", RISK_RGB[RiskColor.RED], "High / critical risk - renegotiate before signing"),
            ("Amber", RISK_RGB[RiskColor.AMBER], "Moderate risk - clarify or cap the exposure"),
            ("Green", RISK_RGB[RiskColor.GREEN], "Compliant with the benchmark we checked"),
        ):
            page.draw_rect(fitz.Rect(margin, cursor - 8, margin + 16, cursor + 2), color=rgb, fill=rgb)
            page.insert_text(
                fitz.Point(margin + 26, cursor + 1),
                f"{colour_name}: {label}",
                fontsize=9,
                fontname="helv",
                color=(0.18, 0.20, 0.24),
            )
            cursor += 18

        cursor += 14
        page.insert_textbox(
            fitz.Rect(margin, cursor, margin + width, _SUMMARY_PAGE_SIZE[1] - margin),
            (
                f"Generated {datetime.now(tz=timezone.utc).strftime('%d %b %Y, %H:%M UTC')} by "
                f"LeaseLens.\n\nBenchmarks: {summary.statute_name}\n\n{summary.disclaimer}"
            ),
            fontsize=7.5,
            fontname="helv",
            color=(0.42, 0.44, 0.48),
        )


def _score_rgb(score: int) -> tuple[float, float, float]:
    if score >= 60:
        return RISK_RGB[RiskColor.RED]
    if score >= 20:
        return RISK_RGB[RiskColor.AMBER]
    return RISK_RGB[RiskColor.GREEN]


def _trim(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3].rstrip(' ,.;')}..."
