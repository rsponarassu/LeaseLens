"""Shared fixtures.

One application instance is created for the whole session: the demo leases are
prepared in the lifespan, and re-preparing them per test would triple the runtime
for no extra coverage. Tests that mutate state (deleting a session) create their
own session, so they cannot disturb the demo data.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.data.sample_leases import HIGH_RISK, TENANT_FRIENDLY, SampleLeaseSpec
from app.main import create_app
from app.services.sample_pdf import build_lease_pdf


@pytest.fixture(scope="session")
def settings() -> Settings:
    """Deterministic configuration: no network, short TTL, quiet logs."""
    return Settings(
        llm_provider="offline",
        environment="local",
        log_level="WARNING",
        cache_ttl_seconds=900,
        cache_max_entries=32,
        sample_warm_on_startup=True,
    )


@pytest.fixture(scope="session")
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture(scope="session")
def client(app: FastAPI):
    with TestClient(app) as test_client:
        yield test_client


def render_lease(spec: SampleLeaseSpec) -> bytes:
    """Render a sample specification to a real PDF, in memory."""
    return build_lease_pdf(
        title=spec.title,
        subtitle=spec.property_description,
        parties=list(spec.parties),
        preamble=list(spec.preamble),
        clauses=list(spec.clauses),
        closing="Signed by the Landlord and the Tenant in the presence of the witnesses.",
        header=f"{spec.sample_id} | test render",
    )


@pytest.fixture(scope="session")
def high_risk_pdf() -> bytes:
    return render_lease(HIGH_RISK)


@pytest.fixture(scope="session")
def friendly_pdf() -> bytes:
    return render_lease(TENANT_FRIENDLY)
