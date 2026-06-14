from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
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
BusinessCriticality = Literal["low", "medium", "high"]
VendorRegion = Literal["EU_EEA", "US", "UK", "OTHER", "UNKNOWN"]
VendorDocumentType = Literal[
    "main_dpa",
    "privacy_policy",
    "security_toms",
    "subprocessors",
    "data_transfer_terms",
    "ai_terms",
    "service_terms",
    "security_certification",
    "custom_agreement",
    "other",
]
DocumentLifecycleStatus = Literal["active", "archived", "deleted"]
ApprovalRecommendation = Literal["approve", "approve_with_conditions", "escalate", "reject"]
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
    "GROUPING_CATEGORIES",
    "EMBEDDING_CHECKS",
    "FORMING_SEMANTIC_GROUPS",
    "VERIFYING_OVERLAPS",
    "RESOLVING_GROUPS",
    "MERGING_GROUPS",
    "FINALIZING_OUTPUT",
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
    vendor_review_id: uuid.UUID
    status: str
    ws_url: str
    status_url: str


class VendorReviewContext(BaseModel):
    vendor_name: str | None = Field(default=None, max_length=255)
    vendor_website: str | None = None
    tool_or_service_name: str | None = Field(default=None, max_length=255)
    intended_use_case: str | None = None
    data_types: list[str] = Field(default_factory=list)
    shares_personal_data: bool = False
    shares_customer_data: bool = False
    shares_employee_data: bool = False
    shares_sensitive_data: bool = False
    has_ai_features: bool = False
    business_criticality: BusinessCriticality | None = None
    vendor_region: VendorRegion | None = None
    processes_eu_personal_data: bool | None = None
    transfers_data_outside_eea: bool | None = None
    internal_owner: str | None = Field(default=None, max_length=255)
    review_deadline: date | None = None
    context_completed_at: datetime | None = None

    @field_validator("vendor_name", "vendor_website", "tool_or_service_name", "intended_use_case", "internal_owner", mode="before")
    @classmethod
    def strip_optional_text(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("data_types", mode="before")
    @classmethod
    def normalize_data_types(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


class VendorReviewCreationContext(BaseModel):
    vendor_name: str = Field(min_length=1, max_length=255)
    intended_use_case: str = Field(min_length=1)
    shares_personal_data: bool
    business_criticality: BusinessCriticality
    vendor_website: str | None = None
    tool_or_service_name: str | None = Field(default=None, max_length=255)
    data_types: list[str] = Field(default_factory=list)
    shares_customer_data: bool = False
    shares_employee_data: bool = False
    shares_sensitive_data: bool = False
    has_ai_features: bool = False
    vendor_region: VendorRegion | None = None
    processes_eu_personal_data: bool | None = None
    transfers_data_outside_eea: bool | None = None
    internal_owner: str | None = Field(default=None, max_length=255)
    review_deadline: date | None = None

    @field_validator("vendor_name", "intended_use_case", "vendor_website", "tool_or_service_name", "internal_owner", mode="before")
    @classmethod
    def strip_creation_text(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("data_types", mode="before")
    @classmethod
    def normalize_creation_data_types(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


class ProjectSummary(BaseModel):
    vendor_review_id: uuid.UUID
    project_id: uuid.UUID
    name: str
    status: ProjectStatus | str
    review_type: str = "vendor_dpa_review"
    vendor_name: str | None = None
    tool_or_service_name: str | None = None
    intended_use_case: str | None = None
    business_criticality: BusinessCriticality | str | None = None
    current_recommendation: ApprovalRecommendation | str | None = None
    document_count: int = 0
    primary_document_id: uuid.UUID | None = None
    primary_document_filename: str | None = None
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
    document_type: VendorDocumentType | str = "main_dpa"
    display_name: str | None = None
    description: str | None = None
    is_primary: bool = False
    source_kind: str = "uploaded"
    source_url: str | None = None
    lifecycle_status: DocumentLifecycleStatus | str = "active"
    active: bool = True
    archived_at: datetime | None = None
    archive_expires_at: datetime | None = None
    deleted_at: datetime | None = None
    hard_deleted_at: datetime | None = None
    parse_status: str | None = None
    parser_route: str | None = None
    pdf_classification: str | None = None
    token_count_estimate: int | None = None
    extracted_text_format: str | None = None
    uploaded_at: datetime


class AnalysisRunSummary(BaseModel):
    analysis_run_id: uuid.UUID
    vendor_review_id: uuid.UUID
    project_id: uuid.UUID
    document_id: uuid.UUID
    primary_document_id: uuid.UUID | None = None
    input_document_ids: list[uuid.UUID] = Field(default_factory=list)
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
    finding_count: int = 0


class ApprovedChecklistSummary(BaseModel):
    approved_checklist_id: uuid.UUID
    vendor_review_id: uuid.UUID
    project_id: uuid.UUID
    document_id: uuid.UUID
    input_document_ids: list[uuid.UUID] = Field(default_factory=list)
    version: str
    selected_source_ids: list[str]
    review_mode: str = "vendor_dpa_review"
    profile_id: str = "standard_vendor_dpa_v1"
    auto_approved: bool = False
    stale_at: datetime | None = None
    stale_reason: str | None = None
    stale_document_ids: list[uuid.UUID] = Field(default_factory=list)
    owner: str
    approval_status: str
    approved_by: str | None = None
    approved_at: datetime | None = None
    change_note: str | None = None
    created_at: datetime


class ProjectDetail(BaseModel):
    project: ProjectSummary
    vendor_context: VendorReviewContext
    documents: list[ProjectDocumentSummary] = Field(default_factory=list)
    document: ProjectDocumentSummary | None = None
    parse_job: UploadJobSnapshot | None = None
    checklist_draft: ChecklistDraftSnapshot | None = None
    approved_checklist: ApprovedChecklistSummary | None = None
    analysis_run: AnalysisRunSummary | None = None


class CreateProjectRequest(BaseModel):
    name: str | None = Field(default=None, max_length=255)


class CreateVendorReviewRequest(VendorReviewCreationContext):
    name: str | None = Field(default=None, max_length=255)


class UpdateVendorReviewRequest(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    vendor_context: VendorReviewContext | None = None


class UpdateDocumentRequest(BaseModel):
    document_type: VendorDocumentType | None = None
    display_name: str | None = Field(default=None, max_length=512)
    description: str | None = None


class MarkPrimaryDocumentRequest(BaseModel):
    replacement_document_id: uuid.UUID | None = None


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


class VendorCriteriaDraftRequest(BaseModel):
    user_instruction: str | None = None


class ChecklistDraftBootstrapResponse(BaseModel):
    checklist_draft_id: uuid.UUID
    document_id: uuid.UUID
    project_id: uuid.UUID
    vendor_review_id: uuid.UUID
    input_document_ids: list[uuid.UUID] = Field(default_factory=list)
    status: str
    ws_url: str
    status_url: str


class ChecklistDraftSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    checklist_draft_id: uuid.UUID
    document_id: uuid.UUID
    project_id: uuid.UUID
    vendor_review_id: uuid.UUID
    input_document_ids: list[uuid.UUID] = Field(default_factory=list)
    status: str
    stage: str
    progress_pct: int
    message: str | None = None
    selected_source_ids: list[str]
    user_instruction: str | None = None
    meta: dict[str, Any] | None = Field(default=None)
    result: ChecklistDraftOutput | None = None
    error_code: str | None = None
    error_message: str | None = None


class ReviewSetupResponse(BaseModel):
    analysis_run_id: uuid.UUID
    document_id: uuid.UUID
    project_id: uuid.UUID
    vendor_review_id: uuid.UUID
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


class ApprovalPackResponse(BaseModel):
    approval_pack_id: uuid.UUID
    vendor_review_id: uuid.UUID
    project_id: uuid.UUID
    analysis_run_id: uuid.UUID | None = None
    approved_checklist_id: uuid.UUID | None = None
    version: str
    status: str
    recommendation: ApprovalRecommendation | str
    recommendation_summary: str
    confidence: float
    review_required: bool
    pack: dict[str, Any]
    stale_at: datetime | None = None
    stale_reason: str | None = None
    stale_document_ids: list[uuid.UUID] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None = None


class CopilotThreadResponse(BaseModel):
    thread_id: uuid.UUID
    vendor_review_id: uuid.UUID
    project_id: uuid.UUID
    approval_pack_id: uuid.UUID | None = None
    title: str | None = None
    status: str
    created_by: str
    created_at: datetime
    updated_at: datetime


class CreateCopilotThreadRequest(BaseModel):
    title: str | None = Field(default=None, max_length=255)


class CopilotCitationResponse(BaseModel):
    source_type: str
    label: str
    excerpt: str | None = None
    document_id: str | None = None
    document_name: str | None = None
    document_type: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    kb_source_id: str | None = None
    url: str | None = None


class ApprovalPackRevisionResponse(BaseModel):
    revision_id: uuid.UUID
    vendor_review_id: uuid.UUID
    project_id: uuid.UUID
    approval_pack_id: uuid.UUID
    created_by_type: str
    created_by: str
    summary: str
    reason: str
    changes_summary: str
    patch: dict[str, Any]
    previous_pack: dict[str, Any] | None = None
    new_pack: dict[str, Any] | None = None
    status: str
    created_at: datetime
    applied_at: datetime | None = None
    rejected_at: datetime | None = None


class CopilotMessageResponse(BaseModel):
    message_id: uuid.UUID
    thread_id: uuid.UUID
    vendor_review_id: uuid.UUID
    project_id: uuid.UUID
    role: str
    content: str
    content_json: dict[str, Any] | None = None
    model_version: str | None = None
    agent_run_id: uuid.UUID | None = None
    status: str
    created_at: datetime
    citations: list[CopilotCitationResponse] = Field(default_factory=list)
    sources: list[CopilotCitationResponse] = Field(default_factory=list)
    tool_activities: list[dict[str, Any]] = Field(default_factory=list)
    revisions: list[ApprovalPackRevisionResponse] = Field(default_factory=list)
    meta: dict[str, Any] | None = None


class CopilotMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=12000)

    @field_validator("content", mode="before")
    @classmethod
    def strip_content(cls, value):
        if isinstance(value, str):
            return value.strip()
        return value


class CopilotTurnResponse(BaseModel):
    user_message: CopilotMessageResponse
    assistant_message: CopilotMessageResponse
    revision: ApprovalPackRevisionResponse | None = None


class CopilotThreadEventResponse(BaseModel):
    event_type: str
    thread_id: uuid.UUID
    message: CopilotMessageResponse | None = None
    revision: ApprovalPackRevisionResponse | None = None


class RenameProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
