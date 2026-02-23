from __future__ import annotations

import hashlib
import json
from pathlib import Path

import tiktoken

from kb_pipeline.models import ChunkTaskPlan, PlanningResult, SourcePlan


def tokenizer() -> tiktoken.Encoding:
    try:
        return tiktoken.get_encoding("cl100k_base")
    except KeyError:
        return tiktoken.encoding_for_model("gpt-4o-mini")


def chunk_tokens(enc: tiktoken.Encoding, text: str, chunk_size: int, overlap: int) -> list[str]:
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")
    tokens = enc.encode(text)
    if not tokens:
        return []
    chunks: list[str] = []
    step = chunk_size - overlap
    for start in range(0, len(tokens), step):
        window = tokens[start : start + chunk_size]
        if not window:
            break
        chunks.append(enc.decode(window))
        if start + chunk_size >= len(tokens):
            break
    return chunks


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_manifest(kb_dir: Path) -> tuple[dict, bytes]:
    manifest_path = kb_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"{manifest_path} not found. Run scripts/build_kb.py first.")
    raw = manifest_path.read_bytes()
    return json.loads(raw.decode("utf-8")), raw


def plan_from_kb(
    kb_dir: Path,
    *,
    source_filter: set[str] | None,
    chunk_size: int,
    overlap: int,
    full_doc_threshold_tokens: int,
    max_chunks: int | None = None,
) -> PlanningResult:
    manifest, manifest_raw = _load_manifest(kb_dir)
    enc = tokenizer()

    manifest_sources = manifest.get("sources", [])
    if source_filter:
        manifest_sources = [item for item in manifest_sources if item["source_id"] in source_filter]
    source_plans: list[SourcePlan] = []
    task_plans: list[ChunkTaskPlan] = []
    by_source: dict[str, dict] = {}

    for item in manifest_sources:
        txt_path = Path(item["txt_path"])
        md_path = Path(item["md_path"])
        if not txt_path.is_absolute():
            txt_path = (kb_dir.parent / txt_path).resolve()
        if not md_path.is_absolute():
            md_path = (kb_dir.parent / md_path).resolve()
        doc_text = txt_path.read_text(encoding="utf-8")
        doc_tokens = len(enc.encode(doc_text))
        chunks = chunk_tokens(enc, doc_text, chunk_size=chunk_size, overlap=overlap)

        source_plans.append(
            SourcePlan(
                source_id=item["source_id"],
                title=item["title"],
                authority=item["authority"],
                source_kind=str(item["kind"]).upper(),
                source_url=item["url"],
                local_txt_path=str(txt_path),
                local_md_path=str(md_path),
                content_sha256=_sha256_text(doc_text),
                char_count=len(doc_text),
                token_count=doc_tokens,
            )
        )

        by_source[item["source_id"]] = {
            "chunks": len(chunks),
            "doc_tokens": doc_tokens,
            "context_mode_counts": {"FULL_DOC": 0, "SURROUNDING_CHUNKS": 0},
        }

        for idx, raw_chunk in enumerate(chunks):
            if max_chunks is not None and len(task_plans) >= max_chunks:
                break
            chunk_tokens_count = len(enc.encode(raw_chunk))
            if doc_tokens <= full_doc_threshold_tokens:
                context_mode = "FULL_DOC"
                context_text = doc_text
                window_start = 0
                window_end = len(chunks) - 1
            else:
                context_mode = "SURROUNDING_CHUNKS"
                top = max(0, idx - 3)
                bottom = min(len(chunks) - 1, idx + 3)
                neighbors = [
                    f"[Chunk {n + 1}/{len(chunks)}]\n{chunks[n]}" for n in range(top, bottom + 1) if n != idx
                ]
                context_text = "\n\n".join(neighbors)
                window_start = top
                window_end = bottom
            by_source[item["source_id"]]["context_mode_counts"][context_mode] += 1
            task_plans.append(
                ChunkTaskPlan(
                    source_id=item["source_id"],
                    chunk_index=idx,
                    chunk_count=len(chunks),
                    raw_text=raw_chunk,
                    raw_text_sha256=_sha256_text(raw_chunk),
                    chunk_token_count=chunk_tokens_count,
                    doc_token_count=doc_tokens,
                    context_mode=context_mode,
                    context_window_start=window_start,
                    context_window_end=window_end,
                    context_text=context_text,
                )
            )
        if max_chunks is not None and len(task_plans) >= max_chunks:
            break

    summary = {
        "sources": len(source_plans),
        "chunks": len(task_plans),
        "chunk_size": chunk_size,
        "overlap": overlap,
        "full_doc_threshold": full_doc_threshold_tokens,
        "by_source": by_source,
    }

    return PlanningResult(
        manifest_sha256=_sha256_bytes(manifest_raw),
        sources=source_plans,
        tasks=task_plans,
        summary=summary,
    )
