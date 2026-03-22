from __future__ import annotations

import asyncio
import json
import mimetypes
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from db.models import (
    AnalysisReport,
    AnalysisRun,
    ApprovedChecklist,
    ChecklistDraftJob,
    Document,
    DocumentChunk,
    DocumentParseJob,
    Finding,
    Project,
    Tenant,
)
from dpa_checklist import ApprovalStatus, ChecklistDocument, ChecklistDraftOutput, ChecklistGovernance

from .checklist_agent import ChecklistDraftAgent
from .config import Settings
from .document_retrieval import DpaPageRecord, DocumentChunkIndexer, derive_evidence_metadata
from .events import JobEventBus
from .parsers import (
    estimate_token_count,
    inspect_pdf,
    parse_with_mistral_ocr,
)
from .review_agent import ReviewAgent
from .schemas import (
    AnalysisFindingDetail,
    AnalysisRunBootstrapResponse,
    AnalysisRunReportResponse,
    AnalysisRunSnapshot,
    AnalysisRunSummary,
    ApproveChecklistRequest,
    ApprovedChecklistResponse,
    ApprovedChecklistSummary,
    ChecklistDraftBootstrapResponse,
    ChecklistDraftSnapshot,
    CreateAnalysisRunRequest,
    CreateProjectResponse,
    ProjectDetail,
    ProjectDocumentSummary,
    ProjectSummary,
    ReferenceSource,
    ReviewSetupRequest,
    ReviewSetupResponse,
    UploadBootstrapResponse,
    UploadJobSnapshot,
)
from .storage import LocalStorage
from dpa_schemas import CheckAssessmentOutput, CheckResult, OutputV2Report, ReviewState, ReviewSynthesisOutput, RiskLevel


def utcnow() -> datetime:
    return datetime.now(UTC)


STAGE_PROGRESS = {
    "UPLOADING": 5,
    "VALIDATING": 12,
    "CLASSIFYING_PDF": 20,
    "PARSING_MISTRAL_OCR": 58,
    "COUNTING_TOKENS": 80,
    "PERSISTING_RESULTS": 90,
    "INDEXING_DOCUMENT": 96,
    "READY_FOR_REFERENCE_SELECTION": 100,
    "FAILED": 100,
}

CHECKLIST_STAGE_PROGRESS = {
    "QUEUED": 5,
    "RETRIEVING_KB": 18,
    "EXPANDING_SOURCE_CONTEXT": 32,
    "INSPECTING_DPA": 50,
    "DRAFTING_CHECKLIST": 74,
    "VALIDATING_OUTPUT": 92,
    "COMPLETED": 100,
    "FAILED": 100,
}

ANALYSIS_STAGE_PROGRESS = {
    "QUEUED": 5,
    "PREFETCHING_EVIDENCE": 18,
    "REVIEWING_CHECKS": 70,
    "SYNTHESIZING": 90,
    "COMPLETED": 100,
    "FAILED": 100,
}

ALLOWED_EXTENSIONS = {".pdf": "pdf", ".docx": "docx"}
DEFAULT_DEV_TENANT_NAME = "Local Dev Tenant"
UNTITLED_PROJECT_NAME = "Untitled analysis"
DEFAULT_APPROVAL_OWNER = "local-dev-owner"
DEFAULT_APPROVED_BY = "local-dev-reviewer"


@dataclass(frozen=True)
class UploadCreateResult:
    job_id: uuid.UUID
    document_id: uuid.UUID
    project_id: uuid.UUID


@dataclass(frozen=True)
class DocumentFileResult:
    path: Path
    filename: str
    mime_type: str | None


