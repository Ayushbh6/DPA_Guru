from __future__ import annotations

import asyncio
import uuid

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .config import load_settings
from .db import build_session_factory
from .events import JobEventBus
from .jobs import UploadPipelineService
from .schemas import (
    ApproveChecklistRequest,
    ChecklistDraftRequest,
    CreateAnalysisRunRequest,
    CreateProjectRequest,
    RenameProjectRequest,
)
from .storage import LocalStorage


settings = load_settings()
session_factory = build_session_factory(settings.database_url)
event_bus = JobEventBus()
storage = LocalStorage(settings.upload_storage_dir, settings.parsed_storage_dir)
service = UploadPipelineService(
    settings=settings,
    session_factory=session_factory,
    storage=storage,
    event_bus=event_bus,
)


def create_app() -> FastAPI:
    app = FastAPI(title="AI DPA Upload API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3001",
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def recover_incomplete_jobs() -> None:
        await asyncio.to_thread(service.recover_incomplete_jobs)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/projects")
    async def create_project(payload: CreateProjectRequest | None = None):
        return await asyncio.to_thread(service.create_project, payload.name if payload else None)

    @app.get("/v1/projects")
    async def list_projects():
        return await asyncio.to_thread(service.list_projects)

    @app.get("/v1/projects/{project_id}")
    async def get_project(project_id: uuid.UUID):
        detail = await asyncio.to_thread(service.get_project_detail, project_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="Project not found.")
        return detail

    @app.get("/v1/documents/{document_id}/file")
    async def get_document_file(document_id: uuid.UUID):
        document = await asyncio.to_thread(service.get_document_file, document_id)
        return FileResponse(
            path=document.path,
            media_type=document.mime_type,
            filename=document.filename,
            content_disposition_type="inline",
        )

    @app.patch("/v1/projects/{project_id}")
    async def rename_project(project_id: uuid.UUID, payload: RenameProjectRequest):
        detail = await asyncio.to_thread(service.rename_project, project_id, payload.name)
        if detail is None:
            raise HTTPException(status_code=404, detail="Project not found.")
        return detail

    @app.delete("/v1/projects/{project_id}")
    async def delete_project(project_id: uuid.UUID):
        await asyncio.to_thread(service.delete_project, project_id)
        return {"status": "ok"}

    @app.post("/v1/uploads")
    async def create_upload(project_id: uuid.UUID = Form(...), file: UploadFile = File(...)):
        if not file.filename:
            raise HTTPException(status_code=400, detail="Filename is required.")
        data = await file.read()
        return await service.create_upload(
            project_id=project_id,
            filename=file.filename,
            mime_type=file.content_type,
            data=data,
        )

    @app.get("/v1/uploads/{job_id}")
    async def get_upload(job_id: uuid.UUID):
        snapshot = await asyncio.to_thread(service.get_job_snapshot, job_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="Upload job not found.")
        return snapshot

    @app.get("/v1/uploads/{job_id}/result")
    async def get_upload_result(job_id: uuid.UUID):
        return await asyncio.to_thread(service.get_job_result, job_id)

    @app.websocket("/v1/uploads/{job_id}/events")
    async def upload_events(websocket: WebSocket, job_id: uuid.UUID) -> None:
        await event_bus.connect(job_id, websocket)
        try:
            snapshot = await asyncio.to_thread(service.get_job_snapshot, job_id)
            if snapshot is None:
                await websocket.send_json({"error": "Upload job not found."})
                return
            await websocket.send_json(snapshot.model_dump(mode="json"))
            while True:
                # We don't require client messages, but this keeps the socket open and detects disconnects.
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            await event_bus.disconnect(job_id, websocket)

    @app.get("/v1/reference-sources")
    async def list_reference_sources():
        return await asyncio.to_thread(service.list_reference_sources)

    @app.post("/v1/checklist-drafts")
    async def create_checklist_draft(payload: ChecklistDraftRequest):
        return await service.create_checklist_draft(
            document_id=payload.document_id,
            selected_source_ids=payload.selected_source_ids,
            user_instruction=payload.user_instruction,
        )

    @app.get("/v1/checklist-drafts/{draft_id}")
    async def get_checklist_draft(draft_id: uuid.UUID):
        snapshot = await asyncio.to_thread(service.get_checklist_draft_snapshot, draft_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="Checklist draft job not found.")
        return snapshot

    @app.post("/v1/checklist-drafts/{draft_id}/cancel")
    async def cancel_checklist_draft(draft_id: uuid.UUID):
        return await service.cancel_checklist_draft(draft_id)

    @app.websocket("/v1/checklist-drafts/{draft_id}/events")
    async def checklist_draft_events(websocket: WebSocket, draft_id: uuid.UUID) -> None:
        await event_bus.connect(draft_id, websocket)
        try:
            snapshot = await asyncio.to_thread(service.get_checklist_draft_snapshot, draft_id)
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
    async def get_approved_checklist(project_id: uuid.UUID):
        detail = await asyncio.to_thread(service.get_approved_checklist, project_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="Approved checklist not found.")
        return detail

    @app.put("/v1/projects/{project_id}/approved-checklist")
    async def approve_checklist(project_id: uuid.UUID, payload: ApproveChecklistRequest):
        return await asyncio.to_thread(service.approve_checklist, project_id, payload)

    @app.post("/v1/analysis-runs")
    async def create_analysis_run(payload: CreateAnalysisRunRequest):
        return await service.create_analysis_run(payload)

    @app.get("/v1/analysis-runs/{run_id}")
    async def get_analysis_run(run_id: uuid.UUID):
        snapshot = await asyncio.to_thread(service.get_analysis_run_snapshot, run_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="Analysis run not found.")
        return snapshot

    @app.get("/v1/analysis-runs/{run_id}/report")
    async def get_analysis_report(run_id: uuid.UUID):
        return await asyncio.to_thread(service.get_analysis_report, run_id)

    @app.websocket("/v1/analysis-runs/{run_id}/events")
    async def analysis_run_events(websocket: WebSocket, run_id: uuid.UUID) -> None:
        await event_bus.connect(run_id, websocket)
        try:
            snapshot = await asyncio.to_thread(service.get_analysis_run_snapshot, run_id)
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
