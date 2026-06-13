from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass

from upload_api.config import Settings
from upload_api.document_retrieval import DocumentVectorRetriever, DpaPageRecord
from upload_api.kb_retrieval import KbVectorRetriever, RetrievedKbChunk

from .schemas import SearchDocumentHit


_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{1,}")
_ANCHOR_MIN_LEN = 4


@dataclass(frozen=True)
class KbSourceRecord:
    source_id: str
    title: str
    authority: str
    kind: str
    url: str
    text: str


@dataclass(frozen=True)
class DocumentRecord:
    document_id: str
    document_name: str
    document_type: str
    is_primary: bool


def keyword_terms(text: str) -> list[str]:
    seen: set[str] = set()
    terms: list[str] = []
    for match in _WORD_RE.finditer(text.lower()):
        term = match.group(0)
        if term in seen or len(term) < 3:
            continue
        seen.add(term)
        terms.append(term)
    return terms


def chunk_text(text: str, *, chunk_chars: int = 1800) -> list[str]:
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


def score_text(query: str, text: str) -> float:
    lowered = text.lower()
    score = 0.0
    for term in keyword_terms(query):
        score += lowered.count(term)
    return score


def best_anchor_window(text: str, anchor: str, *, window: int) -> str:
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


def load_kb_sources(settings: Settings, selected_source_ids: list[str]) -> list[KbSourceRecord]:
    manifest_path = settings.repo_root / "kb" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_rows = manifest.get("sources")
    if not isinstance(source_rows, list):
        raise RuntimeError("KB manifest is invalid.")

    selected = set(selected_source_ids)
    records: list[KbSourceRecord] = []
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
            (settings.repo_root / candidate for candidate in candidate_paths if (settings.repo_root / candidate).exists()),
            None,
        )
        if path is None:
            continue
        records.append(
            KbSourceRecord(
                source_id=source_id,
                title=str(row.get("title") or source_id),
                authority=str(row.get("authority") or ""),
                kind=str(row.get("kind") or ""),
                url=str(row.get("url") or ""),
                text=path.read_text(encoding="utf-8"),
            )
        )
    return records


def search_kb_sources(
    *,
    retriever: KbVectorRetriever,
    sources: list[KbSourceRecord],
    query: str,
    kb_source_ids: list[str] | None = None,
    top_k: int = 6,
) -> list[dict]:
    if not query.strip():
        return []
    source_map = {source.source_id: source for source in sources}
    allowed_ids = list(kb_source_ids or source_map.keys())
    allowed_sources = [source_map[source_id] for source_id in allowed_ids if source_id in source_map]
    if not allowed_sources:
        return []

    try:
        vector_results = retriever.search_selected_sources(
            query=query,
            selected_source_ids=[source.source_id for source in allowed_sources],
            top_k=top_k,
        )
    except Exception:
        vector_results = []

    if vector_results:
        return [
            {
                "source_id": item.source_id,
                "title": item.source_title,
                "authority": source_map.get(item.source_id).authority if item.source_id in source_map else "",
                "url": item.source_url,
                "chunk_index": item.chunk_index,
                "score": item.score,
                "excerpt": item.excerpt,
                "structured_text": item.structured_text,
                "retrieval_mode": "vector",
            }
            for item in vector_results
        ]

    lexical_hits: list[tuple[float, RetrievedKbChunk]] = []
    for source in allowed_sources:
        for index, chunk in enumerate(chunk_text(source.text), start=1):
            score = score_text(query, chunk)
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
    return [
        {
            "source_id": item.source_id,
            "title": item.source_title,
            "authority": source_map.get(item.source_id).authority if item.source_id in source_map else "",
            "url": item.source_url,
            "chunk_index": item.chunk_index,
            "score": item.score,
            "excerpt": item.excerpt,
            "structured_text": item.structured_text,
            "retrieval_mode": "lexical_fallback",
        }
        for _, item in lexical_hits[: max(1, min(top_k, 12))]
    ]


class DocumentCorpus:
    def __init__(
        self,
        *,
        document_retriever: DocumentVectorRetriever,
        document_records: list[DocumentRecord],
        pages_by_document: dict[str, list[DpaPageRecord]],
    ) -> None:
        self._document_retriever = document_retriever
        self._document_records = {record.document_id: record for record in document_records}
        self._pages_by_document = pages_by_document

    def list_records(self) -> list[dict[str, object]]:
        return [
            {
                "document_id": record.document_id,
                "document_name": record.document_name,
                "document_type": record.document_type,
                "is_primary": record.is_primary,
            }
            for record in self._document_records.values()
        ]

    def search(
        self,
        *,
        query: str,
        document_ids: list[str] | None = None,
        document_types: list[str] | None = None,
        top_k: int = 6,
    ) -> list[SearchDocumentHit]:
        if not query.strip():
            return []

        allowed_ids = set(document_ids or self._document_records.keys())
        allowed_types = set(document_types or [])
        hits: list[SearchDocumentHit] = []
        seen: set[str] = set()

        for document_id, record in self._document_records.items():
            if document_id not in allowed_ids:
                continue
            if allowed_types and record.document_type not in allowed_types:
                continue

            try:
                vector_hits = self._document_retriever.search_document(
                    document_id=uuid.UUID(document_id),
                    query=query,
                    top_k=top_k,
                )
            except Exception:
                vector_hits = []

            for item in vector_hits:
                hit_id = f"{document_id}:{item.provenance_id}"
                if hit_id in seen:
                    continue
                seen.add(hit_id)
                hits.append(
                    SearchDocumentHit(
                        hit_id=hit_id,
                        document_id=document_id,
                        document_name=record.document_name,
                        document_type=record.document_type,
                        page_start=item.page_start,
                        page_end=item.page_end,
                        score=item.score,
                        excerpt=item.text[:800].strip(),
                        provenance_id=item.provenance_id,
                    )
                )

            if vector_hits:
                continue

            for page in self._pages_by_document.get(document_id, []):
                score = score_text(query, page.text)
                if score <= 0:
                    continue
                hit_id = f"{document_id}:page-{page.page}"
                if hit_id in seen:
                    continue
                seen.add(hit_id)
                hits.append(
                    SearchDocumentHit(
                        hit_id=hit_id,
                        document_id=document_id,
                        document_name=record.document_name,
                        document_type=record.document_type,
                        page_start=page.page,
                        page_end=page.page,
                        score=score,
                        excerpt=page.text[:800].strip(),
                        provenance_id=f"page-{page.page}",
                    )
                )

        hits.sort(key=lambda item: (-item.score, item.document_name, item.page_start, item.page_end))
        return hits[: max(1, min(top_k, 12))]

    def fetch_pages(self, *, document_id: str, start_page: int, end_page: int) -> list[dict[str, object]]:
        record = self._document_records.get(document_id)
        if record is None:
            return []
        if start_page > end_page:
            start_page, end_page = end_page, start_page
        return [
            {
                "document_id": document_id,
                "document_name": record.document_name,
                "document_type": record.document_type,
                "page": page.page,
                "text": page.text,
            }
            for page in self._pages_by_document.get(document_id, [])
            if start_page <= page.page <= end_page
        ]
