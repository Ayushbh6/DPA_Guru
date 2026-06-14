from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from dpa_checklist import (
    ChecklistDraftItem,
    ChecklistDraftMeta,
    CriteriaDocumentInventoryItem,
    CriteriaValidationWarning,
    ReviewProfile,
)
from dpa_schemas import EvidenceItem


class AgentStrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


AgentExecutionBackend = Literal["local_postgres", "celery_redis"]
CriteriaResearchStatus = Literal["queued", "running", "completed", "failed", "canceled", "timeout"]


class AgentLoopConfig(AgentStrictModel):
    agent_name: str
    agent_role: str
    agent_version: str
    prompt_version: str
    model_name: str
    max_tool_calls: int = 50
    output_type: str
    output_schema_version: str


class AgentRunScope(AgentStrictModel):
    tenant_id: uuid.UUID
    project_id: uuid.UUID | None = None
    analysis_run_id: uuid.UUID | None = None
    approval_pack_id: uuid.UUID | None = None
    copilot_thread_id: uuid.UUID | None = None
    parent_agent_run_id: uuid.UUID | None = None


class AgentPromptSpec(AgentStrictModel):
    prompt_path: Path
    loop_config: AgentLoopConfig


class CriteriaGenerationContext(AgentStrictModel):
    vendor_review_id: str
    vendor_context: dict[str, Any]
    review_profile: ReviewProfile
    primary_document_id: str
    active_document_ids: list[str]
    documents: list[CriteriaDocumentInventoryItem]
    selected_kb_source_ids: list[str]


class CriteriaAgentModelOutput(AgentStrictModel):
    version: str = Field(min_length=1)
    meta: ChecklistDraftMeta
    validation_warnings: list[CriteriaValidationWarning] = Field(default_factory=list)
    checks: list[ChecklistDraftItem] = Field(min_length=1)


class StartCriteriaResearchInput(AgentStrictModel):
    query: str = Field(min_length=1)
    scope: str | None = None
    document_types: list[str] = Field(default_factory=list)
    kb_source_ids: list[str] = Field(default_factory=list)


class CriteriaResearchPayload(AgentStrictModel):
    answer: str = Field(min_length=1)
    key_points: list[str] = Field(default_factory=list)
    criteria_implications: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)


class CriteriaResearchResult(AgentStrictModel):
    research_id: str
    query: str
    status: CriteriaResearchStatus
    agent_run_id: str | None = None
    payload: CriteriaResearchPayload | None = None
    error_message: str | None = None


class SearchDocumentHit(AgentStrictModel):
    hit_id: str
    document_id: str
    document_name: str
    document_type: str
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    score: float
    excerpt: str = Field(min_length=1)
    provenance_id: str | None = None
    section_title: str | None = None


class ReviewAssessmentInput(AgentStrictModel):
    vendor_context: dict[str, Any]
    criterion: dict[str, Any]
    document_records: list[dict[str, Any]]
    selected_kb_source_ids: list[str]


class ApprovalPackAgentInput(AgentStrictModel):
    vendor_context: dict[str, Any]
    recommendation: str
    recommendation_summary: str
    top_risks: list[dict[str, Any]] = Field(default_factory=list)
    weak_or_missing_clauses: list[dict[str, Any]] = Field(default_factory=list)
    findings: list[dict[str, Any]] = Field(default_factory=list)
    vendor_questions: list[str] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)


class ApprovalPackAgentOutput(AgentStrictModel):
    executive_summary: str = Field(min_length=1)
    top_risks: list[str] = Field(default_factory=list)
    weak_or_missing_clauses: list[str] = Field(default_factory=list)
    vendor_follow_up_questions: list[str] = Field(default_factory=list)
    internal_memo: str = Field(min_length=1)
    confidence_notes: list[str] = Field(default_factory=list)


class CopilotCitation(AgentStrictModel):
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


class CopilotRevisionProposal(AgentStrictModel):
    reason: str = Field(min_length=1)
    changes_summary: str = Field(min_length=1)
    patch: dict[str, Any]
    preview_pack: dict[str, Any]


class CopilotAgentOutput(AgentStrictModel):
    answer: str = Field(min_length=1)
    citations: list[CopilotCitation] = Field(default_factory=list)
    suggested_questions: list[str] = Field(default_factory=list)
    revision: CopilotRevisionProposal | None = None
