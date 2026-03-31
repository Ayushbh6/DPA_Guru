from __future__ import annotations

from types import SimpleNamespace

import pytest

from dpa_checklist import ChecklistCategory, ChecklistDraftItem, ChecklistDraftMeta, ChecklistDraftOutput, ChecklistSource

from upload_api.checklist_synthesis import (
    CategoryGroupChecklistSynthesizer,
    ChecklistSynthesisCanceledError,
    ResolvedCheck,
    SemanticGroupChecklistSynthesizer,
    build_category_groups,
    build_semantic_candidate_edges,
    build_semantic_groups,
    build_synthesis_candidates,
    collapse_exact_duplicate_candidates,
    dedupe_resolved_checks,
    normalize_draft_output,
)


def _source(ref: str, excerpt: str) -> ChecklistSource:
    return ChecklistSource(
        source_type="LAW",
        authority="EDPB",
        source_ref=ref,
        source_url="https://example.com/source",
        source_excerpt=excerpt,
    )


def _draft_item(
    title: str,
    *,
    draft_id: str = "CHECK_001",
    category: str = ChecklistCategory.SECURITY_AND_CONFIDENTIALITY.value,
    rationale: str,
    legal_basis: list[str],
    pass_criteria: list[str],
    fail_criteria: list[str],
    severity: str = "HIGH",
) -> ChecklistDraftItem:
    return ChecklistDraftItem(
        check_id=draft_id,
        title=title,
        category=category,
        legal_basis=legal_basis,
        required=True,
        severity=severity,
        evidence_hint="Look for the security clause in the DPA.",
        pass_criteria=pass_criteria,
        fail_criteria=fail_criteria,
        sources=[_source("Art 28", "Processor must implement appropriate security controls and regular review steps.")],
        draft_rationale=rationale,
    )


def _draft(*checks: ChecklistDraftItem, confidence: float = 0.91) -> ChecklistDraftOutput:
    return ChecklistDraftOutput(
        version="v1",
        meta=ChecklistDraftMeta(
            selected_source_ids=["gdpr_regulation_2016_679"],
            confidence=confidence,
            open_questions=["Is security testing frequency defined?"],
            generation_summary="Drafted from GDPR obligations.",
        ),
        checks=list(checks),
    )


