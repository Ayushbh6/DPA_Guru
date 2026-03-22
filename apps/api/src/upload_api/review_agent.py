from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dpa_checklist import ChecklistDocument, ChecklistItem
from dpa_schemas import CheckAssessmentOutput, ReviewSynthesisOutput
from google import genai

from .config import Settings
from .document_retrieval import DocumentVectorRetriever, DpaPageRecord, RetrievedDpaSpan
from .kb_retrieval import KbVectorRetriever, RetrievedKbChunk


_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{1,}")
_ANCHOR_MIN_LEN = 4


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    title: str
    authority: str
    kind: str
    url: str
    text: str


@dataclass(frozen=True)
class PrefetchedReviewEvidence:
    kb_hits: list[RetrievedKbChunk]
    dpa_spans: list[RetrievedDpaSpan]


def _keyword_terms(text: str) -> list[str]:
    seen: set[str] = set()
    terms: list[str] = []
    for match in _WORD_RE.finditer(text.lower()):
        term = match.group(0)
        if term in seen or len(term) < 3:
            continue
        seen.add(term)
        terms.append(term)
    return terms


def _chunk_text(text: str, *, chunk_chars: int = 1800) -> list[str]:
    text = text.strip()
    if not text:
        return []
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for paragraph in paragraphs:
        para_len = len(paragraph)
        if current and current_len + para_len + 2 > chunk_chars:
            chunks.append("\n\n".join(current))
            current = [paragraph]
            current_len = para_len
        else:
            current.append(paragraph)
            current_len += para_len + (2 if current else 0)
    if current:
        chunks.append("\n\n".join(current))
    if chunks:
        return chunks
    return [text[index:index + chunk_chars] for index in range(0, len(text), chunk_chars)] or [text]


def _score_text(query: str, text: str) -> float:
    lowered = text.lower()
    score = 0.0
    for term in _keyword_terms(query):
        score += lowered.count(term)
    return score


def _best_anchor_window(text: str, anchor: str, *, window: int) -> str:
    if not text.strip():
        return ""

    anchor = anchor.strip()
    if len(anchor) >= _ANCHOR_MIN_LEN:
        idx = text.lower().find(anchor.lower())
        if idx >= 0:
            start = max(0, idx - window)
            end = min(len(text), idx + len(anchor) + window)
            return text[start:end].strip()

    return text[: window * 2].strip()


def _check_assessment_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "check_id": {"type": "string"},
            "status": {
                "type": "string",
                "enum": ["COMPLIANT", "NON_COMPLIANT", "PARTIAL", "UNKNOWN"],
            },
            "risk": {
                "type": "string",
                "enum": ["LOW", "MEDIUM", "HIGH"],
            },
            "confidence": {"type": "number"},
            "evidence_quotes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "page": {"type": "integer"},
                        "quote": {"type": "string"},
                    },
                    "required": ["page", "quote"],
                },
            },
            "kb_citations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "source_id": {"type": "string"},
                        "source_ref": {"type": "string"},
                        "source_excerpt": {"type": "string"},
                    },
                    "required": ["source_id", "source_ref", "source_excerpt"],
                },
            },
            "missing_elements": {
                "type": "array",
                "items": {"type": "string"},
            },
            "risk_rationale": {"type": "string"},
            "abstained": {"type": "boolean"},
            "abstain_reason": {"type": "string"},
        },
        "required": ["check_id", "status", "risk", "confidence", "risk_rationale"],
    }


def _review_synthesis_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "overall": {
                "type": "object",
                "properties": {
                    "score": {"type": "number"},
                    "risk_level": {
                        "type": "string",
                        "enum": ["LOW", "MEDIUM", "HIGH"],
                    },
                    "summary": {"type": "string"},
                },
                "required": ["score", "risk_level", "summary"],
            },
            "highlights": {
                "type": "array",
                "items": {"type": "string"},
            },
            "next_actions": {
                "type": "array",
                "items": {"type": "string"},
            },
            "confidence": {"type": "number"},
            "abstained": {"type": "boolean"},
            "abstain_reason": {"type": "string"},
            "risk_rationale": {"type": "string"},
        },
        "required": ["overall", "confidence", "risk_rationale"],
    }


