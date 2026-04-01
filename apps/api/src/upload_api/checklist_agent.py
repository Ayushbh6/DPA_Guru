from __future__ import annotations

import logging
import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from dpa_checklist import ChecklistDraftOutput, checklist_category_guidance_lines, checklist_category_values
from google import genai
from google.genai import types
from pydantic import ValidationError

from .logging_utils import log_event
from .config import Settings
from .kb_retrieval import KbVectorRetriever
from .checklist_synthesis import (
    CategoryGroupChecklistSynthesizer,
    ChecklistSynthesisCanceledError,
    SynthesisCancelCallback,
    SynthesisProgressCallback,
    SynthesisTraceCallback,
    SemanticGroupChecklistSynthesizer,
    normalize_draft_output,
)


ProgressCallback = Callable[[str, str], None]

_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{1,}")
_ANCHOR_MIN_LEN = 4
_CATEGORY_ENUM_VALUES = checklist_category_values()
_CATEGORY_GUIDANCE_BLOCK = "\n".join(checklist_category_guidance_lines())


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    title: str
    authority: str
    kind: str
    url: str
    text: str


@dataclass(frozen=True)
class DpaPageRecord:
    page: int
    text: str


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

    return text[:window * 2].strip()


def _normalize_check_ids(payload: ChecklistDraftOutput) -> ChecklistDraftOutput:
    data = payload.model_dump(mode="python")
    for index, item in enumerate(data["checks"], start=1):
        item["check_id"] = f"CHECK_{index:03d}"
    return ChecklistDraftOutput.model_validate(data)


def _strip_json_fences(value: str) -> str:
    text = value.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _response_finish_reasons(response: Any) -> list[str]:
    reasons: list[str] = []
    for candidate in list(getattr(response, "candidates", []) or []):
        reason = getattr(candidate, "finish_reason", None)
        if reason is None:
            continue
        reasons.append(str(reason))
    return reasons


def _response_usage_metadata(response: Any) -> dict[str, Any] | None:
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return None
    if hasattr(usage, "model_dump"):
        return usage.model_dump(mode="python")
    if hasattr(usage, "__dict__"):
        return dict(vars(usage))
    return {"value": str(usage)}


def _raise_if_cancelled(cancel_check: SynthesisCancelCallback | None, *, phase: str) -> None:
    if cancel_check is not None and cancel_check():
        raise ChecklistSynthesisCanceledError(f"Checklist synthesis canceled during {phase}.")


def _parse_checklist_output_text(
    raw_text: str,
    *,
    phase: str,
    model: str,
    attempt: int,
    response: Any,
) -> ChecklistDraftOutput:
    json_text = _strip_json_fences(raw_text)
    try:
        return normalize_draft_output(ChecklistDraftOutput.model_validate_json(json_text))
    except ValidationError as exc:
        log_event(
            logging.WARNING,
            severity="warn",
            event="checklist_model_parse_failed",
            phase=phase,
            model=model,
            attempt=attempt,
            raw_text_length=len(raw_text),
            finish_reasons=_response_finish_reasons(response),
            usage_metadata=_response_usage_metadata(response),
            validation_error=str(exc),
            response_excerpt=raw_text[:500],
        )
        raise


def _gemini_response_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "version": {"type": "string"},
            "meta": {
                "type": "object",
                "properties": {
                    "selected_source_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "confidence": {"type": "number"},
                    "open_questions": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "generation_summary": {"type": "string"},
                },
                "required": ["selected_source_ids", "confidence", "open_questions"],
            },
            "checks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "check_id": {"type": "string"},
                        "title": {"type": "string"},
                        "category": {
                            "type": "string",
                            "enum": _CATEGORY_ENUM_VALUES,
                            "description": "Choose exactly one approved DPA checklist category from the fixed taxonomy.",
                        },
                        "legal_basis": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "required": {"type": "boolean"},
                        "severity": {
                            "type": "string",
                            "enum": ["LOW", "MEDIUM", "HIGH", "MANDATORY"],
                        },
                        "evidence_hint": {"type": "string"},
                        "pass_criteria": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "fail_criteria": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "sources": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "source_type": {
                                        "type": "string",
                                        "enum": ["LAW", "GUIDELINE", "INTERNAL_POLICY"],
                                    },
                                    "authority": {"type": "string"},
                                    "source_ref": {"type": "string"},
                                    "source_url": {"type": "string"},
                                    "source_excerpt": {"type": "string"},
                                    "interpretation_notes": {"type": "string"},
                                },
                                "required": [
                                    "source_type",
                                    "authority",
                                    "source_ref",
                                    "source_url",
                                    "source_excerpt",
                                ],
                            },
                        },
                        "draft_rationale": {"type": "string"},
                    },
                    "required": [
                        "check_id",
                        "title",
                        "category",
                        "legal_basis",
                        "required",
                        "severity",
                        "evidence_hint",
                        "pass_criteria",
                        "fail_criteria",
                        "sources",
                        "draft_rationale",
                    ],
                },
            },
        },
        "required": ["version", "meta", "checks"],
    }


