from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegistrySourceType(str, Enum):
    LAW = "LAW"
    GUIDELINE = "GUIDELINE"
    MONITOR = "MONITOR"


class SnapshotParseStatus(str, Enum):
    PARSED = "PARSED"
    RAW_ONLY = "RAW_ONLY"
    FAILED = "FAILED"


class ChangeClass(str, Enum):
    NO_CHANGE = "NO_CHANGE"
    MINOR_TEXT_CHANGE = "MINOR_TEXT_CHANGE"
    MATERIAL_CHANGE = "MATERIAL_CHANGE"


class ChecklistVersionStatus(str, Enum):
    DRAFT = "DRAFT"
    REVIEWED = "REVIEWED"
    REJECTED = "REJECTED"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"
    FAILED_CLOSED = "FAILED_CLOSED"


class ReviewDecision(str, Enum):
    REVIEWED = "REVIEWED"
    REJECTED = "REJECTED"


class ApprovalAction(str, Enum):
    APPROVED_AND_PROMOTED = "APPROVED_AND_PROMOTED"
    ROLLBACK_PROMOTE = "ROLLBACK_PROMOTE"


class SourceRegistryEntry(StrictModel):
    source_id: str = Field(min_length=1)
    authority: str = Field(min_length=1)
    celex_or_doc_id: str = Field(min_length=1)
    source_type: RegistrySourceType
    languages: list[str] = Field(min_length=1)
    status_rule: str = Field(min_length=1)
    fetch_url_map: dict[str, str] = Field(min_length=1)


class SourceSnapshot(StrictModel):
    snapshot_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    language: str = Field(min_length=2, max_length=8)
    fetched_at: datetime
    http_etag: str | None = None
    http_last_modified: str | None = None
    sha256: str = Field(min_length=64, max_length=64)
    storage_path: str = Field(min_length=1)
    parse_status: SnapshotParseStatus


class SourceDiff(StrictModel):
    diff_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    language: str = Field(min_length=2, max_length=8)
    from_snapshot_id: str | None = None
    to_snapshot_id: str = Field(min_length=1)
    change_class: ChangeClass
    summary: str = Field(min_length=1)


class ChecklistVersion(StrictModel):
    version_id: str = Field(min_length=1)
    status: ChecklistVersionStatus
    generated_from_snapshot_set: list[str] = Field(default_factory=list)
    approved_by: str | None = None
    approved_at: datetime | None = None
    policy_version: str = Field(min_length=1)


class FetchedDocument(StrictModel):
    url: str
    language: str
    status_code: int
    content_type: str | None = None
    body_bytes: bytes
    http_etag: str | None = None
    http_last_modified: str | None = None


class NormalizedDocument(StrictModel):
    normalized_text: str
    tracked_sections: list[str] = Field(default_factory=list)
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class DiffResult(StrictModel):
    change_class: ChangeClass
    summary: str
    changed_sections: list[str] = Field(default_factory=list)
    token_change_ratio: float = Field(ge=0.0, le=1.0)
