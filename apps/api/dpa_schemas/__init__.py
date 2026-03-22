from __future__ import annotations

from pathlib import Path
from pkgutil import extend_path


__path__ = extend_path(__path__, __name__)

SRC_PACKAGE = Path(__file__).resolve().parents[3] / "packages" / "schemas" / "python" / "dpa_schemas"
src_path = str(SRC_PACKAGE)
if src_path not in __path__:
    __path__.append(src_path)

from .common import EvidenceSpan, FindingStatus, OverallSummary, ReviewState, RiskLevel, StrictModel  # noqa: E402,F401
from .output_v2 import CheckResult, OutputV2Report  # noqa: E402,F401
from .review_v1 import CheckAssessmentOutput, EvidenceQuote, KbCitation, ReviewSynthesisOutput  # noqa: E402,F401

__all__ = [
    "CheckAssessmentOutput",
    "CheckResult",
    "EvidenceQuote",
    "EvidenceSpan",
    "FindingStatus",
    "KbCitation",
    "OutputV2Report",
    "OverallSummary",
    "ReviewState",
    "ReviewSynthesisOutput",
    "RiskLevel",
    "StrictModel",
]
