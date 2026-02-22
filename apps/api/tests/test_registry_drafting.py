from __future__ import annotations

import json

import pytest

from dpa_registry.drafting import DraftContext, DraftGenerationError, generate_candidate_checklist


def _valid_checklist_json() -> str:
    payload = {
        "version": "official_v1",
        "governance": {
            "owner": "Policy Team",
            "approval_status": "REVIEWED",
            "approved_by": None,
            "approved_at": None,
            "policy_version": "policy-2026-02-17",
            "change_note": "Generated from material source diffs."
        },
        "checks": [
            {
                "check_id": "CHECK_001",
                "title": "Instruction limitation",
                "category": "Instructions",
                "legal_basis": ["Policy Section 1"],
                "required": True,
                "severity": "MANDATORY",
                "evidence_hint": "Locate controller instruction clause.",
                "pass_criteria": ["Processor is limited to documented instructions."],
                "fail_criteria": ["Processor can repurpose data."],
                "sources": [
                    {
                        "source_type": "LAW",
                        "authority": "EUR-Lex",
                        "source_ref": "CELEX:32016R0679 Article 28",
                        "source_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32016R0679",
                        "source_excerpt": "Processor shall process data only on documented instructions."
                    }
                ]
            }
        ]
    }
    return json.dumps(payload)


def test_generate_candidate_with_retry_then_success() -> None:
    calls = {"count": 0}

    def transport(_prompt: str) -> str:
        calls["count"] += 1
        if calls["count"] == 1:
            return "{not_json"
        return _valid_checklist_json()

    checklist = generate_candidate_checklist(
        DraftContext(
            policy_version="policy-2026-02-17",
            changed_sections=["Article 28 paragraph changed"],
            prior_checklist_json={"version": "old"},
        ),
        transport=transport,
        retries=2,
    )

    assert checklist.version == "official_v1"
    assert calls["count"] == 2


def test_generate_candidate_fails_closed_after_retries() -> None:
    def transport(_prompt: str) -> str:
        return '{"invalid":"payload"}'

    with pytest.raises(DraftGenerationError):
        generate_candidate_checklist(
            DraftContext(
                policy_version="policy-2026-02-17",
                changed_sections=["Article 28 paragraph changed"],
                prior_checklist_json=None,
            ),
            transport=transport,
            retries=1,
        )
