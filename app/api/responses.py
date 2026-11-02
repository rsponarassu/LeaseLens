"""Shared HTTP response helpers.

PDFs are streamed from memory: the service never writes an uploaded document to
disk, so a ``FileResponse`` (which needs a path) would defeat the privacy design.
"""

from __future__ import annotations

import re

from fastapi import Response

_NON_ASCII = re.compile(r"[^A-Za-z0-9._-]+")


def download_name(name: str, *, suffix: str = "-annotated") -> str:
    """Build an ASCII-safe ``<stem><suffix>.pdf`` name for the save dialog."""
    stem = name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if stem.lower().endswith(".pdf"):
        stem = stem[:-4]
    stem = _NON_ASCII.sub("-", stem).strip("-.") or "lease"
    return f"{stem[:80]}{suffix}.pdf"


def pdf_response(content: bytes, file_name: str, *, inline: bool = False) -> Response:
    """Return PDF bytes with headers that discourage caching by proxies."""
    disposition = "inline" if inline else "attachment"
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'{disposition}; filename="{file_name}"',
            "Content-Length": str(len(content)),
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
