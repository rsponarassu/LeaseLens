"""Anthropic Claude adapter using a forced tool call for structured output."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from app.core.config import Settings
from app.core.errors import LLMNotConfiguredError, LLMResponseFormatError
from app.llm._http import HttpLLMClient, TokenMeter
from app.llm.base import (
    LLMBatchResult,
    LLMResponse,
    LLMUsage,
    build_response_schema,
    build_system_prompt,
    build_user_prompt,
)
from app.models.clause import Clause

logger = logging.getLogger(__name__)

TOOL_NAME = "record_clause_classifications"


class AnthropicClient(HttpLLMClient):
    """Uses a single forced tool to obtain schema-constrained JSON."""

    name = "anthropic"

    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__(settings)
        if not self.settings.anthropic_api_key:
            raise LLMNotConfiguredError(
                "ANTHROPIC_API_KEY is not set.",
            )
        self._api_key = self.settings.anthropic_api_key.get_secret_value()
        self.model = self.settings.anthropic_model

    async def classify_batch(self, clauses: Sequence[Clause]) -> LLMBatchResult:
        url = f"{self.settings.anthropic_api_base.rstrip('/')}/messages"
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.settings.llm_max_output_tokens,
            "temperature": 0.0,
            "system": build_system_prompt(),
            "messages": [
                {"role": "user", "content": build_user_prompt(clauses)},
            ],
            "tools": [
                {
                    "name": TOOL_NAME,
                    "description": (
                        "Return the clause classification for every clause supplied."
                    ),
                    "input_schema": build_response_schema("anthropic"),
                }
            ],
            "tool_choice": {"type": "tool", "name": TOOL_NAME},
        }

        body, elapsed_ms = await self._post(
            url,
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": self.settings.anthropic_version,
                "content-type": "application/json",
            },
            payload=payload,
            label="anthropic",
        )

        blocks = body.get("content") or []
        tool_input: dict[str, Any] | None = None
        for block in blocks:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                candidate = block.get("input")
                if isinstance(candidate, dict):
                    tool_input = candidate
                    break

        if tool_input is None:
            raise LLMResponseFormatError(
                "Anthropic did not return a tool_use block.",
                details={"stop_reason": body.get("stop_reason")},
            )

        if body.get("stop_reason") == "max_tokens":
            raise LLMResponseFormatError(
                "Anthropic response was truncated (max_tokens). Reduce batch size.",
            )

        try:
            parsed = LLMResponse.model_validate(tool_input)
        except Exception as exc:
            raise LLMResponseFormatError(
                "Anthropic tool input did not match the schema.",
                details={"error": str(exc).splitlines()[:6]},
            ) from exc

        input_tokens, output_tokens = TokenMeter.anthropic(body.get("usage"))
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
