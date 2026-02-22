from __future__ import annotations

from dpa_registry.diffing import classify_change
from dpa_registry.models import ChangeClass


def test_classify_change_detects_no_change_after_normalization() -> None:
    previous = "Article 28 Processor obligations apply.\nClause 1."
    current = "Article 28 Processor obligations apply. Clause 1."

    result = classify_change(previous, current, tracked_sections=["Article 28 Processor obligations apply."])

    assert result.change_class == ChangeClass.NO_CHANGE
    assert result.token_change_ratio == 0.0


def test_classify_change_detects_material_change() -> None:
    previous = "Article 28 Processor must follow instructions."
    current = "Article 28 Processor may process data for independent purposes."

    result = classify_change(previous, current, tracked_sections=["Article 28 Processor may process data"])

    assert result.change_class == ChangeClass.MATERIAL_CHANGE
    assert result.token_change_ratio >= 0.02


def test_classify_change_detects_minor_change_without_tracked_sections() -> None:
    previous = "Article 28 Processor follows instructions."
    current = "Article 28 Processor follows controller instructions."

    result = classify_change(previous, current, tracked_sections=[])

    assert result.change_class == ChangeClass.MINOR_TEXT_CHANGE
