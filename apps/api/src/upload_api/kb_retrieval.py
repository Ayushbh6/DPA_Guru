from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import psycopg
from openai import OpenAI
from psycopg.rows import dict_row

from .config import Settings


@dataclass(frozen=True)
class RetrievedKbChunk:
    source_id: str
    source_title: str
    source_url: str
    chunk_index: int
    score: float
    excerpt: str
    structured_text: str | None


class KbVectorRetriever:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._database_url = settings.database_url.replace("postgresql+psycopg://", "postgresql://")

    def search_selected_sources(self, *, query: str, selected_source_ids: list[str], top_k: int = 6) -> list[RetrievedKbChunk]:
        if not query.strip() or not selected_source_ids:
            return []
        if not self._settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for live KB vector retrieval.")

        embedding = self._embed_query(query)
        vector_literal = self._vector_literal(embedding)
        limit = max(1, min(top_k, 12))
        candidate_limit = max(limit * 4, 12)

        with psycopg.connect(self._database_url, row_factory=dict_row) as conn:
            rows = conn.execute(
                """
                WITH vector_candidates AS (
                  SELECT
                    source_id,
                    source_title,
                    source_url,
                    chunk_index,
                    structured_text,
                    combined_text,
                    (embedding <=> %(embedding)s::vector) AS distance,
                    ROW_NUMBER() OVER (ORDER BY embedding <=> %(embedding)s::vector ASC) AS vector_rank
                  FROM kb_chunks
                  WHERE source_id = ANY(%(source_ids)s)
                  ORDER BY embedding <=> %(embedding)s::vector ASC
                  LIMIT %(candidate_limit)s
                ),
                lexical_candidates AS (
                  SELECT
                    source_id,
                    source_title,
                    source_url,
                    chunk_index,
                    structured_text,
                    combined_text,
                    ts_rank_cd(
                      to_tsvector('english', combined_text),
                      websearch_to_tsquery('english', %(query)s)
                    ) AS lexical_score,
                    ROW_NUMBER() OVER (
                      ORDER BY
                        ts_rank_cd(
                          to_tsvector('english', combined_text),
                          websearch_to_tsquery('english', %(query)s)
                        ) DESC,
                        source_id,
                        chunk_index
                    ) AS lexical_rank
                  FROM kb_chunks
                  WHERE source_id = ANY(%(source_ids)s)
                    AND to_tsvector('english', combined_text) @@ websearch_to_tsquery('english', %(query)s)
                  ORDER BY lexical_score DESC, source_id, chunk_index
                  LIMIT %(candidate_limit)s
                ),
                merged AS (
                  SELECT
                    source_id,
                    chunk_index,
                    MAX(source_title) AS source_title,
                    MAX(source_url) AS source_url,
                    MAX(structured_text) AS structured_text,
                    MAX(combined_text) AS combined_text,
                    MIN(distance) AS distance,
                    MIN(vector_rank) AS vector_rank,
                    MAX(lexical_score) AS lexical_score,
                    MIN(lexical_rank) AS lexical_rank
                  FROM (
                    SELECT
                      source_id,
                      chunk_index,
                      source_title,
                      source_url,
                      structured_text,
                      combined_text,
                      distance,
                      vector_rank,
                      NULL::float AS lexical_score,
                      NULL::int AS lexical_rank
                    FROM vector_candidates
                    UNION ALL
                    SELECT
                      source_id,
                      chunk_index,
                      source_title,
                      source_url,
                      structured_text,
                      combined_text,
                      NULL::float AS distance,
                      NULL::int AS vector_rank,
                      lexical_score,
                      lexical_rank
                    FROM lexical_candidates
                  ) candidate_union
                  GROUP BY source_id, chunk_index
                )
                SELECT
                  source_id,
                  source_title,
                  source_url,
                  chunk_index,
                  structured_text,
                  combined_text,
                  distance,
                  lexical_score,
                  (
                    COALESCE(1.0 / (%(rrf_k)s + vector_rank), 0.0) +
                    COALESCE(1.0 / (%(rrf_k)s + lexical_rank), 0.0)
                  ) AS hybrid_score
                FROM merged
                ORDER BY
                  hybrid_score DESC,
                  COALESCE(lexical_score, 0.0) DESC,
                  COALESCE(distance, 1.0) ASC
                LIMIT %(limit)s
                """,
                {
                    "embedding": vector_literal,
                    "source_ids": selected_source_ids,
                    "query": query,
                    "candidate_limit": candidate_limit,
                    "limit": limit,
                    "rrf_k": 60,
                },
            ).fetchall()

        chunks: list[RetrievedKbChunk] = []
        for row in rows:
            combined_text = str(row.get("combined_text") or "")
            chunks.append(
                RetrievedKbChunk(
                    source_id=str(row["source_id"]),
                    source_title=str(row["source_title"]),
                    source_url=str(row["source_url"]),
                    chunk_index=int(row["chunk_index"]),
                    score=float(row["hybrid_score"]),
                    excerpt=combined_text[:900],
                    structured_text=str(row["structured_text"]) if row.get("structured_text") is not None else None,
                )
            )
        return chunks

    def _embed_query(self, query: str) -> list[float]:
        client = OpenAI(api_key=self._settings.openai_api_key)
        response = client.embeddings.create(
            model=self._settings.openai_embedding_model,
            input=query,
        )
        embedding = response.data[0].embedding
        return [float(value) for value in embedding]

    @staticmethod
    def _vector_literal(values: list[float]) -> str:
        return "[" + ",".join(f"{value:.12f}" for value in values) + "]"
