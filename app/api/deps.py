"""FastAPI dependencies and the single upload entry point.

Uploads are validated before a single byte reaches the parser: declared type,
size (counted while streaming, not trusted from a header) and the ``%PDF``
signature. The temporary file is closed in a ``finally`` block so the spooled
body is released as soon as the request ends.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request, UploadFile

from app.cache.sessions import SessionCache
from app.core.config import Settings
from app.core.errors import EmptyFileError, FileTooLargeError, InvalidFileTypeError
from app.data.sample_repository import SampleLeaseRepository
from app.runtime import Runtime
from app.services.pipeline import AnalysisPipeline

logger = logging.getLogger(__name__)

PDF_MAGIC = b"%PDF"
_CHUNK_SIZE = 256 * 1024
_ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/x-pdf",
    "application/octet-stream",
    "",
}
_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9._ ()-]+")
MAX_FILE_NAME = 120


@dataclass(frozen=True)
class UploadedPDF:
    """A validated upload, held only for the duration of the request."""

    file_name: str
    content_type: str
    data: bytes

    @property
    def size(self) -> int:
        return len(self.data)


# ---------------------------------------------------------------------------
# Runtime accessors
# ---------------------------------------------------------------------------
def get_runtime(request: Request) -> Runtime:
    """Return the object graph created at startup."""
    runtime: Runtime | None = getattr(request.app.state, "runtime", None)
    if runtime is None:  # pragma: no cover - startup wiring bug
        raise RuntimeError("Application runtime has not been initialised.")
    return runtime


RuntimeDep = Annotated[Runtime, Depends(get_runtime)]


def get_app_settings(runtime: RuntimeDep) -> Settings:
    return runtime.settings


def get_pipeline(runtime: RuntimeDep) -> AnalysisPipeline:
    return runtime.pipeline


def get_session_cache(runtime: RuntimeDep) -> SessionCache:
    return runtime.sessions


def get_sample_repository(runtime: RuntimeDep) -> SampleLeaseRepository:
    return runtime.samples


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
PipelineDep = Annotated[AnalysisPipeline, Depends(get_pipeline)]
SessionsDep = Annotated[SessionCache, Depends(get_session_cache)]
SamplesDep = Annotated[SampleLeaseRepository, Depends(get_sample_repository)]


# ---------------------------------------------------------------------------
# Upload handling
# ---------------------------------------------------------------------------
async def read_pdf_upload(file: UploadFile, settings: Settings) -> UploadedPDF:
    """Stream a multipart upload into memory, enforcing the limits as we go."""
    file_name = safe_file_name(file.filename)
    _check_declared_type(file.content_type, file_name)

    chunks: list[bytes] = []
    total = 0
    try:
        while True:
            chunk = await file.read(_CHUNK_SIZE)
            if not chunk:
                break
            total += len(chunk)
            if total > settings.max_upload_bytes:
                raise FileTooLargeError(
                    f"'{file_name}' exceeds the {settings.max_upload_mb} MB limit.",
                    details={"limit_mb": settings.max_upload_mb, "received_bytes": total},
                )
            chunks.append(chunk)
    finally:
        await file.close()

    data = b"".join(chunks)
    if not data:
        raise EmptyFileError(f"'{file_name}' is empty.")

    if PDF_MAGIC not in data[:1024]:
        raise InvalidFileTypeError(
            f"'{file_name}' is not a PDF (no %PDF header found).",
            details={"file_name": file_name},
        )

    logger.info("accepted upload: name=%s bytes=%s", file_name, len(data))
    return UploadedPDF(
        file_name=file_name,
        content_type=file.content_type or "application/pdf",
        data=data,
    )


def safe_file_name(name: str | None) -> str:
    """Strip directories and unsafe characters from a client-supplied name."""
    candidate = (name or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    candidate = _UNSAFE_NAME.sub("_", candidate).strip(" ._")
    if not candidate:
        return "lease.pdf"
    if not candidate.lower().endswith(".pdf"):
        candidate = f"{candidate}.pdf"
    return candidate[:MAX_FILE_NAME]


def _check_declared_type(content_type: str | None, file_name: str) -> None:
    declared = (content_type or "").lower().split(";")[0].strip()
    if declared in _ALLOWED_CONTENT_TYPES:
        return
    if file_name.lower().endswith(".pdf"):
        # Browsers and some clients send odd types for PDFs; the magic-byte
        # check below is the authoritative test.
        return
    raise InvalidFileTypeError(
        f"Unsupported content type '{declared}'. Upload a PDF file.",
        details={"content_type": declared, "file_name": file_name},
    )
