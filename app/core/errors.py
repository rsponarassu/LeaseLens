"""Domain exception hierarchy and the JSON error envelope.

Every failure surfaced by the API goes through one of these types so that
clients always receive the same machine-readable shape::

    {"error": {"code": "...", "message": "...", "details": {...},
               "request_id": "..."}}

Services raise domain errors; only the API layer knows about HTTP.
"""

from __future__ import annotations

from typing import Any


class LeaseLensError(Exception):
    """Base class for all expected application failures."""

    status_code: int = 500
    code: str = "internal_error"
    message: str = "An unexpected error occurred."
    headers: dict[str, str] | None = None

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
        status_code: int | None = None,
        code: str | None = None,
    ) -> None:
        self.message = message or self.message
        self.details = details or {}
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code
        super().__init__(self.message)

    def to_payload(self, request_id: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
        }
        if self.details:
            body["details"] = self.details
        if request_id:
            body["request_id"] = request_id
        return {"error": body}


# ---------------------------------------------------------------------------
# Upload / document errors (4xx)
# ---------------------------------------------------------------------------
class UploadError(LeaseLensError):
    status_code = 400
    code = "invalid_upload"
    message = "The uploaded file could not be accepted."


class InvalidFileTypeError(UploadError):
    status_code = 415
    code = "unsupported_media_type"
    message = "Only PDF files are supported."


class FileTooLargeError(UploadError):
    status_code = 413
    code = "file_too_large"
    message = "The uploaded file exceeds the maximum allowed size."


class EmptyFileError(UploadError):
    status_code = 400
    code = "empty_file"
    message = "The uploaded file is empty."


class CorruptPDFError(LeaseLensError):
    status_code = 422
    code = "corrupt_pdf"
    message = "The PDF appears to be corrupted or is not a valid document."


class EncryptedPDFError(LeaseLensError):
    status_code = 422
    code = "password_protected_pdf"
    message = (
        "This PDF is password protected. Remove the password (or provide an "
        "unprotected copy) and upload it again."
    )


class DocumentTooLargeError(LeaseLensError):
    status_code = 422
    code = "document_too_large"
    message = "The document has more pages than this service accepts."


class OCRUnavailableError(LeaseLensError):
    status_code = 422
    code = "ocr_unavailable"
    message = (
        "This looks like a scanned lease with no text layer, and OCR is not "
        "available on the server. Install Tesseract (and pytesseract) or upload "
        "a text-based PDF."
    )


class TextExtractionError(LeaseLensError):
    status_code = 422
    code = "text_extraction_failed"
    message = "No readable text could be extracted from this document."


class NoClausesFoundError(LeaseLensError):
    status_code = 422
    code = "no_clauses_found"
    message = (
        "No numbered or headed clauses could be identified in this document. "
        "LeaseLens needs a structured tenancy agreement to analyse."
    )


# ---------------------------------------------------------------------------
# LLM errors (5xx, upstream)
# ---------------------------------------------------------------------------
class LLMError(LeaseLensError):
    status_code = 502
    code = "llm_error"
    message = "The clause classification model could not be reached."


class LLMTimeoutError(LLMError):
    status_code = 504
    code = "llm_timeout"
    message = "The clause classification model timed out. Please retry."


class LLMResponseFormatError(LLMError):
    code = "llm_response_invalid"
    message = "The clause classification model returned an unusable response."


class LLMNotConfiguredError(LLMError):
    status_code = 503
    code = "llm_not_configured"
    message = "No LLM provider is configured for this deployment."


# ---------------------------------------------------------------------------
# Session / artefact errors
# ---------------------------------------------------------------------------
class SessionNotFoundError(LeaseLensError):
    status_code = 404
    code = "session_not_found"
    message = "Unknown analysis session."


class SessionExpiredError(LeaseLensError):
    status_code = 410
    code = "session_expired"
    message = (
        "This analysis session has expired and its artefacts were purged. "
        "Re-run the analysis to download the annotated PDF again."
    )


class ArtefactNotFoundError(LeaseLensError):
    status_code = 404
    code = "artefact_not_found"
    message = "The requested artefact is not available for this session."


# ---------------------------------------------------------------------------
# Configuration / internal errors
# ---------------------------------------------------------------------------
class RuleConfigurationError(LeaseLensError):
    status_code = 500
    code = "rule_configuration_invalid"
    message = "The rule base could not be loaded."


class SampleDataError(LeaseLensError):
    status_code = 500
    code = "sample_data_unavailable"
    message = "Demo sample leases are unavailable."


class SampleNotFoundError(LeaseLensError):
    status_code = 404
    code = "sample_not_found"
    message = "Unknown demo sample lease."


class RuleNotFoundError(LeaseLensError):
    status_code = 404
    code = "rule_not_found"
    message = "Unknown rule id."