def _checklist_tool_declarations() -> list[types.Tool]:
    return [
        types.Tool(function_declarations=[
            {
                "name": "search_selected_kb",
                "description": "Run hybrid retrieval over the selected KB sources and return the best matching excerpts.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "top_k": {"type": "integer"},
                    },
                    "required": ["query"],
                },
            },
            {
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
                "name": "search_dpa",
                "description": "Search the parsed DPA text for the most relevant pages or excerpts.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "top_k": {"type": "integer"},
                    },
                    "required": ["query"],
                },
            },
            {
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
            {
                "name": "fetch_dpa_excerpt",
                "description": "Fetch a focused excerpt from a specific DPA page around an anchor text.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "page": {"type": "integer"},
                        "anchor_text": {"type": "string"},
                        "window": {"type": "integer"},
                    },
                    "required": ["page", "anchor_text"],
                },
            },
        ])
    ]


class ChecklistDraftAgent:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._kb_retriever = KbVectorRetriever(settings)
        self._semantic_group_synthesizer = SemanticGroupChecklistSynthesizer(settings)
        self._category_group_synthesizer = CategoryGroupChecklistSynthesizer(settings)

    def generate(
        self,
        *,
        document_id: uuid.UUID,
        selected_source_ids: list[str],
        user_instruction: str | None,
        parsed_markdown_path: Path,
        parsed_pages_path: Path | None,
        progress_cb: ProgressCallback | None = None,
    ) -> ChecklistDraftOutput:
        if not self._settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is required for checklist generation.")

        if progress_cb:
            progress_cb("RETRIEVING_KB", "Loading selected KB source files.")
        sources = self._load_sources(selected_source_ids)
        if not sources:
            raise RuntimeError("No selected KB source files could be loaded.")

        if progress_cb:
            progress_cb("INSPECTING_DPA", "Loading parsed DPA pages for bounded inspection.")
        dpa_pages = self._load_dpa_pages(parsed_markdown_path, parsed_pages_path)

        toolset = _ChecklistToolset(
            sources=sources,
            dpa_pages=dpa_pages,
            kb_retriever=self._kb_retriever,
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
        dpa_summary = {
            "document_id": str(document_id),
            "page_count": len(dpa_pages),
            "has_page_text": any(page.text.strip() for page in dpa_pages),
        }

        contents = [
            "Generate a source-backed DPA review checklist draft.",
            "Selected sources:",
            json.dumps(source_catalog, indent=2),
            "Parsed DPA summary:",
            json.dumps(dpa_summary, indent=2),
            f"User instruction: {(user_instruction or '').strip() or 'None provided'}",
        ]

        if progress_cb:
            progress_cb("DRAFTING_CHECKLIST", "Preparing the checklist draft.")

        with genai.Client(api_key=self._settings.gemini_api_key) as client:
            tools_map = {
                "search_selected_kb": toolset.search_selected_kb,
                "fetch_selected_source_context": toolset.fetch_selected_source_context,
                "search_dpa": toolset.search_dpa,
                "fetch_dpa_pages": toolset.fetch_dpa_pages,
                "fetch_dpa_excerpt": toolset.fetch_dpa_excerpt,
            }

            config = types.GenerateContentConfig(
                system_instruction=_SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=_gemini_response_schema(),
                temperature=0.0,
                thinking_config=types.ThinkingConfig(thinking_budget=1024),
                tools=_checklist_tool_declarations(),
            )

            history: list[types.Content] = [
                types.Content(role="user", parts=[types.Part(text="\n\n".join(contents))])
            ]

            final_text = None
            for iteration in range(15):
                response = client.models.generate_content(
                    model=self._settings.gemini_checklist_model,
                    contents=history,
                    config=config,
                )

                parts = response.candidates[0].content.parts
                fc_parts = [p for p in parts if p.function_call]

                if fc_parts:
                    if progress_cb:
                        first_call = fc_parts[0].function_call.name
                        if first_call in {"search_selected_kb", "fetch_selected_source_context"}:
                            progress_cb("DRAFTING_CHECKLIST", "Gathering supporting information from the selected references.")
                        elif first_call in {"search_dpa", "fetch_dpa_pages", "fetch_dpa_excerpt"}:
                            progress_cb("DRAFTING_CHECKLIST", "Reviewing the document for the most relevant sections.")
                        else:
                            progress_cb("DRAFTING_CHECKLIST", "Organizing the information needed for the checklist.")

                    history.append(response.candidates[0].content)

                    tool_response_parts: list[types.Part] = []
                    for part in fc_parts:
                        fc = part.function_call
                        name = fc.name
                        args = dict(fc.args) if fc.args else {}

                        if name in tools_map:
                            try:
                                result = tools_map[name](**args)
                                tool_response_parts.append(
                                    types.Part(function_response=types.FunctionResponse(
                                        name=name,
                                        response={"result": result},
                                        id=fc.id,
                                    ))
                                )
                            except Exception as e:
                                tool_response_parts.append(
                                    types.Part(function_response=types.FunctionResponse(
                                        name=name,
                                        response={"error": str(e)},
                                        id=fc.id,
                                    ))
                                )
                        else:
                            tool_response_parts.append(
                                types.Part(function_response=types.FunctionResponse(
                                    name=name,
                                    response={"error": f"Unknown tool: {name}"},
                                    id=fc.id,
                                ))
                            )
                    history.append(types.Content(role="user", parts=tool_response_parts))
                    continue
                else:
                    if response.text:
                        final_text = response.text
                    break

        if not final_text:
            raise RuntimeError("Gemini did not return structured checklist output after tool iterations.")

        if progress_cb:
            progress_cb("VALIDATING_OUTPUT", "Finalizing the checklist.")

        payload = _parse_checklist_output_text(
            final_text,
            phase="checklist_drafting",
            model=self._settings.gemini_checklist_model,
            attempt=1,
            response=response,
        )

        return _normalize_check_ids(payload)

    def synthesize_drafts_legacy(
        self,
        drafts: list[ChecklistDraftOutput],
        user_instruction: str | None = None,
        progress_cb: ProgressCallback | None = None,
        cancel_check: SynthesisCancelCallback | None = None,
    ) -> ChecklistDraftOutput:
        if not self._settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is required for checklist synthesis.")

        if progress_cb:
            progress_cb("SYNTHESIZING", "Merging and deduplicating final checklist")

        system_instruction = (
            "You are an expert privacy lawyer and technical auditor. "
            "Your task is to merge multiple partial data protection checklists into a single, cohesive, "
            "and deduplicated master checklist.\n"
            "Combine overlapping or redundant items, ensuring all unique pass/fail criteria and sources "
            "are preserved. Combine the open questions. Your output must strictly follow the expected JSON schema."
        )

        contents = [
            "Please merge the following partial checklists into a single final checklist:",
            f"User instruction: {(user_instruction or '').strip() or 'None provided'}",
            "Partial Checklists:"
        ]

        for i, draft in enumerate(drafts):
            contents.append(f"--- Partial Checklist {i + 1} ---")
            contents.append(draft.model_dump_json(indent=2))

        with genai.Client(api_key=self._settings.gemini_api_key) as client:
            for attempt in range(1, 3):
                _raise_if_cancelled(cancel_check, phase="legacy_synthesis_request")
                response = client.models.generate_content(
                    model=self._settings.gemini_checklist_model,
                    contents="\n\n".join(contents),
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type="application/json",
                        response_schema=_gemini_response_schema(),
                        temperature=0.0,
                    ),
                )
                _raise_if_cancelled(cancel_check, phase="legacy_synthesis_response")
                if not response.text:
                    log_event(
                        logging.WARNING,
                        severity="warn",
                        event="checklist_model_empty_response",
                        phase="legacy_synthesis",
                        model=self._settings.gemini_checklist_model,
                        attempt=attempt,
                        finish_reasons=_response_finish_reasons(response),
                        usage_metadata=_response_usage_metadata(response),
                    )
                    raise RuntimeError("Gemini did not return structured output for synthesis.")
                try:
                    payload = _parse_checklist_output_text(
                        response.text,
                        phase="legacy_synthesis",
                        model=self._settings.gemini_checklist_model,
                        attempt=attempt,
                        response=response,
                    )
                    break
                except ValidationError:
                    if attempt >= 2:
                        raise
                    if progress_cb:
                        progress_cb("SYNTHESIZING", "Received malformed synthesis output. Retrying final merge.")
                    _raise_if_cancelled(cancel_check, phase="legacy_synthesis_retry")
        
        all_sources = set()
        for draft in drafts:
            all_sources.update(draft.meta.selected_source_ids)
        payload.meta.selected_source_ids = sorted(list(all_sources))
        
        return _normalize_check_ids(payload)

    def synthesize_drafts_semantic_groups(
        self,
        drafts: list[ChecklistDraftOutput],
        user_instruction: str | None = None,
        progress_cb: SynthesisProgressCallback | None = None,
        trace_cb: SynthesisTraceCallback | None = None,
        cancel_check: SynthesisCancelCallback | None = None,
    ) -> ChecklistDraftOutput:
        payload = self._semantic_group_synthesizer.synthesize(
            drafts=drafts,
            user_instruction=user_instruction,
            progress_cb=progress_cb,
            trace_cb=trace_cb,
            cancel_check=cancel_check,
        )
        return _normalize_check_ids(payload)

    def synthesize_drafts_category_groups(
        self,
        drafts: list[ChecklistDraftOutput],
        user_instruction: str | None = None,
        progress_cb: SynthesisProgressCallback | None = None,
        trace_cb: SynthesisTraceCallback | None = None,
        cancel_check: SynthesisCancelCallback | None = None,
    ) -> ChecklistDraftOutput:
        payload = self._category_group_synthesizer.synthesize(
            drafts=drafts,
            user_instruction=user_instruction,
            progress_cb=progress_cb,
            trace_cb=trace_cb,
            cancel_check=cancel_check,
        )
        return _normalize_check_ids(payload)

    def synthesize_drafts_verified(
        self,
        drafts: list[ChecklistDraftOutput],
        user_instruction: str | None = None,
        progress_cb: SynthesisProgressCallback | None = None,
        trace_cb: SynthesisTraceCallback | None = None,
        cancel_check: SynthesisCancelCallback | None = None,
    ) -> ChecklistDraftOutput:
        return self.synthesize_drafts_category_groups(
            drafts,
            user_instruction=user_instruction,
            progress_cb=progress_cb,
            trace_cb=trace_cb,
            cancel_check=cancel_check,
        )

    def synthesize_drafts(
        self,
        drafts: list[ChecklistDraftOutput],
        user_instruction: str | None = None,
        progress_cb: ProgressCallback | None = None,
    ) -> ChecklistDraftOutput:
        return self.synthesize_drafts_legacy(
            drafts,
            user_instruction=user_instruction,
            progress_cb=progress_cb,
        )

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
            candidate_paths = [path for path in (md_path, txt_path) if isinstance(path, str)]
            path = next(
                (self._settings.repo_root / candidate for candidate in candidate_paths if (self._settings.repo_root / candidate).exists()),
                None,
            )
            if path is None:
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

    def _load_dpa_pages(self, parsed_markdown_path: Path, parsed_pages_path: Path | None) -> list[DpaPageRecord]:
        if parsed_pages_path and parsed_pages_path.exists():
            payload = json.loads(parsed_pages_path.read_text(encoding="utf-8"))
            pages_raw = payload.get("pages")
            if isinstance(pages_raw, list):
                pages: list[DpaPageRecord] = []
                for row in pages_raw:
                    if not isinstance(row, dict):
                        continue
                    page_no = row.get("page_no")
                    page_text = row.get("page_text")
                    if isinstance(page_no, int) and isinstance(page_text, str):
                        pages.append(DpaPageRecord(page=page_no, text=page_text))
                if pages:
                    return pages

        text = parsed_markdown_path.read_text(encoding="utf-8")
        matches = list(re.finditer(r"(?m)^page_no:\s*(\d+)\s*$", text))
        pages: list[DpaPageRecord] = []
        for index, match in enumerate(matches):
            page = int(match.group(1))
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            block = text[start:end]
            text_match = re.search(r"page_text:\n(?P<body>.*?)(?:\npage_images:|\Z)", block, flags=re.S)
            body = text_match.group("body").strip() if text_match else block.strip()
            pages.append(DpaPageRecord(page=page, text=body))
        return pages


