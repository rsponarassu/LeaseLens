"""ASGI entry point.

``uvicorn app.main:app --reload`` is all that is needed to run LeaseLens.

The app is built by a factory so tests can inject their own :class:`Settings`
(offline LLM, short cache TTL) without touching the environment. Everything
stateful is created inside the lifespan and hung off ``app.state.runtime``; no
module-level singletons hold a document, which is what makes "privacy by design"
verifiable rather than aspirational.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import LeaseLensError
from app.core.logging import configure_logging, get_request_id, set_request_id
from app.runtime import Runtime, build_runtime, shutdown_runtime

logger = logging.getLogger("leaselens.main")

REQUEST_ID_HEADER = "X-Request-ID"

DESCRIPTION = """
**LeaseLens** analyses a rental agreement against the Tamil Nadu Regulation of
Rights and Responsibilities of Landlords and Tenants Act, 2017 (Act 42 of 2017).

Every analysis follows the same five stages and the same division of labour:

| stage | component | decides |
| --- | --- | --- |
| extraction | `pdf_parser` (PyMuPDF, Tesseract fallback) | text + coordinates |
| segmentation | `clause_splitter` | clause boundaries |
| classification | `ai_classifier` (Gemini / Claude / offline) | category + typed entities |
| **verdict** | `rule_engine` + `rules.yaml` | violations, severity, **score** |
| remediation | `fix_generator` | explanation (EN/TA), counter-clause, email |

The model is never asked for a legal conclusion. It returns labels and numbers;
plain Python compares those numbers with the thresholds in `rules.yaml` and cites
the section. That is why the same PDF produces the same score twice in a row, and
why `GET /rules` can show exactly which benchmark fired.

**Try it without an upload:** `GET /api/v1/sample-leases` returns three fully
analysed demo leases, including one that is a critical risk and one that is
almost clean. Their PDFs can be downloaded and annotated like any upload.

**Privacy:** uploads are held in memory for one hour, never written to disk,
and returned with `Cache-Control: private, no-store`. `DELETE
/api/v1/sessions/{id}` drops one immediately.
"""

TAGS_METADATA: list[dict[str, Any]] = [
    {
        "name": "health",
        "description": "Liveness, rule-base status and demo self-check.",
    },
    {
        "name": "samples",
        "description": (
            "Three pre-analysed demo leases. No upload, no API key, no network call - "
            "the path that always works during a live review."
        ),
    },
    {
        "name": "analysis",
        "description": "The full pipeline: upload a lease, get a scored, explained report.",
    },
    {
        "name": "documents",
        "description": "Extraction and segmentation only, for debugging and integration.",
    },
    {
        "name": "annotation",
        "description": "Colour-coded highlights drawn onto the original PDF.",
    },
    {
        "name": "sessions",
        "description": "List, re-fetch or forget an analysis held in memory.",
    },
    {
        "name": "rules",
        "description": "The statutory benchmarks and the scoring model behind every verdict.",
    },
]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Build the runtime, warm the demo leases, then tear everything down."""
    settings: Settings = app.state.settings
    runtime = build_runtime(settings)
    app.state.runtime = runtime

    if settings.sample_warm_on_startup:
        await _warm_samples(runtime)

    logger.info(
        "LeaseLens ready: env=%s rules=%s llm=%s ttl=%ss",
        settings.environment,
        len(runtime.pipeline.rule_base.rules),
        settings.resolved_llm_provider,
        settings.cache_ttl_seconds,
    )
    try:
        yield
    finally:
        await shutdown_runtime(runtime)
        logger.info("LeaseLens stopped; every cached document was dropped")


