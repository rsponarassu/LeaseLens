"""Health and demo self-check."""

from __future__ import annotations


def test_health_reports_every_component(client):
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ok", "limited"}
    assert body["statute"].startswith("Tamil Nadu Regulation of Rights")
    assert {"rules", "samples", "cache", "llm", "ocr", "extraction"} <= set(body["components"])


def test_rule_base_is_loaded_with_benchmarks(client):
    rules = client.get("/api/v1/health").json()["components"]["rules"]["detail"]

    assert rules["rule_count"] >= 20
    assert rules["act_number"] == "Act 42 of 2017"
    assert "deposit" in rules["categories"]


def test_demo_leases_self_check_passes(client):
    samples = client.get("/api/v1/health").json()["components"]["samples"]

    assert samples["status"] == "ok", samples["detail"].get("failed")
    diagnostics = samples["detail"]["diagnostics"]
    assert len(diagnostics) == 3
    for entry in diagnostics:
        assert entry["ok"] is True, entry
        assert entry["actual_risk_level"] == entry["expected_risk_level"]
        assert entry["violation_count"] >= entry["expected_min_violations"]


def test_llm_is_reported_as_offline_in_tests(client):
    llm = client.get("/api/v1/health").json()["components"]["llm"]["detail"]

    assert llm["enabled"] is False
    assert llm["provider_resolved"] == "offline"


def test_uptime_and_version_are_present(client):
    body = client.get("/api/v1/health").json()

    assert body["version"] == "1.0.0"
    assert body["uptime_seconds"] >= 0
