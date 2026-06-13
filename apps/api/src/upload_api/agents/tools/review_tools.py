from __future__ import annotations

from pydantic import BaseModel, Field

from upload_api.kb_retrieval import KbVectorRetriever

from ..base import AgentTool
from ..helpers import DocumentCorpus, KbSourceRecord, best_anchor_window, search_kb_sources


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


class ReviewAgentToolset:
    def __init__(
        self,
        *,
        corpus: DocumentCorpus,
        kb_sources: list[KbSourceRecord],
        kb_retriever: KbVectorRetriever,
    ) -> None:
        self._corpus = corpus
        self._kb_sources = {source.source_id: source for source in kb_sources}
        self._kb_retriever = kb_retriever

    def as_tools(self) -> list[AgentTool]:
        return [
            AgentTool(
                name="search_uploaded_documents",
                description="Search across all uploaded review documents for evidence relevant to the current approved criterion.",
                input_model=_SearchDocumentsInput,
                handler=self.search_uploaded_documents,
            ),
            AgentTool(
                name="fetch_document_pages",
                description="Fetch exact pages from one uploaded review document for a closer reading.",
                input_model=_FetchDocumentPagesInput,
                handler=self.fetch_document_pages,
            ),
            AgentTool(
                name="search_kb",
                description="Search the selected KB sources for legal grounding relevant to the current approved criterion.",
                input_model=_SearchKbInput,
                handler=self.search_kb,
            ),
            AgentTool(
                name="fetch_kb_context",
                description="Fetch a larger excerpt from one selected KB source around a concrete anchor.",
                input_model=_FetchKbContextInput,
                handler=self.fetch_kb_context,
            ),
        ]

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
