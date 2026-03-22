from __future__ import annotations

import asyncio
import json
import mimetypes
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from db.models import AnalysisRun, ChecklistDraftJob, Document, DocumentParseJob, Project, Tenant
from dpa_checklist import ChecklistDraftOutput

from .checklist_agent import ChecklistDraftAgent
from .config import Settings
from .events import JobEventBus
from .parsers import (
    estimate_token_count,
    inspect_pdf,
    parse_with_mistral_ocr,
)
from .schemas import (
    AnalysisRunSummary,
    ChecklistDraftBootstrapResponse,
    ChecklistDraftSnapshot,
    CreateProjectResponse,
    ProjectDetail,
    ProjectDocumentSummary,
    ProjectSummary,
    ReferenceSource,
    ReviewSetupResponse,
    UploadBootstrapResponse,
    UploadJobSnapshot,
)
from .storage import LocalStorage


def utcnow() -> datetime:
    return datetime.now(UTC)


STAGE_PROGRESS = {
    "UPLOADING": 5,
    "VALIDATING": 12,
    "CLASSIFYING_PDF": 20,
    "PARSING_MISTRAL_OCR": 58,
    "COUNTING_TOKENS": 80,
    "PERSISTING_RESULTS": 90,
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

ALLOWED_EXTENSIONS = {".pdf": "pdf", ".docx": "docx"}
DEFAULT_DEV_TENANT_NAME = "Local Dev Tenant"
UNTITLED_PROJECT_NAME = "Untitled analysis"


@dataclass(frozen=True)
class UploadCreateResult:
    job_id: uuid.UUID
    document_id: uuid.UUID
    project_id: uuid.UUID


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
        self._tasks_lock = asyncio.Lock()
        self.checklist_agent = ChecklistDraftAgent(settings)

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
        if project is None:
            return None

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
        run_summary = None
        if analysis_run is not None:
            run_summary = AnalysisRunSummary(
                analysis_run_id=analysis_run.id,
                project_id=analysis_run.project_id,
                document_id=analysis_run.document_id,
                status=analysis_run.status,
                model_version=analysis_run.model_version,
                policy_version=analysis_run.policy_version,
                started_at=analysis_run.started_at,
                completed_at=analysis_run.completed_at,
                latency_ms=analysis_run.latency_ms,
                cost_usd=analysis_run.cost_usd,
            )

        return ProjectDetail(
            project=self._build_project_summary(session, project),
            document=doc_summary,
            parse_job=parse_snapshot,
            checklist_draft=checklist_snapshot,
            analysis_run=run_summary,
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
                message="Document processed. Select reference documents to begin review.",
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
                message="Checklist generation queued.",
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
                message="Loading selected regulatory sources.",
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
            await asyncio.to_thread(self._finalize_checklist_success, draft_id, result)
            await self._transition_checklist_job(
                draft_id,
                status="COMPLETED",
                stage="COMPLETED",
                message="Checklist draft is ready for review.",
            )
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
        progress_pct = CHECKLIST_STAGE_PROGRESS.get(stage, 0)
        await asyncio.to_thread(self._touch_checklist_job_sync, draft_id, status, stage, progress_pct, message)
        snapshot = await asyncio.to_thread(self.get_checklist_draft_snapshot, draft_id)
        if snapshot:
            await self.event_bus.publish(draft_id, snapshot.model_dump(mode="json"))

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

    def _finalize_checklist_success(self, draft_id: uuid.UUID, result: ChecklistDraftOutput) -> None:
        with self.session_factory() as session:
            job = session.get(ChecklistDraftJob, draft_id)
            if job is None:
                return
            job.result_json = result.model_dump(mode="json")
            job.updated_at = utcnow()
            self._sync_project_state(session, job.project_id)
            session.commit()

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
