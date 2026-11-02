"""PDF ingestion: text + layout extraction with an OCR fallback.

Privacy note: uploads are processed entirely from an in-memory ``bytes`` buffer
via ``fitz.open(stream=...)``. Nothing is written to disk in this module, so a
request cannot leave lease text behind in ``%TEMP%``.
"""

from __future__ import annotations

import hashlib
import importlib.util
import logging
import re
import shutil
import unicodedata
from typing import Any

from app.core.config import Settings, get_settings
from app.core.errors import (
    CorruptPDFError,
    DocumentTooLargeError,
    EmptyFileError,
    EncryptedPDFError,
    InvalidFileTypeError,
    OCRUnavailableError,
    TextExtractionError,
)
from app.models.document import (
    BoundingBox,
    ExtractedDocument,
    PageLayout,
    TextLine,
    WordBox,
)
from app.models.enums import ExtractionMethod

try:  # PyMuPDF >= 1.24 exposes the canonical module name
    import pymupdf as fitz
except ImportError:  # pragma: no cover - legacy alias
    import fitz  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

PDF_MAGIC = b"%PDF-"

# Characters PyMuPDF/Tesseract commonly emit that should be normalised away.
_LIGATURES = {
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
    "\u00a0": " ",
    "\u2007": " ",
    "\u202f": " ",
    "\u200b": "",
    "\u00ad": "",
    "\u2010": "-",
    "\u2011": "-",
    "\u2012": "-",
    "\u2013": "-",
    "\u2014": "-",
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2022": "-",
    "\uff1a": ":",
}
_LIGATURE_TABLE = str.maketrans(_LIGATURES)

_WHITESPACE_RE = re.compile(r"[ \t\u00a0]+")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")


def clean_text(value: str) -> str:
    """Unicode-normalise and tidy a block of extracted text."""
    if not value:
        return ""
    text = unicodedata.normalize("NFC", value)
    text = text.translate(_LIGATURE_TABLE)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _WHITESPACE_RE.sub(" ", text)
    text = _MULTI_NEWLINE_RE.sub("\n\n", text)
    return text.strip()


def ocr_diagnostics(settings: Settings | None = None) -> dict[str, Any]:
    """Report whether OCR can actually run (used by ``/health``)."""
    cfg = settings or get_settings()
    tesseract_bin = shutil.which(cfg.tesseract_cmd or "tesseract")
    has_lib = importlib.util.find_spec("pytesseract") is not None
    version: str | None = None
    if tesseract_bin and has_lib:
        try:
            import pytesseract  # noqa: PLC0415 - optional dependency

            if cfg.tesseract_cmd:
                pytesseract.pytesseract.tesseract_cmd = cfg.tesseract_cmd
            version = str(pytesseract.get_tesseract_version())
        except Exception:  # pragma: no cover - environment dependent
            version = None
    return {
        "enabled": cfg.ocr_enabled,
        "available": bool(tesseract_bin and has_lib and version),
        "binary": tesseract_bin,
        "pytesseract_installed": has_lib,
        "version": version,
    }


