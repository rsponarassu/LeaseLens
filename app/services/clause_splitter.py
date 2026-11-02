"""Clause segmentation.

Splitting is deliberately rule-based rather than model-based: segmentation must
be deterministic, reproducible and cheap, and the boundaries it produces are the
coordinates we later highlight on the PDF.

Strategy order (most specific first):
1. ``numbered``      - "7. Security deposit:" / "9. Lock-in -" (the norm in
                       Indian tenancy agreements)
2. ``articles``      - "ARTICLE IV ...", "Clause 12 ...", "SECTION 3 ..."
3. ``colon_headings``- "Security Deposit: ..." without a number
4. ``caps_headings`` - standalone "SECURITY DEPOSIT" style headings
5. ``paragraphs``    - blank-space clustering fallback
6. ``sentences``     - last resort for dense unpunctuated text
"""

from __future__ import annotations

import logging
import re
import statistics
from collections.abc import Iterable

from app.core.errors import NoClausesFoundError
from app.models.clause import Clause, ClauseSpan, ClauseSplitResult
from app.models.document import BoundingBox, ExtractedDocument, TextLine

logger = logging.getLogger(__name__)

# "7. Security deposit" / "9) Lock-in" / "12. Notice"
NUMBERED_RE = re.compile(r"^(?P<num>\d{1,2})\s*[.)]\s*(?P<rest>\S.*)$")
# "7.1 The deposit shall ..." -> a sub-clause, stays inside its parent clause.
MULTI_LEVEL_RE = re.compile(r"^\d{1,2}\.\d{1,2}(?!\d)")
ARTICLE_RE = re.compile(
    r"^(?:ARTICLE|Article|CLAUSE|Clause|SECTION|Section|PART|Part)\s+"
    r"(?P<num>[IVXLCDM]+|\d{1,2})\s*[.:\-]?\s*(?P<rest>.*)$"
)
COLON_HEADING_RE = re.compile(r"^(?P<title>[A-Z][A-Za-z0-9 ,&/'()\-]{2,55}?)\s*:\s*(?P<body>.*)$")
ALL_CAPS_RE = re.compile(r"^[A-Z][A-Z0-9 ,&/'()\-]{3,55}$")
INLINE_TITLE_RE = re.compile(
    r"^(?P<title>[A-Z][A-Za-z0-9 ,&/'()\-]{1,60}?)\s*:\s*(?P<body>\S.*)$"
)
PAGE_NUMBER_RE = re.compile(r"^(?:page\s*)?\d{1,3}(?:\s*(?:of|/)\s*\d{1,3})?$", re.IGNORECASE)
NOISE_RE = re.compile(r"^[\W_]+$")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.;:])\s+(?=[A-Z0-9])")

MIN_CLAUSE_CHARS = 30
MAX_CLAUSE_LINES = 80
MAX_PROMPT_CHARS = 6000