def _normalize_assessment_payload(payload: dict[str, Any]) -> dict[str, Any]:
    data = dict(payload)

    if data.get("abstained") and not str(data.get("abstain_reason") or "").strip():
        data["abstain_reason"] = "Reviewer abstained without providing a reason."

    evidence_quotes = data.get("evidence_quotes")
    if isinstance(evidence_quotes, list):
        normalized_quotes: list[dict[str, Any]] = []
        for item in evidence_quotes:
            if not isinstance(item, dict):
                continue
            page = item.get("page")
            quote = item.get("quote")
            if not isinstance(page, int) or not isinstance(quote, str):
                continue
            normalized_quotes.append(
                {
                    "page": page,
                    "quote": quote[:400].strip(),
                }
            )
        data["evidence_quotes"] = normalized_quotes

    kb_citations = data.get("kb_citations")
    if isinstance(kb_citations, list):
        normalized_citations: list[dict[str, Any]] = []
        for item in kb_citations:
            if not isinstance(item, dict):
                continue
            source_id = item.get("source_id")
            source_ref = item.get("source_ref")
            source_excerpt = item.get("source_excerpt")
            if not all(isinstance(value, str) for value in (source_id, source_ref, source_excerpt)):
                continue
            normalized_citations.append(
                {
                    "source_id": source_id,
                    "source_ref": source_ref,
                    "source_excerpt": source_excerpt[:500].strip(),
                }
            )
        data["kb_citations"] = normalized_citations

    missing_elements = data.get("missing_elements")
    if isinstance(missing_elements, list):
        data["missing_elements"] = [item.strip() for item in missing_elements if isinstance(item, str) and item.strip()]

    return data


def _review_tool_declarations() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "name": "fetch_selected_source_context",
            "description": "Fetch a larger excerpt from one selected KB source around an anchor term.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source_id": {"type": "string"},
                    "anchor": {"type": "string"},
                    "window": {"type": "integer"},
                },
                "required": ["source_id", "anchor"],
            },
        },
        {
            "type": "function",
            "name": "fetch_dpa_span",
            "description": "Fetch the full stored DPA span for a known provenance id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "provenance_id": {"type": "string"},
                },
                "required": ["provenance_id"],
            },
        },
        {
            "type": "function",
            "name": "fetch_dpa_pages",
            "description": "Fetch one or more full DPA pages by page range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_page": {"type": "integer"},
                    "end_page": {"type": "integer"},
                },
                "required": ["start_page", "end_page"],
            },
        },
    ]


