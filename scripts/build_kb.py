#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from html import unescape
from pathlib import Path
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover
    BeautifulSoup = None

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None


SourceKind = Literal["html", "pdf"]


@dataclass(frozen=True)
class CorpusSource:
    source_id: str
    title: str
    authority: str
    kind: SourceKind
    url: str


SOURCES: list[CorpusSource] = [
    CorpusSource(
        source_id="gdpr_regulation_2016_679",
        title="GDPR (Regulation (EU) 2016/679) - EUR-Lex EN",
        authority="EUR-Lex",
        kind="html",
        url="https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32016R0679",
    ),
    CorpusSource(
        source_id="scc_transfers_2021_914",
        title="Commission Implementing Decision (EU) 2021/914 (SCCs transfers) - EUR-Lex EN",
        authority="EUR-Lex",
        kind="html",
        url="https://eur-lex.europa.eu/legal-content/EN/ALL/?uri=CELEX%3A32021D0914",
    ),
    CorpusSource(
        source_id="scc_controller_processor_2021_915",
        title="Commission Implementing Decision (EU) 2021/915 (SCCs controller-processor) - EUR-Lex EN",
        authority="EUR-Lex",
        kind="html",
        url="https://eur-lex.europa.eu/legal-content/EN/ALL/?uri=CELEX%3A32021D0915",
    ),
    CorpusSource(
        source_id="edpb_guidelines_07_2020",
        title="EDPB Guidelines 07/2020 on controller and processor concepts (final EN PDF)",
        authority="EDPB",
        kind="pdf",
        url="https://www.edpb.europa.eu/system/files/2023-10/EDPB_guidelines_202007_controllerprocessor_final_en.pdf",
    ),
    CorpusSource(
        source_id="edpb_recommendations_01_2020",
        title="EDPB Recommendations 01/2020 (v2.0, EN PDF)",
        authority="EDPB",
        kind="pdf",
        url="https://www.edpb.europa.eu/system/files/2021-06/edpb_recommendations_202001vo.2.0_supplementarymeasurestransferstools_en.pdf",
    ),
    CorpusSource(
        source_id="edpb_opinion_22_2024",
        title="EDPB Opinion 22/2024 on processor/sub-processor obligations (EN PDF)",
        authority="EDPB",
        kind="pdf",
        url="https://www.edpb.europa.eu/system/files/2024-10/edpb_opinion_202422_relianceonprocessors-sub-processors_en.pdf",
    ),
]


UA = "AI-DPA-KB-Builder/1.0 (+local-dev)"


def _fetch_bytes(url: str, timeout_seconds: int) -> tuple[bytes, str]:
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=timeout_seconds) as resp:  # noqa: S310 - fixed curated URLs
        content_type = resp.headers.get("Content-Type", "")
        return resp.read(), content_type


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    cleaned: list[str] = []
    prev_blank = False
    for line in lines:
        is_blank = not line
        if is_blank and prev_blank:
            continue
        cleaned.append(line)
        prev_blank = is_blank
    return "\n".join(cleaned).strip() + "\n"


def _extract_html_text(html_bytes: bytes, source: CorpusSource) -> str:
    html = html_bytes.decode("utf-8", errors="replace")
    if BeautifulSoup is None:
        text = re.sub(r"(?is)<(script|style).*?>.*?</\\1>", " ", html)
        text = re.sub(r"(?s)<[^>]+>", "\n", text)
        return _normalize_text(unescape(text))

    soup = BeautifulSoup(html, "html.parser")
    for node in soup(["script", "style", "noscript", "svg", "header", "footer", "nav", "aside", "form"]):
        node.decompose()

    # EUR-Lex pages are noisy; try the main legal content containers first.
    candidates = [
        "#document1",
        "#document",
        "#TexteOnly",
        "#texte",
        ".eli-container",
        ".tabContent",
        "main",
        "article",
    ]
    root = None
    for selector in candidates:
        root = soup.select_one(selector)
        if root and root.get_text(strip=True):
            break
    if root is None:
        root = soup.body or soup

    text = root.get_text("\n", strip=False)
    normalized = _normalize_text(text)
    if len(normalized) < 500 and source.authority == "EUR-Lex":
        # Fallback to full body if selector heuristics failed.
        normalized = _normalize_text((soup.body or soup).get_text("\n", strip=False))
    return normalized


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    if PdfReader is None:
        raise RuntimeError(
            "pypdf is not installed. Run: pip install -r apps/worker/requirements.txt"
        )
    reader = PdfReader(io.BytesIO(pdf_bytes))
    page_blocks: list[str] = []
    for idx, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        page_text = _normalize_text(page_text).strip()
        if not page_text:
            continue
        page_blocks.append(f"[Page {idx}]\n{page_text}")
    return "\n\n".join(page_blocks).strip() + "\n"


