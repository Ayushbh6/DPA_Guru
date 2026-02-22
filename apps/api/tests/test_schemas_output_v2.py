from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from dpa_checklist.schema import ChecklistDocument, ChecklistItem, export_checklist_json_schema
from dpa_eval.schema import EvalRecord, export_eval_json_schema
from dpa_schemas.output_v2 import OutputV2Report, export_output_v2_json_schema

REPO_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_SCHEMA_JSON = REPO_ROOT / "packages" / "schemas" / "json" / "output_v2.schema.json"
CHECKLIST_SCHEMA_JSON = REPO_ROOT / "packages" / "checklist" / "json" / "checklist.schema.json"
EVAL_SCHEMA_JSON = REPO_ROOT / "packages" / "eval" / "json" / "eval.schema.json"


def _valid_output_payload() -> dict:
    return {
        "run_id": "run_123",
        "model_version": "managed-1.0",
        "policy_version": "policy-2026-02-16",
        "overall": {"score": 82.5, "risk_level": "MEDIUM", "summary": "Mostly compliant with some review points."},
        "checks": [
            {
                "check_id": "CHECK_900",
                "category": "Instructions",
                "status": "PARTIAL",
                "risk": "HIGH",
                "confidence": 0.89,
                "abstained": False,
                "review_required": False,
                "review_state": "PENDING",
                "citation_pages": [],
                "evidence_span_offsets": [],
                "risk_rationale": "Instruction clause exists but includes broad exceptions."
            }
        ],
        "highlights": ["Instruction clause has exceptions requiring legal review."],
        "next_actions": ["Request narrowing amendment for instruction exceptions."],
        "confidence": 0.84,
        "abstained": False,
        "review_required": False,
        "review_state": "PENDING",
        "citation_pages": [4],
        "evidence_span_offsets": [{"page": 4, "start_offset": 125, "end_offset": 280}],
        "risk_rationale": "One high-risk finding requires review."
    }


def _valid_checklist_payload() -> dict:
    return {
        "version": "baseline_v1",
        "governance": {
            "owner": "Product + Engineering",
            "approval_status": "REVIEWED",
            "policy_version": "policy-2026-02-17",
            "change_note": "Neutral synthetic baseline checklist for testing."
        },
        "checks": [
            {
                "check_id": "CHECK_001",
                "title": "Processor must follow controller instructions",
                "category": "Instructions",
                "legal_basis": ["Policy Section 1.1"],
                "required": True,
                "severity": "MANDATORY",
                "evidence_hint": "Locate instruction-limitation clause.",
                "pass_criteria": ["Clause limits processing to controller instructions."],
                "fail_criteria": ["Clause is missing or allows unrelated processing."],
                "sources": [
                    {
                        "source_type": "LAW",
                        "authority": "Official legal register",
                        "source_ref": "Policy Section 1.1",
                        "source_url": "https://example.com/policy/section-1-1",
                        "source_excerpt": "Authoritative text defining processor instruction limits."
                    }
                ]
            }
        ]
    }


def test_valid_output_payload_and_high_risk_auto_flags_review_required() -> None:
    payload = _valid_output_payload()
    report = OutputV2Report.model_validate(payload)

    assert report.checks[0].review_required is True
    assert report.review_required is True


def test_missing_required_top_level_field_fails() -> None:
    payload = _valid_output_payload()
    payload.pop("run_id")

    with pytest.raises(ValidationError):
        OutputV2Report.model_validate(payload)


def test_abstained_without_reason_fails() -> None:
    payload = _valid_output_payload()
    payload["abstained"] = True
    payload["abstain_reason"] = None

    with pytest.raises(ValidationError):
        OutputV2Report.model_validate(payload)


def test_checklist_schema_rejects_invalid_item() -> None:
    with pytest.raises(ValidationError):
        ChecklistItem.model_validate(
            {
                "check_id": "bad id",
                "title": "Bad item",
                "category": "Security",
                "legal_basis": ["Policy Section 2.0"],
                "required": True,
                "severity": "CRITICAL",
                "evidence_hint": "n/a",
                "pass_criteria": [],
                "fail_criteria": ["Invalid severity and empty pass criteria."],
                "sources": [
                    {
                        "source_type": "LAW",
                        "authority": "Official legal register",
                        "source_ref": "Policy Section 2.0",
                        "source_url": "https://example.com/policy/section-2-0",
                        "source_excerpt": "Authoritative legal text."
                    }
                ]
            }
        )


def test_eval_schema_rejects_missing_threshold_or_pass_fail() -> None:
    with pytest.raises(ValidationError):
        EvalRecord.model_validate(
            {
                "dataset_id": "golden-40",
                "run_id": "run_abc",
                "metric_name": "mandatory_clause_recall",
                "metric_value": 0.95,
                "evaluated_at": datetime.now(timezone.utc).isoformat(),
                "notes": "Missing threshold and pass_fail should fail."
            }
        )


def test_checklist_data_file_validates_against_schema() -> None:
    parsed = ChecklistDocument.model_validate(_valid_checklist_payload())

    assert len(parsed.checks) == 1


def test_checklist_item_requires_sources() -> None:
    with pytest.raises(ValidationError):
        ChecklistItem.model_validate(
            {
                "check_id": "CHECK_999",
                "title": "Synthetic check",
                "category": "Security",
                "legal_basis": ["Policy Section 2.0"],
                "required": True,
                "severity": "HIGH",
                "evidence_hint": "Find security clause.",
                "pass_criteria": ["Security clause exists."],
                "fail_criteria": ["No security clause."]
            }
        )


def test_checklist_document_requires_governance() -> None:
    checklist_data = _valid_checklist_payload()
    checklist_data.pop("governance", None)

    with pytest.raises(ValidationError):
        ChecklistDocument.model_validate(checklist_data)


def test_export_json_schemas() -> None:
    export_output_v2_json_schema(OUTPUT_SCHEMA_JSON)
    export_checklist_json_schema(CHECKLIST_SCHEMA_JSON)
    export_eval_json_schema(EVAL_SCHEMA_JSON)

    assert OUTPUT_SCHEMA_JSON.exists()
    assert CHECKLIST_SCHEMA_JSON.exists()
    assert EVAL_SCHEMA_JSON.exists()
