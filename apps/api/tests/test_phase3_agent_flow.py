from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import timedelta
from pathlib import Path

from sqlalchemy import func, select

from db.models import AgentRun, AgentRunOutput, AgentRunToolCall, AnalysisRun, ApprovalPackStageOutput, ApprovedChecklist, Document, DocumentChunk, DocumentParseJob, Finding, Project
from dpa_checklist import ChecklistDocument, ChecklistItem
from upload_api.config import Settings
from upload_api.db import build_session_factory
from upload_api.agents.execution import CriteriaResearchExecutor
from upload_api.agents.schemas import CriteriaResearchPayload, StartCriteriaResearchInput
from upload_api.events import JobEventBus
from upload_api.jobs import UploadPipelineService, utcnow
from upload_api.schemas import ApproveChecklistRequest, CreateAnalysisRunRequest
from upload_api.storage import ArtifactStore


os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/postgres")

REPO_ROOT = Path(__file__).resolve().parents[3]
TEST_PDF_DIR = REPO_ROOT / "test_pdf"


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=os.environ["DATABASE_URL"],
        api_host="0.0.0.0",
        api_port=8001,
        max_upload_mb=25,
        max_pdf_pages=200,
        document_storage_backend="local",
        upload_storage_dir=tmp_path / "uploads",
        parsed_storage_dir=tmp_path / "parsed",
        tokenizer_encoding="cl100k_base",
        openai_api_key="test-key",
        openai_embedding_model="text-embedding-3-small",
        checklist_synthesis_strategy="legacy",
        checklist_synthesis_legacy_fallback=True,
        checklist_synthesis_group_similarity_threshold=0.90,
        checklist_synthesis_group_merge_threshold=0.92,
        checklist_synthesis_group_max_neighbors=2,
        checklist_synthesis_group_max_size=5,
        checklist_synthesis_group_max_parallel=4,
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
        session_secret="test-session-secret",
        session_cookie_secure=False,
        session_cookie_samesite="lax",
        session_cookie_domain=None,
        app_allowed_origins=("http://localhost:3000",),
        alpha_max_projects_per_user=20,
        alpha_max_documents_per_user=8,
        alpha_max_check_runs_per_user=1000,
        alpha_max_total_documents=50,
        alpha_max_total_active_storage_mb=5000,
        login_rate_limit_per_ip=20,
        login_rate_limit_per_username=10,
        login_rate_limit_window_seconds=300,
        upload_rate_limit_per_user=10,
        upload_rate_limit_per_ip=20,
        upload_rate_limit_window_seconds=600,
        checklist_rate_limit_per_user=1,
        checklist_rate_limit_window_seconds=60,
        analysis_rate_limit_per_user=1,
        analysis_rate_limit_window_seconds=60,
        worker_id="test-worker",
        worker_concurrency=2,
        worker_poll_interval_seconds=1,
        worker_lease_duration_seconds=90,
        worker_heartbeat_interval_seconds=15,
        worker_retry_backoff_first_seconds=30,
        worker_retry_backoff_second_seconds=120,
        deleted_project_retention_days=30,
        document_archive_retention_days=30,
        repo_root=REPO_ROOT,
        gemini_approval_pack_model="gemini-3-flash-preview",
        agent_execution_backend="local_postgres",
        agent_default_max_tool_calls=50,
        agent_criteria_research_max_tool_calls=40,
        agent_criteria_max_children=5,
        agent_child_concurrency=5,
        agent_collect_wait_seconds=1,
    )


def _build_service(tmp_path: Path) -> tuple[UploadPipelineService, callable]:
    settings = _settings(tmp_path)
    session_factory = build_session_factory(settings.database_url)
    service = UploadPipelineService(
        settings=settings,
        session_factory=session_factory,
        storage=ArtifactStore(
            primary_backend="local",
            upload_dir=settings.upload_storage_dir,
            parsed_dir=settings.parsed_storage_dir,
        ),
        event_bus=JobEventBus(),
    )
    return service, session_factory


