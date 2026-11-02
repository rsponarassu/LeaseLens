"""Shared HTTP plumbing for LLM providers: lifecycle, retries, error mapping.

API keys are always sent in headers (never in URLs) so that access logs and the
``httpx`` logs cannot leak them.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import LLMError, LLMResponseFormatError, LLMTimeoutError
from app.llm.base import LLMClient

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504, 529}


class HttpLLMClient(LLMClient):
    """Base class that owns a lazily created ``httpx.AsyncClient``."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client: httpx.AsyncClient | None = None

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    self.settings.llm_timeout_seconds,
                    connect=self.settings.llm_connect_timeout,
                )
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    async def _post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        payload: dict[str, Any],
        label: str,
    ) -> tuple[dict[str, Any], int]:
        """POST JSON with exponential backoff. Returns (body, elapsed_ms)."""
        attempts = max(1, self.settings.llm_max_retries + 1)
        client = self._ensure_client()
        last_error: Exception | None = None
        started = time.perf_counter()

        for attempt in range(attempts):
            try:
                response = await client.post(url, headers=headers, json=payload)
            except httpx.TimeoutException:
                last_error = LLMTimeoutError(
                    f"{label} did not respond within "
                    f"{self.settings.llm_timeout_seconds:.0f}s.",
                    details={"attempt": attempt + 1},
                )
                logger.warning("%s request timed out (attempt %s)", label, attempt + 1)
            except httpx.HTTPError as exc:
                last_error = LLMError(
                    f"{label} request failed: {type(exc).__name__}",
                    details={"attempt": attempt + 1},
                )
                logger.warning("%s transport error: %s", label, exc)
            else:
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                if response.status_code == 200:
                    try:
                        return response.json(), elapsed_ms
                    except ValueError as exc:
                        raise LLMResponseFormatError(
                            f"{label} returned a non-JSON response."
                        ) from exc

                body_preview = response.text[:400]
                if response.status_code in _RETRYABLE_STATUS and attempt < attempts - 1:
                    logger.warning(
                        "%s returned %s, retrying", label, response.status_code
                    )
                else:
                    raise LLMError(
                        f"{label} returned HTTP {response.status_code}.",
                        details={
                            "status_code": response.status_code,
                            "body": body_preview,
                        },
                    )

            if attempt < attempts - 1:
                await asyncio.sleep(0.4 * (2**attempt))

        if isinstance(last_error, LLMTimeoutError):
            raise last_error
        raise LLMError(
            f"{label} could not be reached after {attempts} attempts.",
            details={"last_error": str(last_error)},
        )

    @staticmethod
    def _extract_text_from_parts(parts: list[dict[str, Any]]) -> str:
        chunks = [part.get("text", "") for part in parts if isinstance(part, dict)]
        return "".join(chunk for chunk in chunks if chunk)


class TokenMeter:
    """Small helper to normalise provider usage payloads."""

    @staticmethod
    def gemini(usage: dict[str, Any] | None) -> tuple[int, int]:
        usage = usage or {}
        return (
            int(usage.get("promptTokenCount") or 0),
            int(usage.get("candidatesTokenCount") or 0),
        )

    @staticmethod
    def anthropic(usage: dict[str, Any] | None) -> tuple[int, int]:
        usage = usage or {}
        return (
            int(usage.get("input_tokens") or 0),
            int(usage.get("output_tokens") or 0),
        )
