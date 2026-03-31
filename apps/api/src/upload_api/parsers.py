from __future__ import annotations

import asyncio
import base64
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Awaitable, Callable

try:
    from mistralai.client import Mistral
except Exception:  # pragma: no cover
    Mistral = None

try:
    import tiktoken
except Exception:  # pragma: no cover - optional dependency at runtime
    tiktoken = None

try:
    import fitz  # PyMuPDF
except Exception:  # pragma: no cover
    fitz = None

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None


ProgressCallback = Callable[[str], Awaitable[None]]


@dataclass(frozen=True)
class PdfInspection:
    page_count: int
    sampled_pages: int
    text_chars_per_page: list[int]
    image_only_like_pages: int
    median_text_chars: int
    classification: str


@dataclass(frozen=True)
class ParseOutput:
    text: str
    text_format: str
    page_count: int
    parser_route: str
    pages: list[dict]
    meta: dict


@dataclass(frozen=True)
class ParsedPageImage:
    image_id: str
    image_base64: str | None
    top_left_x: int | None
    top_left_y: int | None
    bottom_right_x: int | None
    bottom_right_y: int | None


@dataclass(frozen=True)
class ParsedPage:
    page_no: int
    page_text: str
    page_images: list[ParsedPageImage]


def _render_pages_markdown(pages: list[ParsedPage], *, include_images: bool) -> str:
    blocks: list[str] = []
    for page in pages:
        blocks.append(f"page_no: {page.page_no}")
        blocks.append("page_text:")
        blocks.append(page.page_text.strip() or "")
        # Image persistence is intentionally disabled by default to control storage costs.
        # Keep the page_images rendering code path available behind a flag so it can be
        # re-enabled later without reworking the OCR parser integration.
        if include_images and page.page_images:
            blocks.append("page_images:")
            for image in page.page_images:
                blocks.append(f"- image_id: {image.image_id}")
                blocks.append(f"  image_base64: {image.image_base64 or ''}")
        else:
            blocks.append("page_images: []")
        blocks.append("")
    return "\n".join(blocks).strip() + "\n"


def _page_dicts(pages: list[ParsedPage]) -> list[dict]:
    return [asdict(page) for page in pages]


def classify_pdf_from_metrics(text_chars_per_page: list[int]) -> str:
    if not text_chars_per_page:
        return "scanned"
    meaningful_pages = sum(1 for chars in text_chars_per_page if chars >= 50)
    sampled_pages = len(text_chars_per_page)
    ratio = meaningful_pages / sampled_pages
    median_text_chars = int(statistics.median(text_chars_per_page))
    if ratio >= 0.7 and median_text_chars >= 120:
        return "native"
    if ratio <= 0.2:
        return "scanned"
    return "mixed"


def inspect_pdf(path: Path) -> PdfInspection:
    if fitz is not None:
        doc = fitz.open(path)
        try:
            sample_count = min(len(doc), 15)
            text_chars_per_page: list[int] = []
            image_only_like_pages = 0
            for idx in range(sample_count):
                page = doc[idx]
                text_chars = len((page.get_text("text") or "").strip())
                text_chars_per_page.append(text_chars)
                has_images = len(page.get_images(full=True)) > 0
                if has_images and text_chars < 50:
                    image_only_like_pages += 1
            median_text = int(statistics.median(text_chars_per_page)) if text_chars_per_page else 0
            return PdfInspection(
                page_count=len(doc),
                sampled_pages=sample_count,
                text_chars_per_page=text_chars_per_page,
                image_only_like_pages=image_only_like_pages,
                median_text_chars=median_text,
                classification=classify_pdf_from_metrics(text_chars_per_page),
            )
        finally:
            doc.close()
    if PdfReader is None:
        raise RuntimeError("PyMuPDF (`pymupdf`) is required for PDF inspection.")

    reader = PdfReader(str(path))
    sample_count = min(len(reader.pages), 15)
    chars: list[int] = []
    for idx in range(sample_count):
        text = (reader.pages[idx].extract_text() or "").strip()
        chars.append(len(text))
    median_text = int(statistics.median(chars)) if chars else 0
    return PdfInspection(
        page_count=len(reader.pages),
        sampled_pages=sample_count,
        text_chars_per_page=chars,
        image_only_like_pages=0,
        median_text_chars=median_text,
        classification=classify_pdf_from_metrics(chars),
    )

