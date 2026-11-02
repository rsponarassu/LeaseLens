"""Tiny PDF writer used to synthesise the demo leases.

Demo leases must exist without shipping binary fixtures, so they are rendered from
plain text at startup. Using explicit line placement (instead of ``insert_textbox``)
keeps the layout predictable, which keeps the extraction tests stable.
"""

from __future__ import annotations

import logging

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

PAGE_WIDTH = 595.0  # A4 portrait, points
PAGE_HEIGHT = 842.0
MARGIN = 56.0
TEXT_WIDTH = PAGE_WIDTH - 2 * MARGIN

INK = (0.09, 0.10, 0.13)
MUTED = (0.42, 0.44, 0.48)


def _wrap(text: str, font: fitz.Font, size: float, width: float) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if font.text_length(candidate, fontsize=size) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


class _Canvas:
    """Sequential text layout with automatic page breaks."""

    def __init__(self, header: str | None = None) -> None:
        self.document = fitz.open()
        self.header = header
        self.page: fitz.Page | None = None
        self.y = MARGIN
        self._new_page()

    def _new_page(self) -> None:
        self.page = self.document.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        self.y = MARGIN
        if self.header:
            self.page.insert_text(
                (MARGIN, 38), self.header[:100], fontsize=7.0, fontname="helv", color=MUTED
            )
            self.page.draw_line(
                (MARGIN, 48), (PAGE_WIDTH - MARGIN, 48), color=(0.85, 0.86, 0.88), width=0.5
            )
            self.y = 66.0

    def _ensure(self, height: float) -> None:
        if self.y + height > PAGE_HEIGHT - MARGIN - 18:
            self._new_page()

    def write(
        self,
        text: str,
        *,
        font: str = "helv",
        size: float = 10.0,
        color: tuple[float, float, float] = INK,
        leading: float = 1.45,
        space_before: float = 0.0,
        space_after: float = 8.0,
    ) -> None:
        assert self.page is not None
        font_obj = fitz.Font(font)
        lines = _wrap(text, font_obj, size, TEXT_WIDTH)
        block_height = len(lines) * size * leading
        self._ensure(block_height + space_before + space_after)
        self.y += space_before
        for line in lines:
            self.page.insert_text(
                (MARGIN, self.y + size),
                line,
                fontname=font,
                fontsize=size,
                color=color,
            )
            self.y += size * leading
        self.y += space_after

    def rule(self, space_before: float = 4.0, space_after: float = 10.0) -> None:
        assert self.page is not None
        self.y += space_before
        self.page.draw_line(
            (MARGIN, self.y), (PAGE_WIDTH - MARGIN, self.y), color=(0.82, 0.83, 0.86), width=0.7
        )
        self.y += space_after

    def finish(self) -> bytes:
        total = self.document.page_count
        for index, page in enumerate(self.document):
            page.insert_text(
                (MARGIN, PAGE_HEIGHT - 34),
                f"Page {index + 1} of {total}  |  LeaseLens demo document (synthetic)",
                fontsize=7.0,
                fontname="helv",
                color=MUTED,
            )
        data = self.document.tobytes(garbage=3, deflate=True)
        self.document.close()
        return data


def build_lease_pdf(
    *,
    title: str,
    subtitle: str,
    parties: list[tuple[str, str]],
    clauses: list[tuple[str, str]],
    preamble: list[str] | None = None,
    closing: str | None = None,
    header: str | None = None,
) -> bytes:
    """Render a synthetic tenancy agreement to PDF bytes."""
    canvas = _Canvas(header=header or "Rental Agreement")

    canvas.write("RENTAL AGREEMENT", font="hebo", size=17, space_after=2)
    canvas.write(title, font="helv", size=10.5, color=MUTED, space_after=12)
    canvas.rule()

    for label, value in parties:
        canvas.write(f"{label}: {value}", font="helv", size=9.5, space_after=3)
    canvas.write("", size=4, space_after=4)

    for paragraph in preamble or []:
        canvas.write(paragraph, size=9.5, space_after=6)
    if preamble:
        canvas.write("", size=4, space_after=4)

    for index, (heading, body) in enumerate(clauses, start=1):
        canvas.write(
            f"{index}. {heading}",
            font="hebo",
            size=10.0,
            space_before=4,
            space_after=3,
        )
        canvas.write(body, size=9.5, space_after=9)

    if closing:
        canvas.rule()
        canvas.write(closing, size=9.0, color=MUTED, space_after=6)

    return canvas.finish()
