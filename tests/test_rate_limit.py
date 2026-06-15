"""Tests for the token-bucket rate limiter and retry policy in auth.with_retry.

Tests never actually sleep — a fake `sleeper` records requested delays so we
can assert backoff shape without slowing the suite.
"""

from __future__ import annotations

import httplib2
import pytest
from googleapiclient.errors import HttpError

from gsuite.auth import TokenBucket, with_retry


def _http_error(status: int, headers: dict[str, str] | None = None) -> HttpError:
    resp = httplib2.Response({"status": str(status), **(headers or {})})
    return HttpError(resp, b"{}")


class FakeSleeper:
    def __init__(self):
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


# --- token bucket ------------------------------------------------------------

def test_bucket_allows_burst_without_sleep():
    sleeper = FakeSleeper()
    bucket = TokenBucket(rate_per_sec=5.0, burst=3)
    for _ in range(3):
        bucket.acquire(sleeper=sleeper)
    assert sleeper.calls == []  # all three served from initial burst


def test_bucket_sleeps_once_burst_exhausted():
    sleeper = FakeSleeper()
    bucket = TokenBucket(rate_per_sec=5.0, burst=2)
    bucket.acquire(sleeper=sleeper)
    bucket.acquire(sleeper=sleeper)
    bucket.acquire(sleeper=sleeper)  # burst empty → must wait
    assert len(sleeper.calls) == 1
    # At 5 req/sec the next token arrives in ~0.2s. Allow a bit of slack.
    assert 0 < sleeper.calls[0] <= 0.25


# --- retry policy ------------------------------------------------------------

def test_success_on_first_try_no_retry():
    sleeper = FakeSleeper()
    bucket = TokenBucket(rate_per_sec=1000.0, burst=10)
    calls = []

    def fn():
        calls.append(1)
        return "ok"

    assert with_retry(fn, bucket=bucket, sleeper=sleeper) == "ok"
    assert len(calls) == 1


def test_retries_429_with_exponential_backoff():
    sleeper = FakeSleeper()
    bucket = TokenBucket(rate_per_sec=1000.0, burst=10)
    attempts = {"n": 0}

    def fn():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise _http_error(429)
        return "ok"

    assert with_retry(fn, bucket=bucket, sleeper=sleeper, max_retries=5) == "ok"
    assert attempts["n"] == 3
    # One sleep per retry (two retries between three attempts). Burst covered
    # the bucket.acquire calls so only backoff sleeps were recorded.
    assert sleeper.calls == [1.0, 2.0]


def test_retries_respect_retry_after_header():
    sleeper = FakeSleeper()
    bucket = TokenBucket(rate_per_sec=1000.0, burst=10)
    attempts = {"n": 0}

    def fn():
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise _http_error(429, {"retry-after": "7"})
        return "ok"

    with_retry(fn, bucket=bucket, sleeper=sleeper)
    assert sleeper.calls == [7.0]


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_retries_transient_5xx(status):
    sleeper = FakeSleeper()
    bucket = TokenBucket(rate_per_sec=1000.0, burst=10)
    attempts = {"n": 0}

    def fn():
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise _http_error(status)
        return "ok"

    assert with_retry(fn, bucket=bucket, sleeper=sleeper) == "ok"
    assert attempts["n"] == 2


def test_gives_up_after_max_retries():
    sleeper = FakeSleeper()
    bucket = TokenBucket(rate_per_sec=1000.0, burst=10)
    attempts = {"n": 0}

    def fn():
        attempts["n"] += 1
        raise _http_error(429)

    with pytest.raises(HttpError):
        with_retry(fn, bucket=bucket, sleeper=sleeper, max_retries=2)
    # Initial attempt + 2 retries = 3 calls total.
    assert attempts["n"] == 3


def test_non_retryable_status_propagates_immediately():
    sleeper = FakeSleeper()
    bucket = TokenBucket(rate_per_sec=1000.0, burst=10)
    attempts = {"n": 0}

    def fn():
        attempts["n"] += 1
        raise _http_error(400)

    with pytest.raises(HttpError):
        with_retry(fn, bucket=bucket, sleeper=sleeper)
    assert attempts["n"] == 1  # no retries on 400


def test_non_http_exception_propagates():
    sleeper = FakeSleeper()
    bucket = TokenBucket(rate_per_sec=1000.0, burst=10)

    def fn():
        raise ValueError("boom")

    with pytest.raises(ValueError):
        with_retry(fn, bucket=bucket, sleeper=sleeper)
