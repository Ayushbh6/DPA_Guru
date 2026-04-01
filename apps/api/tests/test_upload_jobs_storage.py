from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi import HTTPException

from dpa_checklist import ChecklistCategory, ChecklistDraftItem, ChecklistDraftMeta, ChecklistDraftOutput, ChecklistSource
from upload_api.config import Settings
from upload_api.events import JobEventBus
from upload_api.jobs import UploadPipelineService, utcnow
from upload_api.parsers import PdfInspection
from upload_api.storage import ArtifactStore


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url="postgresql+psycopg://postgres:postgres@localhost:5432/postgres",
        api_host="0.0.0.0",
        api_port=8001,
        max_upload_mb=50,
        max_pdf_pages=200,
        document_storage_backend="local",
        upload_storage_dir=tmp_path / "uploads",
        parsed_storage_dir=tmp_path / "parsed",
        tokenizer_encoding="cl100k_base",
        openai_api_key="test-key",
        openai_embedding_model="text-embedding-3-small",
        checklist_synthesis_strategy="category_groups_v1",
        checklist_synthesis_legacy_fallback=True,
        checklist_synthesis_group_similarity_threshold=0.90,
        checklist_synthesis_group_merge_threshold=0.92,
        checklist_synthesis_group_max_neighbors=2,
        checklist_synthesis_group_max_size=5,
        checklist_synthesis_group_max_parallel=4,
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
        alpha_users_json='[{"username":"local-dev","password":"local-dev"}]',
        alpha_bootstrap_owner_username="local-dev",
        session_secret="local-dev-session-secret-change-me",
        session_cookie_secure=False,
        session_cookie_samesite="lax",
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


class _ExecuteResult:
    def __init__(self, scalar_value):
        self._scalar_value = scalar_value

    def scalar_one_or_none(self):
        return self._scalar_value


class _SessionStub:
    def __init__(self, *, existing_document=None) -> None:
        self.existing_document = existing_document
        self.committed = False

    def execute(self, _statement):
        return _ExecuteResult(self.existing_document)

    def commit(self) -> None:
        self.committed = True


class _SessionFactoryStub:
    def __init__(self, session: _SessionStub) -> None:
        self._session = session

    def __call__(self):
        return self

    def __enter__(self) -> _SessionStub:
        return self._session

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class _ChecklistJobStub:
    def __init__(self, *, document_id, status="FAILED", error_code="UserCanceled", finished_at=None) -> None:
        self.document_id = document_id
        self.status = status
        self.error_code = error_code
        self.completed_at = finished_at
        self.updated_at = finished_at
        self.created_at = finished_at


