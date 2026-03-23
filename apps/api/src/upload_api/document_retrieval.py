from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from typing import Protocol

import psycopg
import tiktoken
from openai import OpenAI
from psycopg.rows import dict_row
from sqlalchemy import delete
from sqlalchemy.orm import Session, sessionmaker

from db.models import DocumentChunk
from dpa_schemas import EvidenceQuote, EvidenceSpan

from .config import Settings


_WS_RE = re.compile(r"\s+")


class _Tokenizer(Protocol):
    def encode(self, text: str) -> list[int]: ...


@dataclass(frozen=True)
class DpaPageRecord:
    page: int
    text: str


@dataclass(frozen=True)
class RetrievedDpaSpan:
    provenance_id: str
    page_start: int
    page_end: int
    text: str
    score: float


@dataclass(frozen=True)
class _PageParagraph:
    page: int
    text: str
    token_count: int


@dataclass(frozen=True)
class _ChunkPlan:
    chunk_text: str
    page_start: int
    page_end: int
    provenance_id: str


class DocumentChunkIndexer:
    def __init__(self, settings: Settings, session_factory: sessionmaker[Session]) -> None:
        self._settings = settings
        self._session_factory = session_factory

    def index_document(self, *, document_id: uuid.UUID, pages: list[DpaPageRecord]) -> int:
        plans = build_document_chunks(
            pages=pages,
            chunk_size=self._settings.dpa_chunk_size,
            overlap=self._settings.dpa_chunk_overlap,
        )
        embeddings = self._embed_texts([plan.chunk_text for plan in plans]) if plans else []

        with self._session_factory() as session:
            session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
            session.flush()
            for plan, embedding in zip(plans, embeddings, strict=True):
                session.add(
                    DocumentChunk(
                        document_id=document_id,
                        chunk_text=plan.chunk_text,
                        page_start=plan.page_start,
                        page_end=plan.page_end,
                        provenance_id=plan.provenance_id,
                        embedding=embedding,
                    )
                )
            session.commit()
        return len(plans)

    def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if not self._settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for DPA document indexing.")
        client = OpenAI(api_key=self._settings.openai_api_key)
        response = client.embeddings.create(model=self._settings.openai_embedding_model, input=texts)
        return [[float(value) for value in item.embedding] for item in response.data]


