"""Being turned away is not the same as the page being broken.

The crawl ran flat out at four requests in flight until it finished. ACC Tek
answers 429 under that load, so sixty of its pages came back refused, were
stored as HTTP 429, and surfaced as sixty findings reading "HTTP 429 on page
with demand" — sixty faults attributed to the client's site, for a site that
answers perfectly well when asked more slowly.

Nine clients had a single page in their latest crawl for the same reason:
one page got through, the rest were refused, and the one-page result replaced
a five-hundred-page snapshot.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.ingestion.crawler.fetch import (
    MAX_RATE_LIMIT_RETRIES,
    RATE_LIMIT_BASE_DELAY,
    THROTTLED_MIN_DELAY,
    CrawledPage,
    Throttle,
    _fetch_page,
    retry_after_seconds,
)

HTML = b"<html><head><title>A page</title></head><body><h1>A page</h1></body></html>"


@pytest.fixture
def waits(monkeypatch):
    """Record what the crawler asked to wait instead of waiting it.

    The backoff is real seconds. Serving them would put eight of them in the
    suite's critical path, and asserting on the recorded intervals is the
    stronger test anyway.
    """
    recorded: list[float] = []
    real_sleep = asyncio.sleep

    async def fake_sleep(seconds, *args, **kwargs):
        recorded.append(float(seconds))
        return await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    return recorded


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), follow_redirects=False
    )


# ── Retry-After ──


def test_retry_after_in_seconds():
    assert retry_after_seconds("120") == 120.0


def test_retry_after_as_an_http_date():
    when = datetime.now(timezone.utc) + timedelta(seconds=30)
    header = when.strftime("%a, %d %b %Y %H:%M:%S GMT")
    value = retry_after_seconds(header)
    assert value is not None and 20 <= value <= 40


def test_retry_after_absent_or_unparseable_is_not_zero():
    """Zero would mean "retry immediately", which is how a crawler turns one
    refusal into a hundred."""
    assert retry_after_seconds(None) is None
    assert retry_after_seconds("whenever") is None


# ── The throttle ──


def test_a_refusal_widens_the_gap_and_it_never_narrows():
    t = Throttle(0.0)
    assert t.delay == 0.0
    t.back_off()
    assert t.delay >= THROTTLED_MIN_DELAY
    first = t.delay
    t.back_off()
    assert t.delay > first
    assert t.throttled is True


def test_a_declared_crawl_delay_is_the_starting_point():
    """robots.txt is the site telling us its rate before we ask for
    anything."""
    assert Throttle(2.5).delay == 2.5


def test_the_gap_is_capped():
    t = Throttle(0.0)
    for _ in range(40):
        t.back_off()
    assert t.delay <= 10.0


# ── Fetching ──


@pytest.mark.asyncio
async def test_a_429_is_retried_and_the_page_comes_back(waits):
    """A burst limiter resets. The page is not broken; we asked too fast."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"retry-after": "0"})
        return httpx.Response(200, content=HTML, headers={"content-type": "text/html"})

    async with _client(handler) as client:
        page = await _fetch_page(client, "https://x/p", None, Throttle(0.0))

    assert calls["n"] == 2
    assert page.status_code == 200
    assert page.rate_limited is False
    assert page.parsed is not None


@pytest.mark.asyncio
async def test_a_page_refused_every_time_is_not_recorded_as_an_error(waits):
    """Stored as 429 it becomes "HTTP 429 on page with demand", which is a
    sentence about the client's site. It is a sentence about us."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"retry-after": "0"})

    async with _client(handler) as client:
        page = await _fetch_page(client, "https://x/p", None, Throttle(0.0))

    assert page.rate_limited is True
    # The important line in this file: no 4xx reaches the engine.
    assert page.status_code is None
    assert page.indexable is False
    assert "rate limited" in (page.fetch_error or "")


@pytest.mark.asyncio
async def test_it_gives_up_rather_than_retrying_forever(waits):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429, headers={"retry-after": "0"})

    async with _client(handler) as client:
        await _fetch_page(client, "https://x/p", None, Throttle(0.0))

    assert calls["n"] == MAX_RATE_LIMIT_RETRIES + 1


@pytest.mark.asyncio
async def test_a_long_retry_after_is_a_refusal_not_a_wait(waits):
    """Being told to come back in an hour would hold a worker for the whole
    crawl window."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"retry-after": "3600"})

    async with _client(handler) as client:
        page = await _fetch_page(client, "https://x/p", None, Throttle(0.0))

    assert page.rate_limited is True
    assert page.status_code is None
    # Given up on without ever waiting the hour.
    assert all(w < 3600 for w in waits)


@pytest.mark.asyncio
async def test_the_wait_doubles_when_the_server_names_no_interval(waits):
    """A server that refuses without a Retry-After gets progressively more
    room, rather than the same interval tried three times."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429)

    async with _client(handler) as client:
        await _fetch_page(client, "https://x/p", None, Throttle(0.0))

    backoffs = [w for w in waits if w >= RATE_LIMIT_BASE_DELAY]
    assert backoffs == sorted(backoffs)
    assert len(backoffs) >= 2
    assert backoffs[1] >= backoffs[0] * 2


@pytest.mark.asyncio
async def test_the_server_is_obeyed_when_it_names_an_interval(waits):
    """Our own backoff is a fallback, not an override."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"retry-after": "7"})

    async with _client(handler) as client:
        await _fetch_page(client, "https://x/p", None, Throttle(0.0))

    assert 7.0 in waits


@pytest.mark.asyncio
async def test_a_503_is_treated_the_same_way(waits):
    """Another "not now" wearing a different number."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, headers={"retry-after": "0"})
        return httpx.Response(200, content=HTML, headers={"content-type": "text/html"})

    async with _client(handler) as client:
        page = await _fetch_page(client, "https://x/p", None, Throttle(0.0))

    assert page.status_code == 200


@pytest.mark.asyncio
async def test_a_real_404_is_still_a_real_404():
    """The point is to stop confusing refusal with fault, not to stop
    reporting faults."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    async with _client(handler) as client:
        page = await _fetch_page(client, "https://x/gone", None, Throttle(0.0))

    assert page.status_code == 404
    assert page.rate_limited is False


@pytest.mark.asyncio
async def test_being_refused_slows_everything_that_follows(waits):
    """A site that refused once at this rate will refuse again. The crawl
    used to keep four requests in flight the whole way down."""
    throttle = Throttle(0.0)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"retry-after": "0"})

    async with _client(handler) as client:
        await _fetch_page(client, "https://x/p", None, throttle)

    assert throttle.throttled is True
    assert throttle.delay >= THROTTLED_MIN_DELAY


def test_a_rate_limited_page_is_not_indexable():
    page = CrawledPage(
        raw_url="https://x/p",
        normalized_url="https://x/p",
        status_code=None,
        redirect_url=None,
        redirect_count=0,
        blocked_by_robots=False,
        fetch_error="rate limited (HTTP 429)",
        parsed=None,
        rate_limited=True,
    )
    assert page.indexable is False