def _sample_checklist_result() -> ChecklistDraftOutput:
    return ChecklistDraftOutput(
        version="v1",
        meta=ChecklistDraftMeta(
            selected_source_ids=["gdpr_regulation_2016_679"],
            confidence=0.9,
            open_questions=[],
            generation_summary="summary",
        ),
        checks=[
            ChecklistDraftItem(
                check_id="CHECK_001",
                title="Security Measures",
                category=ChecklistCategory.SECURITY_AND_CONFIDENTIALITY.value,
                legal_basis=["GDPR Art. 32"],
                required=True,
                severity="HIGH",
                evidence_hint="Look for the security clause.",
                pass_criteria=["Processor commits to security measures."],
                fail_criteria=["No security commitment."],
                sources=[
                    ChecklistSource(
                        source_type="LAW",
                        authority="EDPB",
                        source_ref="Art 32",
                        source_url="https://example.com/source",
                        source_excerpt="Security obligations apply.",
                    )
                ],
                draft_rationale="Security obligations should be explicit.",
            )
        ],
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


def test_prepare_upload_context_rejects_per_user_document_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path)
    session = _SessionStub()
    service = UploadPipelineService(
        settings=settings,
        session_factory=_SessionFactoryStub(session),  # type: ignore[arg-type]
        storage=ArtifactStore(
            primary_backend="local",
            upload_dir=settings.upload_storage_dir,
            parsed_dir=settings.parsed_storage_dir,
        ),
        event_bus=JobEventBus(),
    )
    project_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    project = type("ProjectStub", (), {"id": project_id, "tenant_id": tenant_id})()
    audit_events: list[dict[str, object]] = []

    monkeypatch.setattr(service, "_require_owned_project", lambda *args, **kwargs: project)
    monkeypatch.setattr(
        service,
        "_count_documents_for_user_alpha_quota",
        lambda *_args, **_kwargs: settings.alpha_max_documents_per_user,
    )
    monkeypatch.setattr(service, "_count_documents_for_alpha_quota", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(service, "_count_active_artifact_bytes_for_alpha_quota", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(
        service,
        "_record_audit_event",
        lambda _session, **payload: audit_events.append(payload),
    )

    with pytest.raises(HTTPException) as exc:
        service._prepare_upload_context(project_id, "local-dev", "trace-1", 1024)

    assert exc.value.status_code == 409
    assert "8 documents" in exc.value.detail
    assert session.committed is True
    assert audit_events[0]["event_name"] == "document_upload_quota_denied_per_user"


def test_prepare_upload_context_rejects_global_storage_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path)
    session = _SessionStub()
    service = UploadPipelineService(
        settings=settings,
        session_factory=_SessionFactoryStub(session),  # type: ignore[arg-type]
        storage=ArtifactStore(
            primary_backend="local",
            upload_dir=settings.upload_storage_dir,
            parsed_dir=settings.parsed_storage_dir,
        ),
        event_bus=JobEventBus(),
    )
    project_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    project = type("ProjectStub", (), {"id": project_id, "tenant_id": tenant_id})()
    audit_events: list[dict[str, object]] = []
    max_bytes = settings.alpha_max_total_active_storage_mb * 1024 * 1024

    monkeypatch.setattr(service, "_require_owned_project", lambda *args, **kwargs: project)
    monkeypatch.setattr(service, "_count_documents_for_user_alpha_quota", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(service, "_count_documents_for_alpha_quota", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(
        service,
        "_count_active_artifact_bytes_for_alpha_quota",
        lambda *_args, **_kwargs: max_bytes - 512,
    )
    monkeypatch.setattr(
        service,
        "_record_audit_event",
        lambda _session, **payload: audit_events.append(payload),
    )

    with pytest.raises(HTTPException) as exc:
        service._prepare_upload_context(project_id, "local-dev", "trace-2", 1024)

    assert exc.value.status_code == 409
    assert "storage limit" in exc.value.detail.lower()
    assert session.committed is True
    assert audit_events[0]["event_name"] == "document_upload_quota_denied_global_storage"


def test_user_canceled_checklist_job_allows_immediate_rate_limit_bypass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path)
    session = _SessionStub()
    service = UploadPipelineService(
        settings=settings,
        session_factory=_SessionFactoryStub(session),  # type: ignore[arg-type]
        storage=ArtifactStore(
            primary_backend="local",
            upload_dir=settings.upload_storage_dir,
            parsed_dir=settings.parsed_storage_dir,
        ),
        event_bus=JobEventBus(),
    )
    document_id = uuid.uuid4()
    finished_at = utcnow() - timedelta(seconds=5)

    project = type("ProjectStub", (), {"id": uuid.uuid4()})()
    document = type("DocumentStub", (), {"id": document_id})()
    latest_job = _ChecklistJobStub(document_id=document_id, finished_at=finished_at)

    monkeypatch.setattr(service, "_require_owned_document", lambda *_args, **_kwargs: (project, document))
    monkeypatch.setattr(service, "_latest_checklist_job_for_project", lambda *_args, **_kwargs: latest_job)

    assert service.should_bypass_checklist_rate_limit_after_cancel(
        document_id,
        "local-dev",
        settings.checklist_rate_limit_window_seconds,
    ) is True


def test_non_canceled_or_stale_checklist_job_does_not_bypass_rate_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path)
    session = _SessionStub()
    service = UploadPipelineService(
        settings=settings,
        session_factory=_SessionFactoryStub(session),  # type: ignore[arg-type]
        storage=ArtifactStore(
            primary_backend="local",
            upload_dir=settings.upload_storage_dir,
            parsed_dir=settings.parsed_storage_dir,
        ),
        event_bus=JobEventBus(),
    )
    document_id = uuid.uuid4()
    project = type("ProjectStub", (), {"id": uuid.uuid4()})()
    document = type("DocumentStub", (), {"id": document_id})()

    monkeypatch.setattr(service, "_require_owned_document", lambda *_args, **_kwargs: (project, document))

    stale_job = _ChecklistJobStub(
        document_id=document_id,
        finished_at=utcnow() - timedelta(seconds=settings.checklist_rate_limit_window_seconds + 5),
    )
    non_canceled_job = _ChecklistJobStub(
        document_id=document_id,
        error_code="RuntimeError",
        finished_at=utcnow(),
    )

    monkeypatch.setattr(service, "_latest_checklist_job_for_project", lambda *_args, **_kwargs: non_canceled_job)
    assert service.should_bypass_checklist_rate_limit_after_cancel(
        document_id,
        "local-dev",
        settings.checklist_rate_limit_window_seconds,
    ) is False

    monkeypatch.setattr(service, "_latest_checklist_job_for_project", lambda *_args, **_kwargs: stale_job)
    assert service.should_bypass_checklist_rate_limit_after_cancel(
        document_id,
        "local-dev",
        settings.checklist_rate_limit_window_seconds,
    ) is False


def test_category_group_checklist_synthesis_falls_back_to_legacy_when_enabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path)
    settings = Settings(**{**settings.__dict__, "checklist_synthesis_strategy": "category_groups_v1", "checklist_synthesis_legacy_fallback": True})
    service = UploadPipelineService(
        settings=settings,
        session_factory=_SessionFactoryStub(_SessionStub()),  # type: ignore[arg-type]
        storage=ArtifactStore(
            primary_backend="local",
            upload_dir=settings.upload_storage_dir,
            parsed_dir=settings.parsed_storage_dir,
        ),
        event_bus=JobEventBus(),
    )
    expected = _sample_checklist_result()
    traces: list[tuple[str, dict[str, object]]] = []
    progress_updates: list[tuple[str, str, dict[str, object] | None, int | None]] = []

    monkeypatch.setattr(
        service.checklist_agent,
        "synthesize_drafts_category_groups",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(service.checklist_agent, "synthesize_drafts_legacy", lambda *_args, **_kwargs: expected)

    result, fallback_used = service._synthesize_checklist_drafts_sync(
        uuid.uuid4(),
        [expected, expected],
        None,
        lambda stage, message, meta=None, progress_pct=None: progress_updates.append((stage, message, meta, progress_pct)),
        lambda event_type, payload: traces.append((event_type, payload)),
    )

    assert result == expected
    assert fallback_used is True
    assert any(event_type == "legacy_fallback" for event_type, _payload in traces)
    assert any(update[0] == "SYNTHESIZING" for update in progress_updates)


def test_unknown_checklist_synthesis_strategy_uses_legacy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path)
    settings = Settings(**{**settings.__dict__, "checklist_synthesis_strategy": "verified_cluster_v1"})
    service = UploadPipelineService(
        settings=settings,
        session_factory=_SessionFactoryStub(_SessionStub()),  # type: ignore[arg-type]
        storage=ArtifactStore(
            primary_backend="local",
            upload_dir=settings.upload_storage_dir,
            parsed_dir=settings.parsed_storage_dir,
        ),
        event_bus=JobEventBus(),
    )
    expected = _sample_checklist_result()
    legacy_calls: list[bool] = []

    monkeypatch.setattr(
        service.checklist_agent,
        "synthesize_drafts_legacy",
        lambda *_args, **_kwargs: legacy_calls.append(True) or expected,
    )

    result, fallback_used = service._synthesize_checklist_drafts_sync(
        uuid.uuid4(),
        [expected, expected],
        None,
        lambda *_args, **_kwargs: None,
        lambda *_args, **_kwargs: None,
    )

    assert result == expected
    assert fallback_used is False
    assert legacy_calls == [True]


