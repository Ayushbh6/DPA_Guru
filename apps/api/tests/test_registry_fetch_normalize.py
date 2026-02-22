from __future__ import annotations

from dpa_registry.fetchers import FetchOptions, fetch_url
from dpa_registry.normalize import normalize_html_to_text, sha256_hex


class _MockResponse:
    def __init__(self, content: bytes) -> None:
        self.status_code = 200
        self.headers = {"Content-Type": "text/html; charset=utf-8", "ETag": "etag-123", "Last-Modified": "yesterday"}
        self.content = content

    def raise_for_status(self) -> None:
        return None


def test_fetch_and_normalize_with_mocked_http(monkeypatch) -> None:
    html = b"""
    <html>
      <body>
        <h1>Article 28 Processor obligations</h1>
        <p>Processor must act on documented instructions.</p>
      </body>
    </html>
    """

    def mock_get(url: str, timeout: int, headers: dict) -> _MockResponse:  # noqa: ARG001
        return _MockResponse(html)

    monkeypatch.setattr("dpa_registry.fetchers.requests.get", mock_get)

    fetched = fetch_url("https://example.com/legal", language="EN", options=FetchOptions(timeout_seconds=5))
    normalized = normalize_html_to_text(fetched.body_bytes, url=fetched.url)

    assert fetched.status_code == 200
    assert fetched.http_etag == "etag-123"
    assert "Article 28" in normalized.normalized_text
    assert normalized.tracked_sections
    assert len(sha256_hex(fetched.body_bytes)) == 64
