from __future__ import annotations

import uuid

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from upload_api.main import app


def test_reference_sources_endpoint_returns_kb_manifest_sources() -> None:
    client = TestClient(app)
    resp = client.get("/v1/reference-sources")
    assert resp.status_code == 200
    payload = resp.json()
    assert isinstance(payload, list)
    assert len(payload) == 6
    assert {"source_id", "title", "authority", "kind", "url"}.issubset(payload[0].keys())


def test_review_setup_rejects_empty_selection_before_db_lookup() -> None:
    client = TestClient(app)
    resp = client.post(
        "/v1/review-setup",
        json={
            "document_id": str(uuid.uuid4()),
            "selected_source_ids": [],
        },
    )
    assert resp.status_code == 400
    assert "At least one reference source" in resp.json()["detail"]


def test_upload_requires_project_id_form_field() -> None:
    client = TestClient(app)
    resp = client.post(
        "/v1/uploads",
        files={"file": ("sample.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert resp.status_code == 422


def test_checklist_draft_rejects_empty_selection_before_db_lookup() -> None:
    client = TestClient(app)
    resp = client.post(
        "/v1/checklist-drafts",
        json={
            "document_id": str(uuid.uuid4()),
            "selected_source_ids": [],
            "user_instruction": "Focus on subprocessors.",
        },
    )
    assert resp.status_code == 400
    assert "At least one reference source" in resp.json()["detail"]
