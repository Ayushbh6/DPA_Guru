from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from upload_api import parsers
from upload_api.parsers import classify_pdf_from_metrics, estimate_token_count, parse_with_mistral_ocr


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


def test_parse_with_mistral_ocr_omits_image_storage_when_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "model": "mistral-ocr-latest",
        "usage_info": {"doc_size_bytes": 1234},
        "pages": [
            {
                "index": 0,
                "markdown": "# Page 1\n\nClause text.",
                "images": [
                    {
                        "id": "img-1",
                        "image_base64": "data:image/png;base64,AAAA",
                        "top_left_x": 0,
                        "top_left_y": 0,
                        "bottom_right_x": 10,
                        "bottom_right_y": 10,
                    }
                ],
            }
        ],
    }
    calls: dict[str, object] = {}

    class _FakeResponse:
        def model_dump(self, mode: str = "json"):  # noqa: ARG002
            return payload

    class _FakeOCR:
        def process(self, **kwargs):
            calls.update(kwargs)
            return _FakeResponse()

    class _FakeMistral:
        def __init__(self, api_key: str) -> None:  # noqa: ARG002
            self.ocr = _FakeOCR()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):  # noqa: ANN001
            return False

    monkeypatch.setattr(parsers, "Mistral", _FakeMistral)
    sample = tmp_path / "sample.pdf"
    sample.write_bytes(b"%PDF-1.4\n")

    result = asyncio.run(
        parse_with_mistral_ocr(
            file_path=sample,
            mime_type="application/pdf",
            api_key="test-key",
            model="mistral-ocr-latest",
            include_image_base64=False,
        )
    )

    assert calls["include_image_base64"] is False
    assert result.meta["includes_image_base64"] is False
    assert "image_base64" not in result.text
    assert result.pages[0]["page_images"] == []
