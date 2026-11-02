"""Demo leases: the guaranteed-working path."""

from __future__ import annotations

import fitz

EXPECTED_IDS = ["sample-high-deposit", "sample-moderate-rent", "sample-tenant-friendly"]


def page_count(data: bytes) -> int:
    with fitz.open(stream=data, filetype="pdf") as document:
        return document.page_count


def test_lists_three_samples_in_demo_order(client):
    response = client.get("/api/v1/sample-leases")

    assert response.status_code == 200
    body = response.json()
    assert [sample["sample_id"] for sample in body] == EXPECTED_IDS
    assert [sample["analysis"]["risk"]["risk_level"] for sample in body] == [
        "critical",
        "elevated",
        "low",
    ]


def test_every_sample_carries_a_complete_report(client):
    for sample in client.get("/api/v1/sample-leases").json():
        report = sample["analysis"]
        assert report["risk"]["overall_score"] > 0
        assert report["findings"], sample["sample_id"]
        assert report["engine"]["analysis_mode"] == "offline_heuristic"
        assert report["session_id"] == sample["sample_id"]
        assert report["cache_hit"] is True
        assert report["disclaimer"]


def test_flagged_sample_has_bilingual_fix_it_kits(client):
    body = client.get("/api/v1/sample-leases/sample-high-deposit").json()
    violations = [f for f in body["analysis"]["findings"] if f["status"] == "violation"]

    assert len(violations) >= 5
    for finding in violations:
        fix = finding["fix"]
        assert fix is not None
        assert fix["explanation_en"] and fix["explanation_ta"]
        assert any("\u0b80" <= char <= "\u0bff" for char in fix["explanation_ta"])
        assert fix["counter_clause"] and fix["email_body"]
        assert finding["statute_references"]


def test_single_sample_matches_the_listing(client):
    listed = client.get("/api/v1/sample-leases").json()[0]
    single = client.get("/api/v1/sample-leases/sample-high-deposit").json()
    report = client.get("/api/v1/sample-leases/sample-high-deposit/analysis").json()

    assert single["analysis"]["risk"] == listed["analysis"]["risk"]
    assert report["risk"]["overall_score"] == listed["analysis"]["risk"]["overall_score"]


def test_sample_pdf_downloads(client):
    response = client.get("/api/v1/sample-leases/sample-tenant-friendly/pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert "inline" in response.headers["content-disposition"]


def test_sample_annotated_pdf_adds_a_cover_page(client):
    source = client.get("/api/v1/sample-leases/sample-high-deposit/pdf").content
    annotated = client.get("/api/v1/sample-leases/sample-high-deposit/annotated-pdf")

    assert annotated.status_code == 200
    assert annotated.content.startswith(b"%PDF")
    assert page_count(annotated.content) == page_count(source) + 1
    assert len(annotated.content) > len(source)


def test_annotating_a_sample_through_the_post_endpoint(client):
    response = client.post(
        "/api/v1/annotate-pdf",
        json={"sample_id": "sample-tenant-friendly", "include_summary_page": False},
    )

    source = client.get("/api/v1/sample-leases/sample-tenant-friendly/pdf").content
    assert response.status_code == 200
    assert page_count(response.content) == page_count(source)


def test_unknown_sample_returns_the_error_envelope(client):
    response = client.get("/api/v1/sample-leases/nope")

    assert response.status_code == 404
    body = response.json()["error"]
    assert body["code"] == "sample_not_found"
    assert body["details"]["available"] == EXPECTED_IDS
    assert body["request_id"]