class _ChecklistToolset:
    def __init__(
        self,
        *,
        sources: list[SourceRecord],
        dpa_pages: list[DpaPageRecord],
        kb_retriever: KbVectorRetriever,
    ) -> None:
        self._sources = {source.source_id: source for source in sources}
        self._selected_source_ids = [source.source_id for source in sources]
        self._source_chunks = {
            source.source_id: _chunk_text(source.text)
            for source in sources
        }
        self._dpa_pages = dpa_pages
        self._kb_retriever = kb_retriever

    def search_selected_kb(self, query: str, top_k: int = 6) -> str:
        """Run hybrid retrieval over only the selected KB sources and return the best matching excerpts.

        Args:
            query: A focused legal obligation, clause concept, article, or compliance topic to search for.
              Good examples:
              - "processor acts only on documented controller instructions"
              - "subprocessor authorization and objection rights"
              - "Article 28 security and confidentiality obligations"
              Bad examples:
              - "checklist"
              - "GDPR"
              - "everything about DPAs"
            top_k: Maximum number of ranked excerpts to return.

        Usage guidance:
        - Use this as the primary KB discovery tool before drafting checklist items.
        - Start with a focused obligation or clause query, not a broad generic query.
        - If a returned excerpt looks promising but incomplete, call `fetch_selected_source_context`
          to inspect more context from that same selected source.
        - This tool searches only the user-selected KB sources.
        - Internally this is hybrid retrieval: vector similarity plus lexical/full-text ranking.
        """
        try:
            vector_results = self._kb_retriever.search_selected_sources(
                query=query,
                selected_source_ids=self._selected_source_ids,
                top_k=top_k,
            )
        except Exception:
            vector_results = []

        if vector_results:
            payload = [
                {
                    "source_id": item.source_id,
                    "title": item.source_title,
                    "chunk_index": item.chunk_index,
                    "score": item.score,
                    "excerpt": item.excerpt,
                    "structured_text": item.structured_text,
                    "retrieval_mode": "vector",
                }
                for item in vector_results
            ]
            return json.dumps(payload, ensure_ascii=False)

        results: list[dict[str, Any]] = []
        for source_id, chunks in self._source_chunks.items():
            source = self._sources[source_id]
            for index, chunk in enumerate(chunks, start=1):
                score = _score_text(query, chunk)
                if score <= 0:
                    continue
                results.append(
                    {
                        "source_id": source.source_id,
                        "title": source.title,
                        "authority": source.authority,
                        "chunk_index": index,
                        "score": score,
                        "excerpt": chunk,
                        "retrieval_mode": "lexical_fallback",
                    }
                )
        results.sort(key=lambda item: item["score"], reverse=True)
        return json.dumps(results[: max(1, min(top_k, 12))], ensure_ascii=False)

    def fetch_selected_source_context(self, source_id: str, anchor: str, window: int = 1200) -> str:
        """Fetch a larger excerpt from one selected KB source around an anchor term.

        Args:
            source_id: One of the user-selected KB source ids.
            anchor: Text to center the excerpt around.
            window: Approximate number of surrounding characters to include.

        Usage guidance:
        - Use this after `search_selected_kb` when you need broader legal context from a selected source.
        - Pass a concrete anchor such as an article number, clause phrase, or excerpt fragment.
        - Do not use this as a replacement for search; use it for verification and expansion.
        """
        source = self._sources.get(source_id)
        if source is None:
            return json.dumps({"error": f"Unknown or unselected source_id: {source_id}"})

        payload = {
            "source_id": source.source_id,
            "title": source.title,
            "authority": source.authority,
            "url": source.url,
            "anchor": anchor,
            "text": source.text,
        }
        return json.dumps(payload, ensure_ascii=False)

    def search_dpa(self, query: str, top_k: int = 6) -> str:
        """Search the parsed uploaded DPA pages for relevant clauses.

        Args:
            query: Document concept or clause to search for.
            top_k: Maximum number of page matches to return.

        Usage guidance:
        - Use this only after establishing the legal obligation from the selected KB sources.
        - Use focused clause-style queries such as "audit rights", "delete or return personal data", or
          "breach notification without undue delay".
        - The DPA is a refinement input, not the legal source of truth.
        """
        results: list[dict[str, Any]] = []
        for page in self._dpa_pages:
            score = _score_text(query, page.text)
            if score <= 0:
                continue
            results.append({"page": page.page, "score": score, "text": page.text})
        results.sort(key=lambda item: item["score"], reverse=True)
        return json.dumps(results[: max(1, min(top_k, 12))], ensure_ascii=False)

    def fetch_dpa_pages(self, start_page: int, end_page: int) -> str:
        """Fetch the parsed text for a contiguous DPA page range.

        Args:
            start_page: Inclusive starting page number.
            end_page: Inclusive ending page number.

        Usage guidance:
        - Use this when `search_dpa` identifies promising pages and you need broader surrounding context.
        - Prefer short ranges instead of large document sweeps.
        """
        if start_page > end_page:
            start_page, end_page = end_page, start_page
        selected = [
            {"page": page.page, "text": page.text}
            for page in self._dpa_pages
            if start_page <= page.page <= end_page
        ]
        return json.dumps(selected, ensure_ascii=False)

    def fetch_dpa_excerpt(self, page: int, anchor_text: str, window: int = 900) -> str:
        """Fetch a bounded excerpt from a single parsed DPA page around anchor text.

        Args:
            page: Parsed page number.
            anchor_text: Text to center the excerpt around.
            window: Approximate surrounding characters to include.

        Usage guidance:
        - Use this after `search_dpa` when you need precise local context around a clause.
        - Prefer this over fetching many full pages when the target clause is already known.
        """
        page_record = next((item for item in self._dpa_pages if item.page == page), None)
        if page_record is None:
            return json.dumps({"error": f"Unknown page: {page}"})
        return json.dumps({"page": page, "anchor_text": anchor_text, "text": page_record.text}, ensure_ascii=False)


