"""A host that answers a plain 403 to our reader.

nashvillehomeorganizers.com answered 403 on its pages. The Decision Engine then reviewed its services page as
"403 Forbidden", three words and no way to enquire, and the page lost the best-page choice for a title nobody had
read. A refusal is us being turned away, not a broken page, and is recorded that way.

The crawler asks under one name, its own, and never again under another. (For a while a refused page was asked
for a second time as a browser. The refusals that prompted it turned out to be two hostnames sharing one
connection, fixed in `safe_http`, and the second ask was removed.)
"""

from __future__ import annotations

import asyncio
from datetime import date

import httpx

from app.ingestion.crawler.fetch import USER_AGENT, Throttle, _fetch_page, _get_capped
from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSnapshot
from app.services import crawl_fallback as cf
from app.services import growth_action as ga
from app.services import page_diagnostic as pd
from tests.test_growth_action import COLL, PROD, SEP, crawled, gsc

PAGE = "https://x/services.html"
FORBIDDEN = "<html><head><title>403 Forbidden</title></head><body><h1>403 Forbidden</h1></body></html>"


def _site(seen: list[str]):
    """A server that refuses every request, and records who asked."""

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("user-agent", ""))
        return httpx.Response(403, text=FORBIDDEN, headers={"content-type": "text/html"})

    return handler


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False, headers={"User-Agent": USER_AGENT})


def _fetch(handler, **kwargs):
    async def go():
        async with _client(handler) as client:
            return await _fetch_page(client, PAGE, None, Throttle(0.0), **kwargs)

    return asyncio.run(go())


# ── the site crawl ───────────────────────────────────────────────────────────


def test_an_expected_page_that_is_refused_is_us_turned_away_not_a_broken_page_and_is_asked_for_once():
    seen: list[str] = []
    page = _fetch(_site(seen), expected=True)
    assert seen == [USER_AGENT], "one request, under our own name, and no second ask under another"
    assert page.status_code is None, "stored as 403 it reads as a fault on the client's site"
    assert page.fetch_error == "refused our reader (HTTP 403)" and page.refused_status == 403
    assert page.parsed is None


def test_a_refused_page_nothing_vouches_for_keeps_its_status():
    seen: list[str] = []
    page = _fetch(_site(seen), expected=False)
    assert page.status_code == 403 and page.fetch_error is None and seen == [USER_AGENT]


def test_a_recognised_bot_challenge_is_asked_for_once():
    seen: list[str] = []

    def handler(request):
        seen.append(request.headers["user-agent"])
        return httpx.Response(403, text="<title>Just a moment...</title>", headers={"content-type": "text/html"})

    page = _fetch(handler)
    assert seen == [USER_AGENT], "the crawler does not try to get past a captcha"
    assert page.challenged_by == "Cloudflare's bot challenge"


def test_a_page_robots_disallows_is_not_asked_for():
    from urllib import robotparser

    seen: list[str] = []
    robots = robotparser.RobotFileParser()
    robots.parse(["User-agent: *", "Disallow: /services.html"])

    async def go():
        async with _client(_site(seen)) as client:
            return await _fetch_page(client, PAGE, robots, Throttle(0.0))

    page = asyncio.run(go())
    assert page.blocked_by_robots is True and seen == []


def test_a_refused_robots_file_is_asked_for_once():
    seen: list[str] = []

    async def go():
        async with _client(_site(seen)) as client:
            return await _get_capped(client, "https://x/robots.txt", 10_000)

    status, _, _ = asyncio.run(go())
    assert status == 403 and seen == [USER_AGENT]


# ── the live page reader ─────────────────────────────────────────────────────


def test_the_live_reader_uses_the_crawlers_name_and_asks_once(monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(pd, "PublicOnlyTransport", lambda: httpx.MockTransport(_site(seen)))
    assert pd.USER_AGENT == USER_AGENT, "one name for a host to allow"
    found = asyncio.run(pd._fetch(PAGE))
    assert seen == [USER_AGENT] and found.status == 403 and found.user_agent == USER_AGENT


def _refused(url):
    async def fetch(_):
        return pd.Fetched(status=403, final_url=url, headers={}, body=FORBIDDEN, requested_url=url, user_agent=USER_AGENT)

    return fetch


ROW = {"position": 7.3, "impressions": 287, "clicks": 3, "expected_extra_clicks": 4.0}


def test_a_refused_page_is_not_reviewed_as_an_error_page():
    url = "https://shop.example/services.html"
    out = pd.diagnose(search="home organizer", url=url, row=ROW, client_domain="shop.example", fetch=_refused(url))
    text = " ".join(o["text"] for o in out["observations"])
    assert "refused our reader (HTTP 403)" in text and "Nothing about it is judged" in text
    assert "answers with an error" not in text and "403 Forbidden" not in text
    assert out["prescriptions"] == [] and out["suggestions"] == []


def test_a_refused_page_is_read_from_the_site_crawl_when_the_crawl_holds_it(db, client_a):
    url = "https://shop.example/services.html"
    db.add(FactCrawlPageSnapshot(
        client_id=client_a.id, source=CRAWL_SOURCE_FIRST_PARTY, snapshot_date=date(2026, 11, 3), raw_url=url, normalized_url=url, status_code=200,
        title="Services and Rates", word_count=640, conversion_elements=2, indexable=True,
        sections=[{"level": 1, "heading": "Home organizing", "first_paragraph": "What we do and what it costs."}],
    ))
    db.commit()
    found = asyncio.run(cf.with_crawl(db, client_a, _refused(url))(url))
    assert found.source == "crawl" and "Services and Rates" in found.body


# ── the best page for a topic ────────────────────────────────────────────────


def test_a_page_the_crawler_was_turned_away_from_does_not_lose_the_choice_for_a_title_nobody_read(db, client_a):
    gsc(db, client_a, "natural sunscreen", COLL, 1000)
    gsc(db, client_a, "natural sunscreen", PROD, 1300)
    crawled(db, client_a, COLL, "Natural Sunscreen")
    db.add(FactCrawlPageSnapshot(client_id=client_a.id, source=CRAWL_SOURCE_FIRST_PARTY, snapshot_date=date(2026, 10, 1),
                                 raw_url=PROD, normalized_url=PROD, indexable=False, status_code=403, title=""))
    db.commit()
    out = ga.topic_pages(db, client_a, SEP, "natural sunscreen")
    by = {p["url"]: p for p in out["pages"]}
    assert by[PROD]["title_read"] is False and by[COLL]["title_read"] is True
    assert out["recommended"] == PROD, "the bigger page wins when its title could not be read"