def test_build_checklist_snapshot_tolerates_invalid_stored_result(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    service = UploadPipelineService(
        settings=settings,
        session_factory=_SessionFactoryStub(_SessionStub()),  # type: ignore[arg-type]
        storage=ArtifactStore(
            primary_backend="local",
            upload_dir=settings.upload_storage_dir,
            parsed_dir=settings.parsed_storage_dir,
        ),
        event_bus=JobEventBus(),
    )
    job = type(
        "ChecklistJobStub",
        (),
        {
            "id": uuid.uuid4(),
            "project_id": uuid.uuid4(),
            "status": "COMPLETED",
            "stage": "COMPLETED",
            "progress_pct": 100,
            "message": "Checklist ready.",
            "selected_source_ids": ["gdpr_regulation_2016_679"],
            "user_instruction": None,
            "meta_json": None,
            "result_json": "{\"version\": ",
            "error_code": None,
            "error_message": None,
        },
    )()
    doc = type("DocumentStub", (), {"id": uuid.uuid4()})()

    snapshot = service._build_checklist_snapshot(job, doc)

    assert snapshot.result is None
    assert snapshot.error_code == "StoredResultInvalid"
    assert "could not be loaded" in (snapshot.error_message or "")


def test_enforce_project_alpha_quota_rejects_user_over_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path)
    session = _SessionStub()
    service = UploadPipelineService(
        settings=settings,
        session_factory=_SessionFactoryStub(session),  # type: ignore[arg-type]
        storage=ArtifactStore(
            primary_backend="local",
            upload_dir=settings.upload_storage_dir,
            parsed_dir=settings.parsed_storage_dir,
        ),
        event_bus=JobEventBus(),
    )
    audit_events: list[dict[str, object]] = []

    monkeypatch.setattr(
        service,
        "_count_projects_for_user_alpha_quota",
        lambda *_args, **_kwargs: settings.alpha_max_projects_per_user,
    )
    monkeypatch.setattr(
        service,
        "_record_audit_event",
        lambda _session, **payload: audit_events.append(payload),
    )

    with pytest.raises(HTTPException) as exc:
        service._enforce_project_alpha_quota(
            session,
            tenant_id=uuid.uuid4(),
            actor_username="local-dev",
            trace_id="trace-project-cap",
        )

    assert exc.value.status_code == 409
    assert "20 projects" in exc.value.detail
    assert session.committed is True
    assert audit_events[0]["event_name"] == "project_quota_denied_per_user"


