from __future__ import annotations

import json
from pathlib import Path

from pydantic import Field, model_validator

from dpa_schemas.common import EvidenceSpan, FindingStatus, ReviewState, RiskLevel, StrictModel


class OverallSummary(StrictModel):
    score: float = Field(ge=0.0, le=100.0)
    risk_level: RiskLevel
    summary: str = Field(min_length=1)


class CheckResult(StrictModel):
    check_id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    status: FindingStatus
    risk: RiskLevel
    confidence: float = Field(ge=0.0, le=1.0)
    abstained: bool = False
    abstain_reason: str | None = None
    review_required: bool = False
    review_state: ReviewState = ReviewState.PENDING
    citation_pages: list[int] = Field(default_factory=list)
    evidence_span_offsets: list[EvidenceSpan] = Field(default_factory=list)
    risk_rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def apply_contract_rules(self) -> "CheckResult":
        if self.abstained and not self.abstain_reason:
            raise ValueError("abstain_reason is required when abstained is true")

        has_citation = bool(self.citation_pages) or bool(self.evidence_span_offsets)
        if self.risk == RiskLevel.HIGH and not has_citation:
            self.review_required = True

        return self


class OutputV2Report(StrictModel):
    run_id: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    overall: OverallSummary
    checks: list[CheckResult] = Field(min_length=1)
    highlights: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    abstained: bool = False
    abstain_reason: str | None = None
    review_required: bool = False
    review_state: ReviewState = ReviewState.PENDING
    citation_pages: list[int] = Field(default_factory=list)
    evidence_span_offsets: list[EvidenceSpan] = Field(default_factory=list)
    risk_rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def aggregate_review_requirements(self) -> "OutputV2Report":
        if self.abstained and not self.abstain_reason:
            raise ValueError("abstain_reason is required when abstained is true")

        if any(check.review_required for check in self.checks):
            self.review_required = True

        return self


def export_output_v2_json_schema(path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(OutputV2Report.model_json_schema(), indent=2), encoding="utf-8")
