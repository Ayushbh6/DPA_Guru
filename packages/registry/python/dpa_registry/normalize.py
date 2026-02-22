from __future__ import annotations

import hashlib
import re

from dpa_registry.models import NormalizedDocument

try:
    from bs4 import BeautifulSoup
except ModuleNotFoundError:  # pragma: no cover - dependency fallback
    BeautifulSoup = None

TRACKED_SECTION_PATTERNS = (
    re.compile(r"\barticle\s+\d+[a-z]?\b", re.IGNORECASE),
    re.compile(r"\bmodule\s+\d+\b", re.IGNORECASE),
    re.compile(r"\bclause\s+\d+(\.\d+)*\b", re.IGNORECASE),
)


def sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def normalize_html_to_text(content: bytes, url: str) -> NormalizedDocument:
    if BeautifulSoup is not None:
        soup = BeautifulSoup(content, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
    else:
        decoded = content.decode("utf-8", errors="ignore")
        text = re.sub(r"<[^>]+>", " ", decoded)

    normalized = _normalize_text(text)
    tracked_sections = _extract_tracked_sections(normalized)

    return NormalizedDocument(
        normalized_text=normalized,
        tracked_sections=tracked_sections,
        metadata={"url": url, "length": len(normalized)},
    )


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def _extract_tracked_sections(text: str) -> list[str]:
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    tracked: list[str] = []
    for line in lines:
        if any(pattern.search(line) for pattern in TRACKED_SECTION_PATTERNS):
            tracked.append(line[:300])
    return tracked[:200]