_SYSTEM_PROMPT = """
You generate checklist drafts for DPA review.

Rules:
- Output must strictly match the provided response schema.
- Use only the selected KB sources as the legal basis for checklist items.
- The uploaded DPA is only for tailoring and refinement, not for inventing legal obligations.
- Preserve broad legal coverage implied by the selected KB sources.
- Deduplicate overlapping obligations.
- Treat the user's instruction as a strong preference, but do not fabricate unsupported legal basis or fake citations.
- If a user request is not clearly supported by the selected sources, reflect that uncertainty in open_questions or draft_rationale.
- Every checklist item must be specific, source-backed, and actionable for later review.
- Keep titles concise and professional.
- Every checklist item must use exactly one category from the allowed category taxonomy below.
- Do not invent, rename, abbreviate, or combine category labels outside the allowed list.
- legal_basis should cite the relevant article/section names or source references when visible in the selected-source context.
- evidence_hint should tell the later review agent what clause to look for in the DPA.
- pass_criteria and fail_criteria should be concrete and auditable.
- sources must only reference the selected KB sources.
- Do not include commentary outside the schema.

Allowed categories:
{category_guidance}

Tool usage instructions:
- Use `search_selected_kb` as your primary discovery tool for legal obligations.
- Query the KB in focused slices such as instructions, confidentiality, security, subprocessors, audit rights,
  breach notice, deletion/return, transfers, and assistance obligations.
- When a KB search hit looks relevant but incomplete, use `fetch_selected_source_context` to inspect more context
  from that exact selected source before drafting the checklist item.
- Use DPA tools only after you have established the legal obligation from KB sources.
- Use `search_dpa` to see how the uploaded agreement is structured and whether specific clause families appear present,
  fragmented, unusually worded, or obviously absent.
- Use `fetch_dpa_pages` or `fetch_dpa_excerpt` only for bounded refinement, not for broad document sweeps.
- Do not let DPA wording define the obligation. Let it only refine checklist phrasing, emphasis, and open questions.

Recommended working pattern:
1. Search selected KB sources for a concrete obligation.
2. Expand context from the strongest selected source hits.
3. Draft the source-backed checklist item.
4. Inspect the DPA only to tailor wording, emphasis, and open questions.
5. Repeat until the selected-source coverage is broad and deduplicated.
""".strip().format(category_guidance=_CATEGORY_GUIDANCE_BLOCK)
