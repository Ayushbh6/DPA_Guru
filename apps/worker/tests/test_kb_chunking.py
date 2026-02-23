from __future__ import annotations

import json
from pathlib import Path

from kb_pipeline.chunking import chunk_tokens, plan_from_kb, tokenizer


def test_chunk_tokens_overlap_behavior() -> None:
    enc = tokenizer()
    text = " ".join([f"tok{i}" for i in range(3000)])
    chunks = chunk_tokens(enc, text, chunk_size=100, overlap=20)
    assert len(chunks) > 1
    first_tokens = enc.encode(chunks[0])
    second_tokens = enc.encode(chunks[1])
    assert len(first_tokens) <= 100
    assert len(second_tokens) <= 100


def test_plan_from_kb_uses_surrounding_context_above_threshold(tmp_path: Path) -> None:
    kb_dir = tmp_path / "kb"
    kb_dir.mkdir()
    src_dir = kb_dir / "doc1"
    src_dir.mkdir()
    text = " ".join(["gdpr"] * 3000)
    (src_dir / "content.txt").write_text(text, encoding="utf-8")
    (src_dir / "content.md").write_text("# doc1", encoding="utf-8")
    manifest = {
        "sources": [
            {
                "source_id": "doc1",
                "title": "Doc1",
                "authority": "Test",
                "kind": "html",
                "url": "https://example.com/doc1",
                "txt_path": str((src_dir / "content.txt").relative_to(tmp_path)),
                "md_path": str((src_dir / "content.md").relative_to(tmp_path)),
            }
        ]
    }
    (kb_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    plan = plan_from_kb(
        kb_dir,
        source_filter=None,
        chunk_size=50,
        overlap=10,
        full_doc_threshold_tokens=100,
    )
    assert plan.tasks
    assert all(task.context_mode == "SURROUNDING_CHUNKS" for task in plan.tasks)


def test_plan_from_kb_uses_full_doc_below_threshold(tmp_path: Path) -> None:
    kb_dir = tmp_path / "kb"
    kb_dir.mkdir()
    src_dir = kb_dir / "doc1"
    src_dir.mkdir()
    text = "Article 28 processor obligations. " * 30
    (src_dir / "content.txt").write_text(text, encoding="utf-8")
    (src_dir / "content.md").write_text("# doc1", encoding="utf-8")
    manifest = {
        "sources": [
            {
                "source_id": "doc1",
                "title": "Doc1",
                "authority": "Test",
                "kind": "pdf",
                "url": "https://example.com/doc1.pdf",
                "txt_path": str((src_dir / "content.txt").relative_to(tmp_path)),
                "md_path": str((src_dir / "content.md").relative_to(tmp_path)),
            }
        ]
    }
    (kb_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    plan = plan_from_kb(kb_dir, source_filter=None, chunk_size=80, overlap=20, full_doc_threshold_tokens=50000)
    assert plan.tasks
    assert all(task.context_mode == "FULL_DOC" for task in plan.tasks)
