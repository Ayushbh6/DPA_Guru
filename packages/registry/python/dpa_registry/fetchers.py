from __future__ import annotations

from dataclasses import dataclass

import requests

from dpa_registry.constants import DEFAULT_HTTP_TIMEOUT_SECONDS
from dpa_registry.models import FetchedDocument


@dataclass(frozen=True)
class FetchOptions:
    timeout_seconds: int = DEFAULT_HTTP_TIMEOUT_SECONDS
    user_agent: str = "DPA-Registry-Bot/1.0 (+compliance-source-sync)"


def fetch_url(url: str, language: str, options: FetchOptions | None = None) -> FetchedDocument:
    opts = options or FetchOptions()
    response = requests.get(
        url,
        timeout=opts.timeout_seconds,
        headers={"User-Agent": opts.user_agent},
    )
    response.raise_for_status()

    return FetchedDocument(
        url=url,
        language=language,
        status_code=response.status_code,
        content_type=response.headers.get("Content-Type"),
        body_bytes=response.content,
        http_etag=response.headers.get("ETag"),
        http_last_modified=response.headers.get("Last-Modified"),
    )
