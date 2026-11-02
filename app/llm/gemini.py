"""Google Gemini adapter using native JSON-schema structured output."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from typing import Any

from app.core.config import Settings
from app.core.errors import LLMNotConfiguredError, LLMResponseFormatError
from app.llm._http import HttpLLMClient, TokenMeter
from app.llm.base import (
    LLMBatchResult,
    LLMUsage,
    build_response_schema,
    build_system_prompt,
    build_user_prompt,
    parse_llm_json,
)
from app.models.clause import Clause

logger = logging.getLogger(__name__)


class GeminiClient(HttpLLMClient):
    """Calls ``models/{model}:generateContent`` with ``responseSchema``."""

    name = "gemini"

    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__(settings)
        if not self.settings.gemini_api_key:
            raise LLMNotConfiguredError(
                "GEMINI_API_KEY is not set.",
                code="llm_not_configured",
            )
        self._api_key = self.settings.gemini_api_key.get_secret_value()
        self.model = self.settings.gemini_model

    async def classify_batch(self, clauses: Sequence[Clause]) -> LLMBatchResult:
        url = f"{self.settings.gemini_api_base.rstrip('/')}/models/{self.model}:generateContent"
        payload: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": build_system_prompt()}]},
            "contents": [
                {"role": "user", "parts": [{"text": build_user_prompt(clauses)}]}
            ],
            "generationConfig": {
                "temperature": 0.0,
                "responseMimeType": "application/json",
                "responseSchema": build_response_schema("gemini"),
                "maxOutputTokens": self.settings.llm_max_output_tokens,
            },
        }

        body, elapsed_ms = await self._post(
            url,
            headers={
                "x-goog-api-key": self._api_key,
                "content-type": "application/json",
            },
            payload=payload,
            label="gemini",
        )

        candidates = body.get("candidates") or []
        if not candidates:
            raise LLMResponseFormatError(
                "Gemini returned no candidates.",
                details={"prompt_feedback": body.get("promptFeedback")},
            )

        candidate = candidates[0]
        finish_reason = candidate.get("finishReason")
        parts = candidate.get("content", {}).get("parts", [])
        text = self._extract_text_from_parts(parts)
        if not text.strip():
            raise LLMResponseFormatError(
                f"Gemini returned an empty response (finishReason={finish_reason}).",
            )
        if finish_reason == "MAX_TOKENS":
            raise LLMResponseFormatError(
                "Gemini response was truncated (MAX_TOKENS). Reduce batch size.",
            )

        try:
            parsed = parse_llm_json(text)
        except (ValueError, json.JSONDecodeError) as exc:
            raise LLMResponseFormatError(
                "Gemini response was not valid JSON for the requested schema.",
                details={"preview": text[:200]},
            ) from exc

        input_tokens, output_tokens = TokenMeter.gemini(body.get("usageMetadata"))
        return LLMBatchResult(
            results=parsed.clauses,
            usage=LLMUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=elapsed_ms,
                model=self.model,
            ),
            raw=body,
        )