class DocumentVectorRetriever:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._database_url = settings.database_url.replace("postgresql+psycopg://", "postgresql://")

    def search_document(self, *, document_id: uuid.UUID, query: str, top_k: int = 6) -> list[RetrievedDpaSpan]:
        if not query.strip():
            return []
        if not self._settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for DPA vector retrieval.")

        embedding = self._embed_query(query)
        vector_literal = self._vector_literal(embedding)
        limit = max(1, min(top_k, 12))
        candidate_limit = max(limit * 4, 12)

        with psycopg.connect(self._database_url, row_factory=dict_row) as conn:
            rows = conn.execute(
                """
                WITH vector_candidates AS (
                  SELECT
                    provenance_id,
                    page_start,
                    page_end,
                    chunk_text,
                    (embedding <=> %(embedding)s::vector) AS distance,
                    ROW_NUMBER() OVER (ORDER BY embedding <=> %(embedding)s::vector ASC) AS vector_rank
                  FROM document_chunks
                  WHERE document_id = %(document_id)s
                  ORDER BY embedding <=> %(embedding)s::vector ASC
                  LIMIT %(candidate_limit)s
                ),
                lexical_candidates AS (
                  SELECT
                    provenance_id,
                    page_start,
                    page_end,
                    chunk_text,
                    ts_rank_cd(
                      to_tsvector('english', chunk_text),
                      websearch_to_tsquery('english', %(query)s)
                    ) AS lexical_score,
                    ROW_NUMBER() OVER (
                      ORDER BY
                        ts_rank_cd(
                          to_tsvector('english', chunk_text),
                          websearch_to_tsquery('english', %(query)s)
                        ) DESC,
                        page_start,
                        page_end,
                        provenance_id
                    ) AS lexical_rank
                  FROM document_chunks
                  WHERE document_id = %(document_id)s
                    AND to_tsvector('english', chunk_text) @@ websearch_to_tsquery('english', %(query)s)
                  ORDER BY lexical_score DESC, page_start, page_end, provenance_id
                  LIMIT %(candidate_limit)s
                ),
                merged AS (
                  SELECT
                    provenance_id,
                    MAX(page_start) AS page_start,
                    MAX(page_end) AS page_end,
                    MAX(chunk_text) AS chunk_text,
                    MIN(distance) AS distance,
                    MIN(vector_rank) AS vector_rank,
                    MAX(lexical_score) AS lexical_score,
                    MIN(lexical_rank) AS lexical_rank
                  FROM (
                    SELECT provenance_id, page_start, page_end, chunk_text, distance, vector_rank, NULL::float AS lexical_score, NULL::int AS lexical_rank
                    FROM vector_candidates
                    UNION ALL
                    SELECT provenance_id, page_start, page_end, chunk_text, NULL::float AS distance, NULL::int AS vector_rank, lexical_score, lexical_rank
                    FROM lexical_candidates
                  ) candidate_union
                  GROUP BY provenance_id
                )
                SELECT
                  provenance_id,
                  page_start,
                  page_end,
                  chunk_text,
                  (
                    COALESCE(1.0 / (%(rrf_k)s + vector_rank), 0.0) +
                    COALESCE(1.0 / (%(rrf_k)s + lexical_rank), 0.0)
                  ) AS hybrid_score
                FROM merged
                ORDER BY hybrid_score DESC, page_start ASC, page_end ASC
                LIMIT %(limit)s
                """,
                {
                    "document_id": document_id,
                    "embedding": vector_literal,
                    "query": query,
                    "candidate_limit": candidate_limit,
                    "limit": limit,
                    "rrf_k": 60,
                },
            ).fetchall()

        return [
            RetrievedDpaSpan(
                provenance_id=str(row["provenance_id"]),
                page_start=int(row["page_start"]),
                page_end=int(row["page_end"]),
                text=str(row["chunk_text"]),
                score=float(row["hybrid_score"]),
            )
            for row in rows
        ]

    def fetch_span(self, *, document_id: uuid.UUID, provenance_id: str) -> RetrievedDpaSpan | None:
        with psycopg.connect(self._database_url, row_factory=dict_row) as conn:
            row = conn.execute(
                """
                SELECT provenance_id, page_start, page_end, chunk_text
                FROM document_chunks
                WHERE document_id = %(document_id)s AND provenance_id = %(provenance_id)s
                """,
                {"document_id": document_id, "provenance_id": provenance_id},
            ).fetchone()
        if row is None:
            return None
        return RetrievedDpaSpan(
            provenance_id=str(row["provenance_id"]),
            page_start=int(row["page_start"]),
            page_end=int(row["page_end"]),
            text=str(row["chunk_text"]),
            score=1.0,
        )

    def _embed_query(self, query: str) -> list[float]:
        client = OpenAI(api_key=self._settings.openai_api_key)
        response = client.embeddings.create(model=self._settings.openai_embedding_model, input=query)
        return [float(value) for value in response.data[0].embedding]

    @staticmethod
    def _vector_literal(values: list[float]) -> str:
        return "[" + ",".join(f"{value:.12f}" for value in values) + "]"


def build_document_chunks(*, pages: list[DpaPageRecord], chunk_size: int, overlap: int) -> list[_ChunkPlan]:
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    enc = _tokenizer()
    units = _paragraph_units(enc, pages)
    if not units:
        return []

    chunks: list[_ChunkPlan] = []
    current: list[_PageParagraph] = []
    current_tokens = 0
    chunk_index = 0

    for unit in units:
        if current and current_tokens + unit.token_count > chunk_size:
            chunks.append(_finalize_chunk(current, chunk_index))
            chunk_index += 1
            current, current_tokens = _overlap_units(current, overlap)
        current.append(unit)
        current_tokens += unit.token_count

    if current:
        chunks.append(_finalize_chunk(current, chunk_index))
    return chunks


