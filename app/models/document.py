"""Document-level models: geometry, page layout and extraction results.

The parser keeps *lines* (not just a flat string) because downstream stages need
coordinates: the clause splitter needs page/bbox provenance, and the annotator
needs rectangles to highlight. Building the pipeline on line records, rather
than string offsets, removes a whole class of cross-page mapping bugs.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.models.enums import ExtractionMethod


class BoundingBox(BaseModel):
    """Axis-aligned rectangle in PDF points, origin at the top-left."""

    model_config = ConfigDict(frozen=True)

    x0: float
    y0: float
    x1: float
    y1: float

    @classmethod
    def from_sequence(cls, values: Any) -> BoundingBox:
        """Build from a 4-value sequence (PyMuPDF rect tuples / lists)."""
        x0, y0, x1, y1 = (float(v) for v in values)
        return cls(x0=x0, y0=y0, x1=x1, y1=y1)

    @classmethod
    def union(cls, boxes: list[BoundingBox]) -> BoundingBox | None:
        """Smallest rectangle covering every box, or ``None`` for an empty list."""
        if not boxes:
            return None
        return cls(
            x0=min(b.x0 for b in boxes),
            y0=min(b.y0 for b in boxes),
            x1=max(b.x1 for b in boxes),
            y1=max(b.y1 for b in boxes),
        )

    def as_list(self) -> list[float]:
        return [round(self.x0, 2), round(self.y0, 2), round(self.x1, 2), round(self.y1, 2)]

    def is_valid(self) -> bool:
        return self.x1 > self.x0 and self.y1 > self.y0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def width(self) -> float:
        return self.x1 - self.x0


class WordBox(BaseModel):
    """A single word plus its location, used for precise highlighting."""

    text: str
    bbox: BoundingBox
    block_number: int = 0
    line_number: int = 0


class TextLine(BaseModel):
    """One visual line of text on a page."""

    page_number: int = Field(ge=1)
    text: str
    bbox: BoundingBox
    block_number: int = 0
    line_number: int = 0
    is_bold: bool = False
    font_size: float = 0.0
    is_boilerplate: bool = False

    @computed_field  # type: ignore[prop-decorator]
    @property
    def char_count(self) -> int:
        return len(self.text)


class PageLayout(BaseModel):
    """Everything extracted from a single PDF page."""

    page_number: int = Field(ge=1)
    width: float
    height: float
    rotation: int = 0
    lines: list[TextLine] = Field(default_factory=list)
    words: list[WordBox] = Field(default_factory=list)
    used_ocr: bool = False

    @computed_field  # type: ignore[prop-decorator]
    @property
    def char_count(self) -> int:
        return sum(len(line.text) for line in self.lines)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)


class ExtractedDocument(BaseModel):
    """The parse result for a whole upload."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    file_name: str
    file_size_bytes: int
    sha256: str
    page_count: int = Field(ge=0)
    pages: list[PageLayout] = Field(default_factory=list)
    extraction_method: ExtractionMethod = ExtractionMethod.TEXT_LAYER
    ocr_used: bool = False
    mean_chars_per_page: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_chars(self) -> int:
        return sum(page.char_count for page in self.pages)

    def iter_lines(self, *, include_boilerplate: bool = False) -> list[TextLine]:
        """Flatten all lines in reading order."""
        lines: list[TextLine] = []
        for page in self.pages:
            for line in page.lines:
                if line.is_boilerplate and not include_boilerplate:
                    continue
                lines.append(line)
        return lines

    def page(self, page_number: int) -> PageLayout | None:
        for page in self.pages:
            if page.page_number == page_number:
                return page
        return None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def full_text(self) -> str:
        return "\n".join(page.text for page in self.pages)


class ExtractionSummary(BaseModel):
    """Lightweight, response-friendly view of an extraction (no word map)."""

    file_name: str
    file_size_bytes: int
    page_count: int
    total_chars: int
    extraction_method: ExtractionMethod
    ocr_used: bool
    mean_chars_per_page: float
    warnings: list[str] = Field(default_factory=list)
    pages: list[dict[str, Any]] = Field(default_factory=list)

    @classmethod
    def from_document(cls, document: ExtractedDocument) -> ExtractionSummary:
        return cls(
            file_name=document.file_name,
            file_size_bytes=document.file_size_bytes,
            page_count=document.page_count,
            total_chars=document.total_chars,
            extraction_method=document.extraction_method,
            ocr_used=document.ocr_used,
            mean_chars_per_page=round(document.mean_chars_per_page, 1),
            warnings=list(document.warnings),
            pages=[
                {
                    "page_number": page.page_number,
                    "chars": page.char_count,
                    "lines": len(page.lines),
                    "ocr": page.used_ocr,
                }
                for page in document.pages
            ],
        )