class ClauseSplitter:
    """Turns an :class:`ExtractedDocument` into ordered :class:`Clause` objects."""

    def __init__(
        self,
        *,
        min_clause_chars: int = MIN_CLAUSE_CHARS,
        max_clause_lines: int = MAX_CLAUSE_LINES,
    ) -> None:
        self.min_clause_chars = min_clause_chars
        self.max_clause_lines = max_clause_lines

    # -- public API ---------------------------------------------------------
    def split(self, document: ExtractedDocument) -> ClauseSplitResult:
        lines = self._usable_lines(document)
        if not lines:
            raise NoClausesFoundError()

        median_font = self._median_font_size(lines)
        boundaries, strategy = self._detect_boundaries(lines, median_font)

        if len(boundaries) < 2:
            fallback = self._split_by_paragraphs(lines)
            if len(fallback) >= 2:
                boundaries, strategy = fallback, "paragraphs"
            else:
                chunks = self._split_by_sentences(lines)
                if len(chunks) < 2:
                    raise NoClausesFoundError(
                        "The document does not appear to contain discrete clauses.",
                        details={"lines": len(lines)},
                    )
                boundaries, strategy = chunks, "sentences"

        clauses = self._build_clauses(boundaries)
        clauses = self._merge_undersized(clauses)
        clauses = self._reindex(clauses)

        result = ClauseSplitResult(
            clauses=clauses,
            strategy=strategy,
            dropped_boilerplate_lines=sum(
                1 for page in document.pages for line in page.lines if line.is_boilerplate
            ),
        )
        if len(clauses) < 3:
            result.warnings.append(
                "Only a few clauses were detected; the PDF may not be a standard "
                "tenancy agreement."
            )
        logger.info(
            "split document into %s clauses using %s strategy", len(clauses), strategy
        )
        return result

    # -- line preparation ---------------------------------------------------
    @staticmethod
    def _usable_lines(document: ExtractedDocument) -> list[TextLine]:
        lines: list[TextLine] = []
        for page in document.pages:
            for line in page.lines:
                if line.is_boilerplate:
                    continue
                text = line.text.strip()
                if not text or NOISE_RE.match(text) or PAGE_NUMBER_RE.match(text):
                    continue
                if len(text) <= 2 and not text.isdigit():
                    continue
                lines.append(line)
        return lines

    @staticmethod
    def _median_font_size(lines: Iterable[TextLine]) -> float:
        sizes = [line.font_size for line in lines if line.font_size > 0]
        return statistics.median(sizes) if sizes else 0.0

    # -- boundary detection -------------------------------------------------
    def _detect_boundaries(
        self, lines: list[TextLine], median_font: float
    ) -> tuple[list[tuple[str, str, list[TextLine]]], str]:
        """Return ``[(kind, title, lines)]`` groups plus the strategy name."""
        groups: list[tuple[str, str, list[TextLine]]] = []
        preamble: list[TextLine] = []
        current: dict[str, object] | None = None
        last_number: int | None = None
        matched_numbered = 0
        matched_other = 0

        def flush() -> None:
            nonlocal current
            if current is not None and current["lines"]:
                groups.append(
                    (str(current["kind"]), str(current["title"]), current["lines"])  # type: ignore[arg-type]
                )
            current = None

        for line in lines:
            detected, last_number = self._classify_line(line, last_number, median_font)
            if detected is None:
                if current is None:
                    if groups:
                        # Text after an overflowed clause: keep it rather than
                        # letting it leak into the preamble bucket.
                        current = {"kind": "continuation", "title": "Continues", "lines": []}
                    else:
                        preamble.append(line)
                        continue
                current["lines"].append(line)  # type: ignore[union-attr]
                if len(current["lines"]) >= self.max_clause_lines:  # type: ignore[arg-type]
                    flush()
                continue

            kind, title, body_line = detected
            flush()
            if preamble and not groups:
                groups.append(("preamble", "Preamble", preamble))
                preamble = []
            current = {
                "kind": kind,
                "title": title,
                "lines": [body_line] if body_line else [],
            }
            if kind == "numbered":
                matched_numbered += 1
            else:
                matched_other += 1

        flush()
        if preamble and not groups:
            groups.append(("preamble", "Preamble", preamble))

        if matched_numbered:
            strategy = "numbered"
        elif matched_other:
            strategy = "articles" if any(g[0] == "article" for g in groups) else "colon_headings"
        return groups, strategy

    def _classify_line(
        self,
        line: TextLine,
        last_number: int | None,
        median_font: float,
    ) -> tuple[tuple[str, str, TextLine | None] | None, int | None]:
        """Decide whether ``line`` starts a new clause."""
        text = line.text.strip()

        article = ARTICLE_RE.match(text)
        if article:
            rest = article.group("rest").strip()
            title = rest[:80] if rest else f"Article {article.group('num')}"
            return ("article", title.rstrip(".:"), line), last_number

        numbered = NUMBERED_RE.match(text)
        if numbered and not MULTI_LEVEL_RE.match(text):
            number = int(numbered.group("num"))
            if self._accepts_number(number, last_number):
                rest = numbered.group("rest").strip()
                title, body = self._split_title_body(rest)
                return ("numbered", title, line), number

        if not MULTI_LEVEL_RE.match(text):
            colon = COLON_HEADING_RE.match(text)
            if colon and len(colon.group("title").split()) <= 8:
                title = colon.group("title").strip()
                if title.lower() not in _STOPWORD_HEADINGS:
                    return ("colon", title, line), last_number

        if self._looks_like_caps_heading(line, text, median_font):
            return ("caps", text.title().strip(), line), last_number

        return None, last_number

    @staticmethod
    def _accepts_number(number: int, last_number: int | None) -> bool:
        """Reject dates and stray digits while tolerating restarted numbering."""
        if last_number is None:
            return 1 <= number <= 5
        if number == last_number + 1 or number == 1:
            return True
        return 1 <= number - last_number <= 3

    @staticmethod
    def _split_title_body(rest: str) -> tuple[str, str]:
        """Split "Security deposit: ten months rent" into title and body."""
        inline = INLINE_TITLE_RE.match(rest)
        if inline:
            title = inline.group("title").strip()
            body = inline.group("body").strip()
            if 1 <= len(title.split()) <= 8 and not title[0].islower():
                return title, f"{title}: {body}"
        words = rest.split()
        if len(words) <= 8 and len(rest) <= 70 and not rest.endswith((",", ";")):
            return rest.strip().rstrip(":-").strip(), rest
        return _truncate_heading(rest), rest

    @staticmethod
    def _looks_like_caps_heading(line: TextLine, text: str, median_font: float) -> bool:
        if not ALL_CAPS_RE.match(text):
            return False
        words = text.split()
        if len(words) > 6:
            return False
        if median_font and line.font_size >= median_font * 1.15:
            return True
        return line.is_bold or text.isupper()

    # -- clause assembly ----------------------------------------------------
    def _build_clauses(
        self, groups: list[tuple[str, str, list[TextLine]]]
    ) -> list[Clause]:
        clauses: list[Clause] = []
        for order, (_kind, title, group_lines) in enumerate(groups, start=1):
            text = "\n".join(line.text for line in group_lines).strip()
            text = _dedupe_lines(text)
            if not text:
                continue
            spans = self._spans_for(group_lines)
            bbox = spans[0].bbox if spans else (group_lines[0].bbox if group_lines else None)
            clauses.append(
                Clause(
                    clause_id=f"c{order:03d}",
                    order=order,
                    heading=title or _truncate_heading(text),
                    raw_text=text[:MAX_PROMPT_CHARS],
                    page_number=group_lines[0].page_number if group_lines else 1,
                    bbox=bbox,
                    spans=spans,
                )
            )
        return clauses

    @staticmethod
    def _spans_for(lines: list[TextLine]) -> list[ClauseSpan]:
        """Union the clause's line boxes per page."""
        by_page: dict[int, list[TextLine]] = {}
        for line in lines:
            by_page.setdefault(line.page_number, []).append(line)
        spans: list[ClauseSpan] = []
        for page_number in sorted(by_page):
            page_lines = by_page[page_number]
            union = BoundingBox.union([line.bbox for line in page_lines])
            if union is None or not union.is_valid():
                continue
            spans.append(
                ClauseSpan(page_number=page_number, bbox=union, line_count=len(page_lines))
            )
        return spans

    def _merge_undersized(self, clauses: list[Clause]) -> list[Clause]:
        """Fold fragments (e.g. a stray "9." line) into the previous clause."""
        merged: list[Clause] = []
        for clause in clauses:
            if merged and len(clause.raw_text) < self.min_clause_chars:
                previous = merged[-1]
                previous.raw_text = f"{previous.raw_text}\n{clause.raw_text}"[:MAX_PROMPT_CHARS]
                previous.spans = _merge_spans(previous.spans, clause.spans)
                continue
            merged.append(clause)
        return merged

    @staticmethod
    def _reindex(clauses: list[Clause]) -> list[Clause]:
        for order, clause in enumerate(clauses, start=1):
            clause.order = order
            clause.clause_id = f"c{order:03d}"
            if not clause.heading:
                clause.heading = _truncate_heading(clause.raw_text)
        return clauses

    # -- fallbacks ----------------------------------------------------------
    def _split_by_paragraphs(
        self, lines: list[TextLine]
    ) -> list[tuple[str, str, list[TextLine]]]:
        groups: list[tuple[str, str, list[TextLine]]] = []
        current: list[TextLine] = []
        heights = [line.bbox.height for line in lines if line.bbox.height > 0]
        gap_threshold = (statistics.median(heights) * 1.9) if heights else 0.0

        for previous, line in zip([None, *lines], lines, strict=False):
            if previous is not None:
                same_page = previous.page_number == line.page_number
                gap = line.bbox.y0 - previous.bbox.y1
                if not same_page or gap > gap_threshold:
                    if current:
                        groups.append(("paragraph", _truncate_heading(_join(current)), current))
                    current = []
            current.append(line)
        if current:
            groups.append(("paragraph", _truncate_heading(_join(current)), current))
        return groups

    def _split_by_sentences(
        self, lines: list[TextLine], target_chars: int = 900
    ) -> list[tuple[str, str, list[TextLine]]]:
        groups: list[tuple[str, str, list[TextLine]]] = []
        buffer: list[TextLine] = []
        buffer_chars = 0
        for line in lines:
            buffer.append(line)
            buffer_chars += len(line.text)
            if buffer_chars >= target_chars and line.text.rstrip().endswith((".", ";")):
                groups.append(("sentence_chunk", _truncate_heading(_join(buffer)), buffer))
                buffer, buffer_chars = [], 0
        if buffer:
            groups.append(("sentence_chunk", _truncate_heading(_join(buffer)), buffer))
        return groups


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_STOPWORD_HEADINGS = {
    "note",
    "notes",
    "provided",
    "provided that",
    "whereas",
    "witness",
    "terms",
    "conditions",
    "schedule",
    # Party / identity blocks look exactly like colon headings ("Landlord: Mr. S.
    # Rajagopal, No. 12, ...") but they are front matter, not clauses. Splitting on
    # them produced four junk findings before every real one.
    "landlord",
    "tenant",
    "lessor",
    "lessee",
    "owner",
    "occupant",
    "premises",
    "property",
    "address",
    "name",
    "names",
    "date",
    "place",
    "parties",
    "between",
    "witnesses",
    "signed",
    "email",
    "phone",
    "mobile",
    "contact",
    "pan",
    "aadhaar",
}


def _truncate_heading(text: str, limit: int = 64) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3].rstrip(' ,.;:-')}..."


def _join(lines: list[TextLine]) -> str:
    return "\n".join(line.text for line in lines).strip()


def _dedupe_lines(text: str) -> str:
    """Remove consecutive duplicate lines produced by overlapping text layers."""
    seen: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if seen and seen[-1] == stripped:
            continue
        seen.append(stripped)
    return "\n".join(line for line in seen if line)


def _merge_spans(a: list[ClauseSpan], b: list[ClauseSpan]) -> list[ClauseSpan]:
    by_page: dict[int, list[ClauseSpan]] = {}
    for span in [*a, *b]:
        by_page.setdefault(span.page_number, []).append(span)
    merged: list[ClauseSpan] = []
    for page_number in sorted(by_page):
        box = BoundingBox.union([span.bbox for span in by_page[page_number]])
        if box is None:
            continue
        merged.append(
            ClauseSpan(
                page_number=page_number,
                bbox=box,
                line_count=sum(span.line_count for span in by_page[page_number]),
            )
        )
    return merged