def test_enforce_check_run_alpha_quota_rejects_user_over_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path)
    session = _SessionStub()
    service = UploadPipelineService(
        settings=settings,
        session_factory=_SessionFactoryStub(session),  # type: ignore[arg-type]
        storage=ArtifactStore(
            primary_backend="local",
            upload_dir=settings.upload_storage_dir,
            parsed_dir=settings.parsed_storage_dir,
        ),
        event_bus=JobEventBus(),
    )
    audit_events: list[dict[str, object]] = []

    monkeypatch.setattr(
        service,
        "_count_check_runs_for_user_alpha_quota",
        lambda *_args, **_kwargs: settings.alpha_max_check_runs_per_user,
    )
    monkeypatch.setattr(
        service,
        "_record_audit_event",
        lambda _session, **payload: audit_events.append(payload),
    )

    with pytest.raises(HTTPException) as exc:
        service._enforce_check_run_alpha_quota(
            session,
            tenant_id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            actor_username="local-dev",
            trace_id="trace-check-cap",
            event_name="checklist_quota_denied_per_user",
            label="checklist",
        )

    assert exc.value.status_code == 409
    assert "15 checklist/review runs" in exc.value.detail
    assert session.committed is True
    assert audit_events[0]["event_name"] == "checklist_quota_denied_per_user"