def estimate_token_count(text: str, encoding_name: str) -> int:
    if not text.strip():
        return 0
    if tiktoken is not None:
        try:
            enc = tiktoken.get_encoding(encoding_name)
            return len(enc.encode(text))
        except Exception:
            # Fall back when tiktoken assets are unavailable offline.
            return max(1, len(text.split()))
    return max(1, len(text.split()))


def _document_data_url(file_path: Path, mime_type: str) -> str:
    payload = base64.b64encode(file_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{payload}"


def _extract_mistral_pages(payload: dict) -> list[ParsedPage]:
    pages = payload.get("pages")
    if not isinstance(pages, list):
        return []

    parsed_pages: list[ParsedPage] = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        markdown = page.get("markdown")
        images_raw = page.get("images")
        page_images: list[ParsedPageImage] = []
        if isinstance(images_raw, list):
            for image in images_raw:
                if not isinstance(image, dict):
                    continue
                page_images.append(
                    ParsedPageImage(
                        image_id=str(image.get("id") or ""),
                        image_base64=image.get("image_base64") if isinstance(image.get("image_base64"), str) else None,
                        top_left_x=image.get("top_left_x") if isinstance(image.get("top_left_x"), int) else None,
                        top_left_y=image.get("top_left_y") if isinstance(image.get("top_left_y"), int) else None,
                        bottom_right_x=image.get("bottom_right_x") if isinstance(image.get("bottom_right_x"), int) else None,
                        bottom_right_y=image.get("bottom_right_y") if isinstance(image.get("bottom_right_y"), int) else None,
                    )
                )
        parsed_pages.append(
            ParsedPage(
                page_no=(int(page.get("index")) + 1) if isinstance(page.get("index"), int) else (len(parsed_pages) + 1),
                page_text=markdown.strip() if isinstance(markdown, str) else "",
                page_images=page_images,
            )
        )
    return parsed_pages


async def parse_with_mistral_ocr(
    *,
    file_path: Path,
    mime_type: str,
    api_key: str,
    model: str,
    include_image_base64: bool,
    progress_cb: ProgressCallback | None = None,
) -> ParseOutput:
    if Mistral is None:
        raise RuntimeError("mistralai is required for Mistral OCR integration.")
    if progress_cb:
        await progress_cb("Extracting text from document")

    def _run() -> ParseOutput:
        with Mistral(api_key=api_key) as mistral:
            response = mistral.ocr.process(
                model=model,
                document={
                    "type": "document_url",
                    "document_url": _document_data_url(file_path, mime_type),
                },
                table_format="markdown",
                include_image_base64=include_image_base64,
                extract_header=False,
                extract_footer=False,
            )
        payload = response.model_dump(mode="json") if hasattr(response, "model_dump") else response
        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected Mistral OCR response format.")
        pages = _extract_mistral_pages(payload)
        if not pages:
            raise RuntimeError("Mistral OCR returned no page output.")
        if not include_image_base64:
            pages = [
                ParsedPage(
                    page_no=page.page_no,
                    page_text=page.page_text,
                    page_images=[],
                )
                for page in pages
            ]
        usage_info = payload.get("usage_info") if isinstance(payload.get("usage_info"), dict) else {}
        return ParseOutput(
            text=_render_pages_markdown(pages, include_images=include_image_base64),
            text_format="markdown",
            page_count=len(pages),
            parser_route="mistral_ocr",
            pages=_page_dicts(pages),
            meta={
                "mistral_model": payload.get("model") or model,
                "mistral_usage_info": usage_info,
                "page_count": len(pages),
                "includes_image_base64": include_image_base64,
                "table_format": "markdown",
            },
        )

    return await asyncio.to_thread(_run)
