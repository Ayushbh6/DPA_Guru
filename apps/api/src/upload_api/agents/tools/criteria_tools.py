from __future__ import annotations

from typing import Callable

from pydantic import BaseModel, Field

from upload_api.kb_retrieval import KbVectorRetriever

from ..base import AgentTool
from ..execution import CriteriaResearchExecutor
from ..helpers import DocumentCorpus, KbSourceRecord, best_anchor_window, search_kb_sources
from ..schemas import CriteriaGenerationContext, StartCriteriaResearchInput


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


class _CollectCriteriaResearchInput(BaseModel):
    research_ids: list[str] = Field(default_factory=list)
    wait_seconds: int | None = Field(default=None, ge=0, le=30)


class CriteriaAgentToolset:
    def __init__(
        self,
        *,
        context: CriteriaGenerationContext,
        corpus: DocumentCorpus,
        kb_sources: list[KbSourceRecord],
        kb_retriever: KbVectorRetriever,
        research_executor: CriteriaResearchExecutor,
        research_launcher: Callable[[str, StartCriteriaResearchInput], tuple[str, object]],
        parent_run_id_getter: Callable[[], str | None],
        max_children: int,
        default_wait_seconds: int,
        allow_delegation: bool = True,
    ) -> None:
        self._context = context
        self._corpus = corpus
        self._kb_sources = {source.source_id: source for source in kb_sources}
        self._kb_retriever = kb_retriever
        self._research_executor = research_executor
        self._research_launcher = research_launcher
        self._parent_run_id_getter = parent_run_id_getter
        self._max_children = max_children
        self._default_wait_seconds = default_wait_seconds
        self._allow_delegation = allow_delegation
        self._started_research_ids: list[str] = []

    def as_tools(self) -> list[AgentTool]:
        tools = [
            AgentTool(
                name="list_documents",
                description="Return metadata for all active documents in this vendor review. This is metadata only, not document summaries.",
                input_model=_EmptyInput,
                handler=self.list_documents,
            ),
            AgentTool(
                name="get_review_profile",
                description="Return the standard Vendor DPA review profile that governs required and contextual coverage.",
                input_model=_EmptyInput,
                handler=self.get_review_profile,
            ),
            AgentTool(
                name="search_uploaded_documents",
                description="Search the uploaded vendor documents for clauses, evidence, or gaps relevant to the current question.",
                input_model=_SearchDocumentsInput,
                handler=self.search_uploaded_documents,
            ),
            AgentTool(
                name="fetch_document_pages",
                description="Fetch exact document pages from one uploaded document for closer inspection.",
                input_model=_FetchDocumentPagesInput,
                handler=self.fetch_document_pages,
            ),
            AgentTool(
                name="search_kb",
                description="Search the selected legal and guidance KB sources for obligations or interpretive context.",
                input_model=_SearchKbInput,
                handler=self.search_kb,
            ),
            AgentTool(
                name="fetch_kb_context",
                description="Fetch a larger excerpt from one selected KB source around a specific anchor or clause.",
                input_model=_FetchKbContextInput,
                handler=self.fetch_kb_context,
            ),
        ]
        if self._allow_delegation:
            tools.extend(
                [
                    AgentTool(
                        name="start_criteria_research",
                        description="Start an asynchronous delegated Criteria Research child run. Only query is required; all other fields are optional hints.",
                        input_model=StartCriteriaResearchInput,
                        handler=self.start_criteria_research,
                    ),
                    AgentTool(
                        name="collect_criteria_research",
                        description="Collect results from previously started asynchronous Criteria Research child runs.",
                        input_model=_CollectCriteriaResearchInput,
                        handler=self.collect_criteria_research,
                    ),
                ]
            )
        return tools

    def list_documents(self, _: _EmptyInput) -> list[dict]:
        return [item.model_dump(mode="json") for item in self._context.documents]

    def get_review_profile(self, _: _EmptyInput) -> dict:
        return self._context.review_profile.model_dump(mode="json")

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

    def start_criteria_research(self, payload: StartCriteriaResearchInput):
        if len(self._started_research_ids) >= self._max_children:
            raise ValueError(f"Criteria research child limit reached ({self._max_children}).")
        parent_run_id = self._parent_run_id_getter()
        if not parent_run_id:
            raise RuntimeError("Parent agent run id is not available yet.")
        result = self._research_executor.start(
            parent_agent_run_id=parent_run_id,
            payload=payload,
            launch_fn=self._research_launcher,
        )
        self._started_research_ids.append(result.research_id)
        return result

    def collect_criteria_research(self, payload: _CollectCriteriaResearchInput) -> list[dict]:
        parent_run_id = self._parent_run_id_getter()
        if not parent_run_id:
            raise RuntimeError("Parent agent run id is not available yet.")
        results = self._research_executor.collect(
            parent_agent_run_id=parent_run_id,
            research_ids=payload.research_ids or None,
            wait_seconds=payload.wait_seconds if payload.wait_seconds is not None else self._default_wait_seconds,
        )
        return [item.model_dump(mode="json") for item in results]
