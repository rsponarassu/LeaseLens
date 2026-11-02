"""Version 1 router: one place that decides what the API exposes."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import (
    analyze,
    annotation,
    health,
    parse,
    rules,
    samples,
    sessions,
)

api_router = APIRouter()

# Order matters only for the generated docs: the demo path first, then the live
# pipeline, then the plumbing a client reaches for afterwards.
api_router.include_router(health.router)
api_router.include_router(samples.router)
api_router.include_router(analyze.router)
api_router.include_router(parse.router)
api_router.include_router(annotation.router)
api_router.include_router(sessions.router)
api_router.include_router(rules.router)

__all__ = ["api_router"]
