from __future__ import annotations

import json

from kb_pipeline.models import KbStructureOutput, TaskPayload


def system_prompt() -> str:
    example = {
        "source_title": "GDPR (Regulation (EU) 2016/679) - EUR-Lex EN",
        "source_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32016R0679",
        "article_no": "Article 28(3)",
        "short_description": "Requires processor terms to include mandatory clauses and bind processor actions to controller instructions.",
        "consequences": "Missing or weak processor clauses can create GDPR non-compliance and contract remediation risk.",
        "possible_reasons": [
            "No clause limiting processing to documented controller instructions",
            "Processor obligations are stated only at a high level without required specifics",
            "Template omits audit/assistance requirements in processor terms",
        ],
        "citation_quote": "The processing by a processor shall be governed by a contract ... processes the personal data only on documented instructions from the controller...",
        "citation_section": "Article 28(3)",
    }
    example_ambiguous = {
        "source_title": "EDPB Opinion 22/2024 on processor/sub-processor obligations (EN PDF)",
        "source_url": "https://www.edpb.europa.eu/system/files/2024-10/edpb_opinion_202422_relianceonprocessors-sub-processors_en.pdf",
        "article_no": "Section 4.2",
        "short_description": "Explains practical interpretation boundaries for processor/sub-processor obligation chains.",
        "consequences": None,
        "possible_reasons": [
            "Flow-down clauses are incomplete across the processor/sub-processor chain",
            "Responsibilities are allocated ambiguously between processor and sub-processor",
        ],
        "citation_quote": "The Board considers that the contractual chain must ensure that the obligations remain effective in practice...",
        "citation_section": "Section 4.2",
    }
    return (
        "You perform contextual compression for regulatory/legal text chunks used in a DPA compliance knowledge base.\n"
        "Task: convert one CURRENT_CHUNK_TEXT into a compact, faithful structured record for downstream RAG retrieval.\n"
        "Return only JSON matching the provided schema. No markdown, no prose, no code fences.\n"
        "Ground the output in CURRENT_CHUNK_TEXT first. Use extra context only for disambiguation.\n"
        "Prioritize faithfulness over completeness. Do not invent obligations, article numbers, citations, or legal claims.\n"
        "Copy source_title and source_url exactly from SOURCE_TITLE and SOURCE_URL metadata.\n"
        "citation_quote must be a short verbatim quote from CURRENT_CHUNK_TEXT.\n"
        "citation_section should be the nearest visible article/clause/heading label if present, else null.\n"
        "If consequences are not explicit, infer practical consequences briefly or set it to null.\n"
        "Keep short_description to 1-2 lines and possible_reasons concise (0-3 items).\n"
        "Internal method (do not output): identify legal point in chunk -> disambiguate using context -> compress -> attach exact quote.\n"
        f"Example JSON (clear):\n{json.dumps(example, indent=2)}\n\n"
        f"Example JSON (ambiguous but grounded):\n{json.dumps(example_ambiguous, indent=2)}"
    )


def user_prompt(task: TaskPayload) -> str:
    schema = KbStructureOutput.model_json_schema()
    context_header = (
        f"FULL_DOCUMENT_CONTEXT (doc tokens={task.doc_token_count})\n{task.context_text}"
        if task.context_mode == "FULL_DOC"
        else (
            f"SURROUNDING_CHUNK_CONTEXT (chunks {task.context_window_start + 1}..{task.context_window_end + 1})\n"
            f"{task.context_text}"
        )
    )
    return (
        f"SOURCE_ID: {task.source_id}\n"
        f"SOURCE_TITLE: {task.source_title}\n"
        f"SOURCE_URL: {task.source_url}\n"
        f"CHUNK_INDEX: {task.chunk_index + 1}/{task.chunk_count}\n"
        f"CHUNK_TOKEN_COUNT_EST: {task.chunk_token_count}\n"
        f"CONTEXT_MODE: {task.context_mode}\n\n"
        f"JSON_SCHEMA:\n{json.dumps(schema, indent=2)}\n\n"
        f"CURRENT_CHUNK_TEXT:\n{task.raw_text}\n\n"
        f"{context_header}\n"
    )
