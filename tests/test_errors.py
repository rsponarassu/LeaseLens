"""Upload rejection, validation and the shape of every error body."""

from __future__ import annotations

import pytest


def error_body(response) -> dict:
    body = response.json()
    assert set(body) == {"error"}
    assert {"code", "message", "request_id"} <= set(body["error"])
    return body["error"]


def test_rejects_a_declared_non_pdf(client):
    response = client.post(
        "/api/v1/analyze",
        files={"file": ("notes.txt", b"just some notes", "text/plain")},
    )

    assert response.status_code == 415
    assert error_body(response)["code"] == "unsupported_media_type"


def test_rejects_a_file_without_the_pdf_signature(client):
    response = client.post(
        "/api/v1/analyze",
        files={"file": ("lease.pdf", b"MZ\x90\x00 not a pdf at all", "application/pdf")},
    )

    assert response.status_code == 415
    assert error_body(response)["code"] == "unsupported_media_type"


def test_rejects_an_empty_upload(client):
    response = client.post(
        "/api/v1/analyze",
        files={"file": ("lease.pdf", b"", "application/pdf")},
    )

    assert response.status_code == 400
    assert error_body(response)["code"] == "empty_file"


def test_rejects_a_corrupt_pdf(client):
    payload = b"%PDF-1.7\n" + b"\x00" * 512 + b"\ntrailer\n%%EOF"
    response = client.post(
        "/api/v1/analyze",
        files={"file": ("broken.pdf", payload, "application/pdf")},
    )

    assert response.status_code == 422
    assert error_body(response)["code"] in {"corrupt_pdf", "text_extraction_failed"}


def test_rejects_a_password_protected_pdf(client):
    import fitz

    document = fitz.open()
    document.new_page().insert_text((72, 72), "Rental agreement")
    payload = document.tobytes(
        encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="owner"
    )
    document.close()

    response = client.post(
        "/api/v1/analyze",
        files={"file": ("locked.pdf", payload, "application/pdf")},
    )

    assert response.status_code == 422
    assert error_body(response)["code"] == "password_protected_pdf"


def test_missing_file_field_is_a_validation_error(client):
    response = client.post("/api/v1/analyze")

    assert response.status_code == 422
    body = error_body(response)
    assert body["code"] == "validation_error"
    assert body["details"]["errors"]


def test_annotate_requires_exactly_one_target(client):
    neither = client.post("/api/v1/annotate-pdf", json={})
    both = client.post(
        "/api/v1/annotate-pdf",
        json={"session_id": "abc", "sample_id": "sample-high-deposit"},
    )

    assert neither.status_code == 422
    assert both.status_code == 422
    assert error_body(neither)["code"] == "validation_error"


def test_annotate_rejects_unknown_fields(client):
    response = client.post("/api/v1/annotate-pdf", json={"sample_id": "x", "colour": "red"})

    assert response.status_code == 422


def test_unknown_session_is_404_and_expired_session_is_410(client, app, high_risk_pdf):
    assert client.get("/api/v1/sessions/does-not-exist").status_code == 404
    assert client.get("/api/v1/download-annotated/does-not-exist").status_code == 404

    runtime = app.state.runtime
    session = client.post(
        "/api/v1/analyze", files={"file": ("lease.pdf", high_risk_pdf, "application/pdf")}
    ).json()
    runtime.sessions._cache.delete(session["session_id"])  # simulate TTL expiry

    expired = client.get(f"/api/v1/sessions/{session['session_id']}")
    assert expired.status_code == 410
    assert error_body(expired)["code"] == "session_expired"


def test_unknown_rule_id(client):
    response = client.get("/api/v1/rules/XXX-999")

    assert response.status_code == 404
    assert error_body(response)["code"] == "rule_not_found"


def test_unknown_route_uses_the_same_envelope(client):
    response = client.get("/api/v1/nope")

    assert response.status_code == 404
    assert error_body(response)["code"] == "not_found"


def test_request_id_is_echoed_and_generated(client):
    supplied = client.get("/api/v1/health", headers={"X-Request-ID": "demo-123"})
    generated = client.get("/api/v1/health")

    assert supplied.headers["X-Request-ID"] == "demo-123"
    assert len(generated.headers["X-Request-ID"]) == 32


@pytest.mark.parametrize("path", ["/api/v1/health", "/api/v1/rules", "/api/v1/sample-leases"])
def test_security_headers_are_set(client, path):
    response = client.get(path)

    assert response.headers["x-content-type-options"] == "nosniff"