class UploadPipelineService:
    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: sessionmaker[Session],
        storage: LocalStorage,
        event_bus: JobEventBus,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.storage = storage
        self.event_bus = event_bus
        self._tasks: dict[uuid.UUID, asyncio.Task] = {}
        self._checklist_tasks: dict[uuid.UUID, asyncio.Task] = {}
        self._analysis_tasks: dict[uuid.UUID, asyncio.Task] = {}
        self._tasks_lock = asyncio.Lock()
        self.checklist_agent = ChecklistDraftAgent(settings)
        self.review_agent = ReviewAgent(settings)
        self.document_indexer = DocumentChunkIndexer(settings, session_factory)

    def recover_incomplete_jobs(self) -> None:
        with self.session_factory() as session:
            now = utcnow()

            parse_jobs = session.execute(
                select(DocumentParseJob).where(DocumentParseJob.status.in_(("QUEUED", "RUNNING")))
            ).scalars().all()
            for job in parse_jobs:
                job.status = "FAILED"
                job.stage = "FAILED"
                job.progress_pct = STAGE_PROGRESS["FAILED"]
                job.error_code = "ServiceRestarted"
                job.error_message = "The service restarted before document processing completed."
                job.message = "Document processing stopped when the service restarted."
                if job.started_at is None:
                    job.started_at = now
                job.completed_at = now
                job.updated_at = now

                document = session.get(Document, job.document_id)
                if document is not None and document.parse_status != "COMPLETED":
                    document.parse_status = "FAILED"

            checklist_jobs = session.execute(
                select(ChecklistDraftJob).where(ChecklistDraftJob.status.in_(("QUEUED", "RUNNING")))
            ).scalars().all()
            for job in checklist_jobs:
                job.status = "FAILED"
                job.stage = "FAILED"
                job.progress_pct = CHECKLIST_STAGE_PROGRESS["FAILED"]
                job.error_code = "ServiceRestarted"
                job.error_message = "The service restarted before checklist generation completed."
                job.message = "Checklist generation stopped when the service restarted."
                if job.started_at is None:
                    job.started_at = now
                job.completed_at = now
                job.updated_at = now

            analysis_runs = session.execute(
                select(AnalysisRun).where(AnalysisRun.status.in_(("QUEUED", "RUNNING")))
            ).scalars().all()
            for run in analysis_runs:
                run.status = "FAILED"
                run.stage = "FAILED"
                run.progress_pct = ANALYSIS_STAGE_PROGRESS["FAILED"]
                run.error_code = "ServiceRestarted"
                run.error_message = "The service restarted before final review completed."
                run.message = "Final review stopped when the service restarted."
                run.completed_at = now

            affected_project_ids = {
                *[job.project_id for job in parse_jobs],
                *[job.project_id for job in checklist_jobs],
                *[run.project_id for run in analysis_runs],
            }
            for project_id in affected_project_ids:
                self._sync_project_state(session, project_id)

            session.commit()

    def create_project(self, name: str | None = None) -> CreateProjectResponse:
        with self.session_factory() as session:
            tenant = self._ensure_dev_tenant(session)
            now = utcnow()
            project = Project(
                tenant_id=tenant.id,
                name=(name or "").strip() or UNTITLED_PROJECT_NAME,
                status="EMPTY",
                created_at=now,
                updated_at=now,
                last_activity_at=now,
            )
            session.add(project)
            session.commit()
            session.refresh(project)
            summary = self._build_project_summary(session, project)
            return CreateProjectResponse(**summary.model_dump(mode="python"), workspace_url=f"/projects/{project.id}")

    def list_projects(self) -> list[ProjectSummary]:
        with self.session_factory() as session:
            tenant = self._ensure_dev_tenant(session)
            projects = session.execute(
                select(Project)
                .where(Project.tenant_id == tenant.id)
                .where(Project.status != "DELETED")
                .order_by(Project.last_activity_at.desc(), Project.updated_at.desc(), Project.created_at.desc())
            ).scalars().all()
            summaries = [self._build_project_summary(session, project) for project in projects]
            session.commit()
            return summaries

    def get_project_detail(self, project_id: uuid.UUID) -> ProjectDetail | None:
        with self.session_factory() as session:
            tenant = self._ensure_dev_tenant(session)
            project = session.execute(
                select(Project).where(Project.id == project_id, Project.tenant_id == tenant.id)
            ).scalar_one_or_none()
            if project is None:
                return None
            detail = self._build_project_detail(session, project)
            session.commit()
            return detail

    def rename_project(self, project_id: uuid.UUID, name: str) -> ProjectDetail | None:
        clean_name = name.strip()
        if not clean_name:
            raise HTTPException(status_code=400, detail="Project name is required.")

        with self.session_factory() as session:
            tenant = self._ensure_dev_tenant(session)
            project = session.execute(
                select(Project).where(Project.id == project_id, Project.tenant_id == tenant.id)
            ).scalar_one_or_none()
            if project is None:
                return None
            project.name = clean_name
            project.updated_at = utcnow()
            project.last_activity_at = utcnow()
            session.commit()
            session.refresh(project)
            return self._build_project_detail(session, project)

    def delete_project(self, project_id: uuid.UUID) -> None:
        with self.session_factory() as session:
            tenant = self._ensure_dev_tenant(session)
            project = session.execute(
                select(Project).where(Project.id == project_id, Project.tenant_id == tenant.id)
            ).scalar_one_or_none()
            if project is None:
                raise HTTPException(status_code=404, detail="Project not found.")
            project.status = "DELETED"
            project.updated_at = utcnow()
            project.last_activity_at = utcnow()
            session.commit()

    async def create_upload(
        self,
        *,
        project_id: uuid.UUID,
        filename: str,
        mime_type: str | None,
        data: bytes,
    ) -> UploadBootstrapResponse:
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail="Unsupported file type. Only PDF and DOCX are allowed.")

        size_limit = self.settings.max_upload_mb * 1024 * 1024
        if len(data) > size_limit:
            raise HTTPException(status_code=400, detail=f"File exceeds {self.settings.max_upload_mb}MB limit.")

        mime_type = (mime_type or mimetypes.guess_type(filename)[0] or "").strip() or "application/octet-stream"
        file_type = ALLOWED_EXTENSIONS[ext]
        job_id = uuid.uuid4()

        upload_path = self.storage.save_upload(job_id=job_id, filename=filename, data=data)

        created = await asyncio.to_thread(
            self._create_document_and_job,
            project_id,
            job_id,
            filename,
            mime_type,
            file_type,
            upload_path,
        )
        await self._schedule_job(created.job_id)

        return UploadBootstrapResponse(
            job_id=created.job_id,
            document_id=created.document_id,
            project_id=created.project_id,
            status="QUEUED",
            ws_url=f"/v1/uploads/{created.job_id}/events",
            status_url=f"/v1/uploads/{created.job_id}",
        )

    def _create_document_and_job(
        self,
        project_id: uuid.UUID,
        job_id: uuid.UUID,
        filename: str,
        mime_type: str,
        file_type: str,
        upload_path: Path,
    ) -> UploadCreateResult:
        with self.session_factory() as session:
            tenant = self._ensure_dev_tenant(session)
            project = session.execute(
                select(Project).where(Project.id == project_id, Project.tenant_id == tenant.id)
            ).scalar_one_or_none()
            if project is None:
                raise HTTPException(status_code=404, detail="Project not found.")
            existing_document = session.execute(
                select(Document.id).where(Document.project_id == project.id)
            ).scalar_one_or_none()
            if existing_document is not None:
                raise HTTPException(status_code=409, detail="This project already has a document.")
            document = Document(
                tenant_id=tenant.id,
                project_id=project.id,
                filename=filename,
                mime_type=mime_type,
                page_count=0,
                storage_uri=str(upload_path),
                parse_status="QUEUED",
            )
            session.add(document)
            session.flush()

            job = DocumentParseJob(
                id=job_id,
                tenant_id=tenant.id,
                project_id=project.id,
                document_id=document.id,
                status="QUEUED",
                stage="UPLOADING",
                progress_pct=STAGE_PROGRESS["UPLOADING"],
                message="Upload received. Queuing background processing.",
                file_type=file_type,
                meta_json={"original_filename": filename, "upload_path": str(upload_path)},
            )
            session.add(job)
            self._sync_project_state(session, project.id)
            session.commit()
            return UploadCreateResult(job_id=job.id, document_id=document.id, project_id=project.id)

    def _ensure_dev_tenant(self, session: Session) -> Tenant:
        tenant = session.get(Tenant, self.settings.default_dev_tenant_id)
        if tenant is not None:
            return tenant
        tenant = Tenant(
            id=self.settings.default_dev_tenant_id,
            name=DEFAULT_DEV_TENANT_NAME,
            region="EU",
            status="ACTIVE",
        )
        session.add(tenant)
        session.flush()
        return tenant

    def _project_name_from_filename(self, filename: str) -> str:
        return f"Project for {filename}"

    def _is_placeholder_project_name(self, name: str | None) -> bool:
        return not name or name.strip() == UNTITLED_PROJECT_NAME

    def _latest_document_for_project(self, session: Session, project_id: uuid.UUID) -> Document | None:
        return session.execute(
            select(Document).where(Document.project_id == project_id).order_by(Document.uploaded_at.desc())
        ).scalars().first()

    def _latest_parse_job_for_project(self, session: Session, project_id: uuid.UUID) -> DocumentParseJob | None:
        return session.execute(
            select(DocumentParseJob)
            .where(DocumentParseJob.project_id == project_id)
            .order_by(DocumentParseJob.created_at.desc())
        ).scalars().first()

    def _latest_checklist_job_for_project(self, session: Session, project_id: uuid.UUID) -> ChecklistDraftJob | None:
        return session.execute(
            select(ChecklistDraftJob)
            .where(ChecklistDraftJob.project_id == project_id)
            .order_by(ChecklistDraftJob.created_at.desc())
        ).scalars().first()

    def _latest_approved_checklist_for_project(self, session: Session, project_id: uuid.UUID) -> ApprovedChecklist | None:
        return session.execute(
            select(ApprovedChecklist)
            .where(ApprovedChecklist.project_id == project_id)
            .order_by(ApprovedChecklist.created_at.desc())
        ).scalars().first()

    def _latest_analysis_run_for_project(self, session: Session, project_id: uuid.UUID) -> AnalysisRun | None:
        return session.execute(
            select(AnalysisRun)
            .where(AnalysisRun.project_id == project_id)
            .order_by(AnalysisRun.started_at.desc())
        ).scalars().first()

    def _derive_project_status(
        self,
        document: Document | None,
        parse_job: DocumentParseJob | None,
        checklist_job: ChecklistDraftJob | None,
        analysis_run: AnalysisRun | None,
    ) -> str:
        if analysis_run is not None:
            if analysis_run.status == "FAILED":
                return "FAILED"
            if analysis_run.status != "COMPLETED":
                return "REVIEW_IN_PROGRESS"
            return "COMPLETED"
        if checklist_job is not None:
            if checklist_job.status == "FAILED":
                return "FAILED"
            if checklist_job.status != "COMPLETED":
                return "CHECKLIST_IN_PROGRESS"
            return "CHECKLIST_READY"
        if parse_job is not None:
            if parse_job.status == "FAILED":
                return "FAILED"
            if parse_job.status != "COMPLETED":
                return "UPLOADING"
        if document is not None and document.parse_status == "COMPLETED":
            return "READY_FOR_CHECKLIST"
        if document is not None:
            return "UPLOADING"
        return "EMPTY"

    def _sync_project_state(self, session: Session, project_id: uuid.UUID) -> Project | None:
        project = session.get(Project, project_id)
        if project is None or project.status == "DELETED":
            return project

        document = self._latest_document_for_project(session, project_id)
        parse_job = self._latest_parse_job_for_project(session, project_id)
        checklist_job = self._latest_checklist_job_for_project(session, project_id)
        analysis_run = self._latest_analysis_run_for_project(session, project_id)

        project.status = self._derive_project_status(document, parse_job, checklist_job, analysis_run)
        if document is not None and self._is_placeholder_project_name(project.name):
            project.name = self._project_name_from_filename(document.filename)

        timestamps = [
            project.created_at,
            getattr(document, "uploaded_at", None),
            getattr(document, "parse_completed_at", None),
            getattr(parse_job, "updated_at", None),
            getattr(parse_job, "completed_at", None),
            getattr(checklist_job, "updated_at", None),
            getattr(checklist_job, "completed_at", None),
            getattr(analysis_run, "started_at", None),
            getattr(analysis_run, "completed_at", None),
        ]
        latest = max(ts for ts in timestamps if ts is not None)
        project.last_activity_at = latest
        project.updated_at = utcnow()
        return project

    def _build_upload_snapshot(self, job: DocumentParseJob, doc: Document) -> UploadJobSnapshot:
        result = None
        if job.status == "COMPLETED":
            result = {
                "filename": doc.filename,
                "mime_type": doc.mime_type,
                "page_count": doc.page_count,
                "pdf_classification": doc.pdf_classification,
                "parser_route": doc.parser_route,
                "token_count_estimate": doc.token_count_estimate,
                "extracted_text_format": doc.extracted_text_format,
            }
        return UploadJobSnapshot(
            job_id=job.id,
            document_id=doc.id,
            project_id=doc.project_id,
            status=job.status,
            stage=job.stage,
            progress_pct=job.progress_pct,
            message=job.message,
            file_type=job.file_type,
            pdf_classification=job.pdf_classification,
            parser_route=job.parser_route,
            page_count=doc.page_count if doc.page_count is not None else None,
            token_count_estimate=job.token_count_estimate or doc.token_count_estimate,
            result=result,
            error_code=job.error_code,
            error_message=job.error_message,
            meta=job.meta_json,
        )

    def _build_checklist_snapshot(self, job: ChecklistDraftJob, doc: Document) -> ChecklistDraftSnapshot:
        result = ChecklistDraftOutput.model_validate(job.result_json) if job.result_json else None
        return ChecklistDraftSnapshot(
            checklist_draft_id=job.id,
            document_id=doc.id,
            project_id=job.project_id,
            status=job.status,
            stage=job.stage,
            progress_pct=job.progress_pct,
            message=job.message,
            selected_source_ids=list(job.selected_source_ids or []),
            user_instruction=job.user_instruction,
            result=result,
            error_code=job.error_code,
            error_message=job.error_message,
        )

    def _build_approved_checklist_summary(self, checklist: ApprovedChecklist) -> ApprovedChecklistSummary:
        return ApprovedChecklistSummary(
            approved_checklist_id=checklist.id,
            project_id=checklist.project_id,
            document_id=checklist.document_id,
            version=checklist.version,
            selected_source_ids=list(checklist.selected_source_ids or []),
            owner=checklist.owner,
            approval_status=checklist.approval_status,
            approved_by=checklist.approved_by,
            approved_at=checklist.approved_at,
            change_note=checklist.change_note,
            created_at=checklist.created_at,
        )

    def _build_analysis_run_summary(self, session: Session, run: AnalysisRun) -> AnalysisRunSummary:
        return AnalysisRunSummary(
            analysis_run_id=run.id,
            project_id=run.project_id,
            document_id=run.document_id,
            status=run.status,
            model_version=run.model_version,
            policy_version=run.policy_version,
            stage=run.stage,
            progress_pct=run.progress_pct,
            message=run.message,
            error_code=run.error_code,
            error_message=run.error_message,
            approved_checklist_id=run.approved_checklist_id,
            started_at=run.started_at,
            completed_at=run.completed_at,
            latency_ms=run.latency_ms,
            cost_usd=run.cost_usd,
        )

    def _build_project_summary(self, session: Session, project: Project) -> ProjectSummary:
        self._sync_project_state(session, project.id)
        document = self._latest_document_for_project(session, project.id)
        return ProjectSummary(
            project_id=project.id,
            name=project.name,
            status=project.status,
            created_at=project.created_at,
            updated_at=project.updated_at,
            last_activity_at=project.last_activity_at,
            document_id=document.id if document is not None else None,
            document_filename=document.filename if document is not None else None,
        )

    def _build_project_detail(self, session: Session, project: Project) -> ProjectDetail:
        self._sync_project_state(session, project.id)
        document = self._latest_document_for_project(session, project.id)
        parse_job = self._latest_parse_job_for_project(session, project.id)
        checklist_job = self._latest_checklist_job_for_project(session, project.id)
        approved_checklist = self._latest_approved_checklist_for_project(session, project.id)
        analysis_run = self._latest_analysis_run_for_project(session, project.id)

        doc_summary = None
        if document is not None:
            doc_summary = ProjectDocumentSummary(
                document_id=document.id,
                filename=document.filename,
                mime_type=document.mime_type,
                page_count=document.page_count,
                parse_status=document.parse_status,
                parser_route=document.parser_route,
                pdf_classification=document.pdf_classification,
                token_count_estimate=document.token_count_estimate,
                extracted_text_format=document.extracted_text_format,
                uploaded_at=document.uploaded_at,
            )

        parse_snapshot = self._build_upload_snapshot(parse_job, document) if parse_job and document else None
        checklist_snapshot = self._build_checklist_snapshot(checklist_job, document) if checklist_job and document else None
        approved_summary = self._build_approved_checklist_summary(approved_checklist) if approved_checklist else None
        run_summary = None
        if analysis_run is not None:
            run_summary = self._build_analysis_run_summary(session, analysis_run)

        return ProjectDetail(
            project=self._build_project_summary(session, project),
            document=doc_summary,
            parse_job=parse_snapshot,
            checklist_draft=checklist_snapshot,
            approved_checklist=approved_summary,
            analysis_run=run_summary,
        )

    def get_document_file(self, document_id: uuid.UUID) -> DocumentFileResult:
        with self.session_factory() as session:
            document = session.get(Document, document_id)
            if document is None:
                raise HTTPException(status_code=404, detail="Document not found.")

            storage_path = Path(document.storage_uri).resolve()
            upload_root = self.storage.upload_dir.resolve()
            if not storage_path.is_relative_to(upload_root):
                raise HTTPException(status_code=404, detail="Document file is unavailable.")
            if not storage_path.exists() or not storage_path.is_file():
                raise HTTPException(status_code=404, detail="Document file is missing.")

            mime_type = document.mime_type or mimetypes.guess_type(document.filename)[0]
            return DocumentFileResult(
                path=storage_path,
                filename=document.filename,
                mime_type=mime_type,
            )

    async def _schedule_job(self, job_id: uuid.UUID) -> None:
        async with self._tasks_lock:
            existing = self._tasks.get(job_id)
            if existing and not existing.done():
                return
            task = asyncio.create_task(self._run_job(job_id))
            self._tasks[job_id] = task
            task.add_done_callback(lambda _t, jid=job_id: asyncio.create_task(self._drop_task(jid)))

    async def _drop_task(self, job_id: uuid.UUID) -> None:
        async with self._tasks_lock:
            self._tasks.pop(job_id, None)

    async def _schedule_checklist_job(self, draft_id: uuid.UUID) -> None:
        async with self._tasks_lock:
            existing = self._checklist_tasks.get(draft_id)
            if existing and not existing.done():
                return
            task = asyncio.create_task(self._run_checklist_job(draft_id))
            self._checklist_tasks[draft_id] = task
            task.add_done_callback(lambda _t, did=draft_id: asyncio.create_task(self._drop_checklist_task(did)))

    async def _drop_checklist_task(self, draft_id: uuid.UUID) -> None:
        async with self._tasks_lock:
            self._checklist_tasks.pop(draft_id, None)

    async def cancel_checklist_draft(self, draft_id: uuid.UUID) -> ChecklistDraftSnapshot:
        async with self._tasks_lock:
            task = self._checklist_tasks.get(draft_id)
            if task and not task.done():
                task.cancel()
        await asyncio.to_thread(self._cancel_checklist_draft_sync, draft_id)
        snapshot = await asyncio.to_thread(self.get_checklist_draft_snapshot, draft_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="Checklist draft job not found.")
        await self.event_bus.publish(draft_id, snapshot.model_dump(mode="json"))
        return snapshot

    async def _schedule_analysis_run(self, run_id: uuid.UUID) -> None:
        async with self._tasks_lock:
            existing = self._analysis_tasks.get(run_id)
            if existing and not existing.done():
                return
            task = asyncio.create_task(self._run_analysis_run(run_id))
            self._analysis_tasks[run_id] = task
            task.add_done_callback(lambda _t, rid=run_id: asyncio.create_task(self._drop_analysis_task(rid)))

    async def _drop_analysis_task(self, run_id: uuid.UUID) -> None:
        async with self._tasks_lock:
            self._analysis_tasks.pop(run_id, None)

    async def _run_job(self, job_id: uuid.UUID) -> None:
        try:
            await self._transition_job(job_id, status="RUNNING", stage="VALIDATING", message="Validating uploaded file.")
            job_record = await asyncio.to_thread(self._get_job_record, job_id)
            if job_record is None:
                return
            file_path = Path(job_record["document_storage_uri"])
            filename = job_record["filename"]
            mime_type = job_record["mime_type"]
            file_type = job_record["file_type"]

            parsed_text: str
            parsed_format = "markdown"
            parser_route: str
            pdf_classification: str | None = None
            fallback_used = False
            page_count = job_record["page_count"] or 0
            parser_meta: dict[str, Any] = {}
            parsed_pages: list[dict[str, Any]] = []

            if file_type == "pdf":
                await self._transition_job(job_id, stage="CLASSIFYING_PDF", message="Checking whether PDF is native or scanned.")
                inspection = await asyncio.to_thread(inspect_pdf, file_path)
                pdf_classification = inspection.classification
                page_count = inspection.page_count
                await self._update_job_details(
                    job_id,
                    pdf_classification=pdf_classification,
                    parser_route="mistral_ocr",
                    meta_merge={
                        "pdf_inspection": {
                            "sampled_pages": inspection.sampled_pages,
                            "text_chars_per_page": inspection.text_chars_per_page,
                            "image_only_like_pages": inspection.image_only_like_pages,
                            "median_text_chars": inspection.median_text_chars,
                        }
                    },
                )
                await self._transition_job(
                    job_id,
                    stage="PARSING_MISTRAL_OCR",
                    message=f"Parsing {pdf_classification} PDF with Mistral OCR ({self.settings.mistral_ocr_model}).",
                )
                parsed = await self._parse_via_mistral_ocr(job_id, file_path, mime_type)
                parsed_text = parsed.text
                parsed_format = parsed.text_format
                parser_route = parsed.parser_route
                page_count = parsed.page_count or page_count
                parsed_pages = parsed.pages
                parser_meta = parsed.meta
            elif file_type == "docx":
                await self._transition_job(
                    job_id,
                    stage="PARSING_MISTRAL_OCR",
                    message=f"Parsing DOCX with Mistral OCR ({self.settings.mistral_ocr_model}).",
                )
                parsed = await self._parse_via_mistral_ocr(job_id, file_path, mime_type)
                parsed_text = parsed.text
                parsed_format = parsed.text_format
                parser_route = parsed.parser_route
                page_count = parsed.page_count
                parsed_pages = parsed.pages
                parser_meta = parsed.meta
            else:
                raise RuntimeError(f"Unsupported file_type '{file_type}'")

            await self._transition_job(job_id, stage="COUNTING_TOKENS", message="Estimating token count.")
            token_count = await asyncio.to_thread(estimate_token_count, parsed_text, self.settings.tokenizer_encoding)

            await self._transition_job(job_id, stage="PERSISTING_RESULTS", message="Saving parsed document artifacts.")
            parsed_path = self.storage.save_parsed_markdown(document_id=job_record["document_id"], text=parsed_text)
            parsed_pages_path = self.storage.save_parsed_pages(document_id=job_record["document_id"], pages=parsed_pages)

            await self._transition_job(job_id, stage="INDEXING_DOCUMENT", message="Indexing document chunks for final review.")
            indexed_chunks = await asyncio.to_thread(
                self._index_document_chunks,
                job_record["document_id"],
                parsed_pages,
            )
            await self._update_job_details(
                job_id,
                meta_merge={"document_chunk_count": indexed_chunks},
            )

            await asyncio.to_thread(
                self._finalize_success,
                job_id,
                parser_route,
                pdf_classification,
                fallback_used,
                token_count,
                page_count,
                parsed_format,
                parsed_path,
                parsed_pages_path,
                parser_meta,
            )

            await self._transition_job(
                job_id,
                status="COMPLETED",
                stage="READY_FOR_REFERENCE_SELECTION",
                message="Document processed and indexed. Select reference documents to begin review.",
            )
        except Exception as exc:
            await asyncio.to_thread(self._mark_failed, job_id, exc)
            snapshot = await asyncio.to_thread(self.get_job_snapshot, job_id)
            if snapshot:
                await self.event_bus.publish(job_id, snapshot.model_dump(mode="json"))

    async def _parse_via_mistral_ocr(self, job_id: uuid.UUID, file_path: Path, mime_type: str):
        if not self.settings.mistral_api_key:
            raise RuntimeError("MISTRAL_API_KEY is required for Mistral OCR fallback/parsing.")

        async def progress_cb(message: str) -> None:
            await self._touch_job(
                job_id,
                message=message,
                stage="PARSING_MISTRAL_OCR",
                progress_pct=STAGE_PROGRESS["PARSING_MISTRAL_OCR"],
            )

        return await parse_with_mistral_ocr(
            file_path=file_path,
            mime_type=mime_type,
            api_key=self.settings.mistral_api_key,
            model=self.settings.mistral_ocr_model,
            progress_cb=progress_cb,
        )

    def _index_document_chunks(self, document_id: uuid.UUID, parsed_pages: list[dict[str, Any]]) -> int:
        pages = [
            DpaPageRecord(page=row["page_no"], text=row["page_text"])
            for row in parsed_pages
            if isinstance(row, dict) and isinstance(row.get("page_no"), int) and isinstance(row.get("page_text"), str)
        ]
        return self.document_indexer.index_document(document_id=document_id, pages=pages)

    def _get_job_record(self, job_id: uuid.UUID) -> dict[str, Any] | None:
        with self.session_factory() as session:
            row = session.execute(
                select(DocumentParseJob, Document)
                .join(Document, Document.id == DocumentParseJob.document_id)
                .where(DocumentParseJob.id == job_id)
            ).first()
            if not row:
                return None
            job, doc = row
            return {
                "job_id": job.id,
                "document_id": doc.id,
                "project_id": doc.project_id,
                "file_type": job.file_type,
                "filename": doc.filename,
                "mime_type": doc.mime_type,
                "page_count": doc.page_count,
                "document_storage_uri": doc.storage_uri,
            }

    async def _transition_job(
        self,
        job_id: uuid.UUID,
        *,
        status: str | None = None,
        stage: str,
        message: str | None = None,
    ) -> None:
        progress_pct = STAGE_PROGRESS.get(stage, 0)
        await self._touch_job(job_id, status=status, stage=stage, progress_pct=progress_pct, message=message)

    async def _touch_job(
        self,
        job_id: uuid.UUID,
        *,
        status: str | None = None,
        stage: str | None = None,
        progress_pct: int | None = None,
        message: str | None = None,
    ) -> None:
        await asyncio.to_thread(self._touch_job_sync, job_id, status, stage, progress_pct, message)
        snapshot = await asyncio.to_thread(self.get_job_snapshot, job_id)
        if snapshot:
            await self.event_bus.publish(job_id, snapshot.model_dump(mode="json"))

    def _touch_job_sync(
        self,
        job_id: uuid.UUID,
        status: str | None,
        stage: str | None,
        progress_pct: int | None,
        message: str | None,
    ) -> None:
        with self.session_factory() as session:
            job = session.get(DocumentParseJob, job_id)
            if job is None:
                return
            if status is not None:
                job.status = status
                if status == "RUNNING" and job.started_at is None:
                    job.started_at = utcnow()
                if status in {"COMPLETED", "FAILED"}:
                    job.completed_at = utcnow()
            if stage is not None:
                job.stage = stage
            if progress_pct is not None:
                job.progress_pct = progress_pct
            if message is not None:
                job.message = message
            job.updated_at = utcnow()

            document = session.get(Document, job.document_id)
            if document is not None and status is not None:
                document.parse_status = status
            self._sync_project_state(session, job.project_id)
            session.commit()

    async def _update_job_details(
        self,
        job_id: uuid.UUID,
        *,
        pdf_classification: str | None = None,
        parser_route: str | None = None,
        token_count_estimate: int | None = None,
        fallback_used: bool | None = None,
        meta_merge: dict[str, Any] | None = None,
    ) -> None:
        await asyncio.to_thread(
            self._update_job_details_sync,
            job_id,
            pdf_classification,
            parser_route,
            token_count_estimate,
            fallback_used,
            meta_merge,
        )
        snapshot = await asyncio.to_thread(self.get_job_snapshot, job_id)
        if snapshot:
            await self.event_bus.publish(job_id, snapshot.model_dump(mode="json"))

    def _update_job_details_sync(
        self,
        job_id: uuid.UUID,
        pdf_classification: str | None,
        parser_route: str | None,
        token_count_estimate: int | None,
        fallback_used: bool | None,
        meta_merge: dict[str, Any] | None,
    ) -> None:
        with self.session_factory() as session:
            job = session.get(DocumentParseJob, job_id)
            if job is None:
                return
            if pdf_classification is not None:
                job.pdf_classification = pdf_classification
            if parser_route is not None:
                job.parser_route = parser_route
            if token_count_estimate is not None:
                job.token_count_estimate = token_count_estimate
            if fallback_used is not None:
                job.fallback_used = fallback_used
            if meta_merge:
                meta = dict(job.meta_json or {})
                meta.update(meta_merge)
                job.meta_json = meta
            job.updated_at = utcnow()
            self._sync_project_state(session, job.project_id)
            session.commit()

    def _finalize_success(
        self,
        job_id: uuid.UUID,
        parser_route: str,
        pdf_classification: str | None,
        fallback_used: bool,
        token_count_estimate: int,
        page_count: int,
        parsed_format: str,
        parsed_path: Path,
        parsed_pages_path: Path,
        parser_meta: dict[str, Any],
    ) -> None:
        with self.session_factory() as session:
            job = session.get(DocumentParseJob, job_id)
            if job is None:
                return
            doc = session.get(Document, job.document_id)
            if doc is None:
                return

            job.parser_route = parser_route
            job.pdf_classification = pdf_classification
            job.fallback_used = fallback_used
            job.token_count_estimate = token_count_estimate
            meta = dict(job.meta_json or {})
            meta["parser_meta"] = parser_meta
            meta["parsed_pages_uri"] = str(parsed_pages_path)
            job.meta_json = meta
            job.updated_at = utcnow()

            doc.page_count = page_count
            doc.parser_route = parser_route
            doc.pdf_classification = pdf_classification
            doc.token_count_estimate = token_count_estimate
            doc.extracted_text_uri = str(parsed_path)
            doc.extracted_text_format = parsed_format
            doc.parse_completed_at = utcnow()
            doc.parse_status = "COMPLETED"

            self._sync_project_state(session, job.project_id)
            session.commit()

    def _mark_failed(self, job_id: uuid.UUID, exc: Exception) -> None:
        with self.session_factory() as session:
            job = session.get(DocumentParseJob, job_id)
            if job is None:
                return
            job.status = "FAILED"
            job.stage = "FAILED"
            job.progress_pct = STAGE_PROGRESS["FAILED"]
            job.error_code = exc.__class__.__name__
            job.error_message = str(exc)
            job.message = "Processing failed."
            job.updated_at = utcnow()
            if job.started_at is None:
                job.started_at = utcnow()
            job.completed_at = utcnow()

            doc = session.get(Document, job.document_id)
            if doc is not None:
                doc.parse_status = "FAILED"
            self._sync_project_state(session, job.project_id)
            session.commit()

    def get_job_snapshot(self, job_id: uuid.UUID) -> UploadJobSnapshot | None:
        with self.session_factory() as session:
            row = session.execute(
                select(DocumentParseJob, Document)
                .join(Document, Document.id == DocumentParseJob.document_id)
                .where(DocumentParseJob.id == job_id)
            ).first()
            if not row:
                return None
            job, doc = row
            return self._build_upload_snapshot(job, doc)

    def get_job_result(self, job_id: uuid.UUID) -> dict[str, Any]:
        snapshot = self.get_job_snapshot(job_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="Upload job not found.")
        if snapshot.status != "COMPLETED" or snapshot.result is None:
            raise HTTPException(status_code=409, detail="Upload job is not completed yet.")
        return snapshot.model_dump(mode="json")

    def list_reference_sources(self) -> list[ReferenceSource]:
        manifest_path = self.settings.repo_root / "kb" / "manifest.json"
        if not manifest_path.exists():
            raise HTTPException(status_code=500, detail="KB manifest not found.")
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        sources = payload.get("sources")
        if not isinstance(sources, list):
            raise HTTPException(status_code=500, detail="KB manifest is invalid.")
        return [
            ReferenceSource(
                source_id=src["source_id"],
                title=src["title"],
                authority=src["authority"],
                kind=src["kind"],
                url=src["url"],
            )
            for src in sources
        ]

    async def create_checklist_draft(
        self,
        *,
        document_id: uuid.UUID,
        selected_source_ids: list[str],
        user_instruction: str | None,
    ) -> ChecklistDraftBootstrapResponse:
        selected_source_ids = [source_id for source_id in selected_source_ids if source_id]
        if not selected_source_ids:
            raise HTTPException(status_code=400, detail="At least one reference source must be selected.")

        valid_sources = {src.source_id for src in self.list_reference_sources()}
        unknown = [sid for sid in selected_source_ids if sid not in valid_sources]
        if unknown:
            raise HTTPException(status_code=400, detail=f"Unknown reference source ids: {unknown}")

        draft_id = uuid.uuid4()
        project_id = await asyncio.to_thread(self._get_project_id_for_document, document_id)
        created = await asyncio.to_thread(
            self._create_checklist_draft_job,
            draft_id,
            document_id,
            selected_source_ids,
            user_instruction.strip() if user_instruction and user_instruction.strip() else None,
        )
        await self._schedule_checklist_job(created)
        return ChecklistDraftBootstrapResponse(
            checklist_draft_id=created,
            document_id=document_id,
            project_id=project_id,
            status="QUEUED",
            ws_url=f"/v1/checklist-drafts/{created}/events",
            status_url=f"/v1/checklist-drafts/{created}",
        )

    def _get_project_id_for_document(self, document_id: uuid.UUID) -> uuid.UUID:
        with self.session_factory() as session:
            document = session.get(Document, document_id)
            if document is None:
                raise HTTPException(status_code=404, detail="Document not found.")
            return document.project_id

    def _create_checklist_draft_job(
        self,
        draft_id: uuid.UUID,
        document_id: uuid.UUID,
        selected_source_ids: list[str],
        user_instruction: str | None,
    ) -> uuid.UUID:
        with self.session_factory() as session:
            document = session.get(Document, document_id)
            if document is None:
                raise HTTPException(status_code=404, detail="Document not found.")
            if document.parse_status != "COMPLETED" or not document.extracted_text_uri:
                raise HTTPException(status_code=409, detail="Document parsing must complete before checklist generation.")

            job = ChecklistDraftJob(
                id=draft_id,
                tenant_id=document.tenant_id,
                project_id=document.project_id,
                document_id=document.id,
                status="QUEUED",
                stage="QUEUED",
                progress_pct=CHECKLIST_STAGE_PROGRESS["QUEUED"],
                message="Starting checklist generation.",
                selected_source_ids=selected_source_ids,
                user_instruction=user_instruction,
            )
            session.add(job)
            self._sync_project_state(session, document.project_id)
            session.commit()
            return draft_id

    async def _run_checklist_job(self, draft_id: uuid.UUID) -> None:
        try:
            await self._transition_checklist_job(
                draft_id,
                status="RUNNING",
                stage="RETRIEVING_KB",
                message="Preparing the selected references.",
            )
            record = await asyncio.to_thread(self._get_checklist_job_record, draft_id)
            if record is None:
                return

            loop = asyncio.get_running_loop()

            def progress_cb(stage: str, message: str) -> None:
                fut = asyncio.run_coroutine_threadsafe(
                    self._transition_checklist_job(draft_id, stage=stage, message=message),
                    loop,
                )
                fut.result()

            result = await asyncio.to_thread(
                self.checklist_agent.generate,
                document_id=record["document_id"],
                selected_source_ids=record["selected_source_ids"],
                user_instruction=record["user_instruction"],
                parsed_markdown_path=record["parsed_markdown_path"],
                parsed_pages_path=record["parsed_pages_path"],
                progress_cb=progress_cb,
            )
            finalized = await asyncio.to_thread(self._finalize_checklist_success, draft_id, result)
            if not finalized:
                return
            await self._transition_checklist_job(
                draft_id,
                status="COMPLETED",
                stage="COMPLETED",
                message="Checklist is ready for review.",
            )
        except asyncio.CancelledError:
            snapshot = await asyncio.to_thread(self.get_checklist_draft_snapshot, draft_id)
            if snapshot:
                await self.event_bus.publish(draft_id, snapshot.model_dump(mode="json"))
            raise
        except Exception as exc:
            await asyncio.to_thread(self._mark_checklist_failed, draft_id, exc)
            snapshot = await asyncio.to_thread(self.get_checklist_draft_snapshot, draft_id)
            if snapshot:
                await self.event_bus.publish(draft_id, snapshot.model_dump(mode="json"))

    def _get_checklist_job_record(self, draft_id: uuid.UUID) -> dict[str, Any] | None:
        with self.session_factory() as session:
            row = session.execute(
                select(ChecklistDraftJob, Document)
                .join(Document, Document.id == ChecklistDraftJob.document_id)
                .where(ChecklistDraftJob.id == draft_id)
            ).first()
            if not row:
                return None
            job, doc = row
            parse_job = session.execute(
                select(DocumentParseJob)
                .where(DocumentParseJob.document_id == doc.id)
                .order_by(DocumentParseJob.created_at.desc())
            ).scalars().first()
            parsed_pages_uri = None
            if parse_job is not None and isinstance(parse_job.meta_json, dict):
                value = parse_job.meta_json.get("parsed_pages_uri")
                if isinstance(value, str) and value:
                    parsed_pages_uri = Path(value)
            return {
                "document_id": doc.id,
                "selected_source_ids": list(job.selected_source_ids or []),
                "user_instruction": job.user_instruction,
                "parsed_markdown_path": Path(doc.extracted_text_uri),
                "parsed_pages_path": parsed_pages_uri,
            }

    async def _transition_checklist_job(
        self,
        draft_id: uuid.UUID,
        *,
        status: str | None = None,
        stage: str,
        message: str | None = None,
    ) -> None:
        progress_pct = await asyncio.to_thread(self._resolve_checklist_progress_sync, draft_id, stage)
        await asyncio.to_thread(self._touch_checklist_job_sync, draft_id, status, stage, progress_pct, message)
        snapshot = await asyncio.to_thread(self.get_checklist_draft_snapshot, draft_id)
        if snapshot:
            await self.event_bus.publish(draft_id, snapshot.model_dump(mode="json"))

    def _resolve_checklist_progress_sync(self, draft_id: uuid.UUID, stage: str) -> int:
        mapped_progress = CHECKLIST_STAGE_PROGRESS.get(stage)
        with self.session_factory() as session:
            job = session.get(ChecklistDraftJob, draft_id)
            current_progress = job.progress_pct if job is not None else 0
        if mapped_progress is None:
            return current_progress
        return max(current_progress, mapped_progress)

    def _touch_checklist_job_sync(
        self,
        draft_id: uuid.UUID,
        status: str | None,
        stage: str | None,
        progress_pct: int | None,
        message: str | None,
    ) -> None:
        with self.session_factory() as session:
            job = session.get(ChecklistDraftJob, draft_id)
            if job is None:
                return
            if job.status in {"FAILED", "COMPLETED"} and status not in {"FAILED", "COMPLETED"}:
                return
            if status is not None:
                job.status = status
                if status == "RUNNING" and job.started_at is None:
                    job.started_at = utcnow()
                if status in {"COMPLETED", "FAILED"}:
                    job.completed_at = utcnow()
            if stage is not None:
                job.stage = stage
            if progress_pct is not None:
                job.progress_pct = progress_pct
            if message is not None:
                job.message = message
            job.updated_at = utcnow()
            self._sync_project_state(session, job.project_id)
            session.commit()

    def _finalize_checklist_success(self, draft_id: uuid.UUID, result: ChecklistDraftOutput) -> bool:
        with self.session_factory() as session:
            job = session.get(ChecklistDraftJob, draft_id)
            if job is None:
                return False
            if job.status in {"FAILED", "COMPLETED"}:
                return False
            job.result_json = result.model_dump(mode="json")
            job.updated_at = utcnow()
            self._sync_project_state(session, job.project_id)
            session.commit()
            return True

    def _mark_checklist_failed(self, draft_id: uuid.UUID, exc: Exception) -> None:
        with self.session_factory() as session:
            job = session.get(ChecklistDraftJob, draft_id)
            if job is None:
                return
            job.status = "FAILED"
            job.stage = "FAILED"
            job.progress_pct = CHECKLIST_STAGE_PROGRESS["FAILED"]
            job.error_code = exc.__class__.__name__
            job.error_message = str(exc)
            job.message = "Checklist generation failed."
            job.updated_at = utcnow()
            if job.started_at is None:
                job.started_at = utcnow()
            job.completed_at = utcnow()
            self._sync_project_state(session, job.project_id)
            session.commit()

    def _cancel_checklist_draft_sync(self, draft_id: uuid.UUID) -> None:
        with self.session_factory() as session:
            job = session.get(ChecklistDraftJob, draft_id)
            if job is None:
                raise HTTPException(status_code=404, detail="Checklist draft job not found.")
            if job.status in {"COMPLETED", "FAILED"}:
                return
            job.status = "FAILED"
            job.stage = "FAILED"
            job.progress_pct = CHECKLIST_STAGE_PROGRESS["FAILED"]
            job.error_code = "UserCanceled"
            job.error_message = "Checklist generation was stopped by the user."
            job.message = "Checklist generation was stopped."
            if job.started_at is None:
                job.started_at = utcnow()
            job.completed_at = utcnow()
            job.updated_at = utcnow()
            self._sync_project_state(session, job.project_id)
            session.commit()

    def get_checklist_draft_snapshot(self, draft_id: uuid.UUID) -> ChecklistDraftSnapshot | None:
        with self.session_factory() as session:
            row = session.execute(
                select(ChecklistDraftJob, Document)
                .join(Document, Document.id == ChecklistDraftJob.document_id)
                .where(ChecklistDraftJob.id == draft_id)
            ).first()
            if not row:
                return None
            job, doc = row
            return self._build_checklist_snapshot(job, doc)

    def create_review_setup(self, *, document_id: uuid.UUID, selected_source_ids: list[str]) -> ReviewSetupResponse:
        if not selected_source_ids:
            raise HTTPException(status_code=400, detail="At least one reference source must be selected.")

        valid_sources = {src.source_id for src in self.list_reference_sources()}
        unknown = [sid for sid in selected_source_ids if sid not in valid_sources]
        if unknown:
            raise HTTPException(status_code=400, detail=f"Unknown reference source ids: {unknown}")

        with self.session_factory() as session:
            document = session.get(Document, document_id)
            if document is None:
                raise HTTPException(status_code=404, detail="Document not found.")
            tenant_id = document.tenant_id

            run = AnalysisRun(
                tenant_id=tenant_id,
                project_id=document.project_id,
                document_id=document.id,
                status="QUEUED",
                model_version="placeholder-upload-setup",
                policy_version="kb-v1",
            )
            session.add(run)
            session.flush()

            latest_job = session.execute(
                select(DocumentParseJob)
                .where(DocumentParseJob.document_id == document.id)
                .order_by(DocumentParseJob.created_at.desc())
            ).scalars().first()
            if latest_job is not None:
                meta = dict(latest_job.meta_json or {})
                meta["selected_source_ids"] = selected_source_ids
                meta["analysis_run_id"] = str(run.id)
                latest_job.meta_json = meta
                latest_job.updated_at = utcnow()

            self._sync_project_state(session, document.project_id)
            session.commit()
            return ReviewSetupResponse(
                analysis_run_id=run.id,
                document_id=document.id,
                project_id=document.project_id,
                selected_source_ids=selected_source_ids,
                status=run.status,
            )

    def get_approved_checklist(self, project_id: uuid.UUID) -> ApprovedChecklistResponse | None:
        with self.session_factory() as session:
            tenant = self._ensure_dev_tenant(session)
            checklist = session.execute(
                select(ApprovedChecklist)
                .where(ApprovedChecklist.project_id == project_id, ApprovedChecklist.tenant_id == tenant.id)
                .order_by(ApprovedChecklist.created_at.desc())
            ).scalars().first()
            if checklist is None:
                return None
            document = ChecklistDocument.model_validate(checklist.checklist_json)
            return ApprovedChecklistResponse(
                **self._build_approved_checklist_summary(checklist).model_dump(mode="python"),
                checklist=document,
            )

    def approve_checklist(self, project_id: uuid.UUID, payload: ApproveChecklistRequest) -> ApprovedChecklistResponse:
        valid_sources = {src.source_id for src in self.list_reference_sources()}
        unknown = [sid for sid in payload.selected_source_ids if sid not in valid_sources]
        if unknown:
            raise HTTPException(status_code=400, detail=f"Unknown reference source ids: {unknown}")

        with self.session_factory() as session:
            tenant = self._ensure_dev_tenant(session)
            project = session.execute(
                select(Project).where(Project.id == project_id, Project.tenant_id == tenant.id)
            ).scalar_one_or_none()
            if project is None:
                raise HTTPException(status_code=404, detail="Project not found.")
            document = self._latest_document_for_project(session, project_id)
            if document is None:
                raise HTTPException(status_code=409, detail="Project has no uploaded document.")
            governance = ChecklistGovernance(
                owner=DEFAULT_APPROVAL_OWNER,
                approval_status=ApprovalStatus.APPROVED,
                approved_by=DEFAULT_APPROVED_BY,
                approved_at=utcnow(),
                policy_version=payload.version,
                change_note=payload.change_note,
            )
            checklist = ChecklistDocument(version=payload.version, governance=governance, checks=payload.checks)
            row = ApprovedChecklist(
                tenant_id=tenant.id,
                project_id=project.id,
                document_id=document.id,
                version=checklist.version,
                selected_source_ids=payload.selected_source_ids,
                checklist_json=checklist.model_dump(mode="json"),
                owner=governance.owner,
                approval_status=governance.approval_status.value,
                approved_by=governance.approved_by,
                approved_at=governance.approved_at,
                change_note=governance.change_note,
            )
            session.add(row)
            self._sync_project_state(session, project.id)
            session.commit()
            session.refresh(row)
            return ApprovedChecklistResponse(
                **self._build_approved_checklist_summary(row).model_dump(mode="python"),
                checklist=checklist,
            )

    async def create_analysis_run(self, payload: CreateAnalysisRunRequest) -> AnalysisRunBootstrapResponse:
        run_id = await asyncio.to_thread(self._create_analysis_run_sync, payload.project_id)
        await self._schedule_analysis_run(run_id)
        snapshot = await asyncio.to_thread(self.get_analysis_run_snapshot, run_id)
        if snapshot is None:
            raise HTTPException(status_code=500, detail="Failed to load analysis run.")
        return AnalysisRunBootstrapResponse(
            **snapshot.model_dump(mode="python"),
            ws_url=f"/v1/analysis-runs/{run_id}/events",
            status_url=f"/v1/analysis-runs/{run_id}",
        )

    def _create_analysis_run_sync(self, project_id: uuid.UUID) -> uuid.UUID:
        with self.session_factory() as session:
            tenant = self._ensure_dev_tenant(session)
            project = session.execute(
                select(Project).where(Project.id == project_id, Project.tenant_id == tenant.id)
            ).scalar_one_or_none()
            if project is None:
                raise HTTPException(status_code=404, detail="Project not found.")
            document = self._latest_document_for_project(session, project_id)
            if document is None or document.parse_status != "COMPLETED":
                raise HTTPException(status_code=409, detail="Project document must be parsed before final review.")
            approved = self._latest_approved_checklist_for_project(session, project_id)
            if approved is None:
                raise HTTPException(status_code=409, detail="An approved checklist is required before final review.")
            run = AnalysisRun(
                tenant_id=tenant.id,
                project_id=project.id,
                document_id=document.id,
                status="QUEUED",
                model_version=self.settings.gemini_review_model,
                policy_version=approved.version,
                stage="QUEUED",
                progress_pct=ANALYSIS_STAGE_PROGRESS["QUEUED"],
                message="Final review queued.",
                approved_checklist_id=approved.id,
            )
            session.add(run)
            self._sync_project_state(session, project.id)
            session.commit()
            return run.id

    def get_analysis_run_snapshot(self, run_id: uuid.UUID) -> AnalysisRunSnapshot | None:
        with self.session_factory() as session:
            run = session.get(AnalysisRun, run_id)
            if run is None:
                return None
            finding_count = len(
                session.execute(select(Finding.id).where(Finding.run_id == run.id)).scalars().all()
            )
            return AnalysisRunSnapshot(
                **self._build_analysis_run_summary(session, run).model_dump(mode="python"),
                finding_count=finding_count,
            )

    def get_analysis_report(self, run_id: uuid.UUID) -> AnalysisRunReportResponse:
        with self.session_factory() as session:
            run = session.get(AnalysisRun, run_id)
            if run is None:
                raise HTTPException(status_code=404, detail="Analysis run not found.")
            report = session.get(AnalysisReport, run_id)
            if report is None:
                raise HTTPException(status_code=404, detail="Analysis report not found.")
            approved = session.get(ApprovedChecklist, run.approved_checklist_id)
            approved_document = ChecklistDocument.model_validate(approved.checklist_json) if approved is not None else None
            title_map = {check.check_id: check.title for check in approved_document.checks} if approved_document else {}
            category_map = {check.check_id: check.category for check in approved_document.checks} if approved_document else {}

            payload = OutputV2Report.model_validate(report.report_json)
            report_check_map = {check.check_id: check for check in payload.checks}
            findings = session.execute(
                select(Finding)
                .where(Finding.run_id == run_id)
                .order_by(Finding.check_id.asc())
            ).scalars().all()
            finding_rows = []
            for finding in findings:
                assessment = CheckAssessmentOutput.model_validate(finding.assessment_json or {})
                report_check = report_check_map.get(finding.check_id)
                finding_rows.append(
                    AnalysisFindingDetail(
                        check_id=finding.check_id,
                        title=title_map.get(finding.check_id, finding.check_id),
                        category=category_map.get(finding.check_id, finding.category),
                        assessment=assessment,
                        citation_pages=list(report_check.citation_pages if report_check else []),
                        evidence_span_offsets=list(report_check.evidence_span_offsets if report_check else []),
                    )
                )
            return AnalysisRunReportResponse(report=payload, findings=finding_rows)

    async def _run_analysis_run(self, run_id: uuid.UUID) -> None:
        started_at = utcnow()
        try:
            await self._transition_analysis_run(
                run_id,
                status="RUNNING",
                stage="PREFETCHING_EVIDENCE",
                message="Loading approved checklist and preparing evidence.",
            )
            record = await asyncio.to_thread(self._get_analysis_run_record, run_id)
            if record is None:
                return

            approved_checklist = record["approved_checklist"]
            dpa_pages = record["dpa_pages"]
            if not record["chunk_count"]:
                raise RuntimeError("Document index is missing. Re-parse the document to regenerate chunks.")

            checks = approved_checklist.checks
            total_checks = len(checks)
            concurrency = min(6, total_checks or 1)
            prefetch_count = 0
            completed_checks = 0
            prefetch_semaphore = asyncio.Semaphore(concurrency)
            review_semaphore = asyncio.Semaphore(concurrency)

            async def prefetch_one(check):
                nonlocal prefetch_count
                async with prefetch_semaphore:
                    evidence = await asyncio.to_thread(
                        self.review_agent.prefetch_evidence,
                        document_id=record["document_id"],
                        query=self._build_check_query(check),
                        sources=record["sources"],
                        dpa_pages=dpa_pages,
                        kb_top_k=4,
                        dpa_top_k=6,
                    )
                prefetch_count += 1
                progress = 18 + int((prefetch_count / max(total_checks, 1)) * 18)
                await self._transition_analysis_run(
                    run_id,
                    stage="PREFETCHING_EVIDENCE",
                    message=f"Prepared evidence for {prefetch_count}/{total_checks} checklist items.",
                    progress_pct=progress,
                )
                return evidence

            prefetched_evidence = await asyncio.gather(*(prefetch_one(check) for check in checks))

            async def review_one(index: int, check) -> CheckAssessmentOutput:
                nonlocal completed_checks
                async with review_semaphore:
                    result = await asyncio.to_thread(
                        self._review_single_check_with_retry,
                        record["document_id"],
                        approved_checklist,
                        check,
                        record["sources"],
                        dpa_pages,
                        prefetched_evidence[index],
                    )
                await asyncio.to_thread(
                    self._persist_partial_assessment,
                    run_id,
                    approved_checklist,
                    result,
                    dpa_pages,
                )
                completed_checks += 1
                progress = 36 + int((completed_checks / max(total_checks, 1)) * 46)
                finding_count = await asyncio.to_thread(self._count_findings_for_run, run_id)
                await self._transition_analysis_run(
                    run_id,
                    stage="REVIEWING_CHECKS",
                    message=f"Reviewed {completed_checks}/{total_checks} checklist items. Saved {finding_count} findings.",
                    progress_pct=progress,
                )
                return result

            assessments = await asyncio.gather(*(review_one(index, check) for index, check in enumerate(checks)))

            await self._transition_analysis_run(
                run_id,
                stage="SYNTHESIZING",
                message="Synthesizing final review report.",
            )
            synthesis = await asyncio.to_thread(
                self._synthesize_with_retry,
                approved_checklist,
                assessments,
            )
            await asyncio.to_thread(
                self._persist_analysis_result,
                run_id,
                approved_checklist,
                assessments,
                synthesis,
                dpa_pages,
                started_at,
            )
            await self._transition_analysis_run(
                run_id,
                status="COMPLETED",
                stage="COMPLETED",
                message="Final review complete.",
            )
        except Exception as exc:
            await asyncio.to_thread(self._mark_analysis_failed, run_id, exc)
            snapshot = await asyncio.to_thread(self.get_analysis_run_snapshot, run_id)
            if snapshot:
                await self.event_bus.publish(run_id, snapshot.model_dump(mode="json"))

    def _get_analysis_run_record(self, run_id: uuid.UUID) -> dict[str, Any] | None:
        with self.session_factory() as session:
            run = session.get(AnalysisRun, run_id)
            if run is None:
                return None
            document = session.get(Document, run.document_id)
            if document is None:
                raise RuntimeError("Document not found for analysis run.")
            approved = session.get(ApprovedChecklist, run.approved_checklist_id)
            if approved is None:
                raise RuntimeError("Approved checklist not found for analysis run.")
            parse_job = session.execute(
                select(DocumentParseJob)
                .where(DocumentParseJob.document_id == document.id)
                .order_by(DocumentParseJob.created_at.desc())
            ).scalars().first()
            parsed_pages_uri = None
            if parse_job is not None and isinstance(parse_job.meta_json, dict):
                value = parse_job.meta_json.get("parsed_pages_uri")
                if isinstance(value, str) and value:
                    parsed_pages_uri = Path(value)
            chunk_count = len(
                session.execute(select(DocumentChunk.id).where(DocumentChunk.document_id == document.id)).scalars().all()
            )
            return {
                "document_id": document.id,
                "selected_source_ids": list(approved.selected_source_ids or []),
                "approved_checklist": ChecklistDocument.model_validate(approved.checklist_json),
                "sources": self.review_agent.load_sources(list(approved.selected_source_ids or [])),
                "dpa_pages": self._load_dpa_pages(Path(document.extracted_text_uri), parsed_pages_uri),
                "chunk_count": chunk_count,
            }

    def _load_dpa_pages(self, parsed_markdown_path: Path, parsed_pages_path: Path | None) -> list[DpaPageRecord]:
        if parsed_pages_path and parsed_pages_path.exists():
            payload = json.loads(parsed_pages_path.read_text(encoding="utf-8"))
            pages_raw = payload.get("pages")
            if isinstance(pages_raw, list):
                pages: list[DpaPageRecord] = []
                for row in pages_raw:
                    if not isinstance(row, dict):
                        continue
                    page_no = row.get("page_no")
                    page_text = row.get("page_text")
                    if isinstance(page_no, int) and isinstance(page_text, str):
                        pages.append(DpaPageRecord(page=page_no, text=page_text))
                if pages:
                    return pages

        text = parsed_markdown_path.read_text(encoding="utf-8")
        matches = list(re.finditer(r"(?m)^page_no:\s*(\d+)\s*$", text))
        pages = []
        for index, match in enumerate(matches):
            page = int(match.group(1))
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            block = text[start:end]
            text_match = re.search(r"page_text:\n(?P<body>.*?)(?:\npage_images:|\Z)", block, flags=re.S)
            body = text_match.group("body").strip() if text_match else block.strip()
            pages.append(DpaPageRecord(page=page, text=body))
        return pages

    def _review_single_check_with_retry(
        self,
        document_id: uuid.UUID,
        approved_checklist: ChecklistDocument,
        check,
        sources,
        dpa_pages: list[DpaPageRecord],
        prefetched_evidence,
    ) -> CheckAssessmentOutput:
        last_exc: Exception | None = None
        for _ in range(2):
            try:
                return self.review_agent.assess_check(
                    document_id=document_id,
                    approved_checklist=approved_checklist,
                    check=check,
                    sources=sources,
                    dpa_pages=dpa_pages,
                    prefetched_evidence=prefetched_evidence,
                )
            except Exception as exc:  # noqa: PERF203 - bounded retries
                last_exc = exc
        return self._fallback_assessment(check, last_exc)

    def _synthesize_with_retry(
        self,
        approved_checklist: ChecklistDocument,
        assessments: list[CheckAssessmentOutput],
    ) -> ReviewSynthesisOutput:
        last_exc: Exception | None = None
        for _ in range(2):
            try:
                return self.review_agent.synthesize(approved_checklist=approved_checklist, assessments=assessments)
            except Exception as exc:  # noqa: PERF203 - bounded retries
                last_exc = exc
        raise RuntimeError(f"Failed to synthesize final review output: {last_exc}")

    def _persist_analysis_result(
        self,
        run_id: uuid.UUID,
        approved_checklist: ChecklistDocument,
        assessments: list[CheckAssessmentOutput],
        synthesis: ReviewSynthesisOutput,
        dpa_pages: list[DpaPageRecord],
        started_at: datetime,
    ) -> None:
        check_map = {check.check_id: check for check in approved_checklist.checks}
        final_checks: list[CheckResult] = []
        all_pages: set[int] = set()
        all_spans = []

        for assessment in assessments:
            check = check_map.get(assessment.check_id)
            if check is None:
                continue
            citation_pages, evidence_spans = derive_evidence_metadata(dpa_pages, assessment.evidence_quotes)
            all_pages.update(citation_pages)
            all_spans.extend(evidence_spans)
            final_checks.append(
                CheckResult(
                    check_id=assessment.check_id,
                    category=check.category,
                    status=assessment.status,
                    risk=assessment.risk,
                    confidence=assessment.confidence,
                    abstained=assessment.abstained,
                    abstain_reason=assessment.abstain_reason,
                    review_required=self._derive_review_required(assessment, evidence_spans),
                    review_state=ReviewState.PENDING,
                    citation_pages=citation_pages,
                    evidence_span_offsets=evidence_spans,
                    risk_rationale=assessment.risk_rationale,
                )
            )

        report = OutputV2Report(
            run_id=str(run_id),
            model_version=self.settings.gemini_review_model,
            policy_version=approved_checklist.version,
            overall=synthesis.overall,
            checks=final_checks,
            highlights=synthesis.highlights,
            next_actions=synthesis.next_actions,
            confidence=synthesis.confidence,
            abstained=synthesis.abstained,
            abstain_reason=synthesis.abstain_reason,
            review_required=any(check.review_required for check in final_checks) or synthesis.abstained,
            review_state=ReviewState.PENDING,
            citation_pages=sorted(all_pages),
            evidence_span_offsets=all_spans,
            risk_rationale=synthesis.risk_rationale,
        )

        with self.session_factory() as session:
            for assessment in assessments:
                self._upsert_finding(session, run_id, check_map, assessment, dpa_pages)

            existing_report = session.get(AnalysisReport, run_id)
            if existing_report is None:
                session.add(AnalysisReport(run_id=run_id, report_json=report.model_dump(mode="json")))
            else:
                existing_report.report_json = report.model_dump(mode="json")
                existing_report.updated_at = utcnow()

            run = session.get(AnalysisRun, run_id)
            if run is None:
                raise RuntimeError("Analysis run not found during persistence.")
            run.completed_at = utcnow()
            run.latency_ms = int((run.completed_at - started_at).total_seconds() * 1000)
            run.message = "Final review complete."
            run.progress_pct = ANALYSIS_STAGE_PROGRESS["COMPLETED"]
            run.stage = "COMPLETED"
            self._sync_project_state(session, run.project_id)
            session.commit()

    def _persist_partial_assessment(
        self,
        run_id: uuid.UUID,
        approved_checklist: ChecklistDocument,
        assessment: CheckAssessmentOutput,
        dpa_pages: list[DpaPageRecord],
    ) -> None:
        check_map = {check.check_id: check for check in approved_checklist.checks}
        with self.session_factory() as session:
            self._upsert_finding(session, run_id, check_map, assessment, dpa_pages)
            run = session.get(AnalysisRun, run_id)
            if run is not None:
                run.updated_at = utcnow()
                self._sync_project_state(session, run.project_id)
            session.commit()

    def _upsert_finding(
        self,
        session: Session,
        run_id: uuid.UUID,
        check_map: dict[str, Any],
        assessment: CheckAssessmentOutput,
        dpa_pages: list[DpaPageRecord],
    ) -> None:
        check = check_map.get(assessment.check_id)
        if check is None:
            return
        citation_pages, evidence_spans = derive_evidence_metadata(dpa_pages, assessment.evidence_quotes)
        finding = session.execute(
            select(Finding).where(Finding.run_id == run_id, Finding.check_id == assessment.check_id)
        ).scalars().first()
        if finding is None:
            finding = Finding(run_id=run_id, check_id=assessment.check_id, category=check.category)
            session.add(finding)
        finding.category = check.category
        finding.status = assessment.status.value
        finding.risk = assessment.risk.value
        finding.confidence = assessment.confidence
        finding.abstained = assessment.abstained
        finding.abstain_reason = assessment.abstain_reason
        finding.risk_rationale = assessment.risk_rationale
        finding.review_required = self._derive_review_required(assessment, evidence_spans)
        finding.review_state = ReviewState.PENDING.value
        finding.assessment_json = assessment.model_dump(mode="json")

    def _count_findings_for_run(self, run_id: uuid.UUID) -> int:
        with self.session_factory() as session:
            return len(session.execute(select(Finding.id).where(Finding.run_id == run_id)).scalars().all())

    def _derive_review_required(self, assessment: CheckAssessmentOutput, evidence_spans: list) -> bool:
        if assessment.abstained:
            return True
        if assessment.status.value == "UNKNOWN":
            return True
        if assessment.risk == RiskLevel.HIGH and not evidence_spans:
            return True
        return False

    def _fallback_assessment(self, check, exc: Exception | None) -> CheckAssessmentOutput:
        severity = str(getattr(check, "severity", "MEDIUM"))
        fallback_risk = RiskLevel.HIGH if severity in {"HIGH", "MANDATORY"} else RiskLevel.MEDIUM
        abstain_reason = "Reviewer execution failed."
        if exc is not None:
            detail = str(exc).strip()
            abstain_reason = f"{exc.__class__.__name__}: {detail}" if detail else exc.__class__.__name__
        return CheckAssessmentOutput(
            check_id=check.check_id,
            status="UNKNOWN",
            risk=fallback_risk,
            confidence=0.0,
            evidence_quotes=[],
            kb_citations=[],
            missing_elements=[],
            risk_rationale="Review agent failed before a reliable assessment could be completed.",
            abstained=True,
            abstain_reason=abstain_reason,
        )

    def _build_check_query(self, check) -> str:
        parts = [
            check.title,
            check.evidence_hint,
            *check.legal_basis,
            *check.pass_criteria,
            *check.fail_criteria,
        ]
        return "\n".join(part.strip() for part in parts if part and part.strip())

    async def _transition_analysis_run(
        self,
        run_id: uuid.UUID,
        *,
        status: str | None = None,
        stage: str,
        message: str | None = None,
        progress_pct: int | None = None,
    ) -> None:
        if progress_pct is None:
            progress_pct = ANALYSIS_STAGE_PROGRESS.get(stage, 0)
        await asyncio.to_thread(self._touch_analysis_run_sync, run_id, status, stage, progress_pct, message)
        snapshot = await asyncio.to_thread(self.get_analysis_run_snapshot, run_id)
        if snapshot:
            await self.event_bus.publish(run_id, snapshot.model_dump(mode="json"))

    def _touch_analysis_run_sync(
        self,
        run_id: uuid.UUID,
        status: str | None,
        stage: str | None,
        progress_pct: int,
        message: str | None,
    ) -> None:
        with self.session_factory() as session:
            run = session.get(AnalysisRun, run_id)
            if run is None:
                return
            if status is not None:
                run.status = status
                if status == "RUNNING" and run.started_at is None:
                    run.started_at = utcnow()
                if status in {"COMPLETED", "FAILED"}:
                    run.completed_at = utcnow()
            if stage is not None:
                run.stage = stage
            run.progress_pct = progress_pct
            if message is not None:
                run.message = message
            self._sync_project_state(session, run.project_id)
            session.commit()

    def _mark_analysis_failed(self, run_id: uuid.UUID, exc: Exception) -> None:
        with self.session_factory() as session:
            run = session.get(AnalysisRun, run_id)
            if run is None:
                return
            run.status = "FAILED"
            run.stage = "FAILED"
            run.progress_pct = ANALYSIS_STAGE_PROGRESS["FAILED"]
            run.error_code = exc.__class__.__name__
            run.error_message = str(exc)
            run.message = "Final review failed."
            if run.started_at is None:
                run.started_at = utcnow()
            run.completed_at = utcnow()
            run.latency_ms = int((run.completed_at - run.started_at).total_seconds() * 1000)
            self._sync_project_state(session, run.project_id)
            session.commit()
