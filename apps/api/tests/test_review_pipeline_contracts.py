from __future__ import annotations

import uuid
from pathlib import Path

from dpa_schemas import CheckAssessmentOutput, ReviewSynthesisOutput
from upload_api.document_retrieval import DpaPageRecord, build_document_chunks, derive_evidence_metadata
from upload_api.config import Settings
from upload_api.review_agent import ReviewAgent, SourceRecord, _ReviewToolset


def _settings() -> Settings:
    return Settings(
        database_url="postgresql+psycopg://postgres:postgres@localhost:5432/postgres",
        api_host="0.0.0.0",
        api_port=8001,
        max_upload_mb=50,
        document_storage_backend="local",
        upload_storage_dir=Path("/tmp/uploads"),
        parsed_storage_dir=Path("/tmp/parsed"),
        tokenizer_encoding="cl100k_base",
        openai_api_key="test-key",
        openai_embedding_model="text-embedding-3-small",
        gemini_api_key="test-key",
        gemini_checklist_model="gemini-3-flash-preview",
        gemini_review_model="gemini-3-flash-preview",
        mistral_api_key=None,
        mistral_ocr_model="mistral-ocr-latest",
        mistral_include_image_base64=False,
        store_parsed_pages_json=False,
        r2_account_id=None,
        r2_bucket=None,
        r2_access_key_id=None,
        r2_secret_access_key=None,
        r2_endpoint_url=None,
        dpa_chunk_size=800,
        dpa_chunk_overlap=300,
        default_dev_tenant_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        alpha_users_json='[{"username":"local-dev","password":"local-dev"}]',
        alpha_bootstrap_owner_username="local-dev",
        session_secret="local-dev-session-secret-change-me",
        session_cookie_secure=False,
        session_cookie_domain=None,
        app_allowed_origins=("http://localhost:3000",),
        alpha_max_total_documents=50,
        deleted_project_retention_days=30,
        repo_root=Path("/tmp/repo"),
    )


def test_check_assessment_requires_abstain_reason() -> None:
    try:
        CheckAssessmentOutput.model_validate(
            {
                "check_id": "CHECK_001",
                "status": "UNKNOWN",
                "risk": "MEDIUM",
                "confidence": 0.0,
                "evidence_quotes": [],
                "kb_citations": [],
                "missing_elements": [],
                "risk_rationale": "Insufficient evidence.",
                "abstained": True,
            }
        )
    except Exception:
        pass
    else:  # pragma: no cover - explicit assertion branch
        raise AssertionError("Expected abstained assessment without reason to fail validation.")


def test_review_synthesis_requires_abstain_reason() -> None:
    try:
        ReviewSynthesisOutput.model_validate(
            {
                "overall": {"score": 0, "risk_level": "HIGH", "summary": "Incomplete review."},
                "highlights": [],
                "next_actions": [],
                "confidence": 0.0,
                "abstained": True,
                "risk_rationale": "Incomplete.",
            }
        )
    except Exception:
        pass
    else:  # pragma: no cover - explicit assertion branch
        raise AssertionError("Expected abstained synthesis without reason to fail validation.")


def test_build_document_chunks_preserves_page_ranges() -> None:
    pages = [
        DpaPageRecord(page=1, text="Controller instructions apply.\n\nProcessor only acts as directed."),
        DpaPageRecord(page=2, text="Security measures are documented.\n\nAudit rights are available."),
    ]

    chunks = build_document_chunks(pages=pages, chunk_size=12, overlap=4)

    assert chunks
    assert chunks[0].page_start == 1
    assert chunks[-1].page_end == 2
    assert all(chunk.provenance_id.startswith("chunk-") for chunk in chunks)


def test_derive_evidence_metadata_matches_whitespace_normalized_quotes() -> None:
    pages = [
        DpaPageRecord(page=4, text="The processor shall process personal data only on documented instructions from the controller.")
    ]
    assessment = CheckAssessmentOutput.model_validate(
        {
            "check_id": "CHECK_001",
            "status": "COMPLIANT",
            "risk": "LOW",
            "confidence": 0.92,
            "evidence_quotes": [
                {
                    "page": 4,
                    "quote": "process personal data only   on documented instructions",
                }
            ],
            "kb_citations": [],
            "missing_elements": [],
            "risk_rationale": "The clause is present.",
            "abstained": False,
        }
    )

    citation_pages, spans = derive_evidence_metadata(pages, assessment.evidence_quotes)

    assert citation_pages == [4]
    assert len(spans) == 1
    assert spans[0].page == 4
    assert spans[0].end_offset > spans[0].start_offset


def test_review_agent_prefetch_uses_lexical_fallbacks_when_vector_search_fails() -> None:
    agent = ReviewAgent(_settings())
    agent._kb_retriever.search_selected_sources = lambda **_: (_ for _ in ()).throw(RuntimeError("kb down"))  # type: ignore[method-assign]
    agent._document_retriever.search_document = lambda **_: (_ for _ in ()).throw(RuntimeError("doc down"))  # type: ignore[method-assign]

    sources = [
        SourceRecord(
            source_id="gdpr",
            title="GDPR",
            authority="EUR-Lex",
            kind="html",
            url="https://example.com/gdpr",
            text="The processor shall process personal data only on documented instructions.",
        )
    ]
    pages = [DpaPageRecord(page=2, text="Confidentiality obligations bind all authorized personnel.")]

    evidence = agent.prefetch_evidence(
        document_id=uuid.uuid4(),
        query="documented instructions confidentiality",
        sources=sources,
        dpa_pages=pages,
        kb_top_k=4,
        dpa_top_k=6,
    )

    assert evidence.kb_hits
    assert evidence.kb_hits[0].source_id == "gdpr"
    assert evidence.dpa_spans
    assert evidence.dpa_spans[0].page_start == 2


def test_review_toolset_fetch_dpa_span_supports_page_fallback_ids() -> None:
    class _Retriever:
        def fetch_span(self, *, document_id, provenance_id):  # noqa: ANN001
            return None

    toolset = _ReviewToolset(
        document_id=uuid.uuid4(),
        sources=[],
        dpa_pages=[DpaPageRecord(page=5, text="Audit rights are available on request.")],
        document_retriever=_Retriever(),
    )

    payload = toolset.fetch_dpa_span("page-5")

    assert "Audit rights are available on request." in payload
