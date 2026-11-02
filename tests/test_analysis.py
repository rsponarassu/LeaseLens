"""The live pipeline over HTTP: upload, score, annotate, forget."""

from __future__ import annotations

import fitz


def analyze(client, data: bytes, name: str = "lease.pdf", **params):
    return client.post(
        "/api/v1/analyze",
        files={"file": (name, data, "application/pdf")},
        params=params,
    )


def page_count(data: bytes) -> int:
    with fitz.open(stream=data, filetype="pdf") as document:
        return document.page_count


def test_analyze_returns_a_scored_report(client, high_risk_pdf):
    response = analyze(client, high_risk_pdf)

    assert response.status_code == 200, response.text
    report = response.json()
    assert report["risk"]["overall_score"] >= 80
    assert report["risk"]["risk_level"] == "critical"
    assert report["engine"]["analysis_mode"] == "offline_heuristic"
    assert report["page_count"] >= 2
    assert report["session_id"]
    assert report["annotated_pdf_url"].endswith(report["session_id"])


def test_findings_are_ordered_worst_first(client, high_risk_pdf):
    findings = analyze(client, high_risk_pdf).json()["findings"]

    assert findings
    assert findings[0]["status"] == "violation"
    # violations, then compliant checks, then clauses no benchmark applies to
    rank = {"violation": 0, "compliant": 1, "not_applicable": 2}
    groups = [rank[finding["status"]] for finding in findings]
    assert groups == sorted(groups)


def test_deposit_breach_cites_the_statute(client, high_risk_pdf):
    report = analyze(client, high_risk_pdf).json()
    deposit = [
        finding
        for finding in report["findings"]
        if finding["category"] == "deposit" and finding["violations"]
    ]

    assert deposit, "the high-deposit sample must flag its deposit clause"
    worst = max(deposit[0]["violations"], key=lambda violation: violation["penalty_points"])
    assert worst["observed_value"] > worst["threshold"]
    assert any("Security deposit" in ref["heading"] for ref in deposit[0]["statute_references"])


def test_analysis_is_deterministic(client, high_risk_pdf):
    first = analyze(client, high_risk_pdf).json()
    second = analyze(client, high_risk_pdf).json()

    assert first["session_id"] != second["session_id"]
    assert first["risk"]["overall_score"] == second["risk"]["overall_score"]
    assert [f["clause_id"] for f in first["findings"]] == [f["clause_id"] for f in second["findings"]]


def test_a_clean_lease_scores_far_lower(client, high_risk_pdf, friendly_pdf):
    risky = analyze(client, high_risk_pdf).json()["risk"]
    friendly = analyze(client, friendly_pdf).json()["risk"]

    assert friendly["overall_score"] < risky["overall_score"]
    assert friendly["risk_level"] in {"low", "moderate"}
    assert friendly["violation_count"] < risky["violation_count"]


def test_session_can_be_re_fetched_and_listed(client, high_risk_pdf):
    session_id = analyze(client, high_risk_pdf).json()["session_id"]

    replayed = client.get(f"/api/v1/sessions/{session_id}")
    assert replayed.status_code == 200
    assert replayed.json()["session_id"] == session_id
    assert replayed.json()["cache_hit"] is True

    listing = client.get("/api/v1/sessions").json()
    assert session_id in {entry["session_id"] for entry in listing}


def test_annotated_pdf_round_trip(client, high_risk_pdf):
    session_id = analyze(client, high_risk_pdf).json()["session_id"]

    rendered = client.post("/api/v1/annotate-pdf", json={"session_id": session_id})
    assert rendered.status_code == 200
    assert rendered.content.startswith(b"%PDF")
    assert page_count(rendered.content) == page_count(high_risk_pdf) + 1

    downloaded = client.get(f"/api/v1/download-annotated/{session_id}")
    assert downloaded.status_code == 200
    assert downloaded.content == rendered.content, "the rendered file is cached per session"
    assert "attachment" in downloaded.headers["content-disposition"]
    assert downloaded.headers["cache-control"] == "private, no-store"


def test_a_session_can_be_forgotten(client, high_risk_pdf):
    session_id = analyze(client, high_risk_pdf).json()["session_id"]

    assert client.delete(f"/api/v1/sessions/{session_id}").status_code == 204
    assert client.get(f"/api/v1/sessions/{session_id}").status_code == 404
    assert client.get(f"/api/v1/download-annotated/{session_id}").status_code == 404


def test_parse_returns_coordinates_on_request(client, high_risk_pdf):
    response = client.post(
        "/api/v1/parse-lease",
        files={"file": ("lease.pdf", high_risk_pdf, "application/pdf")},
        params={"include_coordinates": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["clause_count"] >= 10
    assert body["strategy"] == "numbered"
    assert body["clauses"][0]["page_number"] == 1
    assert body["clauses"][0]["bbox"] is not None
    assert body["coordinates"][0]["words"]
    assert body["extraction"]["ocr_used"] is False