def test_criteria_research_executor_finishes_parent_and_cleans_completed_tasks(tmp_path: Path) -> None:
    executor = CriteriaResearchExecutor(settings=_settings(tmp_path))
    parent_run_id = str(uuid.uuid4())
    payload = StartCriteriaResearchInput(query="Research deletion obligations.")

    started = executor.start(
        parent_agent_run_id=parent_run_id,
        payload=payload,
        launch_fn=lambda _research_id, _payload: (
            str(uuid.uuid4()),
            CriteriaResearchPayload(answer="Deletion obligations require return or deletion on termination."),
        ),
    )

    assert started.status == "queued"
    collected = executor.collect(parent_agent_run_id=parent_run_id, wait_seconds=1)
    assert [item.status for item in collected] == ["completed"]

    executor.finish_parent(parent_agent_run_id=parent_run_id)
    assert executor.collect(parent_agent_run_id=parent_run_id) == []
    assert not executor.is_parent_cancelled(parent_agent_run_id=parent_run_id)


def _task_input_from_contents(contents) -> dict:
    text = contents[0].parts[0].text
    _, payload = text.split("Task input JSON:\n", 1)
    return json.loads(payload)


class _FakeUsage:
    def model_dump(self, mode: str = "python") -> dict[str, int]:
        return {"prompt_token_count": 100, "candidates_token_count": 50, "total_token_count": 150}


class _FakeFunctionCall:
    def __init__(self, name: str, args: dict, call_id: str) -> None:
        self.name = name
        self.args = args
        self.id = call_id


class _FakePart:
    def __init__(self, *, text: str | None = None, function_call: _FakeFunctionCall | None = None) -> None:
        self.text = text
        self.function_call = function_call
        self.function_response = None


class _FakeContent:
    def __init__(self, parts: list[_FakePart]) -> None:
        self.parts = parts


class _FakeCandidate:
    def __init__(self, parts: list[_FakePart]) -> None:
        self.content = _FakeContent(parts)


class _FakeResponse:
    def __init__(self, *, parts: list[_FakePart], text: str | None = None) -> None:
        self.candidates = [_FakeCandidate(parts)]
        self.text = text
        self.usage_metadata = _FakeUsage()


