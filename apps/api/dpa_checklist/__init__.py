from __future__ import annotations

from pathlib import Path
from pkgutil import extend_path


__path__ = extend_path(__path__, __name__)

SRC_PACKAGE = Path(__file__).resolve().parents[3] / "packages" / "checklist" / "python" / "dpa_checklist"
src_path = str(SRC_PACKAGE)
if src_path not in __path__:
    __path__.append(src_path)

from .schema import (  # noqa: E402,F401
    ApprovalStatus,
    ChecklistDocument,
    ChecklistDraftItem,
    ChecklistDraftMeta,
    ChecklistDraftOutput,
    ChecklistGovernance,
    ChecklistItem,
    ChecklistSource,
)

__all__ = [
    "ApprovalStatus",
    "ChecklistDocument",
    "ChecklistDraftItem",
    "ChecklistDraftMeta",
    "ChecklistDraftOutput",
    "ChecklistGovernance",
    "ChecklistItem",
    "ChecklistSource",
]
