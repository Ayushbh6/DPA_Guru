from __future__ import annotations

from pydantic import Field, model_validator

from dpa_schemas.common import FindingStatus, OverallSummary, RiskLevel, StrictModel


class KbCitation(StrictModel):
    source_id: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    source_excerpt: str = Field(min_length=1, max_length=500)


class EvidenceQuote(StrictModel):
    page: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=400)


class CheckAssessmentOutput(StrictModel):
    check_id: str = Field(min_length=1)
    status: FindingStatus
    risk: RiskLevel
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_quotes: list[EvidenceQuote] = Field(default_factory=list)
    kb_citations: list[KbCitation] = Field(default_factory=list)
    missing_elements: list[str] = Field(default_factory=list)
    risk_rationale: str = Field(min_length=1)
    abstained: bool = False
    abstain_reason: str | None = None

    @model_validator(mode="after")
    def validate_abstain_reason(self) -> "CheckAssessmentOutput":
        if self.abstained and not self.abstain_reason:
            raise ValueError("abstain_reason is required when abstained is true")
        return self


class ReviewSynthesisOutput(StrictModel):
    overall: OverallSummary
    highlights: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    abstained: bool = False
    abstain_reason: str | None = None
    risk_rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_abstain_reason(self) -> "ReviewSynthesisOutput":
        if self.abstained and not self.abstain_reason:
            raise ValueError("abstain_reason is required when abstained is true")
        return self
