from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

LlmStatus = Literal["PENDING", "RUNNING", "SUCCEEDED", "FAILED"]
EmbedStatus = Literal["PENDING", "RUNNING", "SUCCEEDED", "FAILED"]
UpsertStatus = Literal["PENDING", "RUNNING", "SUCCEEDED", "FAILED"]
FinalStatus = Literal["PENDING", "COMPLETED", "FAILED"]
RunStatus = Literal["PENDING", "RUNNING", "PARTIAL_FAILURE", "FAILED", "COMPLETED", "CANCELLED"]
ContextMode = Literal["FULL_DOC", "SURROUNDING_CHUNKS"]


class KbStructureOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_title: str = Field(description="Exact source title copied from SOURCE_TITLE metadata.")
    source_url: str = Field(description="Exact source URL copied from SOURCE_URL metadata.")
    article_no: str = Field(description="Article/clause/section identifier, or best matching label.")
    short_description: str = Field(description="1-2 line summary of why this text matters for DPA checks.")
    consequences: str | None = Field(default=None, description="Practical or legal consequences of non-compliance.")
    possible_reasons: list[str] = Field(
        min_length=0,
        max_length=3,
        description="2-3 likely violation patterns or failure modes. Can be empty if not inferable.",
    )
    citation_quote: str = Field(description="Short verbatim quote from CURRENT_CHUNK_TEXT supporting the output.")
    citation_section: str | None = Field(default=None, description="Nearest heading/article label if visible, else null.")


@dataclass(frozen=True)
class SourcePlan:
    source_id: str
    title: str
    authority: str
    source_kind: str
    source_url: str
    local_txt_path: str
    local_md_path: str
    content_sha256: str
    char_count: int
    token_count: int


@dataclass(frozen=True)
class ChunkTaskPlan:
    source_id: str
    chunk_index: int
    chunk_count: int
    raw_text: str
    raw_text_sha256: str
    chunk_token_count: int
    doc_token_count: int
    context_mode: ContextMode
    context_window_start: int
    context_window_end: int
    context_text: str


@dataclass(frozen=True)
class PlanningResult:
    manifest_sha256: str
    sources: list[SourcePlan]
    tasks: list[ChunkTaskPlan]
    summary: dict[str, Any]


@dataclass(frozen=True)
class TaskPayload:
    task_id: str
    run_id: str
    source_id: str
    source_title: str
    source_url: str
    chunk_index: int
    chunk_count: int
    raw_text: str
    raw_text_sha256: str
    chunk_token_count: int
    doc_token_count: int
    context_mode: ContextMode
    context_window_start: int
    context_window_end: int
    context_text: str
    structured_json: dict[str, Any] | None = None
    structured_text: str | None = None
    embedding: list[float] | None = None


@dataclass(frozen=True)
class LlmStageResult:
    task_id: str
    structured_json: dict[str, Any]
    structured_text: str
    attempts_used: int


@dataclass(frozen=True)
class EmbedStageResult:
    task_id: str
    embedding: list[float]
    embedding_dim: int
    attempts_used: int


@dataclass(frozen=True)
class UpsertStageResult:
    task_id: str


@dataclass(frozen=True)
class RunQueueSeed:
    llm_task_ids: list[str]
    embed_task_ids: list[str]
    upsert_task_ids: list[str]