class FakeGenAIClient:
    def __init__(self, *args, **kwargs) -> None:  # noqa: D401, ANN002, ANN003
        self.models = self
        self._step = 0

    def __enter__(self) -> "FakeGenAIClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001, ANN201
        return False

    def generate_content(self, *, model, contents, config):  # noqa: ANN001
        self._step += 1
        assert config.response_schema is None
        assert isinstance(config.response_json_schema, dict)
        system_prompt = config.system_instruction or ""
        if "delegated Criteria Research agent" in system_prompt:
            return self._criteria_research_response(contents)
        if "Criteria Agent for Checker" in system_prompt:
            return self._criteria_response(contents)
        if "Review Agent for Checker" in system_prompt:
            return self._review_response(contents)
        if "Approval Pack Agent for Checker" in system_prompt:
            return self._approval_pack_response()
        raise AssertionError(f"Unexpected fake Gemini prompt: {system_prompt[:80]}")

    def _function_response(self, name: str, args: dict) -> _FakeResponse:
        call = _FakeFunctionCall(name=name, args=args, call_id=f"call-{self._step}")
        return _FakeResponse(parts=[_FakePart(function_call=call)])

    def _json_response(self, payload: dict) -> _FakeResponse:
        text = json.dumps(payload)
        return _FakeResponse(parts=[_FakePart(text=text)], text=text)

    def _criteria_response(self, contents) -> _FakeResponse:  # noqa: ANN001
        task_input = _task_input_from_contents(contents)
        selected_source_ids = task_input["criteria_context"]["selected_kb_source_ids"]
        if self._step == 1:
            return self._function_response("list_documents", {})
        if self._step == 2:
            return self._function_response("get_review_profile", {})
        if self._step == 3:
            return self._function_response(
                "start_criteria_research",
                {
                    "query": "Research deletion and retention obligations for vendor DPAs and summarize practical checklist implications.",
                    "document_types": ["main_dpa"],
                    "kb_source_ids": selected_source_ids,
                },
            )
        if self._step == 4:
            return self._function_response("collect_criteria_research", {"wait_seconds": 1})
        return self._json_response(
            {
                "version": "criteria_v1",
                "meta": {
                    "selected_source_ids": selected_source_ids,
                    "confidence": 0.9,
                    "open_questions": [],
                    "generation_summary": "Focused on transfer controls and post-termination deletion handling for this vendor DPA.",
                },
                "validation_warnings": [],
                "checks": [
                    {
                        "check_id": "TEMP_001",
                        "title": "International transfers must rely on documented transfer mechanisms",
                        "category": "International Transfers & Localization",
                        "legal_basis": ["GDPR Article 28", "EU SCCs"],
                        "required": True,
                        "severity": "HIGH",
                        "evidence_hint": "Find the clauses that address international transfers and SCC incorporation.",
                        "pass_criteria": ["The DPA explains the transfer mechanism for restricted transfers."],
                        "fail_criteria": ["The DPA is silent on cross-border transfer mechanics for applicable regions."],
                        "sources": [
                            {
                                "source_type": "LAW",
                                "authority": "EUR-Lex",
                                "source_ref": "EU SCCs",
                                "source_url": "https://example.com/eu-sccs",
                                "source_excerpt": "Transfers outside Europe need an appropriate transfer mechanism.",
                            }
                        ],
                        "draft_rationale": "Transfer mechanics are business-critical for EU personal data flows.",
                        "rationale": "This determines whether the vendor can lawfully receive personal data outside Europe.",
                        "applicability": "Applies because the review profile and DPA include regional transfer terms.",
                        "priority": "high",
                        "expected_evidence": [
                            {
                                "document_types": ["main_dpa", "data_transfer_terms"],
                                "description": "Regional transfer clauses or SCC incorporation language.",
                            }
                        ],
                        "likely_document_types": ["main_dpa", "data_transfer_terms"],
                        "vendor_context_factors": ["processes_eu_personal_data", "transfers_data_outside_eea"],
                        "profile_references": ["standard_vendor_dpa_v1"],
                    },
                    {
                        "check_id": "TEMP_002",
                        "title": "Post-termination deletion obligations must be operationally clear",
                        "category": "Retention, Deletion & Exit",
                        "legal_basis": ["GDPR Article 28(3)(g)"],
                        "required": True,
                        "severity": "MEDIUM",
                        "evidence_hint": "Find the post-termination deletion clause and any retention carve-outs.",
                        "pass_criteria": ["The DPA clearly states deletion or return obligations and practical handling of retained copies."],
                        "fail_criteria": ["Deletion obligations are vague or leave retention practices unclear."],
                        "sources": [
                            {
                                "source_type": "LAW",
                                "authority": "EUR-Lex",
                                "source_ref": "GDPR Article 28(3)(g)",
                                "source_url": "https://example.com/gdpr-28-3-g",
                                "source_excerpt": "Processors should delete or return personal data after the end of services unless law requires storage.",
                            }
                        ],
                        "draft_rationale": "Post-termination handling is frequently where operational gaps appear.",
                        "rationale": "The business needs to know what happens to customer data at exit and during backup retention.",
                        "applicability": "Applies to all vendor DPAs, especially when the vendor controls service-side backups.",
                        "priority": "medium",
                        "expected_evidence": [
                            {
                                "document_types": ["main_dpa"],
                                "description": "Termination deletion clause, retention exceptions, and documentation references.",
                            }
                        ],
                        "likely_document_types": ["main_dpa"],
                        "vendor_context_factors": ["shares_personal_data"],
                        "profile_references": ["standard_vendor_dpa_v1"],
                    },
                ],
            }
        )

    def _criteria_research_response(self, contents) -> _FakeResponse:  # noqa: ANN001
        task_input = _task_input_from_contents(contents)
        document = task_input["document_records"][0]
        if self._step == 1:
            return self._function_response(
                "search_kb",
                {
                    "query": task_input["query"],
                    "kb_source_ids": task_input["kb_source_hints"],
                },
            )
        if self._step == 2:
            return self._function_response(
                "search_uploaded_documents",
                {
                    "query": "delete retention termination backups",
                    "document_ids": [document["document_id"]],
                    "top_k": 4,
                },
            )
        return self._json_response(
            {
                "answer": "The DPA should be checked for a clear delete-or-return obligation plus explicit treatment of backups and legally required retention.",
                "key_points": [
                    "A retention carve-out is common, but it should remain bounded by confidentiality and no further processing.",
                    "Operational clarity matters because business owners need to know when data actually leaves the vendor environment.",
                ],
                "criteria_implications": [
                    "Verify whether the DPA states deletion timing or only references documentation.",
                    "Check whether retained backup copies remain protected and limited in use.",
                ],
                "evidence": [
                    {
                        "source_type": "uploaded_document",
                        "source_name": document["document_name"],
                        "document_id": document["document_id"],
                        "document_name": document["document_name"],
                        "document_type": document["document_type"],
                        "page_number": 2,
                        "excerpt": "Following expiration or termination of the Agreement, Atlassian must, in accordance with the Documentation, delete all Customer Personal Data.",
                        "explanation": "The DPA contains an express post-termination deletion clause.",
                    }
                ],
                "uncertainties": ["The clause references Documentation for operational detail rather than stating a concrete deletion timeline in the DPA itself."],
            }
        )

    def _review_response(self, contents) -> _FakeResponse:  # noqa: ANN001
        task_input = _task_input_from_contents(contents)
        criterion = task_input["criterion"]
        document = task_input["document_records"][0]
        title = criterion["title"]
        if self._step == 1:
            return self._function_response(
                "search_uploaded_documents",
                {"query": title, "document_ids": [document["document_id"]], "top_k": 4},
            )
        if self._step == 2:
            page = 4 if "transfer" in title.lower() else 2
            return self._function_response(
                "fetch_document_pages",
                {"document_id": document["document_id"], "start_page": page, "end_page": page},
            )
        if "transfer" in title.lower():
            return self._json_response(
                {
                    "check_id": criterion["check_id"],
                    "status": "COMPLIANT",
                    "risk": "LOW",
                    "confidence": 0.9,
                    "evidence_quotes": [
                        {
                            "page": 4,
                            "quote": "Where Personal Data protected by the EU Data Protection Law is transferred, either directly or via onward transfer, to a country outside of Europe that is not subject to an adequacy decision, the following applies:",
                        }
                    ],
                    "kb_citations": [],
                    "evidence": [
                        {
                            "source_type": "uploaded_document",
                            "source_name": document["document_name"],
                            "document_id": document["document_id"],
                            "document_name": document["document_name"],
                            "document_type": document["document_type"],
                            "page_number": 4,
                            "excerpt": "Where Personal Data protected by the EU Data Protection Law is transferred, either directly or via onward transfer, to a country outside of Europe that is not subject to an adequacy decision, the following applies:",
                            "explanation": "The DPA includes region-specific transfer mechanics and SCC language.",
                        }
                    ],
                    "missing_elements": [],
                    "vendor_questions": [],
                    "recommended_action": "No immediate action required for transfer mechanics based on the current DPA text.",
                    "risk_rationale": "The DPA contains explicit European transfer provisions and SCC incorporation language.",
                    "abstained": False,
                }
            )
        return self._json_response(
            {
                "check_id": criterion["check_id"],
                "status": "PARTIAL",
                "risk": "MEDIUM",
                "confidence": 0.78,
                "evidence_quotes": [
                    {
                        "page": 2,
                        "quote": "Following expiration or termination of the Agreement, Atlassian must, in accordance with the Documentation, delete all Customer Personal Data.",
                    }
                ],
                "kb_citations": [],
                "evidence": [
                    {
                        "source_type": "uploaded_document",
                        "source_name": document["document_name"],
                        "document_id": document["document_id"],
                        "document_name": document["document_name"],
                        "document_type": document["document_type"],
                        "page_number": 2,
                        "excerpt": "Following expiration or termination of the Agreement, Atlassian must, in accordance with the Documentation, delete all Customer Personal Data.",
                        "explanation": "The DPA states a delete obligation at termination.",
                    }
                ],
                "missing_elements": [
                    "The DPA does not state a concrete deletion timeline in the agreement text.",
                    "The DPA does not mention a destruction certificate or equivalent deletion confirmation.",
                ],
                "vendor_questions": [
                    "What is the standard deletion timeline after termination, and can Atlassian provide deletion confirmation on request?"
                ],
                "recommended_action": "Approve only if the vendor can confirm the post-termination deletion timeline and evidence mechanism.",
                "risk_rationale": "The DPA has a deletion obligation, but operational handling is deferred to documentation and leaves evidence of completion unclear.",
                "abstained": False,
            }
        )

    def _approval_pack_response(self) -> _FakeResponse:
        if self._step == 1:
            return self._function_response("get_review_findings", {})
        if self._step == 2:
            return self._function_response("get_vendor_context", {})
        if self._step == 3:
            return self._function_response("get_evidence_appendix", {})
        return self._json_response(
            {
                "executive_summary": "The DPA is broadly usable, but approval should stay conditional on clarifying how post-termination deletion is operationalized and evidenced.",
                "top_risks": [
                    "Deletion obligations depend on external documentation rather than a concrete timeline in the DPA itself."
                ],
                "weak_or_missing_clauses": [
                    "The DPA does not describe a specific deletion timeline or destruction-confirmation process."
                ],
                "vendor_follow_up_questions": [
                    "What is the standard deletion timeline after termination, and can Atlassian provide deletion confirmation on request?"
                ],
                "internal_memo": "Approve with conditions. Transfer mechanics appear adequate, but the team should obtain operational deletion detail before relying on the exit posture.",
                "confidence_notes": [
                    "Narrative is grounded in two validated criterion assessments and the stored evidence appendix."
                ],
            }
        )


