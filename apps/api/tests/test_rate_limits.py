from __future__ import annotations

from upload_api.rate_limits import InMemoryRateLimiter


def test_rate_limiter_blocks_after_limit_until_window_expires(monkeypatch) -> None:
    limiter = InMemoryRateLimiter()
    timeline = iter([0.0, 1.0, 2.0, 12.5])
    monkeypatch.setattr("upload_api.rate_limits.monotonic", lambda: next(timeline))

    first = limiter.check(bucket="login", subject="127.0.0.1", limit=2, window_seconds=10)
    second = limiter.check(bucket="login", subject="127.0.0.1", limit=2, window_seconds=10)
    blocked = limiter.check(bucket="login", subject="127.0.0.1", limit=2, window_seconds=10)
    after_window = limiter.check(bucket="login", subject="127.0.0.1", limit=2, window_seconds=10)

    assert first.allowed is True
    assert second.allowed is True
    assert blocked.allowed is False
    assert blocked.retry_after_seconds >= 1
    assert after_window.allowed is True
