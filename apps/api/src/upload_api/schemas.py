from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from dpa_checklist import ChecklistDocument, ChecklistDraftOutput, ChecklistItem
from dpa_schemas import CheckAssessmentOutput, EvidenceSpan, OutputV2Report


UploadStage = Literal[
    "UPLOADING",
    "VALIDATING",
    "CLASSIFYING_PDF",
    "PARSING_MISTRAL_OCR",
    "COUNTING_TOKENS",
    "PERSISTING_RESULTS",
    "READY_FOR_REFERENCE_SELECTION",
    "FAILED",
]

JobStatus = Literal["QUEUED", "RUNNING", "COMPLETED", "FAILED"]
ProjectStatus = Literal[
    "EMPTY",
    "UPLOADING",
    "READY_FOR_CHECKLIST",
    "CHECKLIST_IN_PROGRESS",
    "CHECKLIST_READY",
    "REVIEW_IN_PROGRESS",
    "COMPLETED",
    "FAILED",
    "DELETED",
]
AnalysisRunStatus = Literal["QUEUED", "RUNNING", "COMPLETED", "FAILED"]
ChecklistDraftStage = Literal[
    "QUEUED",
    "RETRIEVING_KB",
    "EXPANDING_SOURCE_CONTEXT",
    "INSPECTING_DPA",
    "DRAFTING_CHECKLIST",
    "SYNTHESIZING",
    "VALIDATING_OUTPUT",
    "COMPLETED",
    "FAILED",
]


class ParsedDocumentSummary(BaseModel):
    filename: str
    mime_type: str
    page_count: int
    pdf_classification: str | None = None
    parser_route: str | None = None
    token_count_estimate: int | None = None
    extracted_text_format: str | None = None


class UploadJobSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    job_id: uuid.UUID
    document_id: uuid.UUID
    project_id: uuid.UUID
    status: str
    stage: str
    progress_pct: int
    message: str | None = None
    file_type: str
    pdf_classification: str | None = None
    parser_route: str | None = None
    page_count: int | None = None
    token_count_estimate: int | None = None
    result: ParsedDocumentSummary | None = None
    error_code: str | None = None
    error_message: str | None = None
    meta: dict[str, Any] | None = Field(default=None)


class UploadBootstrapResponse(BaseModel):
    job_id: uuid.UUID
    document_id: uuid.UUID
    project_id: uuid.UUID
    status: str
    ws_url: str
    status_url: str


class ProjectSummary(BaseModel):
    project_id: uuid.UUID
    name: str
    status: ProjectStatus | str
    created_at: datetime
    updated_at: datetime
    last_activity_at: datetime
    document_id: uuid.UUID | None = None
    document_filename: str | None = None


class ProjectDocumentSummary(BaseModel):
    document_id: uuid.UUID
    filename: str
    mime_type: str
    page_count: int
    parse_status: str | None = None
    parser_route: str | None = None
    pdf_classification: str | None = None
    token_count_estimate: int | None = None
    extracted_text_format: str | None = None
    uploaded_at: datetime


class AnalysisRunSummary(BaseModel):
    analysis_run_id: uuid.UUID
    project_id: uuid.UUID
    document_id: uuid.UUID
    status: AnalysisRunStatus | str
    model_version: str
    policy_version: str
    stage: str | None = None
    progress_pct: int = 0
    message: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    approved_checklist_id: uuid.UUID | None = None
    started_at: datetime
    completed_at: datetime | None = None
    latency_ms: int | None = None
    cost_usd: float | None = None


class ApprovedChecklistSummary(BaseModel):
    approved_checklist_id: uuid.UUID
    project_id: uuid.UUID
    document_id: uuid.UUID
    version: str
    selected_source_ids: list[str]
    owner: str
    approval_status: str
    approved_by: str | None = None
    approved_at: datetime | None = None
    change_note: str | None = None
    created_at: datetime


class ProjectDetail(BaseModel):
    project: ProjectSummary
    document: ProjectDocumentSummary | None = None
    parse_job: UploadJobSnapshot | None = None
    checklist_draft: ChecklistDraftSnapshot | None = None
    approved_checklist: ApprovedChecklistSummary | None = None
    analysis_run: AnalysisRunSummary | None = None


class CreateProjectRequest(BaseModel):
    name: str | None = Field(default=None, max_length=255)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=255)


class AuthUserResponse(BaseModel):
    username: str


class CreateProjectResponse(ProjectSummary):
    workspace_url: str


class ReferenceSource(BaseModel):
    source_id: str
    title: str
    authority: str
    kind: str
    url: str


class ReviewSetupRequest(BaseModel):
    document_id: uuid.UUID
    selected_source_ids: list[str]


class ChecklistDraftRequest(BaseModel):
    document_id: uuid.UUID
    selected_source_ids: list[str]
    user_instruction: str | None = None


class ChecklistDraftBootstrapResponse(BaseModel):
    checklist_draft_id: uuid.UUID
    document_id: uuid.UUID
    project_id: uuid.UUID
    status: str
    ws_url: str
    status_url: str


class ChecklistDraftSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    checklist_draft_id: uuid.UUID
    document_id: uuid.UUID
    project_id: uuid.UUID
    status: str
    stage: str
    progress_pct: int
    message: str | None = None
    selected_source_ids: list[str]
    user_instruction: str | None = None
    result: ChecklistDraftOutput | None = None
    error_code: str | None = None
    error_message: str | None = None


class ReviewSetupResponse(BaseModel):
    analysis_run_id: uuid.UUID
    document_id: uuid.UUID
    project_id: uuid.UUID
    selected_source_ids: list[str]
    status: str


class ApproveChecklistRequest(BaseModel):
    version: str = Field(min_length=1)
    selected_source_ids: list[str] = Field(min_length=1)
    checks: list[ChecklistItem] = Field(min_length=1)
    change_note: str | None = None


class ApprovedChecklistResponse(ApprovedChecklistSummary):
    checklist: ChecklistDocument


class CreateAnalysisRunRequest(BaseModel):
    project_id: uuid.UUID


class AnalysisRunSnapshot(AnalysisRunSummary):
    finding_count: int = 0


class AnalysisRunBootstrapResponse(AnalysisRunSnapshot):
    ws_url: str
    status_url: str


class AnalysisFindingDetail(BaseModel):
    check_id: str
    title: str
    category: str
    assessment: CheckAssessmentOutput
    citation_pages: list[int] = Field(default_factory=list)
    evidence_span_offsets: list[EvidenceSpan] = Field(default_factory=list)


class AnalysisRunReportResponse(BaseModel):
    report: OutputV2Report
    findings: list[AnalysisFindingDetail] = Field(default_factory=list)


class RenameProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
