from __future__ import annotations

import copy
from typing import Any

from pydantic import BaseModel, Field

from upload_api.kb_retrieval import KbVectorRetriever

from ..base import AgentTool
from ..helpers import DocumentCorpus, KbSourceRecord, best_anchor_window, search_kb_sources


ALLOWED_APPROVAL_PACK_PATCH_PATHS = {
    "recommendation_summary",
    "executive_summary.narrative",
    "top_risks_narrative",
    "weak_clauses_narrative",
    "vendor_questions",
    "internal_memo",
    "confidence_notes",
}


class _EmptyInput(BaseModel):
    pass


class _SearchDocumentsInput(BaseModel):
    query: str = Field(min_length=1)
    document_ids: list[str] = Field(default_factory=list)
    document_types: list[str] = Field(default_factory=list)
    top_k: int = Field(default=6, ge=1, le=12)


class _FetchDocumentPagesInput(BaseModel):
    document_id: str = Field(min_length=1)
    start_page: int = Field(ge=1)
    end_page: int = Field(ge=1)


class _SearchKbInput(BaseModel):
    query: str = Field(min_length=1)
    kb_source_ids: list[str] = Field(default_factory=list)
    top_k: int = Field(default=6, ge=1, le=12)


class _FetchKbContextInput(BaseModel):
    source_id: str = Field(min_length=1)
    anchor: str = Field(min_length=1)
    window: int = Field(default=1200, ge=200, le=4000)


class _ApprovalPackPatchSet(BaseModel):
    path: str = Field(min_length=1)
    value: Any


class _ApprovalPackPatchInput(BaseModel):
    set: list[_ApprovalPackPatchSet] = Field(default_factory=list)


def apply_approval_pack_patch(pack_json: dict[str, Any], patch_json: dict[str, Any]) -> dict[str, Any]:
    patch = _ApprovalPackPatchInput.model_validate(patch_json)
    new_pack = copy.deepcopy(pack_json)
    for item in patch.set:
        if item.path not in ALLOWED_APPROVAL_PACK_PATCH_PATHS:
            raise ValueError(f"Approval Pack field is not editable by copilot: {item.path}")
        target = new_pack
        parts = item.path.split(".")
        for part in parts[:-1]:
            next_target = target.get(part)
            if not isinstance(next_target, dict):
                raise ValueError(f"Approval Pack patch path is invalid: {item.path}")
            target = next_target
        target[parts[-1]] = item.value
    return new_pack