class ReviewAgent:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._kb_retriever = KbVectorRetriever(settings)
        self._document_retriever = DocumentVectorRetriever(settings)

    def load_sources(self, selected_source_ids: list[str]) -> list[SourceRecord]:
        return self._load_sources(selected_source_ids)

    def prefetch_evidence(
        self,
        *,
        document_id: uuid.UUID,
        query: str,
        sources: list[SourceRecord],
        dpa_pages: list[DpaPageRecord],
        kb_top_k: int = 4,
        dpa_top_k: int = 6,
    ) -> PrefetchedReviewEvidence:
        kb_hits = self._prefetch_kb_hits(query=query, sources=sources, top_k=kb_top_k)
        dpa_spans = self._prefetch_dpa_spans(
            document_id=document_id,
            query=query,
            dpa_pages=dpa_pages,
            top_k=dpa_top_k,
        )
        return PrefetchedReviewEvidence(kb_hits=kb_hits, dpa_spans=dpa_spans)

    def assess_check(
        self,
        *,
        document_id: uuid.UUID,
        approved_checklist: ChecklistDocument,
        check: ChecklistItem,
        sources: list[SourceRecord],
        dpa_pages: list[DpaPageRecord],
        prefetched_evidence: PrefetchedReviewEvidence,
    ) -> CheckAssessmentOutput:
        if not self._settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is required for review generation.")

        toolset = _ReviewToolset(
            document_id=document_id,
            sources=sources,
            dpa_pages=dpa_pages,
            document_retriever=self._document_retriever,
        )

        source_catalog = [
            {
                "source_id": source.source_id,
                "title": source.title,
                "authority": source.authority,
                "kind": source.kind,
                "url": source.url,
            }
            for source in sources
        ]
        dpa_payload = [
            {
                "provenance_id": item.provenance_id,
                "page_start": item.page_start,
                "page_end": item.page_end,
                "score": item.score,
                "text": item.text,
            }
            for item in prefetched_evidence.dpa_spans
        ]
        kb_payload = [
            {
                "source_id": item.source_id,
                "title": item.source_title,
                "url": item.source_url,
                "chunk_index": item.chunk_index,
                "score": item.score,
                "excerpt": item.excerpt,
                "structured_text": item.structured_text,
            }
            for item in prefetched_evidence.kb_hits
        ]
        contents = [
            "Assess one approved DPA checklist item against the uploaded agreement.",
            "Use the prefetched evidence first. Use tools only to fetch deeper context for a known source, span, or page.",
            "Approved checklist version:",
            approved_checklist.version,
            "Checklist item:",
            json.dumps(check.model_dump(mode="json"), indent=2),
            "Selected source catalog:",
            json.dumps(source_catalog, indent=2),
            "Prefetched KB hits:",
            json.dumps(kb_payload, indent=2),
            "Prefetched DPA spans:",
            json.dumps(dpa_payload, indent=2),
            "DPA page summary:",
            json.dumps({"page_count": len(dpa_pages), "document_id": str(document_id)}, indent=2),
        ]

        with genai.Client(api_key=self._settings.gemini_api_key) as client:
            tools_list = _review_tool_declarations()
            tools_map = {
                "fetch_selected_source_context": toolset.fetch_selected_source_context,
                "fetch_dpa_span": toolset.fetch_dpa_span,
                "fetch_dpa_pages": toolset.fetch_dpa_pages,
            }
            final_text = None
            previous_interaction_id: str | None = None
            pending_input: Any = [{"role": "user", "content": [{"type": "text", "text": "\n\n".join(contents)}]}]

            for _ in range(10):
                response = client.interactions.create(
                    model=self._settings.gemini_review_model,
                    input=pending_input,
                    previous_interaction_id=previous_interaction_id,
                    tools=tools_list,
                    system_instruction=_REVIEW_SYSTEM_PROMPT,
                    response_format=_check_assessment_schema(),
                    generation_config={
                        "temperature": 0,
                        "thinking_level": "low",
                        "thinking_summaries": "none"
                    }
                )
                previous_interaction_id = response.id

                function_calls = [out for out in response.outputs if out.type == "function_call"]
                if function_calls:
                    tool_results = []
                    for function_call in function_calls:
                        name = function_call.name
                        args = function_call.arguments
                        if name in tools_map:
                            try:
                                result = tools_map[name](**args)
                                tool_results.append({
                                    "type": "function_result",
                                    "name": name,
                                    "call_id": function_call.id,
                                    "result": result
                                })
                            except Exception as exc:
                                tool_results.append({
                                    "type": "function_result",
                                    "name": name,
                                    "call_id": function_call.id,
                                    "result": json.dumps({"error": str(exc)})
                                })
                        else:
                            tool_results.append({
                                "type": "function_result",
                                "name": name,
                                "call_id": function_call.id,
                                "result": json.dumps({"error": f"Unknown tool: {name}"})
                            })
                    pending_input = tool_results
                    continue

                text_outputs = [out for out in response.outputs if out.type == "text"]
                if text_outputs:
                    final_text = "".join([out.text for out in text_outputs if out.text])
                break

        if not final_text:
            raise RuntimeError("Gemini did not return structured review output after tool iterations.")
        parsed = json.loads(final_text)
        if not isinstance(parsed, dict):
            raise RuntimeError("Gemini returned non-object review output.")
        return CheckAssessmentOutput.model_validate(_normalize_assessment_payload(parsed))

    def synthesize(
        self,
        *,
        approved_checklist: ChecklistDocument,
        assessments: list[CheckAssessmentOutput],
    ) -> ReviewSynthesisOutput:
        if not self._settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is required for review synthesis.")

        contents = [
            "Synthesize a final DPA review summary from approved checklist assessments.",
            "Approved checklist version:",
            approved_checklist.version,
            "Checklist items:",
            json.dumps([item.model_dump(mode="json") for item in approved_checklist.checks], indent=2),
            "Per-check assessments:",
            json.dumps([item.model_dump(mode="json") for item in assessments], indent=2),
        ]
        with genai.Client(api_key=self._settings.gemini_api_key) as client:
            response = client.interactions.create(
                model=self._settings.gemini_review_model,
                input="\n\n".join(contents),
                system_instruction=_SYNTHESIS_SYSTEM_PROMPT,
                response_format=_review_synthesis_schema(),
                generation_config={
                    "temperature": 0,
                    "thinking_level": "low",
                    "thinking_summaries": "none"
                }
            )
            
            text_outputs = [out for out in response.outputs if out.type == "text"]
            if not text_outputs:
                raise RuntimeError("Gemini did not return synthesis output.")
            
            final_text = "".join([out.text for out in text_outputs if out.text])
        return ReviewSynthesisOutput.model_validate_json(final_text)

    def _prefetch_kb_hits(self, *, query: str, sources: list[SourceRecord], top_k: int) -> list[RetrievedKbChunk]:
        if not query.strip() or not sources:
            return []

        selected_source_ids = [source.source_id for source in sources]
        try:
            vector_results = self._kb_retriever.search_selected_sources(
                query=query,
                selected_source_ids=selected_source_ids,
                top_k=top_k,
            )
        except Exception:
            vector_results = []
        if vector_results:
            return vector_results

        lexical_hits: list[tuple[float, RetrievedKbChunk]] = []
        for source in sources:
            for index, chunk in enumerate(_chunk_text(source.text), start=1):
                score = _score_text(query, chunk)
                if score <= 0:
                    continue
                lexical_hits.append(
                    (
                        score,
                            RetrievedKbChunk(
                                source_id=source.source_id,
                                source_title=source.title,
                                source_url=source.url,
                                chunk_index=index,
                                score=score,
                                excerpt=chunk,
                                structured_text=None,
                            ),
                    )
                )
        lexical_hits.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in lexical_hits[: max(1, min(top_k, 12))]]

    def _prefetch_dpa_spans(
        self,
        *,
        document_id: uuid.UUID,
        query: str,
        dpa_pages: list[DpaPageRecord],
        top_k: int,
    ) -> list[RetrievedDpaSpan]:
        if not query.strip():
            return []

        try:
            results = self._document_retriever.search_document(
                document_id=document_id,
                query=query,
                top_k=top_k,
            )
        except Exception:
            results = []
        if results:
            return results

        fallback: list[tuple[float, RetrievedDpaSpan]] = []
        for page in dpa_pages:
            score = _score_text(query, page.text)
            if score <= 0:
                continue
            fallback.append(
                (
                    score,
                    RetrievedDpaSpan(
                        provenance_id=f"page-{page.page}",
                        page_start=page.page,
                        page_end=page.page,
                        text=page.text,
                        score=score,
                    ),
                )
            )
        fallback.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in fallback[: max(1, min(top_k, 12))]]

    def _load_sources(self, selected_source_ids: list[str]) -> list[SourceRecord]:
        manifest_path = self._settings.repo_root / "kb" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        source_rows = manifest.get("sources")
        if not isinstance(source_rows, list):
            raise RuntimeError("KB manifest is invalid.")

        selected = set(selected_source_ids)
        records: list[SourceRecord] = []
        for row in source_rows:
            if not isinstance(row, dict):
                continue
            source_id = str(row.get("source_id") or "")
            if source_id not in selected:
                continue
            md_path = row.get("md_path")
            txt_path = row.get("txt_path")
            local_path = md_path or txt_path
            if not isinstance(local_path, str):
                continue
            path = self._settings.repo_root / local_path
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8")
            records.append(
                SourceRecord(
                    source_id=source_id,
                    title=str(row.get("title") or source_id),
                    authority=str(row.get("authority") or ""),
                    kind=str(row.get("kind") or ""),
                    url=str(row.get("url") or ""),
                    text=text,
                )
            )
        return records


