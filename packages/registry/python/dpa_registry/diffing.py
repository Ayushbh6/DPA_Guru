from __future__ import annotations

import re
from difflib import SequenceMatcher

from dpa_registry.models import ChangeClass, DiffResult


def classify_change(previous_text: str | None, current_text: str, tracked_sections: list[str]) -> DiffResult:
    if previous_text is None:
        return DiffResult(
            change_class=ChangeClass.MATERIAL_CHANGE,
            summary="First snapshot available. Baseline established.",
            changed_sections=tracked_sections[:20],
            token_change_ratio=1.0,
        )

    previous_tokens = _tokenize(previous_text)
    current_tokens = _tokenize(current_text)

    if previous_tokens == current_tokens:
        return DiffResult(
            change_class=ChangeClass.NO_CHANGE,
            summary="No normalized text change detected.",
            changed_sections=[],
            token_change_ratio=0.0,
        )

    ratio = 1.0 - SequenceMatcher(a=previous_tokens, b=current_tokens).ratio()
    changed_sections = tracked_sections[:20]

    if ratio < 0.01:
        change_class = ChangeClass.MINOR_TEXT_CHANGE
        summary = "Only minor textual or formatting-level change detected."
    elif ratio >= 0.02 and changed_sections:
        change_class = ChangeClass.MATERIAL_CHANGE
        summary = "Material legal text change detected in tracked sections."
    else:
        change_class = ChangeClass.MINOR_TEXT_CHANGE
        summary = "Text changed, but not enough signal for material legal impact."

    return DiffResult(
        change_class=change_class,
        summary=summary,
        changed_sections=changed_sections,
        token_change_ratio=max(0.0, min(1.0, ratio)),
    )


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())
