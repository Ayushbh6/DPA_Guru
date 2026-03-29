from __future__ import annotations

import uuid

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from upload_api.auth import SESSION_COOKIE_NAME, AuthenticatedActor
from upload_api.main import app, auth_manager


def _login(client: TestClient) -> None:
    client.cookies.set(
        SESSION_COOKIE_NAME,
        auth_manager.issue_session_token(AuthenticatedActor(username="local-dev")),
    )


def test_auth_me_requires_login() -> None:
    client = TestClient(app)
    resp = client.get("/v1/auth/me")
    assert resp.status_code == 401


def test_reference_sources_endpoint_returns_kb_manifest_sources() -> None:
    client = TestClient(app)
    _login(client)
    resp = client.get("/v1/reference-sources")
    assert resp.status_code == 200
    payload = resp.json()
    assert isinstance(payload, list)
    assert len(payload) == 6
    assert {"source_id", "title", "authority", "kind", "url"}.issubset(payload[0].keys())


def test_review_setup_rejects_empty_selection_before_db_lookup() -> None:
    client = TestClient(app)
    _login(client)
    resp = client.post(
        "/v1/review-setup",
        json={
            "document_id": str(uuid.uuid4()),
            "selected_source_ids": [],
        },
        headers={"origin": "http://localhost:3000"},
    )
    assert resp.status_code == 400
    assert "At least one reference source" in resp.json()["detail"]


def test_upload_requires_project_id_form_field() -> None:
    client = TestClient(app)
    _login(client)
    resp = client.post(
        "/v1/uploads",
        files={"file": ("sample.pdf", b"%PDF-1.4", "application/pdf")},
        headers={"origin": "http://localhost:3000"},
    )
    assert resp.status_code == 422


def test_checklist_draft_rejects_empty_selection_before_db_lookup() -> None:
    client = TestClient(app)
    _login(client)
    resp = client.post(
        "/v1/checklist-drafts",
        json={
            "document_id": str(uuid.uuid4()),
            "selected_source_ids": [],
            "user_instruction": "Focus on subprocessors.",
        },
        headers={"origin": "http://localhost:3000"},
    )
    assert resp.status_code == 400
    assert "At least one reference source" in resp.json()["detail"]
