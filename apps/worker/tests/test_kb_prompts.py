from __future__ import annotations

from kb_pipeline.models import TaskPayload
from kb_pipeline.prompts import system_prompt, user_prompt


def _task(context_mode: str) -> TaskPayload:
    return TaskPayload(
        task_id="t1",
        run_id="r1",
        source_id="gdpr_regulation_2016_679",
        source_title="GDPR",
        source_url="https://example.com/gdpr",
        chunk_index=0,
        chunk_count=3,
        raw_text="Article 28 processor obligations",
        raw_text_sha256="a" * 64,
        chunk_token_count=10,
        doc_token_count=100,
        context_mode=context_mode,  # type: ignore[arg-type]
        context_window_start=0,
        context_window_end=2,
        context_text="Full or surrounding context",
    )


def test_system_prompt_contains_grounding_and_examples() -> None:
    prompt = system_prompt()
    assert "Contextual compression".lower() in prompt.lower()
    assert "citation_quote" in prompt
    assert "Example JSON" in prompt


def test_user_prompt_includes_full_doc_context() -> None:
    prompt = user_prompt(_task("FULL_DOC"))
    assert "FULL_DOCUMENT_CONTEXT" in prompt
    assert "CURRENT_CHUNK_TEXT" in prompt


def test_user_prompt_includes_surrounding_context() -> None:
    prompt = user_prompt(_task("SURROUNDING_CHUNKS"))
    assert "SURROUNDING_CHUNK_CONTEXT" in prompt