def test_create_upload_rejects_oversized_file_and_records_audit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path)
    service = UploadPipelineService(
        settings=settings,
        session_factory=None,  # type: ignore[arg-type]
        storage=ArtifactStore(
            primary_backend="local",
            upload_dir=settings.upload_storage_dir,
            parsed_dir=settings.parsed_storage_dir,
        ),
        event_bus=JobEventBus(),
    )
    audit_events: list[dict[str, object]] = []
    monkeypatch.setattr(
        service,
        "record_upload_policy_event",
        lambda **payload: audit_events.append(payload),
    )

    oversized = b"x" * ((settings.max_upload_mb * 1024 * 1024) + 1)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            service.create_upload(
                project_id=uuid.uuid4(),
                filename="sample.pdf",
                mime_type="application/pdf",
                data=oversized,
                actor_username="local-dev",
                trace_id="trace-3",
            )
        )

    assert exc.value.status_code == 400
    assert f"{settings.max_upload_mb}MB" in exc.value.detail
    assert audit_events[0]["event_name"] == "document_upload_quota_denied_file_size"


def test_preflight_pdf_upload_rejects_invalid_pdf_and_records_audit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path)
    service = UploadPipelineService(
        settings=settings,
        session_factory=None,  # type: ignore[arg-type]
        storage=ArtifactStore(
            primary_backend="local",
            upload_dir=settings.upload_storage_dir,
            parsed_dir=settings.parsed_storage_dir,
        ),
        event_bus=JobEventBus(),
    )
    audit_events: list[dict[str, object]] = []

    monkeypatch.setattr(
        service,
        "record_upload_policy_event",
        lambda **payload: audit_events.append(payload),
    )
    monkeypatch.setattr("upload_api.jobs.inspect_pdf", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("bad pdf")))

    with pytest.raises(HTTPException) as exc:
        service._preflight_pdf_upload(uuid.uuid4(), "local-dev", "trace-preflight-invalid", b"%PDF-1.4 broken")

    assert exc.value.status_code == 400
    assert "non-password-protected PDF" in exc.value.detail
    assert audit_events[0]["event_name"] == "document_upload_policy_denied_pdf_invalid"


def test_preflight_pdf_upload_rejects_pdf_page_cap_and_records_audit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path)
    service = UploadPipelineService(
        settings=settings,
        session_factory=None,  # type: ignore[arg-type]
        storage=ArtifactStore(
            primary_backend="local",
            upload_dir=settings.upload_storage_dir,
            parsed_dir=settings.parsed_storage_dir,
        ),
        event_bus=JobEventBus(),
    )
    audit_events: list[dict[str, object]] = []

    monkeypatch.setattr(
        service,
        "record_upload_policy_event",
        lambda **payload: audit_events.append(payload),
    )
    monkeypatch.setattr(
        "upload_api.jobs.inspect_pdf",
        lambda *_args, **_kwargs: PdfInspection(
            page_count=settings.max_pdf_pages + 1,
            sampled_pages=15,
            text_chars_per_page=[200] * 15,
            image_only_like_pages=0,
            median_text_chars=200,
            classification="native",
        ),
    )

    with pytest.raises(HTTPException) as exc:
        service._preflight_pdf_upload(uuid.uuid4(), "local-dev", "trace-preflight-pages", b"%PDF-1.4 placeholder")

    assert exc.value.status_code == 400
    assert f"{settings.max_pdf_pages} pages" in exc.value.detail
    assert audit_events[0]["event_name"] == "document_upload_policy_denied_pdf_pages"
