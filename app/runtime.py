"""Process-wide object graph.

Everything stateful is created once at startup and hung off ``app.state.runtime``.
Dependencies read it from there, which keeps the request handlers free of module
level singletons and lets tests build an app with different settings.

Only three things live beyond a request:

* the rule base (immutable, cached for the process),
* the session cache (TTL-bounded, in memory, never on disk),
* the three demo leases (rendered once from text).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.cache.sessions import SessionCache
from app.core.config import Settings, get_settings
from app.data.sample_repository import SampleLeaseRepository
from app.services.pipeline import AnalysisPipeline


@dataclass
class Runtime:
    """The services an API request may depend on."""

    settings: Settings
    pipeline: AnalysisPipeline
    sessions: SessionCache
    samples: SampleLeaseRepository
    started_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))

    @property
    def uptime_seconds(self) -> float:
        return (datetime.now(tz=timezone.utc) - self.started_at).total_seconds()


def build_runtime(settings: Settings | None = None) -> Runtime:
    """Wire the service graph. Cheap: no I/O beyond reading the YAML rule base."""
    cfg = settings or get_settings()
    pipeline = AnalysisPipeline(cfg)
    sessions = SessionCache(cfg, annotator=pipeline.annotator)
    samples = SampleLeaseRepository(cfg, pipeline=pipeline, sessions=sessions)
    return Runtime(settings=cfg, pipeline=pipeline, sessions=sessions, samples=samples)


async def shutdown_runtime(runtime: Runtime) -> None:
    """Release the HTTP client and drop every cached document."""
    await runtime.pipeline.aclose()
    runtime.sessions.clear()
