"""LLM client factory.

Resolution order is driven by configuration so that the same code deploys to a
demos environment with no keys (``offline``) and to production with Gemini or
Claude without changes.
"""

from __future__ import annotations

import logging

from app.core.config import Settings, get_settings
from app.core.errors import LLMNotConfiguredError
from app.llm.anthropic import AnthropicClient
from app.llm.base import LLMClient
from app.llm.gemini import GeminiClient

logger = logging.getLogger(__name__)


def build_llm_client(settings: Settings | None = None) -> LLMClient | None:
    """Return a configured client, or ``None`` when running offline."""
    cfg = settings or get_settings()
    provider = cfg.resolved_llm_provider

    if provider == "gemini":
        if not cfg.gemini_api_key:
            raise LLMNotConfiguredError("LLM_PROVIDER=gemini but GEMINI_API_KEY is empty.")
        return GeminiClient(cfg)

    if provider == "anthropic":
        if not cfg.anthropic_api_key:
            raise LLMNotConfiguredError(
                "LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is empty."
            )
        return AnthropicClient(cfg)

    logger.info("no LLM provider configured; using deterministic heuristic extraction")
    return None
