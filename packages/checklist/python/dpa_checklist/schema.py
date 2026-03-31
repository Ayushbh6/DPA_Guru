from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChecklistSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    MANDATORY = "MANDATORY"


class ChecklistCategory(str, Enum):
    SCOPE_ROLES_AND_INSTRUCTIONS = "Scope, Roles & Instructions"
    SUBPROCESSORS_AND_PERSONNEL = "Subprocessors & Personnel"
    SECURITY_AND_CONFIDENTIALITY = "Security & Confidentiality"
    DATA_SUBJECT_RIGHTS_AND_ASSISTANCE = "Data Subject Rights & Assistance"
    INCIDENT_AND_BREACH_MANAGEMENT = "Incidents & Breach Notification"
    INTERNATIONAL_TRANSFERS_AND_LOCALIZATION = "International Transfers & Localization"
    RETENTION_DELETION_AND_EXIT = "Retention, Deletion & Exit"
    AUDIT_COMPLIANCE_AND_LIABILITY = "Audit, Compliance & Liability"


CHECKLIST_CATEGORY_COVERAGE: dict[ChecklistCategory, str] = {
    ChecklistCategory.SCOPE_ROLES_AND_INSTRUCTIONS: (
        "parties, controller or processor roles, subject matter, duration, purpose, documented instructions, and use limits"
    ),
    ChecklistCategory.SUBPROCESSORS_AND_PERSONNEL: (
        "subprocessor appointment, approval or notice rights, flow-down terms, authorized personnel, training, and staff confidentiality undertakings"
    ),
    ChecklistCategory.SECURITY_AND_CONFIDENTIALITY: (
        "technical and organizational measures, access control, encryption, segregation, resilience, testing, and secure handling commitments"
    ),
    ChecklistCategory.DATA_SUBJECT_RIGHTS_AND_ASSISTANCE: (
        "controller assistance with data subject requests, regulatory inquiries, DPIAs, prior consultation, and related cooperation duties"
    ),
    ChecklistCategory.INCIDENT_AND_BREACH_MANAGEMENT: (
        "security incident handling, breach notification timing and content, investigation support, remediation, and escalation duties"
    ),
    ChecklistCategory.INTERNATIONAL_TRANSFERS_AND_LOCALIZATION: (
        "cross-border transfers, SCCs, adequacy, transfer impact measures, data location commitments, and supplementary safeguards"
    ),
    ChecklistCategory.RETENTION_DELETION_AND_EXIT: (
        "retention limits, return or deletion on termination, exit support, destruction certificates, and post-termination handling"
    ),
    ChecklistCategory.AUDIT_COMPLIANCE_AND_LIABILITY: (
        "audit rights, records, compliance evidence, inspections, liability caps, indemnities, and general compliance or termination terms"
    ),
}


def checklist_category_values() -> list[str]:
    return [category.value for category in ChecklistCategory]


def checklist_category_guidance_lines() -> list[str]:
    return [
        f"- {category.value}: {CHECKLIST_CATEGORY_COVERAGE[category]}."
        for category in ChecklistCategory
    ]


class SourceType(str, Enum):
    LAW = "LAW"
    GUIDELINE = "GUIDELINE"
    INTERNAL_POLICY = "INTERNAL_POLICY"


class ApprovalStatus(str, Enum):
    DRAFT = "DRAFT"
    REVIEWED = "REVIEWED"
    APPROVED = "APPROVED"


class ChecklistSource(StrictModel):
    source_type: SourceType
    authority: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    source_url: HttpUrl
    source_excerpt: str = Field(min_length=1)
    interpretation_notes: str | None = None


class ChecklistGovernance(StrictModel):
    owner: str = Field(min_length=1)
    approval_status: ApprovalStatus
    approved_by: str | None = None
    approved_at: datetime | None = None
    policy_version: str = Field(min_length=1)
    change_note: str | None = None

    @model_validator(mode="after")
    def validate_approval_state(self) -> "ChecklistGovernance":
        if self.approval_status == ApprovalStatus.APPROVED:
            if not self.approved_by or not self.approved_at:
                raise ValueError("approved_by and approved_at are required when approval_status is APPROVED")
        return self


class ChecklistItem(StrictModel):
    check_id: str = Field(pattern=r"^[A-Z0-9_.-]+$")
    title: str = Field(min_length=1)
    category: ChecklistCategory = Field(description="One approved checklist category from the fixed DPA category taxonomy.")
    legal_basis: list[str] = Field(min_length=1)
    required: bool
    severity: ChecklistSeverity
    evidence_hint: str = Field(min_length=1)
    pass_criteria: list[str] = Field(min_length=1)
    fail_criteria: list[str] = Field(min_length=1)
    sources: list[ChecklistSource] = Field(min_length=1)


class ChecklistDraftMeta(StrictModel):
    selected_source_ids: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    open_questions: list[str] = Field(default_factory=list)
    generation_summary: str | None = None


class ChecklistDraftItem(ChecklistItem):
    draft_rationale: str = Field(min_length=1)


class ChecklistDraftOutput(StrictModel):
    version: str = Field(min_length=1)
    meta: ChecklistDraftMeta
    checks: list[ChecklistDraftItem] = Field(min_length=1)


class ChecklistDocument(StrictModel):
    version: str = Field(min_length=1)
    governance: ChecklistGovernance
    checks: list[ChecklistItem] = Field(min_length=1)


def export_checklist_json_schema(path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(ChecklistDocument.model_json_schema(), indent=2), encoding="utf-8")
