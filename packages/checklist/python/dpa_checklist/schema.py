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
    category: str = Field(min_length=1)
    legal_basis: list[str] = Field(min_length=1)
    required: bool
    severity: ChecklistSeverity
    evidence_hint: str = Field(min_length=1)
    pass_criteria: list[str] = Field(min_length=1)
    fail_criteria: list[str] = Field(min_length=1)
    sources: list[ChecklistSource] = Field(min_length=1)


class ChecklistDocument(StrictModel):
    version: str = Field(min_length=1)
    governance: ChecklistGovernance
    checks: list[ChecklistItem] = Field(min_length=1)


def export_checklist_json_schema(path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(ChecklistDocument.model_json_schema(), indent=2), encoding="utf-8")