def _write_source_files(
    out_dir: Path,
    source: CorpusSource,
    fetched_at: str,
    parsed_text: str,
    original_url: str,
) -> dict:
    source_dir = out_dir / source.source_id
    source_dir.mkdir(parents=True, exist_ok=True)

    txt_path = source_dir / "content.txt"
    md_path = source_dir / "content.md"
    meta_path = source_dir / "metadata.json"

    txt_path.write_text(parsed_text, encoding="utf-8")
    md_body = (
        f"# {source.title}\n\n"
        f"- source_id: `{source.source_id}`\n"
        f"- authority: `{source.authority}`\n"
        f"- kind: `{source.kind}`\n"
        f"- source_url: {original_url}\n"
        f"- fetched_at_utc: `{fetched_at}`\n\n"
        f"---\n\n"
        f"{parsed_text}"
    )
    md_path.write_text(md_body, encoding="utf-8")

    metadata = {
        "source_id": source.source_id,
        "title": source.title,
        "authority": source.authority,
        "kind": source.kind,
        "url": original_url,
        "fetched_at_utc": fetched_at,
        "char_count": len(parsed_text),
        "line_count": parsed_text.count("\n"),
        "txt_path": str(txt_path),
        "md_path": str(md_path),
    }
    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def _build_kb(sources: list[CorpusSource], out_dir: Path, timeout_seconds: int) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_entries: list[dict] = []
    failures: list[dict] = []

    for source in sources:
        print(f"[kb] Fetching {source.source_id} ({source.kind})")
        try:
            payload, _content_type = _fetch_bytes(source.url, timeout_seconds=timeout_seconds)
            fetched_at = datetime.now(UTC).isoformat()
            if source.kind == "html":
                parsed_text = _extract_html_text(payload, source)
            else:
                parsed_text = _extract_pdf_text(payload)
            metadata = _write_source_files(
                out_dir=out_dir,
                source=source,
                fetched_at=fetched_at,
                parsed_text=parsed_text,
                original_url=source.url,
            )
            manifest_entries.append(metadata)
            print(f"[kb] OK {source.source_id} ({metadata['char_count']} chars)")
        except (HTTPError, URLError, TimeoutError, RuntimeError, Exception) as exc:  # broad on purpose for batch run
            failures.append({"source_id": source.source_id, "url": source.url, "error": str(exc)})
            print(f"[kb] FAIL {source.source_id}: {exc}", file=sys.stderr)

    manifest = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "source_count_requested": len(sources),
        "source_count_succeeded": len(manifest_entries),
        "source_count_failed": len(failures),
        "sources": manifest_entries,
        "failures": failures,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    readme = (
        "# KB Corpus\n\n"
        "This folder contains parsed text files for the selected legal corpus.\n\n"
        "- `manifest.json`: fetch/parse summary\n"
        "- `<source_id>/content.txt`: clean text for chunking/embedding\n"
        "- `<source_id>/content.md`: same text with metadata header\n"
        "- `<source_id>/metadata.json`: per-source metadata\n"
    )
    (out_dir / "README.md").write_text(readme, encoding="utf-8")

    print(json.dumps({"output_dir": str(out_dir), "succeeded": len(manifest_entries), "failed": len(failures)}, indent=2))
    return 0 if not failures else 1


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build local legal KB corpus in ./kb from curated official sources.")
    parser.add_argument("--output-dir", default="kb", help="Output folder (default: kb)")
    parser.add_argument("--source-id", action="append", help="Only fetch specific source_id (repeatable)")
    parser.add_argument("--timeout-seconds", type=int, default=60, help="HTTP timeout (default: 60)")
    parser.add_argument("--list-sources", action="store_true", help="Print curated source list and exit")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    selected = SOURCES
    if args.source_id:
        wanted = set(args.source_id)
        selected = [s for s in SOURCES if s.source_id in wanted]
        missing = sorted(wanted - {s.source_id for s in selected})
        if missing:
            print(json.dumps({"unknown_source_ids": missing}, indent=2), file=sys.stderr)
            return 2

    if args.list_sources:
        print(json.dumps([asdict(s) for s in selected], indent=2))
        return 0

    return _build_kb(selected, out_dir=Path(args.output_dir), timeout_seconds=args.timeout_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
