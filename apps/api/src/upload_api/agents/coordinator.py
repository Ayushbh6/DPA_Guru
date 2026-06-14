from __future__ import annotations

import json
import uuid
from typing import Any, Iterable

from sqlalchemy.orm import Session, sessionmaker

from dpa_checklist import (
    CHECKLIST_CATEGORY_COVERAGE,
    ChecklistCategory,
    ChecklistDraftItem,
    ChecklistDraftOutput,
    CriteriaValidationWarning,
    ReviewProfile,
)
from dpa_schemas import CheckAssessmentOutput, EvidenceItem, EvidenceQuote, KbCitation, OverallSummary, ReviewSynthesisOutput, RiskLevel
from upload_api.config import Settings
from upload_api.document_retrieval import DocumentVectorRetriever, DpaPageRecord
from upload_api.kb_retrieval import KbVectorRetriever

from .base import AgentLoopRunner
from .execution import CriteriaResearchExecutor, build_criteria_research_executor
from .helpers import DocumentCorpus, DocumentRecord, load_kb_sources
from .registry import approval_pack_prompt_spec, copilot_prompt_spec, criteria_prompt_spec, criteria_research_prompt_spec, review_prompt_spec
from .schemas import (
    AgentRunScope,
    ApprovalPackAgentInput,
    ApprovalPackAgentOutput,
    CopilotAgentOutput,
    CriteriaAgentModelOutput,
    CriteriaGenerationContext,
    CriteriaResearchPayload,
    StartCriteriaResearchInput,
)
from .tools import ApprovalPackToolset, CopilotToolset, CriteriaAgentToolset, ReviewAgentToolset


def build_standard_review_profile() -> ReviewProfile:
    return ReviewProfile(
        profile_id="standard_vendor_dpa_v1",
        version="v1",
        name="Standard Vendor DPA Review",
        required_document_types=["main_dpa"],
        optional_document_types=[
            "privacy_policy",
            "security_toms",
            "subprocessors",
            "data_transfer_terms",
            "ai_terms",
            "service_terms",
            "security_certification",
            "custom_agreement",
            "other",
        ],
        mandatory_categories=[category.value for category in ChecklistCategory],
        contextual_categories=[
            "has_ai_features",
            "shares_sensitive_data",
            "shares_employee_data",
            "shares_customer_data",
            "transfers_data_outside_eea",
            "business_criticality_high",
        ],
    )