def _settings(**overrides):
    values = {
        "openai_api_key": "test-key",
        "openai_embedding_model": "text-embedding-3-small",
        "gemini_api_key": "test-key",
        "gemini_checklist_model": "gemini-3-flash-preview",
        "checklist_synthesis_group_similarity_threshold": 0.90,
        "checklist_synthesis_group_merge_threshold": 0.92,
        "checklist_synthesis_group_max_neighbors": 2,
        "checklist_synthesis_group_max_size": 5,
        "checklist_synthesis_group_max_parallel": 2,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_normalize_draft_output_caps_verbose_fields() -> None:
    verbose = _draft_item(
        "Security Measures and Ongoing Testing",
        rationale="Line 1\nLine 2\nLine 3\nLine 4 that should be removed",
        legal_basis=["GDPR Art. 32", "GDPR Art. 32"],
        pass_criteria=["Maintain encryption at rest and in transit.  ", "Maintain encryption at rest and in transit."],
        fail_criteria=["No stated testing cadence.", "No stated testing cadence."],
    )

    normalized = normalize_draft_output(_draft(verbose))

    assert normalized.checks[0].draft_rationale.count("\n") <= 2
    assert normalized.checks[0].legal_basis == ["GDPR Art. 32"]
    assert normalized.checks[0].pass_criteria == ["Maintain encryption at rest and in transit."]
    assert normalized.checks[0].fail_criteria == ["No stated testing cadence."]


def test_collapse_exact_duplicate_candidates_only_removes_true_duplicates() -> None:
    duplicate_a = _draft_item(
        "Security Measures",
        rationale="Draft A",
        legal_basis=["GDPR Art. 32"],
        pass_criteria=["Encrypt data"],
        fail_criteria=["No encryption"],
    )
    duplicate_b = _draft_item(
        "Security Measures",
        rationale="Draft B",
        legal_basis=["GDPR Art. 32"],
        pass_criteria=["Encrypt data"],
        fail_criteria=["No encryption"],
    )
    distinct = _draft_item(
        "Security Measures",
        rationale="Draft C",
        legal_basis=["GDPR Art. 32"],
        pass_criteria=["Encrypt data"],
        fail_criteria=["No testing cadence"],
    )

    candidates = build_synthesis_candidates([
        _draft(duplicate_a),
        _draft(duplicate_b),
        _draft(distinct),
    ])

    deduped, removed_count, _groups = collapse_exact_duplicate_candidates(candidates)

    assert removed_count == 1
    assert len(deduped) == 2
    assert len(deduped[0].represented_candidate_ids) == 2
    assert len(deduped[0].item.sources) == 1


def test_build_semantic_groups_are_cross_draft_only_and_bounded() -> None:
    candidates = build_synthesis_candidates(
        [
            _draft(_draft_item("Security Measures", rationale="A", legal_basis=["GDPR Art. 32"], pass_criteria=["Encrypt"], fail_criteria=["No encryption"])),
            _draft(_draft_item("Security Measures", rationale="B", legal_basis=["GDPR Art. 32"], pass_criteria=["Encrypt"], fail_criteria=["No encryption"])),
            _draft(_draft_item("Security Testing", rationale="C", legal_basis=["GDPR Art. 32"], pass_criteria=["Test annually"], fail_criteria=["No tests"])),
        ]
    )
    # Force candidate 0 and 1 to remain ungrouped because they share the same draft after exact dedupe collapse is skipped here.
    same_draft_candidates = [
        candidates[0],
        candidates[0],
        candidates[2],
    ]
    embeddings = [
        [1.0, 0.0],
        [1.0, 0.0],
        [0.99, 0.01],
    ]

    edges = build_semantic_candidate_edges(
        same_draft_candidates,
        embeddings,
        similarity_threshold=0.90,
        max_neighbors=2,
    )
    groups = build_semantic_groups(
        same_draft_candidates,
        edges,
        merge_threshold=0.92,
        max_group_size=5,
    )

    assert edges == [(0, 2, edges[0][2]), (1, 2, edges[1][2])]
    assert sorted(sorted(group) for group in groups) == [[0, 2], [1]]


def test_dedupe_resolved_checks_unions_sources_but_keeps_distinct_checks() -> None:
    source_a = _source("Art 28", "First excerpt")
    source_b = _source("Art 32", "Second excerpt")
    duplicate_left = normalize_draft_output(
        _draft(
            ChecklistDraftItem(
                check_id="CHECK_001",
                title="Audit Rights",
                category=ChecklistCategory.AUDIT_COMPLIANCE_AND_LIABILITY.value,
                legal_basis=["GDPR Art. 28(3)(h)"],
                required=True,
                severity="HIGH",
                evidence_hint="Look for audit clauses.",
                pass_criteria=["Allow controller audits"],
                fail_criteria=["No audit right"],
                sources=[source_a],
                draft_rationale="Left",
            )
        )
    ).checks[0]
    duplicate_right = normalize_draft_output(
        _draft(
            ChecklistDraftItem(
                check_id="CHECK_002",
                title="Audit Rights",
                category=ChecklistCategory.AUDIT_COMPLIANCE_AND_LIABILITY.value,
                legal_basis=["GDPR Art. 28(3)(h)"],
                required=True,
                severity="HIGH",
                evidence_hint="Look for audit clauses.",
                pass_criteria=["Allow controller audits"],
                fail_criteria=["No audit right"],
                sources=[source_b],
                draft_rationale="Right",
            )
        )
    ).checks[0]
    distinct = normalize_draft_output(
        _draft(
            ChecklistDraftItem(
                check_id="CHECK_003",
                title="Deletion Rights",
                category=ChecklistCategory.RETENTION_DELETION_AND_EXIT.value,
                legal_basis=["GDPR Art. 28(3)(g)"],
                required=True,
                severity="HIGH",
                evidence_hint="Look for deletion clauses.",
                pass_criteria=["Delete on termination"],
                fail_criteria=["No deletion right"],
                sources=[source_a],
                draft_rationale="Distinct",
            )
        )
    ).checks[0]

    deduped, removed_count = dedupe_resolved_checks(
        [
            ResolvedCheck(candidate_ids=("A",), confidence=0.9, item=duplicate_left),
            ResolvedCheck(candidate_ids=("B",), confidence=0.8, item=duplicate_right),
            ResolvedCheck(candidate_ids=("C",), confidence=0.7, item=distinct),
        ]
    )

    assert removed_count == 1
    assert len(deduped) == 2
    audit_check = next(check for check in deduped if check.item.title == "Audit Rights")
    assert len(audit_check.item.sources) == 2


def test_synthesizer_uses_originating_draft_confidence_for_singletons() -> None:
    settings = _settings()
    synthesizer = SemanticGroupChecklistSynthesizer(settings)
    drafts = [
        _draft(_draft_item("Security Measures", rationale="A", legal_basis=["GDPR Art. 32"], pass_criteria=["Encrypt"], fail_criteria=["No encryption"]), confidence=0.77),
    ]

    def fake_embed(_texts):
        return [[1.0, 0.0]]

    synthesizer._embed_texts = fake_embed  # type: ignore[method-assign]

    result = synthesizer.synthesize(drafts=drafts)

    assert result.meta.confidence == 0.77


def test_synthesizer_stops_after_current_batch_on_cancel() -> None:
    settings = _settings(checklist_synthesis_group_max_parallel=2)
    synthesizer = SemanticGroupChecklistSynthesizer(settings)
    drafts = [
        _draft(_draft_item("Check A1", rationale="A1", legal_basis=["Art 1"], pass_criteria=["A1"], fail_criteria=["A1 fail"])),
        _draft(_draft_item("Check A2", rationale="A2", legal_basis=["Art 2"], pass_criteria=["A2"], fail_criteria=["A2 fail"])),
        _draft(_draft_item("Check B1", rationale="B1", legal_basis=["Art 3"], pass_criteria=["B1"], fail_criteria=["B1 fail"])),
        _draft(_draft_item("Check B2", rationale="B2", legal_basis=["Art 4"], pass_criteria=["B2"], fail_criteria=["B2 fail"])),
        _draft(_draft_item("Check C1", rationale="C1", legal_basis=["Art 5"], pass_criteria=["C1"], fail_criteria=["C1 fail"])),
        _draft(_draft_item("Check C2", rationale="C2", legal_basis=["Art 6"], pass_criteria=["C2"], fail_criteria=["C2 fail"])),
    ]
    candidates = build_synthesis_candidates(drafts)
    call_groups: list[tuple[str, ...]] = []
    cancel_checks = {"count": 0}

    def fake_embed(_texts):
        return [
            [1.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [0.0, 0.0, 1.0],
        ]

    def fake_resolve(group, candidate_rows, **_kwargs):
        group_ids = tuple(candidate_rows[index].candidate_id for index in group)
        call_groups.append(group_ids)
        return [
            ResolvedCheck(
                candidate_ids=group_ids,
                confidence=0.8,
                item=candidate_rows[group[0]].item,
            )
        ]

    def cancel_check():
        cancel_checks["count"] += 1
        return len(call_groups) >= 2 and cancel_checks["count"] > 3

    synthesizer._embed_texts = fake_embed  # type: ignore[method-assign]
    synthesizer._resolve_group_with_retry = fake_resolve  # type: ignore[method-assign]

    with pytest.raises(ChecklistSynthesisCanceledError):
        synthesizer.synthesize(drafts=drafts, cancel_check=cancel_check)

    assert len(call_groups) == 2
    assert all(len(group) >= 1 for group in call_groups)


def test_build_category_groups_keeps_checks_in_category_buckets() -> None:
    candidates = build_synthesis_candidates(
        [
            _draft(_draft_item("Instruction Check", category=ChecklistCategory.SCOPE_ROLES_AND_INSTRUCTIONS.value, rationale="A", legal_basis=["Art 28"], pass_criteria=["A"], fail_criteria=["A fail"])),
            _draft(_draft_item("Security Check", category=ChecklistCategory.SECURITY_AND_CONFIDENTIALITY.value, rationale="B", legal_basis=["Art 32"], pass_criteria=["B"], fail_criteria=["B fail"])),
            _draft(_draft_item("Second Security Check", category=ChecklistCategory.SECURITY_AND_CONFIDENTIALITY.value, rationale="C", legal_basis=["Art 32"], pass_criteria=["C"], fail_criteria=["C fail"])),
        ]
    )

    groups = build_category_groups(candidates)

    assert groups == [
        (ChecklistCategory.SCOPE_ROLES_AND_INSTRUCTIONS.value, [0]),
        (ChecklistCategory.SECURITY_AND_CONFIDENTIALITY.value, [1, 2]),
    ]


def test_category_synthesizer_uses_originating_draft_confidence_for_singletons() -> None:
    settings = _settings()
    synthesizer = CategoryGroupChecklistSynthesizer(settings)
    drafts = [
        _draft(_draft_item("Security Measures", rationale="A", legal_basis=["GDPR Art. 32"], pass_criteria=["Encrypt"], fail_criteria=["No encryption"]), confidence=0.77),
    ]

    result = synthesizer.synthesize(drafts=drafts)

    assert result.meta.confidence == 0.77