def derive_evidence_metadata(
    pages: list[DpaPageRecord],
    evidence_quotes: list[EvidenceQuote],
) -> tuple[list[int], list[EvidenceSpan]]:
    page_map = {page.page: page.text for page in pages}
    citation_pages = sorted({quote.page for quote in evidence_quotes})
    spans: list[EvidenceSpan] = []
    for quote in evidence_quotes:
        page_text = page_map.get(quote.page)
        if not page_text:
            continue
        span = _match_quote_to_page(page_text, quote.quote, quote.page)
        if span is not None:
            spans.append(span)
    return citation_pages, spans


def _finalize_chunk(units: list[_PageParagraph], chunk_index: int) -> _ChunkPlan:
    text = "\n\n".join(unit.text for unit in units).strip()
    page_start = min(unit.page for unit in units)
    page_end = max(unit.page for unit in units)
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
    return _ChunkPlan(
        chunk_text=text,
        page_start=page_start,
        page_end=page_end,
        provenance_id=f"chunk-{chunk_index:04d}-p{page_start}-{page_end}-{digest}",
    )


def _overlap_units(units: list[_PageParagraph], overlap: int) -> tuple[list[_PageParagraph], int]:
    if overlap <= 0 or not units:
        return [], 0
    selected: list[_PageParagraph] = []
    token_total = 0
    for unit in reversed(units):
        selected.insert(0, unit)
        token_total += unit.token_count
        if token_total >= overlap:
            break
    return selected, token_total


def _paragraph_units(enc: _Tokenizer, pages: list[DpaPageRecord]) -> list[_PageParagraph]:
    units: list[_PageParagraph] = []
    for page in pages:
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", page.text) if part.strip()]
        if not paragraphs and page.text.strip():
            paragraphs = [page.text.strip()]
        for paragraph in paragraphs:
            token_count = len(enc.encode(paragraph))
            if token_count == 0:
                continue
            units.append(_PageParagraph(page=page.page, text=paragraph, token_count=token_count))
    return units


def _tokenizer() -> _Tokenizer:
    try:
        return tiktoken.get_encoding("cl100k_base")
    except Exception:
        try:
            return tiktoken.encoding_for_model("gpt-4o-mini")
        except Exception:
            return _WhitespaceTokenizer()


class _WhitespaceTokenizer:
    def encode(self, text: str) -> list[int]:
        words = [part for part in re.split(r"\s+", text.strip()) if part]
        return list(range(len(words)))


def _match_quote_to_page(page_text: str, quote: str, page: int) -> EvidenceSpan | None:
    direct_index = page_text.find(quote)
    if direct_index >= 0:
        return EvidenceSpan(page=page, start_offset=direct_index, end_offset=direct_index + len(quote))

    normalized_page, page_map = _normalize_with_map(page_text)
    normalized_quote = _WS_RE.sub(" ", quote).strip()
    if not normalized_quote:
        return None
    normalized_index = normalized_page.find(normalized_quote)
    if normalized_index < 0:
        return None
    start = page_map[normalized_index]
    end_index = normalized_index + len(normalized_quote) - 1
    end = page_map[end_index] + 1
    return EvidenceSpan(page=page, start_offset=start, end_offset=end)


def _normalize_with_map(text: str) -> tuple[str, list[int]]:
    chars: list[str] = []
    positions: list[int] = []
    previous_was_space = False
    for index, char in enumerate(text):
        if char.isspace():
            if previous_was_space:
                continue
            chars.append(" ")
            positions.append(index)
            previous_was_space = True
        else:
            chars.append(char)
            positions.append(index)
            previous_was_space = False
    normalized = "".join(chars).strip()
    if not normalized:
        return "", []
    leading_trim = len("".join(chars)) - len("".join(chars).lstrip())
    if leading_trim:
        positions = positions[leading_trim:]
    trailing_trim = len("".join(chars).rstrip())
    positions = positions[:trailing_trim - leading_trim]
    return normalized, positions