def _seed_review_project(service: UploadPipelineService, session_factory) -> tuple[uuid.UUID, uuid.UUID]:
    tenant_id = service.settings.default_dev_tenant_id
    project_id = uuid.uuid4()
    document_id = uuid.uuid4()
    parse_job_id = uuid.uuid4()
    now = utcnow()
    pdf_bytes = (TEST_PDF_DIR / "atlassian_dpa_oct_2025.pdf").read_bytes()
    markdown_text = (TEST_PDF_DIR / "atlassian_dpa_mistral_output.md").read_text(encoding="utf-8")
    parsed_pages = json.loads((TEST_PDF_DIR / "atlassian_dpa_mistral_output.pages.json").read_text(encoding="utf-8"))["pages"]

    upload_artifact = service.storage.save_upload(
        tenant_id=tenant_id,
        project_id=project_id,
        document_id=document_id,
        filename="atlassian_dpa_oct_2025.pdf",
        data=pdf_bytes,
        content_type="application/pdf",
    )
    parsed_artifact = service.storage.save_parsed_markdown(
        tenant_id=tenant_id,
        project_id=project_id,
        document_id=document_id,
        text=markdown_text,
    )
    pages_artifact = service.storage.save_parsed_pages(
        tenant_id=tenant_id,
        project_id=project_id,
        document_id=document_id,
        pages=parsed_pages,
    )

    with session_factory() as session:
        service._ensure_dev_tenant(session)
        session.add(
            Project(
                id=project_id,
                tenant_id=tenant_id,
                owner_username="local-dev",
                name="Atlassian Checker Phase 3 Integration",
                status="READY_FOR_CHECKLIST",
                review_type="vendor_dpa_review",
                vendor_name="Atlassian",
                vendor_website="https://www.atlassian.com",
                tool_or_service_name="Atlassian Cloud",
                intended_use_case="Use Atlassian Cloud products for internal engineering and operations workflows.",
                data_types=["employee_data", "customer_support_data"],
                shares_personal_data=True,
                shares_customer_data=True,
                shares_employee_data=True,
                shares_sensitive_data=False,
                has_ai_features=False,
                business_criticality="high",
                vendor_region="US",
                processes_eu_personal_data=True,
                transfers_data_outside_eea=True,
                internal_owner="local-dev",
                context_completed_at=now,
                created_at=now,
                updated_at=now,
                last_activity_at=now,
            )
        )
        session.flush()
        session.add(
            Document(
                id=document_id,
                tenant_id=tenant_id,
                project_id=project_id,
                filename="atlassian_dpa_oct_2025.pdf",
                mime_type="application/pdf",
                page_count=len(parsed_pages),
                storage_uri=upload_artifact.object_uri,
                document_type="main_dpa",
                display_name="Atlassian DPA",
                is_primary=True,
                uploaded_by="local-dev",
                lifecycle_status="active",
                active=True,
                parse_status="COMPLETED",
                parser_route="mistral_ocr",
                pdf_classification="native",
                token_count_estimate=1200,
                extracted_text_uri=parsed_artifact.object_uri,
                extracted_text_format="markdown",
                uploaded_at=now,
                parse_completed_at=now,
            )
        )
        session.flush()
        session.add(
            DocumentParseJob(
                id=parse_job_id,
                tenant_id=tenant_id,
                project_id=project_id,
                document_id=document_id,
                status="COMPLETED",
                stage="READY_FOR_REFERENCE_SELECTION",
                progress_pct=100,
                message="Parsed.",
                file_type="pdf",
                pdf_classification="native",
                parser_route="mistral_ocr",
                token_count_estimate=1200,
                meta_json={"parsed_pages_uri": pages_artifact.object_uri},
                created_at=now,
                updated_at=now,
                available_at=now - timedelta(seconds=1),
                attempt_count=1,
                started_at=now,
                completed_at=now,
            )
        )
        session.add(
            DocumentChunk(
                document_id=document_id,
                chunk_text=str(parsed_pages[0]["page_text"]),
                page_start=int(parsed_pages[0]["page_no"]),
                page_end=int(parsed_pages[0]["page_no"]),
                provenance_id="page-1",
                embedding=[0.0] * 1536,
                chunk_index=1,
                metadata_json={"seeded_for_test": True},
            )
        )
        session.commit()
    return project_id, document_id


