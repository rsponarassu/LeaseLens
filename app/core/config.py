"""Central application configuration.

All tunables live here so that services never read ``os.environ`` directly.
Values are loaded from the environment (and an optional ``.env`` file) using
pydantic-settings, which means every setting is validated and typed at boot
time instead of failing at request time.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
APP_DIR: Path = PROJECT_ROOT / "app"

LLMProviderSetting = Literal["auto", "gemini", "anthropic", "offline"]
LLMProviderResolved = Literal["gemini", "anthropic", "offline"]

DISCLAIMER = (
    "LeaseLens provides automated, non-binding informational analysis of tenancy "
    "clauses against the Tamil Nadu Regulation of Rights and Responsibilities of "
    "Landlords and Tenants Act, 2017 (Act 42 of 2017). It is not legal advice and "
    "does not create an advocate-client relationship. Statutory references are "
    "indicative; always confirm the current text (including amendments and rules) "
    "with a qualified advocate before acting."
)


class Settings(BaseSettings):
    """Typed, validated runtime configuration."""

    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Application ------------------------------------------------------
    app_name: str = "LeaseLens API"
    app_version: str = "1.0.0"
    environment: Literal["local", "staging", "production"] = "local"
    debug: bool = False
    api_prefix: str = "/api/v1"
    allowed_origins: list[str] = Field(default_factory=lambda: ["*"])
    log_level: str = "INFO"
    log_raw_text: bool = False

    # ---- Upload limits ----------------------------------------------------
    max_upload_mb: int = Field(default=15, ge=1, le=200)
    max_pages: int = Field(default=100, ge=1, le=2000)

    # ---- OCR --------------------------------------------------------------
    ocr_enabled: bool = True
    ocr_min_chars_per_page: int = Field(default=60, ge=1, le=5000)
    ocr_dpi: int = Field(default=300, ge=72, le=600)
    ocr_languages: str = "eng"
    tesseract_cmd: str | None = None

    # ---- LLM --------------------------------------------------------------
    llm_provider: LLMProviderSetting = "auto"
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-2.5-flash"
    gemini_api_base: str = "https://generativelanguage.googleapis.com/v1beta"
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-sonnet-4-5"
    anthropic_api_base: str = "https://api.anthropic.com/v1"
    anthropic_version: str = "2023-06-01"
    llm_timeout_seconds: float = Field(default=60.0, gt=0, le=600)
    llm_connect_timeout: float = Field(default=10.0, gt=0, le=120)
    llm_max_retries: int = Field(default=2, ge=0, le=6)
    llm_max_concurrency: int = Field(default=3, ge=1, le=32)
    llm_batch_size: int = Field(default=8, ge=1, le=50)
    llm_max_output_tokens: int = Field(default=8192, ge=512, le=65536)
    llm_polish_fixes: bool = False

    # ---- Caching ----------------------------------------------------------
    cache_ttl_seconds: int = Field(default=3600, ge=0)
    cache_max_entries: int = Field(default=64, ge=1, le=10000)
    cache_max_bytes_mb: int = Field(default=512, ge=16, le=8192)
    annotation_ttl_seconds: int = Field(default=3600, ge=0)
    sample_warm_on_startup: bool = True

    # ---- Paths ------------------------------------------------------------
    rules_file: Path = APP_DIR / "rules" / "rules.yaml"
    samples_dir: Path = APP_DIR / "data" / "samples"
    frontend_dist: Path = PROJECT_ROOT / "frontend" / "dist"
    serve_frontend: bool = True

    # ---- Copy -------------------------------------------------------------
    disclaimer: str = DISCLAIMER

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Accept ``a,b`` as well as a JSON array for CORS origins."""
        if isinstance(value, str) and not value.strip().startswith("["):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("tesseract_cmd")
    @classmethod
    def _empty_to_none(cls, value: str | None) -> str | None:
        return value or None

    @model_validator(mode="after")
    def _normalise_paths(self) -> Settings:
        for attr in ("rules_file", "samples_dir", "frontend_dist"):
            path: Path = getattr(self, attr)
            if not path.is_absolute():
                object.__setattr__(self, attr, (PROJECT_ROOT / path).resolve())
        return self

    # ---- Derived values ---------------------------------------------------
    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def cache_max_bytes(self) -> int:
        """Heap budget for cached sessions (source + annotated PDFs)."""
        return self.cache_max_bytes_mb * 1024 * 1024

    @property
    def resolved_llm_provider(self) -> LLMProviderResolved:
        """Return the provider actually in use (``auto`` is resolved to one)."""
        if self.llm_provider == "offline":
            return "offline"
        if self.llm_provider == "gemini":
            return "gemini"
        if self.llm_provider == "anthropic":
            return "anthropic"
        if self.gemini_api_key:
            return "gemini"
        if self.anthropic_api_key:
            return "anthropic"
        return "offline"

    @property
    def llm_enabled(self) -> bool:
        return self.resolved_llm_provider != "offline"

    @property
    def frontend_built(self) -> bool:
        """True when ``frontend/dist`` holds a production build to serve."""
        return (self.frontend_dist / "index.html").is_file()

    def public_dict(self) -> dict[str, object]:
        """Non-secret configuration safe to expose through diagnostics."""
        return {
            "app_name": self.app_name,
            "app_version": self.app_version,
            "environment": self.environment,
            "llm_provider_setting": self.llm_provider,
            "llm_provider_resolved": self.resolved_llm_provider,
            "llm_model": self._active_model(),
            "ocr_enabled": self.ocr_enabled,
            "max_upload_mb": self.max_upload_mb,
            "max_pages": self.max_pages,
            "cache_ttl_seconds": self.cache_ttl_seconds,
            "cache_max_entries": self.cache_max_entries,
            "cache_max_bytes_mb": self.cache_max_bytes_mb,
            "serve_frontend": self.serve_frontend,
            "frontend_dist": str(self.frontend_dist),
        }

    def _active_model(self) -> str | None:
        provider = self.resolved_llm_provider
        if provider == "gemini":
            return self.gemini_model
        if provider == "anthropic":
            return self.anthropic_model
        return None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()


def reset_settings_cache() -> None:
    """Clear the settings cache (used by tests that patch the environment)."""
    get_settings.cache_clear()