class PdfParser:
    """Extracts words, lines and page geometry from a PDF byte buffer."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    # -- public API ---------------------------------------------------------
    def parse(self, data: bytes, file_name: str) -> ExtractedDocument:
        self._validate_upload(data, file_name)
        digest = hashlib.sha256(data).hexdigest()

        try:
            document = fitz.open(stream=data, filetype="pdf")
        except Exception as exc:  # PyMuPDF raises RuntimeError / FileDataError
            raise CorruptPDFError(details={"file_name": file_name}) from exc

        try:
            if document.needs_pass and not document.authenticate(""):
                raise EncryptedPDFError()
            if document.page_count == 0:
                raise TextExtractionError("The PDF contains no pages.")
            if document.page_count > self.settings.max_pages:
                raise DocumentTooLargeError(
                    f"The document has {document.page_count} pages; "
                    f"the limit is {self.settings.max_pages}.",
                    details={"page_count": document.page_count, "limit": self.settings.max_pages},
                )

            pages = [self._extract_page(document[index], index + 1) for index in range(document.page_count)]
            metadata = self._safe_metadata(document)
            page_count = document.page_count
        finally:
            document.close()

        warnings: list[str] = []
        pages = self._ocr_pages_if_needed(pages, data, warnings)
        self._mark_boilerplate(pages)

        total_chars = sum(page.char_count for page in pages)
        if total_chars < 20:
            raise TextExtractionError(
                details={"pages": page_count, "chars": total_chars},
            )

        mean_chars = total_chars / max(1, page_count)
        ocr_used = any(page.used_ocr for page in pages)
        if ocr_used and all(page.used_ocr for page in pages):
            method = ExtractionMethod.OCR
        elif ocr_used:
            method = ExtractionMethod.HYBRID
        else:
            method = ExtractionMethod.TEXT_LAYER

        return ExtractedDocument(
            file_name=file_name,
            file_size_bytes=len(data),
            sha256=digest,
            page_count=page_count,
            pages=pages,
            extraction_method=method,
            ocr_used=ocr_used,
            mean_chars_per_page=mean_chars,
            metadata=metadata,
            warnings=warnings,
        )

    # -- validation ---------------------------------------------------------
    def _validate_upload(self, data: bytes, file_name: str) -> None:
        if not data:
            raise EmptyFileError()
        if len(data) > self.settings.max_upload_bytes:
            raise InvalidFileTypeError(
                f"File exceeds the {self.settings.max_upload_mb} MB limit.",
                status_code=413,
                code="file_too_large",
            )
        if not data.startswith(PDF_MAGIC) and PDF_MAGIC not in data[:1024]:
            raise InvalidFileTypeError(
                f"'{file_name}' is not a PDF (missing %PDF header).",
            )

    # -- text layer ---------------------------------------------------------
    def _extract_page(self, page: fitz.Page, page_number: int) -> PageLayout:
        lines: list[TextLine] = []
        try:
            raw = page.get_text("dict")
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("dict extraction failed on page %s: %s", page_number, exc)
            raw = {"blocks": []}

        for block in raw.get("blocks", []):
            if block.get("type") != 0:
                continue
            block_no = int(block.get("number", 0))
            for line_no, line in enumerate(block.get("lines", [])):
                spans = [s for s in line.get("spans", []) if s.get("text", "").strip()]
                if not spans:
                    continue
                text = clean_text("".join(span["text"] for span in spans))
                if not text:
                    continue
                bbox = BoundingBox.from_sequence(line["bbox"])
                if not bbox.is_valid():
                    continue
                is_bold = any(int(span.get("flags", 0)) & 2**4 for span in spans)
                font_size = max(float(span.get("size", 0.0)) for span in spans)
                lines.append(
                    TextLine(
                        page_number=page_number,
                        text=text,
                        bbox=bbox,
                        block_number=block_no,
                        line_number=line_no,
                        is_bold=is_bold,
                        font_size=round(font_size, 1),
                    )
                )

        lines = self._merge_hyphenated_lines(lines)
        words = self._extract_words(page, page_number)
        rect = page.rect
        return PageLayout(
            page_number=page_number,
            width=float(rect.width),
            height=float(rect.height),
            rotation=int(page.rotation),
            lines=lines,
            words=words,
            used_ocr=False,
        )

    @staticmethod
    def _merge_hyphenated_lines(lines: list[TextLine]) -> list[TextLine]:
        """Join ``agree-`` / ``ment`` pairs split by the PDF layout engine."""
        if not lines:
            return lines
        merged: list[TextLine] = [lines[0]]
        for line in lines[1:]:
            previous = merged[-1]
            ends_hyphen = previous.text.endswith("-") and len(previous.text) > 1
            starts_lower = line.text[:1].islower()
            same_block = previous.block_number == line.block_number
            if ends_hyphen and starts_lower and same_block:
                previous.text = f"{previous.text[:-1]}{line.text}"
                previous.bbox = BoundingBox.union([previous.bbox, line.bbox]) or previous.bbox
                continue
            merged.append(line)
        return merged

    @staticmethod
    def _extract_words(page: fitz.Page, page_number: int) -> list[WordBox]:
        words: list[WordBox] = []
        try:
            for entry in page.get_text("words"):
                x0, y0, x1, y1, text, block_no, line_no, _word_no = entry
                cleaned = clean_text(str(text))
                if not cleaned:
                    continue
                words.append(
                    WordBox(
                        text=cleaned,
                        bbox=BoundingBox.from_sequence((x0, y0, x1, y1)),
                        block_number=int(block_no),
                        line_number=int(line_no),
                    )
                )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("word extraction failed on page %s: %s", page_number, exc)
        return words

    # -- OCR ----------------------------------------------------------------
    def _ocr_pages_if_needed(
        self,
        pages: list[PageLayout],
        data: bytes,
        warnings: list[str],
    ) -> list[PageLayout]:
        """Replace text-sparse pages with OCR output.

        A page is considered "scanned" when it carries fewer than
        ``ocr_min_chars_per_page`` characters, which is the usual signature of an
        image-only page (as opposed to a short page of a text PDF).
        """
        threshold = self.settings.ocr_min_chars_per_page
        candidates = [page for page in pages if page.char_count < threshold]
        if not candidates or not self.settings.ocr_enabled:
            return pages

        diagnostics = ocr_diagnostics(self.settings)
        if not diagnostics["available"]:
            message = (
                "This document contains image-only pages with no text layer and OCR "
                "is unavailable on this server, so those pages could not be read."
            )
            if all(page.char_count < threshold for page in pages):
                raise OCRUnavailableError(details={"pages": [p.page_number for p in candidates]})
            warnings.append(message)
            logger.warning("OCR unavailable; %s sparse page(s) skipped", len(candidates))
            return pages

        ocr_text_by_page: dict[int, list[TextLine]] = {}
        try:
            document = fitz.open(stream=data, filetype="pdf")
        except Exception:  # pragma: no cover - already validated
            return pages

        try:
            for page in candidates:
                try:
                    ocr_text_by_page[page.page_number] = self._ocr_page(
                        document[page.page_number - 1], page.page_number
                    )
                except Exception as exc:
                    warnings.append(f"OCR failed on page {page.page_number}; it was skipped.")
                    logger.warning("OCR failed on page %s: %s", page.page_number, exc)
        finally:
            document.close()

        updated: list[PageLayout] = []
        for page in pages:
            ocr_lines = ocr_text_by_page.get(page.page_number)
            if not ocr_lines:
                updated.append(page)
                continue
            updated.append(
                page.model_copy(
                    update={
                        "lines": ocr_lines,
                        "words": [],
                        "used_ocr": True,
                    }
                )
            )
            warnings.append(f"Page {page.page_number} was read with OCR; verify quoted text.")
        return updated

    def _ocr_page(self, page: fitz.Page, page_number: int) -> list[TextLine]:
        import pytesseract  # noqa: PLC0415 - optional dependency
        from PIL import Image  # noqa: PLC0415 - optional dependency

        if self.settings.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = self.settings.tesseract_cmd

        pixmap = page.get_pixmap(dpi=self.settings.ocr_dpi)
        image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
        payload = pytesseract.image_to_data(
            image,
            lang=self.settings.ocr_languages,
            output_type=pytesseract.Output.DICT,
        )

        # Tesseract reports pixel coordinates; convert back to PDF points.
        scale_x = page.rect.width / max(1, pixmap.width)
        scale_y = page.rect.height / max(1, pixmap.height)

        grouped: dict[tuple[int, int, int], dict[str, Any]] = {}
        for index, raw_text in enumerate(payload.get("text", [])):
            text = clean_text(str(raw_text))
            if not text:
                continue
            try:
                confidence = float(payload["conf"][index])
            except (KeyError, TypeError, ValueError):
                confidence = 0.0
            if confidence < 0:
                continue
            key = (
                int(payload["block_num"][index]),
                int(payload["par_num"][index]),
                int(payload["line_num"][index]),
            )
            x, y = float(payload["left"][index]), float(payload["top"][index])
            w, h = float(payload["width"][index]), float(payload["height"][index])
            bbox = BoundingBox(
                x0=x * scale_x,
                y0=y * scale_y,
                x1=(x + w) * scale_x,
                y1=(y + h) * scale_y,
            )
            entry = grouped.setdefault(key, {"words": [], "boxes": [], "conf": []})
            entry["words"].append(text)
            entry["boxes"].append(bbox)
            entry["conf"].append(confidence)

        lines: list[TextLine] = []
        for order, (key, entry) in enumerate(sorted(grouped.items())):
            text = clean_text(" ".join(entry["words"]))
            bbox = BoundingBox.union(entry["boxes"])
            if not text or bbox is None:
                continue
            mean_conf = sum(entry["conf"]) / max(1, len(entry["conf"]))
            lines.append(
                TextLine(
                    page_number=page_number,
                    text=text,
                    bbox=bbox,
                    block_number=key[0],
                    line_number=order,
                    is_bold=False,
                    font_size=0.0,
                )
            )
            if mean_conf < 60:
                logger.debug("low OCR confidence %.0f on page %s", mean_conf, page_number)
        return lines

    # -- post-processing ----------------------------------------------------
    @staticmethod
    def _mark_boilerplate(pages: list[PageLayout]) -> None:
        """Flag running headers, footers and page labels.

        Two-page agreements are the common case, so the detector must work from a
        single repeat: a short line in the top/bottom margin band whose text (with
        digits normalised) appears on at least half the pages is furniture, not a
        clause. Marked lines are skipped by the splitter, which otherwise folds a
        page footer into the clause that happens to straddle the page break.
        """
        if not pages:
            return

        repeated: set[str] = set()
        if len(pages) >= 2:
            counts: dict[str, int] = {}
            for page in pages:
                seen: set[str] = set()
                for line in page.lines:
                    if len(line.text) > 80 or not _is_margin_line(line, page):
                        continue
                    key = _boilerplate_key(line.text)
                    if len(key) < 3 or key in seen:
                        continue
                    seen.add(key)
                    counts[key] = counts.get(key, 0) + 1
            threshold = max(2, (len(pages) + 1) // 2)
            repeated = {key for key, count in counts.items() if count >= threshold}

        for page in pages:
            for line in page.lines:
                if not _is_margin_line(line, page):
                    continue
                if _boilerplate_key(line.text) in repeated or PAGE_LABEL_RE.match(line.text.strip()):
                    line.is_boilerplate = True

    @staticmethod
    def _safe_metadata(document: fitz.Document) -> dict[str, Any]:
        """Keep only non-identifying metadata (drop author/producer strings)."""
        try:
            raw = document.metadata or {}
        except Exception:  # pragma: no cover - defensive
            return {}
        return {
            "format": raw.get("format"),
            "encrypted": bool(raw.get("encryption")),
            "page_count": document.page_count,
        }


def normalise_newlines(text: str) -> str:
    """Utility used by the splitter for consistent line handling."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


# A page label such as "Page 1 of 2" / "Page 3" in the top or bottom margin. It must
# contain the word "page" so that a numbered clause near the top of a page is never
# mistaken for furniture.
PAGE_LABEL_RE = re.compile(r"^page\s+\d{1,4}\b(?:\s*(?:of|/)\s*\d{1,4})?", re.IGNORECASE)
MARGIN_BAND = 0.11  # fraction of the page height treated as header/footer space


def _is_margin_line(line: TextLine, page: PageLayout) -> bool:
    """True when the line sits in the header or footer band of its page."""
    if page.height <= 0:
        return False
    band = page.height * MARGIN_BAND
    return line.bbox.y0 <= band or line.bbox.y1 >= page.height - band


def _boilerplate_key(text: str) -> str:
    """Comparison key that ignores the changing page number."""
    return re.sub(r"\d+", "#", " ".join(text.lower().split())).strip()
