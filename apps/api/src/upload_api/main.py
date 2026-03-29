from __future__ import annotations

import asyncio
import io
import logging
import time
import uuid

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .auth import AuthManager, build_cookie_settings
from .config import load_settings
from .db import build_session_factory
from .events import JobEventBus
from .jobs import UploadPipelineService
from .logging_utils import configure_logging, log_event
from .rate_limits import InMemoryRateLimiter
from .schemas import (
    ApproveChecklistRequest,
    AuthUserResponse,
    ChecklistDraftRequest,
    CreateAnalysisRunRequest,
    CreateProjectRequest,
    LoginRequest,
    RenameProjectRequest,
    ReviewSetupRequest,
)
from .storage import ArtifactStore


configure_logging()

settings = load_settings()
auth_manager = AuthManager(settings)
session_factory = build_session_factory(settings.database_url)
event_bus = JobEventBus()
storage = ArtifactStore.from_settings(settings)
service = UploadPipelineService(
    settings=settings,
    session_factory=session_factory,
    storage=storage,
    event_bus=event_bus,
)
rate_limiter = InMemoryRateLimiter()


def create_app() -> FastAPI:
    app = FastAPI(title="AI DPA Upload API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.app_allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        start = time.perf_counter()
        actor = auth_manager.get_optional_actor_from_request(request)
        if actor is not None:
            request.state.actor_username = actor.username

        try:
            response = await call_next(request)
        except Exception as exc:
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            log_event(
                logging.ERROR,
                severity="error",
                event="http_request_failed",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status_code=500,
                latency_ms=latency_ms,
                actor_username=getattr(request.state, "actor_username", None),
                remote_ip=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
                error_code=exc.__class__.__name__,
                error_message=str(exc),
            )
            raise

        response.headers["X-Request-Id"] = request_id
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        log_event(
            logging.INFO,
            severity="info",
            event="http_request",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            latency_ms=latency_ms,
            actor_username=getattr(request.state, "actor_username", None),
            remote_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        return response

    def request_id_for(request: Request) -> str:
        return getattr(request.state, "request_id", str(uuid.uuid4()))

    def require_actor(request: Request):
        return auth_manager.get_required_actor_from_request(request)

    def request_ip(request: Request) -> str:
        return request.client.host if request.client else "unknown"

    async def enforce_rate_limit(
        *,
        bucket: str,
        subject: str,
        limit: int,
        window_seconds: int,
        request: Request,
        actor_username: str | None,
        detail: str,
        audit_callback=None,
    ) -> None:
        result = rate_limiter.check(
            bucket=bucket,
            subject=subject,
            limit=limit,
            window_seconds=window_seconds,
        )
        if result.allowed:
            return
        if audit_callback is not None:
            await audit_callback(result.retry_after_seconds)
        log_event(
            logging.WARNING,
            severity="warning",
            event="rate_limit_denied",
            request_id=request_id_for(request),
            bucket=bucket,
            subject=subject,
            actor_username=actor_username,
            remote_ip=request_ip(request),
            retry_after_seconds=result.retry_after_seconds,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"{detail} Retry in about {result.retry_after_seconds} seconds.",
        )

    async def reject_websocket(websocket: WebSocket, code: int) -> None:
        await websocket.accept()
        await websocket.close(code=code)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/auth/login", response_model=AuthUserResponse)
    async def login(payload: LoginRequest, request: Request, response: Response):
        auth_manager.require_request_origin(request)
        trace_id = request_id_for(request)
        username = payload.username.strip()
        remote_ip = request_ip(request)
        await enforce_rate_limit(
            bucket="auth_login_ip",
            subject=remote_ip,
            limit=settings.login_rate_limit_per_ip,
            window_seconds=settings.login_rate_limit_window_seconds,
            request=request,
            actor_username=username or None,
            detail="Too many login attempts from this IP.",
            audit_callback=lambda retry_after: asyncio.to_thread(
                service.record_auth_event,
                event_name="auth_login_rate_limited",
                actor_username=username or remote_ip,
                trace_id=trace_id,
                metadata_json={
                    "username": username,
                    "remote_ip": remote_ip,
                    "bucket": "ip",
                    "retry_after_seconds": retry_after,
                },
            ),
        )
        await enforce_rate_limit(
            bucket="auth_login_username",
            subject=username.lower() or remote_ip,
            limit=settings.login_rate_limit_per_username,
            window_seconds=settings.login_rate_limit_window_seconds,
            request=request,
            actor_username=username or None,
            detail="Too many login attempts for this username.",
            audit_callback=lambda retry_after: asyncio.to_thread(
                service.record_auth_event,
                event_name="auth_login_rate_limited",
                actor_username=username or remote_ip,
                trace_id=trace_id,
                metadata_json={
                    "username": username,
                    "remote_ip": remote_ip,
                    "bucket": "username",
                    "retry_after_seconds": retry_after,
                },
            ),
        )
        actor = auth_manager.authenticate(payload.username, payload.password)
        if actor is None:
            await asyncio.to_thread(
                service.record_auth_event,
                event_name="auth_login_failed",
                actor_username=username,
                trace_id=trace_id,
                metadata_json={"username": username, "remote_ip": remote_ip},
            )
            log_event(
                logging.WARNING,
                severity="warning",
                event="auth_login_failed",
                request_id=trace_id,
                actor_username=username,
            )
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password.")

        token = auth_manager.issue_session_token(actor)
        response.set_cookie(value=token, **build_cookie_settings(auth_manager))
        request.state.actor_username = actor.username
        await asyncio.to_thread(
            service.record_auth_event,
            event_name="auth_login_succeeded",
            actor_username=actor.username,
            trace_id=trace_id,
            metadata_json={"username": actor.username},
        )
        return AuthUserResponse(username=actor.username)

    @app.post("/v1/auth/logout")
    async def logout(request: Request, response: Response):
        auth_manager.require_request_origin(request)
        actor = require_actor(request)
        response.delete_cookie(
            key=build_cookie_settings(auth_manager)["key"],
            path="/",
            domain=auth_manager.session_cookie_domain,
            secure=auth_manager.session_cookie_secure,
            httponly=True,
            samesite="lax",
        )
        await asyncio.to_thread(
            service.record_auth_event,
            event_name="auth_logout",
            actor_username=actor.username,
            trace_id=request_id_for(request),
            metadata_json={"username": actor.username},
        )
        return {"status": "ok"}

    @app.get("/v1/auth/me", response_model=AuthUserResponse)
    async def auth_me(request: Request):
        actor = require_actor(request)
        return AuthUserResponse(username=actor.username)

    @app.post("/v1/projects")
    async def create_project(request: Request, payload: CreateProjectRequest | None = None):
        auth_manager.require_request_origin(request)
        actor = require_actor(request)
        return await asyncio.to_thread(
            service.create_project,
            payload.name if payload else None,
            actor_username=actor.username,
            trace_id=request_id_for(request),
        )

    @app.get("/v1/projects")
    async def list_projects(request: Request):
        actor = require_actor(request)
        return await asyncio.to_thread(service.list_projects, actor_username=actor.username)

    @app.get("/v1/projects/{project_id}")
    async def get_project(project_id: uuid.UUID, request: Request):
        actor = require_actor(request)
        detail = await asyncio.to_thread(service.get_project_detail, project_id, actor_username=actor.username)
        if detail is None:
            raise HTTPException(status_code=404, detail="Project not found.")
        return detail

    @app.get("/v1/documents/{document_id}/file")
    async def get_document_file(document_id: uuid.UUID, request: Request):
        actor = require_actor(request)
        document = await asyncio.to_thread(
            service.get_document_file,
            document_id,
            actor_username=actor.username,
            trace_id=request_id_for(request),
        )
        headers = {"content-disposition": f'inline; filename="{document.filename}"'}
        return StreamingResponse(
            io.BytesIO(document.content),
            media_type=document.mime_type,
            headers=headers,
        )

    @app.get("/v1/documents/{document_id}/parsed-text")
    async def get_document_parsed_text(document_id: uuid.UUID, request: Request):
        actor = require_actor(request)
        parsed = await asyncio.to_thread(
            service.get_document_parsed_text,
            document_id,
            actor_username=actor.username,
            trace_id=request_id_for(request),
        )
        return {"text": parsed.text}

    @app.patch("/v1/projects/{project_id}")
    async def rename_project(project_id: uuid.UUID, payload: RenameProjectRequest, request: Request):
        auth_manager.require_request_origin(request)
        actor = require_actor(request)
        detail = await asyncio.to_thread(
            service.rename_project,
            project_id,
            payload.name,
            actor_username=actor.username,
            trace_id=request_id_for(request),
        )
        if detail is None:
            raise HTTPException(status_code=404, detail="Project not found.")
        return detail

    @app.delete("/v1/projects/{project_id}")
    async def delete_project(project_id: uuid.UUID, request: Request):
        auth_manager.require_request_origin(request)
        actor = require_actor(request)
        await asyncio.to_thread(
            service.delete_project,
            project_id,
            actor_username=actor.username,
            trace_id=request_id_for(request),
        )
        return {"status": "ok"}

    @app.post("/v1/uploads")
    async def create_upload(request: Request, project_id: uuid.UUID = Form(...), file: UploadFile = File(...)):
        auth_manager.require_request_origin(request)
        actor = require_actor(request)
        remote_ip = request_ip(request)
        await enforce_rate_limit(
            bucket="upload_user",
            subject=actor.username,
            limit=settings.upload_rate_limit_per_user,
            window_seconds=settings.upload_rate_limit_window_seconds,
            request=request,
            actor_username=actor.username,
            detail="Upload rate limit reached for this account.",
            audit_callback=lambda retry_after: asyncio.to_thread(
                service.record_project_policy_event,
                project_id=project_id,
                actor_username=actor.username,
                trace_id=request_id_for(request),
                event_name="document_upload_rate_limited",
                metadata_json={
                    "project_id": str(project_id),
                    "bucket": "user",
                    "remote_ip": remote_ip,
                    "retry_after_seconds": retry_after,
                },
            ),
        )
        await enforce_rate_limit(
            bucket="upload_ip",
            subject=remote_ip,
            limit=settings.upload_rate_limit_per_ip,
            window_seconds=settings.upload_rate_limit_window_seconds,
            request=request,
            actor_username=actor.username,
            detail="Upload rate limit reached from this IP.",
            audit_callback=lambda retry_after: asyncio.to_thread(
                service.record_project_policy_event,
                project_id=project_id,
                actor_username=actor.username,
                trace_id=request_id_for(request),
                event_name="document_upload_rate_limited",
                metadata_json={
                    "project_id": str(project_id),
                    "bucket": "ip",
                    "remote_ip": remote_ip,
                    "retry_after_seconds": retry_after,
                },
            ),
        )
        if not file.filename:
            raise HTTPException(status_code=400, detail="Filename is required.")
        content_length_header = request.headers.get("content-length")
        if content_length_header:
            try:
                content_length = int(content_length_header)
            except ValueError:
                content_length = None
            size_limit = settings.max_upload_mb * 1024 * 1024
            if content_length is not None and content_length > size_limit:
                await asyncio.to_thread(
                    service.record_upload_policy_event,
                    project_id=project_id,
                    actor_username=actor.username,
                    trace_id=request_id_for(request),
                    event_name="document_upload_quota_denied_file_size",
                    metadata_json={
                        "project_id": str(project_id),
                        "quota_mb": settings.max_upload_mb,
                        "content_length": content_length,
                        "enforced_via": "content_length_header",
                    },
                )
                raise HTTPException(status_code=400, detail=f"File exceeds {settings.max_upload_mb}MB limit.")
        data = await file.read()
        return await service.create_upload(
            project_id=project_id,
            filename=file.filename,
            mime_type=file.content_type,
            data=data,
            actor_username=actor.username,
            trace_id=request_id_for(request),
        )

    @app.get("/v1/uploads/{job_id}")
    async def get_upload(job_id: uuid.UUID, request: Request):
        actor = require_actor(request)
        snapshot = await asyncio.to_thread(service.get_job_snapshot, job_id, actor_username=actor.username)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="Upload job not found.")
        return snapshot

    @app.get("/v1/uploads/{job_id}/result")
    async def get_upload_result(job_id: uuid.UUID, request: Request):
        actor = require_actor(request)
        return await asyncio.to_thread(service.get_job_result, job_id, actor_username=actor.username)

    @app.websocket("/v1/uploads/{job_id}/events")
    async def upload_events(websocket: WebSocket, job_id: uuid.UUID) -> None:
        try:
            auth_manager.require_websocket_origin(websocket)
            actor = auth_manager.get_required_actor_from_websocket(websocket)
            await asyncio.to_thread(service.assert_upload_job_access, job_id, actor_username=actor.username)
        except HTTPException as exc:
            await reject_websocket(websocket, 4401 if exc.status_code == 401 else 4403 if exc.status_code == 403 else 4404)
            return

        await event_bus.connect(job_id, websocket)
        try:
            snapshot = await asyncio.to_thread(service.get_job_snapshot, job_id, actor_username=actor.username)
            if snapshot is None:
                await websocket.send_json({"error": "Upload job not found."})
                return
            await websocket.send_json(snapshot.model_dump(mode="json"))
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            await event_bus.disconnect(job_id, websocket)

    @app.get("/v1/reference-sources")
    async def list_reference_sources(request: Request):
        require_actor(request)
        return await asyncio.to_thread(service.list_reference_sources)

    @app.post("/v1/review-setup")
    async def create_review_setup(payload: ReviewSetupRequest, request: Request):
        auth_manager.require_request_origin(request)
        actor = require_actor(request)
        return await asyncio.to_thread(
            service.create_review_setup,
            document_id=payload.document_id,
            selected_source_ids=payload.selected_source_ids,
            actor_username=actor.username,
        )

    @app.post("/v1/checklist-drafts")
    async def create_checklist_draft(payload: ChecklistDraftRequest, request: Request):
        auth_manager.require_request_origin(request)
        actor = require_actor(request)
        await enforce_rate_limit(
            bucket="checklist_user",
            subject=actor.username,
            limit=settings.checklist_rate_limit_per_user,
            window_seconds=settings.checklist_rate_limit_window_seconds,
            request=request,
            actor_username=actor.username,
            detail="Checklist generation is rate limited for this account.",
            audit_callback=lambda retry_after: asyncio.to_thread(
                service.record_document_policy_event,
                document_id=payload.document_id,
                actor_username=actor.username,
                trace_id=request_id_for(request),
                event_name="checklist_rate_limited",
                metadata_json={
                    "document_id": str(payload.document_id),
                    "retry_after_seconds": retry_after,
                },
            ),
        )
        return await service.create_checklist_draft(
            document_id=payload.document_id,
            selected_source_ids=payload.selected_source_ids,
            user_instruction=payload.user_instruction,
            actor_username=actor.username,
            trace_id=request_id_for(request),
        )

    @app.get("/v1/checklist-drafts/{draft_id}")
    async def get_checklist_draft(draft_id: uuid.UUID, request: Request):
        actor = require_actor(request)
        snapshot = await asyncio.to_thread(service.get_checklist_draft_snapshot, draft_id, actor_username=actor.username)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="Checklist draft job not found.")
        return snapshot

    @app.post("/v1/checklist-drafts/{draft_id}/cancel")
    async def cancel_checklist_draft(draft_id: uuid.UUID, request: Request):
        auth_manager.require_request_origin(request)
        actor = require_actor(request)
        return await service.cancel_checklist_draft(
            draft_id,
            actor_username=actor.username,
            trace_id=request_id_for(request),
        )

    @app.websocket("/v1/checklist-drafts/{draft_id}/events")
    async def checklist_draft_events(websocket: WebSocket, draft_id: uuid.UUID) -> None:
        try:
            auth_manager.require_websocket_origin(websocket)
            actor = auth_manager.get_required_actor_from_websocket(websocket)
            await asyncio.to_thread(service.assert_checklist_job_access, draft_id, actor_username=actor.username)
        except HTTPException as exc:
            await reject_websocket(websocket, 4401 if exc.status_code == 401 else 4403 if exc.status_code == 403 else 4404)
            return

        await event_bus.connect(draft_id, websocket)
        try:
            snapshot = await asyncio.to_thread(service.get_checklist_draft_snapshot, draft_id, actor_username=actor.username)
            if snapshot is None:
                await websocket.send_json({"error": "Checklist draft job not found."})
                return
            await websocket.send_json(snapshot.model_dump(mode="json"))
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            await event_bus.disconnect(draft_id, websocket)

    @app.get("/v1/projects/{project_id}/approved-checklist")
    async def get_approved_checklist(project_id: uuid.UUID, request: Request):
        actor = require_actor(request)
        detail = await asyncio.to_thread(service.get_approved_checklist, project_id, actor_username=actor.username)
        if detail is None:
            raise HTTPException(status_code=404, detail="Approved checklist not found.")
        return detail

    @app.put("/v1/projects/{project_id}/approved-checklist")
    async def approve_checklist(project_id: uuid.UUID, payload: ApproveChecklistRequest, request: Request):
        auth_manager.require_request_origin(request)
        actor = require_actor(request)
        return await asyncio.to_thread(
            service.approve_checklist,
            project_id,
            payload,
            actor_username=actor.username,
            trace_id=request_id_for(request),
        )

    @app.post("/v1/analysis-runs")
    async def create_analysis_run(payload: CreateAnalysisRunRequest, request: Request):
        auth_manager.require_request_origin(request)
        actor = require_actor(request)
        await enforce_rate_limit(
            bucket="analysis_user",
            subject=actor.username,
            limit=settings.analysis_rate_limit_per_user,
            window_seconds=settings.analysis_rate_limit_window_seconds,
            request=request,
            actor_username=actor.username,
            detail="Final review is rate limited for this account.",
            audit_callback=lambda retry_after: asyncio.to_thread(
                service.record_project_policy_event,
                project_id=payload.project_id,
                actor_username=actor.username,
                trace_id=request_id_for(request),
                event_name="analysis_rate_limited",
                metadata_json={
                    "project_id": str(payload.project_id),
                    "retry_after_seconds": retry_after,
                },
            ),
        )
        return await service.create_analysis_run(
            payload,
            actor_username=actor.username,
            trace_id=request_id_for(request),
        )

    @app.get("/v1/analysis-runs/{run_id}")
    async def get_analysis_run(run_id: uuid.UUID, request: Request):
        actor = require_actor(request)
        snapshot = await asyncio.to_thread(service.get_analysis_run_snapshot, run_id, actor_username=actor.username)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="Analysis run not found.")
        return snapshot

    @app.get("/v1/analysis-runs/{run_id}/report")
    async def get_analysis_report(run_id: uuid.UUID, request: Request):
        actor = require_actor(request)
        return await asyncio.to_thread(service.get_analysis_report, run_id, actor_username=actor.username)

    @app.websocket("/v1/analysis-runs/{run_id}/events")
    async def analysis_run_events(websocket: WebSocket, run_id: uuid.UUID) -> None:
        try:
            auth_manager.require_websocket_origin(websocket)
            actor = auth_manager.get_required_actor_from_websocket(websocket)
            await asyncio.to_thread(service.assert_analysis_run_access, run_id, actor_username=actor.username)
        except HTTPException as exc:
            await reject_websocket(websocket, 4401 if exc.status_code == 401 else 4403 if exc.status_code == 403 else 4404)
            return

        await event_bus.connect(run_id, websocket)
        try:
            snapshot = await asyncio.to_thread(service.get_analysis_run_snapshot, run_id, actor_username=actor.username)
            if snapshot is None:
                await websocket.send_json({"error": "Analysis run not found."})
                return
            await websocket.send_json(snapshot.model_dump(mode="json"))
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            await event_bus.disconnect(run_id, websocket)

    return app


app = create_app()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run("upload_api.main:app", host=settings.api_host, port=settings.api_port, reload=True)