async def _warm_samples(runtime: Runtime) -> None:
    """Pre-analyse the demo leases so the first demo request is instant."""
    try:
        await runtime.samples.ensure_ready()
    except Exception:  # noqa: BLE001 - a warm-up failure must not stop the server
        # The demo endpoints call ``ensure_ready`` again, so a transient problem
        # (or a missing Tesseract) degrades the demo instead of the deployment.
        logger.warning(
            "demo leases could not be prepared at startup; they will be retried "
            "on the first demo request",
            exc_info=True,
        )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the ASGI application."""
    cfg = settings or get_settings()
    configure_logging(cfg.log_level, json_logs=cfg.environment == "production")

    app = FastAPI(
        title=cfg.app_name,
        version=cfg.app_version,
        summary="Tenancy-clause analysis for the Tamil Nadu Rent Act, 2017.",
        description=DESCRIPTION,
        openapi_tags=TAGS_METADATA,
        contact={"name": "LeaseLens", "url": "https://example.com/leaselens"},
        license_info={"name": "Proprietary"},
        lifespan=lifespan,
    )
    app.state.settings = cfg

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=[REQUEST_ID_HEADER, "Content-Disposition"],
        max_age=600,
    )

    _install_middleware(app)
    _install_exception_handlers(app)

    app.include_router(api_router, prefix=cfg.api_prefix)

    # Anything under the API prefix that no router claimed must still answer with
    # the JSON envelope, so this has to be registered before the UI mount owns
    # ``/`` and would swallow the path as a missing static file.
    _install_api_fallback(app, cfg)

    if not _mount_frontend(app, cfg):
        _install_json_index(app, cfg)

    return app


def _install_json_index(app: FastAPI, cfg: Settings) -> None:
    """Machine-readable banner for deployments that serve the API alone."""

    @app.get("/", include_in_schema=False)
    async def index() -> dict[str, str]:
        return {
            "name": cfg.app_name,
            "version": cfg.app_version,
            "docs": "/docs",
            "openapi": "/openapi.json",
            "health": f"{cfg.api_prefix}/health",
            "samples": f"{cfg.api_prefix}/sample-leases",
        }


def _install_api_fallback(app: FastAPI, cfg: Settings) -> None:
    @app.api_route(
        f"{cfg.api_prefix}/{{unmatched:path}}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        include_in_schema=False,
    )
    async def api_fallback(unmatched: str) -> None:
        raise StarletteHTTPException(
            status_code=404,
            detail=f"No API endpoint at {cfg.api_prefix}/{unmatched}",
        )


def _mount_frontend(app: FastAPI, cfg: Settings) -> bool:
    """Serve ``frontend/dist`` when a production build exists.

    The UI uses hash routing (``#/app/review``), so every path the browser asks
    for is a real file: ``/``, ``/brand/…``, ``/assets/…``. That means no
    catch-all rewrite is needed and :class:`StaticFiles` is enough - the API
    keeps its own prefix, ``/docs`` and ``/openapi.json`` because they were
    registered first.
    """
    if not (cfg.serve_frontend and cfg.frontend_built):
        return False

    assets = cfg.frontend_dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")
    app.mount("/", StaticFiles(directory=cfg.frontend_dist, html=True), name="frontend")
    logger.info("serving the built frontend from %s", cfg.frontend_dist)
    return True


def _apply_cache_headers(path: str, response: Any) -> None:
    """Give the static bundle a cache policy that survives a redeploy.

    Vite writes a content hash into every filename under ``/assets``, so those
    can be cached forever. ``index.html`` is the one file that must not be: it
    is what points at the current hashes, and a stale copy pairs an old shell
    with deleted assets - the classic white screen after a deploy. API responses
    set their own headers (``private, no-store`` for artefacts), so this only
    fills in what is missing.
    """
    if path == "/" or path.endswith(".html"):
        # Whatever the mount or a proxy in front decided: the shell is always
        # revalidated, because it is the file that names the current hashes.
        response.headers["Cache-Control"] = "no-cache"
    elif response.headers.get("Cache-Control"):
        return
    elif path.startswith("/assets/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif path.startswith("/brand/") or path == "/favicon.svg":
        response.headers["Cache-Control"] = "public, max-age=86400"


def _install_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_context(request: Request, call_next: Any) -> Any:
        """Attach a request id, then log one line per request."""
        incoming = request.headers.get(REQUEST_ID_HEADER)
        request_id = (incoming or "").strip()[:64] or uuid.uuid4().hex
        set_request_id(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # The exception handlers below build the body; this only records that
            # the failure happened inside the request span.
            logger.exception(
                "%s %s failed after %.1fms",
                request.method,
                request.url.path,
                (time.perf_counter() - started) * 1000,
            )
            raise

        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        _apply_cache_headers(request.url.path, response)
        if request.url.path != f"{app.state.settings.api_prefix}/health":
            logger.info(
                "%s %s -> %s in %.1fms",
                request.method,
                request.url.path,
                response.status_code,
                elapsed_ms,
            )
        return response


def _install_exception_handlers(app: FastAPI) -> None:
    """One JSON envelope for every failure mode."""

    @app.exception_handler(LeaseLensError)
    async def handle_domain_error(request: Request, exc: LeaseLensError) -> JSONResponse:
        payload = exc.to_payload(get_request_id())
        if exc.status_code >= 500:
            logger.error(
                "domain error: code=%s status=%s", exc.code, exc.status_code, exc_info=exc
            )
        else:
            logger.info("rejected: code=%s status=%s", exc.code, exc.status_code)
        return JSONResponse(
            status_code=exc.status_code,
            content=jsonable_encoder(payload),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "The request body or parameters are invalid.",
                    "details": {"errors": jsonable_encoder(exc.errors())},
                    "request_id": get_request_id(),
                }
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": _HTTP_ERROR_CODES.get(exc.status_code, "http_error"),
                    "message": str(exc.detail),
                    "request_id": get_request_id(),
                }
            },
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "An unexpected error occurred. The request id can be used to trace it.",
                    "request_id": get_request_id(),
                }
            },
        )


_HTTP_ERROR_CODES: dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "file_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
    429: "too_many_requests",
    503: "service_unavailable",
    504: "gateway_timeout",
}


app = create_app()
