from __future__ import annotations

import uuid
from pathlib import Path

from upload_api.config import Settings
from upload_api.events import JobEventBus
from upload_api.jobs import UploadPipelineService
from upload_api.storage import ArtifactStore


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url="postgresql+psycopg://postgres:postgres@localhost:5432/postgres",
        api_host="0.0.0.0",
        api_port=8001,
        max_upload_mb=50,
        document_storage_backend="local",
        upload_storage_dir=tmp_path / "uploads",
        parsed_storage_dir=tmp_path / "parsed",
        tokenizer_encoding="cl100k_base",
        openai_api_key="test-key",
        openai_embedding_model="text-embedding-3-small",
        gemini_api_key="test-key",
        gemini_checklist_model="gemini-3-flash-preview",
        gemini_review_model="gemini-3-flash-preview",
        mistral_api_key=None,
        mistral_ocr_model="mistral-ocr-latest",
        mistral_include_image_base64=False,
        store_parsed_pages_json=False,
        r2_account_id=None,
        r2_bucket=None,
        r2_access_key_id=None,
        r2_secret_access_key=None,
        r2_endpoint_url=None,
        dpa_chunk_size=800,
        dpa_chunk_overlap=300,
        default_dev_tenant_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        repo_root=tmp_path,
    )


def test_load_dpa_pages_falls_back_to_markdown_when_pages_json_missing(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    storage = ArtifactStore(
        primary_backend="local",
        upload_dir=settings.upload_storage_dir,
        parsed_dir=settings.parsed_storage_dir,
    )
    service = UploadPipelineService(
        settings=settings,
        session_factory=None,  # type: ignore[arg-type]
        storage=storage,
        event_bus=JobEventBus(),
    )

    artifact = storage.save_parsed_markdown(
        tenant_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        text=(
            "page_no: 1\n"
            "page_text:\n"
            "Controller instructions apply.\n"
            "page_images: []\n\n"
            "page_no: 2\n"
            "page_text:\n"
            "Security measures are documented.\n"
            "page_images: []\n"
        ),
    )

    pages = service._load_dpa_pages(artifact.object_uri, None)

    assert [page.page for page in pages] == [1, 2]
    assert pages[0].text == "Controller instructions apply."
    assert pages[1].text == "Security measures are documented."
