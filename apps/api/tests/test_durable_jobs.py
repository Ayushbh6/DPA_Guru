from __future__ import annotations

import asyncio
import os
import uuid
from datetime import timedelta
from pathlib import Path

from sqlalchemy import delete, select

from db.models import Document, DocumentParseJob, Project
from upload_api.db import build_session_factory
from upload_api.events import JobEventBus
from upload_api.jobs import PermanentJobError, UploadPipelineService, utcnow
from upload_api.storage import ArtifactStore
from upload_api.config import Settings


os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/postgres")


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=os.environ["DATABASE_URL"],
        api_host="0.0.0.0",
        api_port=8001,
        max_upload_mb=25,
        max_pdf_pages=200,
        document_storage_backend="local",
        upload_storage_dir=tmp_path / "uploads",
        parsed_storage_dir=tmp_path / "parsed",
        tokenizer_encoding="cl100k_base",
        openai_api_key="test-key",
        openai_embedding_model="text-embedding-3-small",
        gemini_api_key="test-key",
        gemini_checklist_model="gemini-3-flash-preview",
        gemini_review_model="gemini-3-flash-preview",
        mistral_api_key="test-key",
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
        alpha_users_json='[{"username":"local-dev","password":"local-dev"}]',
        alpha_bootstrap_owner_username="local-dev",
        session_secret="test-session-secret",
        session_cookie_secure=False,
        session_cookie_domain=None,
        app_allowed_origins=("http://localhost:3000",),
        alpha_max_projects_per_user=20,
        alpha_max_documents_per_user=8,
        alpha_max_check_runs_per_user=15,
        alpha_max_total_documents=50,
        alpha_max_total_active_storage_mb=5000,
        login_rate_limit_per_ip=20,
        login_rate_limit_per_username=10,
        login_rate_limit_window_seconds=300,
        upload_rate_limit_per_user=10,
        upload_rate_limit_per_ip=20,
        upload_rate_limit_window_seconds=600,
        checklist_rate_limit_per_user=1,
        checklist_rate_limit_window_seconds=60,
        analysis_rate_limit_per_user=1,
        analysis_rate_limit_window_seconds=60,
        worker_id="test-worker",
        worker_concurrency=2,
        worker_poll_interval_seconds=1,
        worker_lease_duration_seconds=90,
        worker_heartbeat_interval_seconds=15,
        worker_retry_backoff_first_seconds=30,
        worker_retry_backoff_second_seconds=120,
        deleted_project_retention_days=30,
        repo_root=tmp_path,
    )


def _build_service(tmp_path: Path) -> tuple[UploadPipelineService, callable]:
    settings = _settings(tmp_path)
    session_factory = build_session_factory(settings.database_url)
    service = UploadPipelineService(
        settings=settings,
        session_factory=session_factory,
        storage=ArtifactStore(
            primary_backend="local",
            upload_dir=settings.upload_storage_dir,
            parsed_dir=settings.parsed_storage_dir,
        ),
        event_bus=JobEventBus(),
    )
    return service, session_factory


def _seed_parse_job(service: UploadPipelineService, session_factory, *, status: str = "QUEUED", attempt_count: int = 0, lease_expired: bool = False) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    tenant_id = service.settings.default_dev_tenant_id
    project_id = uuid.uuid4()
    document_id = uuid.uuid4()
    job_id = uuid.uuid4()
    now = utcnow()

    with session_factory() as session:
        service._ensure_dev_tenant(session)
        session.add(
            Project(
                id=project_id,
                tenant_id=tenant_id,
                owner_username="local-dev",
                name=f"Project {project_id}",
                status="UPLOADING",
                created_at=now,
                updated_at=now,
                last_activity_at=now,
            )
        )
        session.flush()
        session.add(
            Document(
                id=document_id,
                tenant_id=tenant_id,
                project_id=project_id,
                filename="sample.pdf",
                mime_type="application/pdf",
                page_count=1,
                storage_uri="file:///tmp/source.pdf",
                uploaded_at=now,
                parse_status=status,
            )
        )
        session.flush()
        session.add(
            DocumentParseJob(
                id=job_id,
                tenant_id=tenant_id,
                project_id=project_id,
                document_id=document_id,
                status=status,
                stage="UPLOADING" if status == "QUEUED" else "VALIDATING",
                progress_pct=5,
                message="Queued.",
                file_type="pdf",
                created_at=now,
                updated_at=now,
                available_at=now - timedelta(seconds=1),
                attempt_count=attempt_count,
                claimed_by_worker="dead-worker" if status == "RUNNING" else None,
                claimed_at=now - timedelta(minutes=2) if status == "RUNNING" else None,
                heartbeat_at=now - timedelta(minutes=2) if status == "RUNNING" else None,
                lease_expires_at=now - timedelta(seconds=5) if lease_expired else (now + timedelta(seconds=60) if status == "RUNNING" else None),
            )
        )
        session.commit()
    return project_id, document_id, job_id


