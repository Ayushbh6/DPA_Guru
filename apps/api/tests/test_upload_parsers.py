from __future__ import annotations

from upload_api.parsers import classify_pdf_from_metrics, estimate_token_count


def test_pdf_classifier_marks_native_text_rich_pdf() -> None:
    classification = classify_pdf_from_metrics([600, 450, 390, 720, 510, 290])
    assert classification == "native"


def test_pdf_classifier_marks_scanned_when_text_is_sparse() -> None:
    classification = classify_pdf_from_metrics([0, 3, 12, 0, 8, 4, 0])
    assert classification == "scanned"


def test_pdf_classifier_marks_mixed_when_signal_is_ambiguous() -> None:
    classification = classify_pdf_from_metrics([0, 280, 0, 160, 0, 140])
    assert classification == "mixed"


def test_token_estimation_returns_non_zero_for_content() -> None:
    count = estimate_token_count("This is a small clause with obligations and audit rights.", "cl100k_base")
    assert count > 0