class _ReviewToolset:
    def __init__(
        self,
        *,
        document_id: uuid.UUID,
        sources: list[SourceRecord],
        dpa_pages: list[DpaPageRecord],
        document_retriever: DocumentVectorRetriever,
    ) -> None:
        self._document_id = document_id
        self._sources = {source.source_id: source for source in sources}
        self._dpa_pages = dpa_pages
        self._document_retriever = document_retriever

    def fetch_selected_source_context(self, source_id: str, anchor: str, window: int = 1200) -> str:
        source = self._sources.get(source_id)
        if source is None:
            return json.dumps({"error": f"Unknown or unselected source_id: {source_id}"})
        return json.dumps(
            {
                "source_id": source.source_id,
                "title": source.title,
                "authority": source.authority,
                "url": source.url,
                "anchor": anchor,
                "text": source.text,
            },
            ensure_ascii=False,
        )

    def fetch_dpa_span(self, provenance_id: str) -> str:
        record = self._document_retriever.fetch_span(document_id=self._document_id, provenance_id=provenance_id)
        if record is None and provenance_id.startswith("page-"):
            try:
                page_no = int(provenance_id.removeprefix("page-"))
            except ValueError:
                page_no = -1
            page = next((item for item in self._dpa_pages if item.page == page_no), None)
            if page is not None:
                return json.dumps(
                    {
                        "provenance_id": provenance_id,
                        "page_start": page.page,
                        "page_end": page.page,
                        "text": page.text,
                    },
                    ensure_ascii=False,
                )
        if record is None:
            return json.dumps({"error": f"Unknown provenance_id: {provenance_id}"})
        return json.dumps(
            {
                "provenance_id": record.provenance_id,
                "page_start": record.page_start,
                "page_end": record.page_end,
                "text": record.text,
            },
            ensure_ascii=False,
        )

    def fetch_dpa_pages(self, start_page: int, end_page: int) -> str:
        if start_page > end_page:
            start_page, end_page = end_page, start_page
        selected = [
            {"page": page.page, "text": page.text}
            for page in self._dpa_pages
            if start_page <= page.page <= end_page
        ]
        return json.dumps(selected, ensure_ascii=False)