def _cleanup_parse_job(session_factory, *, project_id: uuid.UUID, document_id: uuid.UUID, job_id: uuid.UUID) -> None:
    with session_factory() as session:
        session.execute(delete(DocumentParseJob).where(DocumentParseJob.id == job_id))
        session.execute(delete(Document).where(Document.id == document_id))
        session.execute(delete(Project).where(Project.id == project_id))
        session.commit()


def test_claim_next_job_marks_parse_job_running_with_lease(tmp_path: Path) -> None:
    service, session_factory = _build_service(tmp_path)
    project_id, document_id, job_id = _seed_parse_job(service, session_factory)
    try:
        claimed = service.claim_next_job(worker_id="test-worker", job_types=("parse",))

        assert claimed is not None
        assert claimed.job_type == "parse"
        assert claimed.job_id == job_id
        with session_factory() as session:
            job = session.get(DocumentParseJob, job_id)
            assert job is not None
            assert job.status == "RUNNING"
            assert job.claimed_by_worker == "test-worker"
            assert job.attempt_count == 1
            assert job.lease_expires_at is not None
    finally:
        _cleanup_parse_job(session_factory, project_id=project_id, document_id=document_id, job_id=job_id)


def test_recover_stale_parse_job_requeues_with_backoff(tmp_path: Path) -> None:
    service, session_factory = _build_service(tmp_path)
    project_id, document_id, job_id = _seed_parse_job(
        service,
        session_factory,
        status="RUNNING",
        attempt_count=1,
        lease_expired=True,
    )
    try:
        reclaimed = service.recover_stale_leases()

        assert reclaimed >= 1
        with session_factory() as session:
            job = session.get(DocumentParseJob, job_id)
            document = session.get(Document, document_id)
            assert job is not None
            assert document is not None
            assert job.status == "QUEUED"
            assert job.claimed_by_worker is None
            assert job.available_at > utcnow()
            assert document.parse_status == "QUEUED"
    finally:
        _cleanup_parse_job(session_factory, project_id=project_id, document_id=document_id, job_id=job_id)


def test_execute_claimed_job_requeues_retryable_failures(tmp_path: Path, monkeypatch) -> None:
    service, session_factory = _build_service(tmp_path)
    project_id, document_id, job_id = _seed_parse_job(service, session_factory)
    try:
        claimed = service.claim_next_job(worker_id="test-worker", job_types=("parse",))
        assert claimed is not None

        async def _boom(_job_id: uuid.UUID) -> None:
            raise RuntimeError("temporary upstream failure")

        monkeypatch.setattr(service, "_run_job", _boom)

        try:
            asyncio.run(service.execute_claimed_job(claimed, worker_id="test-worker"))
        except RuntimeError:
            pass
        else:  # pragma: no cover - explicit assertion branch
            raise AssertionError("Expected retryable parse failure to propagate to worker.")

        with session_factory() as session:
            job = session.get(DocumentParseJob, job_id)
            document = session.get(Document, document_id)
            assert job is not None
            assert document is not None
            assert job.status == "QUEUED"
            assert job.last_error_code == "RuntimeError"
            assert job.claimed_by_worker is None
            assert document.parse_status == "QUEUED"
    finally:
        _cleanup_parse_job(session_factory, project_id=project_id, document_id=document_id, job_id=job_id)


def test_execute_claimed_job_marks_permanent_failures_failed(tmp_path: Path, monkeypatch) -> None:
    service, session_factory = _build_service(tmp_path)
    project_id, document_id, job_id = _seed_parse_job(service, session_factory)
    try:
        claimed = service.claim_next_job(worker_id="test-worker", job_types=("parse",))
        assert claimed is not None

        async def _boom(_job_id: uuid.UUID) -> None:
            raise PermanentJobError("bad document")

        monkeypatch.setattr(service, "_run_job", _boom)

        try:
            asyncio.run(service.execute_claimed_job(claimed, worker_id="test-worker"))
        except PermanentJobError:
            pass
        else:  # pragma: no cover - explicit assertion branch
            raise AssertionError("Expected permanent parse failure to propagate to worker.")

        with session_factory() as session:
            job = session.get(DocumentParseJob, job_id)
            document = session.get(Document, document_id)
            assert job is not None
            assert document is not None
            assert job.status == "FAILED"
            assert job.error_code == "PermanentJobError"
            assert job.claimed_by_worker is None
            assert document.parse_status == "FAILED"
    finally:
        _cleanup_parse_job(session_factory, project_id=project_id, document_id=document_id, job_id=job_id)