def _approved_checks(draft_checks) -> list[ChecklistItem]:  # noqa: ANN001
    checks: list[ChecklistItem] = []
    for check in draft_checks:
        payload = check.model_dump(mode="json")
        payload.pop("draft_rationale", None)
        checks.append(ChecklistItem.model_validate(payload))
    return checks


def test_phase3_checklist_and_review_flow_with_seeded_test_pdf(tmp_path: Path, monkeypatch) -> None:
    service, session_factory = _build_service(tmp_path)
    project_id, document_id = _seed_review_project(service, session_factory)

    monkeypatch.setattr("upload_api.agents.base.genai.Client", FakeGenAIClient)
    service.phase3_agents._document_retriever.search_document = lambda **_: (_ for _ in ()).throw(RuntimeError("vector disabled"))  # type: ignore[method-assign]
    service.phase3_agents._kb_retriever.search_selected_sources = lambda **_: (_ for _ in ()).throw(RuntimeError("vector disabled"))  # type: ignore[method-assign]

    sources = service.list_reference_sources()
    selected_source_ids = [next((src.source_id for src in sources if src.source_id == "gdpr_regulation_2016_679"), sources[0].source_id)]

    draft = asyncio.run(
        service.create_checklist_draft(
            document_id=document_id,
            selected_source_ids=selected_source_ids,
            user_instruction="Focus on practical approval risks rather than exhaustive legal theory.",
            actor_username="local-dev",
            trace_id="phase3-test-draft",
        )
    )
    asyncio.run(service._run_checklist_job(draft.checklist_draft_id))
    draft_snapshot = service.get_checklist_draft_snapshot(draft.checklist_draft_id, actor_username="local-dev")
    assert draft_snapshot is not None
    assert draft_snapshot.status == "COMPLETED"
    assert draft_snapshot.result is not None
    assert draft_snapshot.result.review_profile is not None
    assert draft_snapshot.result.document_inventory
    assert len(draft_snapshot.result.checks) == 8
    assert {
        check.category.value if hasattr(check.category, "value") else str(check.category)
        for check in draft_snapshot.result.checks
    } == set(draft_snapshot.result.review_profile.mandatory_categories)

    approved = service.approve_checklist(
        project_id,
        ApproveChecklistRequest(
            version=draft_snapshot.result.version,
            selected_source_ids=selected_source_ids,
            checks=_approved_checks(draft_snapshot.result.checks),
            change_note="Approved during Phase 3 integration verification.",
        ),
        actor_username="local-dev",
        trace_id="phase3-test-approval",
    )
    assert approved.checklist.review_profile is not None
    assert approved.checklist.context_snapshot is not None
    assert approved.checklist.document_inventory

    run = asyncio.run(
        service.create_analysis_run(
            CreateAnalysisRunRequest(project_id=project_id),
            actor_username="local-dev",
            trace_id="phase3-test-analysis",
        )
    )
    asyncio.run(service._run_analysis_run(run.analysis_run_id))
    run_snapshot = service.get_analysis_run_snapshot(run.analysis_run_id, actor_username="local-dev")
    assert run_snapshot is not None
    assert run_snapshot.status == "COMPLETED"
    assert run_snapshot.finding_count == 8

    report = service.get_analysis_report(run.analysis_run_id, actor_username="local-dev")
    pack = service.get_approval_pack(run.analysis_run_id, actor_username="local-dev")

    assert report.report.overall.risk_level.value == "MEDIUM"
    assert pack.recommendation == "approve_with_conditions"
    assert isinstance(pack.pack["vendor_questions"], list)
    assert pack.pack["internal_memo"]
    assert pack.pack["executive_summary"]["narrative"]

    with session_factory() as session:
        approved_row = session.execute(
            select(ApprovedChecklist).where(ApprovedChecklist.project_id == project_id).order_by(ApprovedChecklist.created_at.desc())
        ).scalars().first()
        assert approved_row is not None
        approved_document = ChecklistDocument.model_validate(approved_row.checklist_json)
        assert approved_document.review_profile is not None
        assert approved_document.document_inventory

        roles = session.execute(
            select(AgentRun.agent_role, AgentRun.parent_agent_run_id)
            .where(AgentRun.project_id == project_id)
            .order_by(AgentRun.created_at.asc())
        ).all()
        role_names = [row.agent_role for row in roles]
        assert "criteria" in role_names
        assert "criteria_research" in role_names
        assert role_names.count("review") == 8
        assert "approval_pack" in role_names
        assert any(row.agent_role == "criteria_research" and row.parent_agent_run_id is not None for row in roles)

        tool_call_count = session.execute(
            select(func.count(AgentRunToolCall.id))
            .join(AgentRun, AgentRun.id == AgentRunToolCall.agent_run_id)
            .where(AgentRun.project_id == project_id)
        ).scalar_one()
        output_count = session.execute(
            select(func.count(AgentRunOutput.id))
            .join(AgentRun, AgentRun.id == AgentRunOutput.agent_run_id)
            .where(AgentRun.project_id == project_id)
        ).scalar_one()
        stage_names = session.execute(
            select(ApprovalPackStageOutput.stage_name)
            .where(ApprovalPackStageOutput.project_id == project_id)
            .order_by(ApprovalPackStageOutput.created_at.asc())
        ).scalars().all()
        findings = session.execute(
            select(Finding)
            .join(AnalysisRun, AnalysisRun.id == Finding.run_id)
            .where(AnalysisRun.project_id == project_id)
        ).scalars().all()

        assert tool_call_count >= 8
        assert output_count >= 4
        assert set(stage_names) == {"action_pack", "assembler"}
        assert len(findings) == 8
        assert any(finding.recommendation for finding in findings)
        assert any(finding.evidence_json for finding in findings)