_REVIEW_SYSTEM_PROMPT = """
You assess one approved DPA checklist item against the uploaded DPA.

Rules:
- Output must strictly match the provided response schema.
- Do not output any free text outside the schema.
- The checklist item defines the obligation to evaluate.
- The uploaded DPA is the contract evidence source.
- The selected KB sources are the legal grounding source.
- Use the prefetched evidence first.
- Be investigative but bounded.
- Challenge your first impression when the evidence is incomplete, ambiguous, or internally inconsistent.
- Use the fetch tools to inspect the exact DPA span, DPA pages, or KB source context behind a hypothesis.
- Do not wander broadly; every tool call should help resolve a concrete uncertainty in the current check.
- Evidence quotes must be short verbatim quotes copied from the DPA page text.
- KB citations must be grounded in selected KB source context only.
- If evidence is insufficient or ambiguous, set abstained=true and provide abstain_reason.
- Keep missing_elements compact and concrete.
- risk_rationale must explain the judgment clearly and specifically.
"""


_SYNTHESIS_SYSTEM_PROMPT = """
You synthesize final DPA review summaries from completed per-check assessments.

Rules:
- Output must strictly match the provided response schema.
- Do not output any free text outside the schema.
- Summarize the aggregate review outcome only from the approved checklist and per-check assessments.
- Keep highlights and next_actions concise and concrete.
- If the review is materially incomplete, reflect that in abstained and risk_rationale.
"""