class CopilotToolset:
    def __init__(
        self,
        *,
        vendor_context: dict[str, Any],
        approval_pack: dict[str, Any],
        findings: list[dict[str, Any]],
        stage_outputs: list[dict[str, Any]],
        prior_revisions: list[dict[str, Any]],
        corpus: DocumentCorpus,
        kb_sources: list[KbSourceRecord],
        kb_retriever: KbVectorRetriever,
    ) -> None:
        self._vendor_context = vendor_context
        self._approval_pack = approval_pack
        self._findings = findings
        self._stage_outputs = stage_outputs
        self._prior_revisions = prior_revisions
        self._corpus = corpus
        self._kb_sources = {source.source_id: source for source in kb_sources}
        self._kb_retriever = kb_retriever

    def as_tools(self) -> list[AgentTool]:
        return [
            AgentTool(
                name="get_vendor_context",
                description="Return the current vendor-review context that frames the Approval Pack.",
                input_model=_EmptyInput,
                handler=self.get_vendor_context,
            ),
            AgentTool(
                name="get_current_approval_pack",
                description="Return the current published Approval Pack JSON.",
                input_model=_EmptyInput,
                handler=self.get_current_approval_pack,
            ),
            AgentTool(
                name="get_review_findings",
                description="Return persisted review findings and evidence-backed assessments.",
                input_model=_EmptyInput,
                handler=self.get_review_findings,
            ),
            AgentTool(
                name="get_stage_outputs",
                description="Return prior approval-pack stage outputs and agent outputs useful for explaining the report.",
                input_model=_EmptyInput,
                handler=self.get_stage_outputs,
            ),
            AgentTool(
                name="list_prior_revisions",
                description="Return previous proposed, applied, and rejected Approval Pack revisions.",
                input_model=_EmptyInput,
                handler=self.list_prior_revisions,
            ),
            AgentTool(
                name="search_uploaded_documents",
                description="Search uploaded review documents for cited evidence relevant to the user's question.",
                input_model=_SearchDocumentsInput,
                handler=self.search_uploaded_documents,
            ),
            AgentTool(
                name="fetch_document_pages",
                description="Fetch exact pages from an uploaded review document for closer reading.",
                input_model=_FetchDocumentPagesInput,
                handler=self.fetch_document_pages,
            ),
            AgentTool(
                name="search_kb",
                description="Search selected KB sources for legal or guidance context relevant to the current review.",
                input_model=_SearchKbInput,
                handler=self.search_kb,
            ),
            AgentTool(
                name="fetch_kb_context",
                description="Fetch a larger excerpt from one selected KB source around a concrete anchor.",
                input_model=_FetchKbContextInput,
                handler=self.fetch_kb_context,
            ),
            AgentTool(
                name="preview_approval_pack_patch",
                description="Validate and preview a narrow proposed Approval Pack patch. The patch is not applied.",
                input_model=_ApprovalPackPatchInput,
                handler=self.preview_approval_pack_patch,
            ),
        ]

    def get_vendor_context(self, _: _EmptyInput) -> dict[str, Any]:
        return self._vendor_context

    def get_current_approval_pack(self, _: _EmptyInput) -> dict[str, Any]:
        return self._approval_pack

    def get_review_findings(self, _: _EmptyInput) -> list[dict[str, Any]]:
        return self._findings

    def get_stage_outputs(self, _: _EmptyInput) -> list[dict[str, Any]]:
        return self._stage_outputs

    def list_prior_revisions(self, _: _EmptyInput) -> list[dict[str, Any]]:
        return self._prior_revisions

    def search_uploaded_documents(self, payload: _SearchDocumentsInput) -> list[dict]:
        hits = self._corpus.search(
            query=payload.query,
            document_ids=payload.document_ids or None,
            document_types=payload.document_types or None,
            top_k=payload.top_k,
        )
        return [hit.model_dump(mode="json") for hit in hits]

    def fetch_document_pages(self, payload: _FetchDocumentPagesInput) -> list[dict]:
        return self._corpus.fetch_pages(
            document_id=payload.document_id,
            start_page=payload.start_page,
            end_page=payload.end_page,
        )

    def search_kb(self, payload: _SearchKbInput) -> list[dict]:
        return search_kb_sources(
            retriever=self._kb_retriever,
            sources=list(self._kb_sources.values()),
            query=payload.query,
            kb_source_ids=payload.kb_source_ids or None,
            top_k=payload.top_k,
        )

    def fetch_kb_context(self, payload: _FetchKbContextInput) -> dict:
        source = self._kb_sources.get(payload.source_id)
        if source is None:
            raise ValueError(f"Unknown selected KB source: {payload.source_id}")
        return {
            "source_id": source.source_id,
            "title": source.title,
            "authority": source.authority,
            "url": source.url,
            "anchor": payload.anchor,
            "excerpt": best_anchor_window(source.text, payload.anchor, window=payload.window),
        }

    def preview_approval_pack_patch(self, payload: _ApprovalPackPatchInput) -> dict[str, Any]:
        patch_json = payload.model_dump(mode="json")
        return {
            "patch": patch_json,
            "preview_pack": apply_approval_pack_patch(self._approval_pack, patch_json),
            "editable_paths": sorted(ALLOWED_APPROVAL_PACK_PATCH_PATHS),
        }