class Phase3AgentCoordinator:
    def __init__(self, *, settings: Settings, session_factory: sessionmaker[Session]) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._document_retriever = DocumentVectorRetriever(settings)
        self._kb_retriever = KbVectorRetriever(settings)
        self._research_executor: CriteriaResearchExecutor = build_criteria_research_executor(settings)

    def cancel_parent_research(self, *, parent_agent_run_id: str) -> None:
        self._research_executor.cancel_parent(parent_agent_run_id=parent_agent_run_id)

    def finish_parent_research(self, *, parent_agent_run_id: str) -> None:
        self._research_executor.finish_parent(parent_agent_run_id=parent_agent_run_id)

    def generate_criteria(
        self,
        *,
        scope: AgentRunScope,
        context: CriteriaGenerationContext,
        document_records: list[DocumentRecord],
        pages_by_document: dict[str, list[DpaPageRecord]],
        user_instruction: str | None,
        cancel_check=None,
        parent_run_started_cb=None,
    ) -> tuple[str, ChecklistDraftOutput]:
        if not self._settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is required for criteria generation.")

        corpus = DocumentCorpus(
            document_retriever=self._document_retriever,
            document_records=document_records,
            pages_by_document=pages_by_document,
        )
        kb_sources = load_kb_sources(self._settings, context.selected_kb_source_ids)
        parent_run_id: dict[str, str | None] = {"value": None}

        def _parent_run_id() -> str | None:
            return parent_run_id["value"]

        def _record_parent_run_id(run_id: str) -> None:
            parent_run_id["value"] = run_id
            if parent_run_started_cb is not None:
                parent_run_started_cb(run_id)

        def _launch_child(research_id: str, payload: StartCriteriaResearchInput):
            current_parent = _parent_run_id()
            if current_parent is None:
                raise RuntimeError("Parent run id not available for delegated research.")
            return self._run_criteria_research_child(
                research_id=research_id,
                parent_agent_run_id=current_parent,
                scope=scope,
                context=context,
                document_records=document_records,
                pages_by_document=pages_by_document,
                payload=payload,
                cancel_check=cancel_check,
            )

        toolset = CriteriaAgentToolset(
            context=context,
            corpus=corpus,
            kb_sources=kb_sources,
            kb_retriever=self._kb_retriever,
            research_executor=self._research_executor,
            research_launcher=_launch_child,
            parent_run_id_getter=_parent_run_id,
            max_children=self._settings.agent_criteria_max_children,
            default_wait_seconds=self._settings.agent_collect_wait_seconds,
        )

        task_input = {
            "criteria_context": context.model_dump(mode="json"),
            "user_instruction": user_instruction,
            "document_records": corpus.list_records(),
        }
        user_message = (
            "Generate a vendor-review criteria draft.\n"
            f"Task input JSON:\n{json.dumps(task_input, indent=2)}"
        )
        spec = criteria_prompt_spec(self._settings)
        runner = AgentLoopRunner(
            api_key=self._settings.gemini_api_key,
            session_factory=self._session_factory,
            scope=scope,
            prompt_path=spec.prompt_path,
            loop_config=spec.loop_config,
            response_model=CriteriaAgentModelOutput,
            tools=toolset.as_tools(),
            task_input=task_input,
            user_message=user_message,
            cancel_check=cancel_check,
            run_started_cb=_record_parent_run_id,
        )
        result = runner.run()
        checks_with_fallbacks, fallback_warnings = self._ensure_mandatory_category_coverage(
            context,
            list(result.output.checks),
        )
        normalized_checks = self._normalize_check_ids(checks_with_fallbacks)
        final_output = ChecklistDraftOutput(
            version=result.output.version,
            meta=result.output.meta,
            review_profile=context.review_profile,
            context_snapshot=context.vendor_context,
            document_inventory=context.documents,
            validation_warnings=self._merge_validation_warnings(
                list(result.output.validation_warnings),
                fallback_warnings,
                self._deterministic_criteria_warnings(context, normalized_checks),
            ),
            checks=normalized_checks,
        )
        return result.agent_run_id, final_output

    def _run_criteria_research_child(
        self,
        *,
        research_id: str,
        parent_agent_run_id: str,
        scope: AgentRunScope,
        context: CriteriaGenerationContext,
        document_records: list[DocumentRecord],
        pages_by_document: dict[str, list[DpaPageRecord]],
        payload: StartCriteriaResearchInput,
        cancel_check=None,
    ) -> tuple[str, CriteriaResearchPayload]:
        if not self._settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is required for delegated criteria research.")

        corpus = DocumentCorpus(
            document_retriever=self._document_retriever,
            document_records=document_records,
            pages_by_document=pages_by_document,
        )
        kb_source_ids = payload.kb_source_ids or context.selected_kb_source_ids
        kb_sources = load_kb_sources(self._settings, kb_source_ids)
        toolset = CriteriaAgentToolset(
            context=context,
            corpus=corpus,
            kb_sources=kb_sources,
            kb_retriever=self._kb_retriever,
            research_executor=self._research_executor,
            research_launcher=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("Child research cannot delegate further.")),
            parent_run_id_getter=lambda: parent_agent_run_id,
            max_children=0,
            default_wait_seconds=self._settings.agent_collect_wait_seconds,
            allow_delegation=False,
        )
        task_input = {
            "research_id": research_id,
            "query": payload.query,
            "scope_hint": payload.scope,
            "document_type_hints": payload.document_types,
            "kb_source_hints": kb_source_ids,
            "criteria_context": context.model_dump(mode="json"),
            "document_records": corpus.list_records(),
        }
        user_message = (
            "Complete one delegated criteria-research task.\n"
            f"Task input JSON:\n{json.dumps(task_input, indent=2)}"
        )
        spec = criteria_research_prompt_spec(self._settings)
        child_scope = AgentRunScope(
            tenant_id=scope.tenant_id,
            project_id=scope.project_id,
            analysis_run_id=scope.analysis_run_id,
            approval_pack_id=scope.approval_pack_id,
            parent_agent_run_id=uuid.UUID(parent_agent_run_id),
        )
        runner = AgentLoopRunner(
            api_key=self._settings.gemini_api_key,
            session_factory=self._session_factory,
            scope=child_scope,
            prompt_path=spec.prompt_path,
            loop_config=spec.loop_config,
            response_model=CriteriaResearchPayload,
            tools=toolset.as_tools(),
            task_input=task_input,
            user_message=user_message,
            cancel_check=lambda: (
                (cancel_check is not None and cancel_check())
                or self._research_executor.is_parent_cancelled(parent_agent_run_id=parent_agent_run_id)
            ),
        )
        result = runner.run()
        return result.agent_run_id, result.output

    def assess_criterion(
        self,
        *,
        scope: AgentRunScope,
        vendor_context: dict[str, Any],
        criterion,
        document_records: list[DocumentRecord],
        pages_by_document: dict[str, list[DpaPageRecord]],
        selected_kb_source_ids: list[str],
        cancel_check=None,
    ) -> tuple[str, CheckAssessmentOutput]:
        if not self._settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is required for review generation.")

        corpus = DocumentCorpus(
            document_retriever=self._document_retriever,
            document_records=document_records,
            pages_by_document=pages_by_document,
        )
        kb_sources = load_kb_sources(self._settings, selected_kb_source_ids)
        task_input = {
            "vendor_context": vendor_context,
            "criterion": criterion.model_dump(mode="json"),
            "document_records": corpus.list_records(),
            "selected_kb_source_ids": selected_kb_source_ids,
        }
        user_message = (
            "Assess one approved vendor-review criterion.\n"
            f"Task input JSON:\n{json.dumps(task_input, indent=2)}"
        )
        spec = review_prompt_spec(self._settings)
        runner = AgentLoopRunner(
            api_key=self._settings.gemini_api_key,
            session_factory=self._session_factory,
            scope=scope,
            prompt_path=spec.prompt_path,
            loop_config=spec.loop_config,
            response_model=CheckAssessmentOutput,
            tools=ReviewAgentToolset(corpus=corpus, kb_sources=kb_sources, kb_retriever=self._kb_retriever).as_tools(),
            task_input=task_input,
            user_message=user_message,
            cancel_check=cancel_check,
        )
        result = runner.run()
        return result.agent_run_id, self._normalize_assessment(result.output)

    def draft_approval_pack(
        self,
        *,
        scope: AgentRunScope,
        payload: ApprovalPackAgentInput,
        cancel_check=None,
    ) -> tuple[str, ApprovalPackAgentOutput]:
        if not self._settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is required for approval-pack drafting.")

        task_input = payload.model_dump(mode="json")
        user_message = (
            "Draft the business-facing approval-pack language from validated review findings.\n"
            f"Task input JSON:\n{json.dumps(task_input, indent=2)}"
        )
        spec = approval_pack_prompt_spec(self._settings)
        runner = AgentLoopRunner(
            api_key=self._settings.gemini_api_key,
            session_factory=self._session_factory,
            scope=scope,
            prompt_path=spec.prompt_path,
            loop_config=spec.loop_config,
            response_model=ApprovalPackAgentOutput,
            tools=ApprovalPackToolset(
                vendor_context=payload.vendor_context,
                findings=payload.findings,
                evidence=payload.evidence,
            ).as_tools(),
            task_input=task_input,
            user_message=user_message,
            cancel_check=cancel_check,
        )
        result = runner.run()
        return result.agent_run_id, result.output

    def run_copilot(
        self,
        *,
        scope: AgentRunScope,
        vendor_context: dict[str, Any],
        approval_pack: dict[str, Any],
        findings: list[dict[str, Any]],
        stage_outputs: list[dict[str, Any]],
        prior_revisions: list[dict[str, Any]],
        document_records: list[DocumentRecord],
        pages_by_document: dict[str, list[DpaPageRecord]],
        selected_kb_source_ids: list[str],
        user_message: str,
        history_messages: list[dict[str, str]],
        cancel_check=None,
    ) -> tuple[str, CopilotAgentOutput]:
        if not self._settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is required for review copilot.")

        corpus = DocumentCorpus(
            document_retriever=self._document_retriever,
            document_records=document_records,
            pages_by_document=pages_by_document,
        )
        kb_sources = load_kb_sources(self._settings, selected_kb_source_ids)
        task_input = {
            "vendor_context": vendor_context,
            "approval_pack_id": str(scope.approval_pack_id) if scope.approval_pack_id else None,
            "copilot_thread_id": str(scope.copilot_thread_id) if scope.copilot_thread_id else None,
            "document_records": corpus.list_records(),
            "selected_kb_source_ids": selected_kb_source_ids,
        }
        prompt_message = (
            "Answer the user's Vendor Review copilot request.\n"
            f"Current user message:\n{user_message}\n\n"
            f"Task input JSON:\n{json.dumps(task_input, indent=2)}"
        )
        spec = copilot_prompt_spec(self._settings)
        runner = AgentLoopRunner(
            api_key=self._settings.gemini_api_key,
            session_factory=self._session_factory,
            scope=scope,
            prompt_path=spec.prompt_path,
            loop_config=spec.loop_config,
            response_model=CopilotAgentOutput,
            tools=CopilotToolset(
                vendor_context=vendor_context,
                approval_pack=approval_pack,
                findings=findings,
                stage_outputs=stage_outputs,
                prior_revisions=prior_revisions,
                corpus=corpus,
                kb_sources=kb_sources,
                kb_retriever=self._kb_retriever,
            ).as_tools(),
            task_input=task_input | {"user_message": user_message},
            user_message=prompt_message,
            history_messages=history_messages,
            cancel_check=cancel_check,
        )
        result = runner.run()
        return result.agent_run_id, result.output

    def deterministic_review_synthesis(self, assessments: list[CheckAssessmentOutput], check_map: dict[str, Any]) -> ReviewSynthesisOutput:
        total = max(len(assessments), 1)
        high_count = sum(1 for item in assessments if item.risk == RiskLevel.HIGH or item.status.value == "NON_COMPLIANT")
        medium_count = sum(1 for item in assessments if item.risk == RiskLevel.MEDIUM or item.status.value == "PARTIAL")
        unknown_count = sum(1 for item in assessments if item.status.value == "UNKNOWN" or item.abstained)
        score = max(0.0, 100.0 - (high_count * 25.0) - (medium_count * 12.0) - (unknown_count * 15.0))
        if high_count or unknown_count > 1:
            risk_level = RiskLevel.HIGH
        elif medium_count or unknown_count:
            risk_level = RiskLevel.MEDIUM
        else:
            risk_level = RiskLevel.LOW
        highlights = self._top_highlights(assessments, check_map)
        next_actions = self._next_actions(assessments)
        confidence = sum(item.confidence for item in assessments) / total
        abstained = any(item.abstained for item in assessments)
        abstain_reasons = [item.abstain_reason for item in assessments if item.abstained and item.abstain_reason]
        summary = (
            f"{high_count} high-risk, {medium_count} medium-risk or partial, and {unknown_count} unresolved criterion result(s) "
            f"were identified across {len(assessments)} approved criteria."
        )
        risk_rationale = (
            "Deterministic synthesis derived from criterion-level evidence-backed assessments, preserving non-compliant, "
            "partial, and unresolved items as drivers of overall risk."
        )
        return ReviewSynthesisOutput(
            overall=OverallSummary(score=score, risk_level=risk_level, summary=summary),
            highlights=highlights,
            next_actions=next_actions,
            confidence=confidence,
            abstained=abstained,
            abstain_reason="; ".join(abstain_reasons[:3]) if abstained else None,
            risk_rationale=risk_rationale,
        )

    def _normalize_check_ids(self, checks: Iterable) -> list:
        normalized = []
        for index, check in enumerate(checks, start=1):
            payload = check.model_dump(mode="python")
            payload["check_id"] = f"CHECK_{index:03d}"
            normalized.append(check.__class__.model_validate(payload))
        return normalized

    def _merge_validation_warnings(self, *warning_groups: list[CriteriaValidationWarning]) -> list[CriteriaValidationWarning]:
        merged: list[CriteriaValidationWarning] = []
        seen: set[tuple[str, str]] = set()
        for warnings in warning_groups:
            for warning in warnings:
                key = (warning.code, warning.message)
                if key in seen:
                    continue
                seen.add(key)
                merged.append(warning)
        return merged

    def _ensure_mandatory_category_coverage(
        self,
        context: CriteriaGenerationContext,
        checks: list,
    ) -> tuple[list, list[CriteriaValidationWarning]]:
        categories_present = {self._category_value(check.category) for check in checks}
        additions: list[ChecklistDraftItem] = []
        warnings: list[CriteriaValidationWarning] = []
        for category in context.review_profile.mandatory_categories:
            if category in categories_present:
                continue
            additions.append(self._fallback_mandatory_criterion(category))
            warnings.append(
                CriteriaValidationWarning(
                    code="mandatory_category_auto_added",
                    message=f"Mandatory review category was deterministically added because the Criteria Agent omitted it: {category}",
                    severity="warning",
                )
            )
        return [*checks, *additions], warnings

    def _fallback_mandatory_criterion(self, category: str) -> ChecklistDraftItem:
        category_enum = ChecklistCategory(category)
        coverage = CHECKLIST_CATEGORY_COVERAGE.get(category_enum, "baseline DPA obligations")
        likely_document_types = self._likely_documents_for_category(category_enum)
        return ChecklistDraftItem.model_validate(
            {
                "check_id": f"AUTO_{category_enum.name}",
                "title": f"{category_enum.value} must be reviewable in the vendor materials",
                "category": category_enum.value,
                "legal_basis": ["GDPR Article 28", "GDPR Article 32"],
                "required": True,
                "severity": "MANDATORY",
                "evidence_hint": f"Inspect the DPA and supporting materials for clauses covering {coverage}.",
                "pass_criteria": [
                    f"The vendor materials provide reviewable obligations covering {coverage}.",
                    "The obligations are concrete enough for Checker to assess compliance and residual business risk.",
                ],
                "fail_criteria": [
                    f"The uploaded materials omit or only vaguely address {coverage}.",
                    "The reviewer cannot determine the vendor's obligation, process, timing, or assistance level from the available evidence.",
                ],
                "sources": [
                    {
                        "source_type": "LAW",
                        "authority": "European Union",
                        "source_ref": "GDPR Articles 28 and 32",
                        "source_url": "https://eur-lex.europa.eu/eli/reg/2016/679/oj",
                        "source_excerpt": "Processor agreements must contain mandatory processing terms and appropriate security obligations.",
                        "interpretation_notes": "Deterministically added to preserve complete baseline category coverage before final review.",
                    }
                ],
                "draft_rationale": "The fixed review profile requires every mandatory category to be represented before the checklist can be approved.",
                "rationale": "A missing baseline category would leave the final approval pack with an unreviewed legal or operational area.",
                "applicability": "Applies to every standard Vendor DPA review unless the approved review profile is changed.",
                "priority": "high",
                "expected_evidence": [
                    {
                        "document_types": likely_document_types,
                        "description": f"Clauses or supporting documentation that address {coverage}.",
                    }
                ],
                "likely_document_types": likely_document_types,
                "vendor_context_factors": self._context_factors_for_category(category_enum),
                "profile_references": ["standard_vendor_dpa_v1"],
            }
        )

    def _category_value(self, category: Any) -> str:
        return category.value if hasattr(category, "value") else str(category)

    def _likely_documents_for_category(self, category: ChecklistCategory) -> list[str]:
        if category == ChecklistCategory.SECURITY_AND_CONFIDENTIALITY:
            return ["main_dpa", "security_toms", "security_certification"]
        if category == ChecklistCategory.SUBPROCESSORS_AND_PERSONNEL:
            return ["main_dpa", "subprocessors"]
        if category == ChecklistCategory.INTERNATIONAL_TRANSFERS_AND_LOCALIZATION:
            return ["main_dpa", "data_transfer_terms"]
        if category == ChecklistCategory.AUDIT_COMPLIANCE_AND_LIABILITY:
            return ["main_dpa", "security_certification", "custom_agreement"]
        return ["main_dpa"]

    def _context_factors_for_category(self, category: ChecklistCategory) -> list[str]:
        if category == ChecklistCategory.INTERNATIONAL_TRANSFERS_AND_LOCALIZATION:
            return ["processes_eu_personal_data", "transfers_data_outside_eea", "vendor_region"]
        if category == ChecklistCategory.SECURITY_AND_CONFIDENTIALITY:
            return ["shares_sensitive_data", "business_criticality"]
        if category == ChecklistCategory.SUBPROCESSORS_AND_PERSONNEL:
            return ["shares_personal_data"]
        if category == ChecklistCategory.DATA_SUBJECT_RIGHTS_AND_ASSISTANCE:
            return ["processes_eu_personal_data", "shares_personal_data"]
        return ["shares_personal_data"]

    def _deterministic_criteria_warnings(self, context: CriteriaGenerationContext, checks: list) -> list[CriteriaValidationWarning]:
        warnings: list[CriteriaValidationWarning] = []
        categories_present = {self._category_value(check.category) for check in checks}
        for category in context.review_profile.mandatory_categories:
            if category not in categories_present:
                warnings.append(
                    CriteriaValidationWarning(
                        code="missing_mandatory_category",
                        message=f"Mandatory review category is missing from the criteria draft: {category}",
                        severity="warning",
                    )
                )
        seen_titles: set[str] = set()
        for check in checks:
            title_key = check.title.strip().lower()
            if title_key in seen_titles:
                warnings.append(
                    CriteriaValidationWarning(
                        code="duplicate_title",
                        message=f"Potential duplicate criterion title detected: {check.title}",
                        severity="warning",
                    )
                )
            seen_titles.add(title_key)
            if not check.expected_evidence:
                warnings.append(
                    CriteriaValidationWarning(
                        code="missing_expected_evidence",
                        message=f"Criterion is missing expected evidence guidance: {check.title}",
                        severity="warning",
                        document_types=list(check.likely_document_types or []),
                    )
                )
        return warnings

    def _normalize_assessment(self, assessment: CheckAssessmentOutput) -> CheckAssessmentOutput:
        payload = assessment.model_dump(mode="python")
        evidence_items = list(payload.get("evidence") or [])
        if not payload.get("evidence_quotes"):
            payload["evidence_quotes"] = [
                {"page": item["page_number"], "quote": item["excerpt"][:400]}
                for item in evidence_items
                if item.get("source_type") == "uploaded_document" and isinstance(item.get("page_number"), int)
            ]
        if not payload.get("kb_citations"):
            payload["kb_citations"] = [
                {
                    "source_id": item.get("source_id") or item["source_name"],
                    "source_ref": item.get("section_title") or item["source_name"],
                    "source_excerpt": item["excerpt"][:500],
                }
                for item in evidence_items
                if item.get("source_type") == "kb_source"
            ]
        if not evidence_items:
            derived_evidence: list[dict[str, Any]] = []
            for quote in payload.get("evidence_quotes", []):
                derived_evidence.append(
                    EvidenceItem(
                        source_type="uploaded_document",
                        source_name="uploaded_document",
                        page_number=quote["page"],
                        excerpt=quote["quote"],
                        explanation="Direct agreement evidence.",
                    ).model_dump(mode="python")
                )
            for citation in payload.get("kb_citations", []):
                derived_evidence.append(
                    EvidenceItem(
                        source_type="kb_source",
                        source_name=citation["source_ref"],
                        source_id=citation["source_id"],
                        excerpt=citation["source_excerpt"],
                        explanation="Supporting KB citation.",
                    ).model_dump(mode="python")
                )
            payload["evidence"] = derived_evidence
        return CheckAssessmentOutput.model_validate(payload)

    def _top_highlights(self, assessments: list[CheckAssessmentOutput], check_map: dict[str, Any]) -> list[str]:
        ranked = sorted(
            assessments,
            key=lambda item: (
                0 if item.risk == RiskLevel.HIGH else 1 if item.risk == RiskLevel.MEDIUM else 2,
                0 if item.status.value == "NON_COMPLIANT" else 1 if item.status.value == "UNKNOWN" else 2,
                item.check_id,
            ),
        )
        highlights: list[str] = []
        for item in ranked[:5]:
            title = getattr(check_map.get(item.check_id), "title", item.check_id)
            highlights.append(f"{title}: {item.risk_rationale}")
        return highlights

    def _next_actions(self, assessments: list[CheckAssessmentOutput]) -> list[str]:
        actions: list[str] = []
        for item in assessments:
            if item.recommended_action:
                actions.append(item.recommended_action)
            for question in item.vendor_questions:
                actions.append(question)
            for missing in item.missing_elements:
                actions.append(f"Provide evidence or clarification for: {missing}")
        deduped: list[str] = []
        for action in actions:
            if action not in deduped:
                deduped.append(action)
        return deduped[:8]
