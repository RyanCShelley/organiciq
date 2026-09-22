"""First-party crawler: parsing, redirect semantics, and source isolation."""

from __future__ import annotations

import asyncio
from datetime import date
from uuid import uuid4

import httpx

from app.ingestion.crawler.fetch import (
    MAX_PAGE_LIMIT,
    USER_AGENT,
    _fetch_page,
    page_limit_for,
)
from app.ingestion.crawler.parse import parse_page
from app.models.crawl import (
    CRAWL_SOURCE_FIRST_PARTY,
    CRAWL_SOURCE_SE_RANKING,
    FactCrawlPageSnapshot,
)

PAGE = "https://example.com/guide"


# --- Parsing ----------------------------------------------------------------


def test_extracts_the_signals_the_technical_lever_reads():
    parsed = parse_page(
        url=PAGE,
        body="""
        <html><head>
          <title>  A   Guide </title>
          <meta name="description" content="How to do the thing.">
          <link rel="canonical" href="/guide/">
        </head><body>
          <h1>A Guide</h1>
          <p>one two three four five</p>
          <a href="/other">internal</a>
          <a href="https://elsewhere.example/x">external</a>
          <a href="mailto:a@b.c">mail</a>
        </body></html>
        """,
    )

    assert parsed.title == "A Guide"
    assert parsed.description == "How to do the thing."
    assert parsed.h1 == "A Guide"
    # Body only: h1 (2) + paragraph (5) + link text (3). The title is not content.
    assert parsed.word_count == 10
    assert parsed.canonical_raw == "https://example.com/guide/"
    assert parsed.internal_links == ["https://example.com/other"]


def test_script_and_style_text_is_not_content():
    parsed = parse_page(
        url=PAGE,
        body="<html><body><script>var a = 1;</script><style>.x{}</style><p>real words here</p></body></html>",
    )
    assert parsed.word_count == 3


def test_json_ld_survives_the_word_count_strip():
    """
    JSON-LD lives in <script>, which the word-count strip removes — extracting
    after that strip silently reported every site as having no structured data.
    """
    parsed = parse_page(
        url=PAGE,
        body="""
        <html><head><script type="application/ld+json">
          {"@context":"https://schema.org","@type":"Organization","name":"Acme"}
        </script></head><body><p>words</p></body></html>
        """,
    )

    assert [b.schema_type for b in parsed.schema_blocks] == ["Organization"]
    assert parsed.word_count == 1


def test_nested_graph_types_are_all_recorded():
    parsed = parse_page(
        url=PAGE,
        body="""
        <html><head><script type="application/ld+json">
          {"@graph":[{"@type":"WebSite"},{"@type":["Article","BlogPosting"]}]}
        </script></head><body></body></html>
        """,
    )
    assert sorted(b.schema_type for b in parsed.schema_blocks) == [
        "Article",
        "BlogPosting",
        "WebSite",
    ]


def test_invalid_json_ld_is_recorded_rather_than_dropped():
    """Present but unparseable is the same as absent to a consumer, and is the
    one schema failure nothing else in the stack reports."""
    parsed = parse_page(
        url=PAGE,
        body='<html><head><script type="application/ld+json">{"@type": "Org",,}</script></head><body></body></html>',
    )

    assert len(parsed.schema_blocks) == 1
    block = parsed.schema_blocks[0]
    assert block.schema_type is None
    assert "invalid JSON" in block.parse_error
    assert block.raw_text  # kept so it can be diagnosed


def test_schema_org_urls_reduce_to_the_bare_type():
    parsed = parse_page(
        url=PAGE,
        body='<html><body><div itemscope itemtype="https://schema.org/LocalBusiness"></div></body></html>',
    )
    assert [b.schema_type for b in parsed.schema_blocks] == ["LocalBusiness"]
    assert [b.syntax for b in parsed.schema_blocks] == ["microdata"]


def test_noindex_is_read_from_meta_and_from_the_header():
    from_meta = parse_page(
        url=PAGE,
        body='<html><head><meta name="robots" content="noindex, follow"></head><body></body></html>',
    )
    assert from_meta.meta_noindex is True

    from_header = parse_page(
        url=PAGE,
        body="<html><head></head><body></body></html>",
        headers={"x-robots-tag": "noindex"},
    )
    assert from_header.meta_noindex is True


# --- Redirect semantics -----------------------------------------------------


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        headers={"User-Agent": USER_AGENT},
        follow_redirects=False,
    )


def test_a_trailing_slash_redirect_records_the_page_that_serves():
    """
    The Element Six case. `/guide` 301s to `/guide/`; both normalize to the same
    key, so the row has to describe the 200 — recording the 301 is what made
    Search Console demand land on a page marked non-indexable.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/guide":
            return httpx.Response(301, headers={"location": "https://example.com/guide/"})
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<html><head><title>Guide</title></head><body><p>hi</p></body></html>",
        )

    async def run():
        async with _client(handler) as client:
            return await _fetch_page(client, PAGE, None)

    page = asyncio.run(run())

    assert page.status_code == 200
    assert page.indexable is True
    assert page.redirect_count == 1
    assert page.raw_url == "https://example.com/guide/"
    assert page.parsed is not None and page.parsed.title == "Guide"


def test_a_redirect_to_a_different_page_stays_a_redirect():
    """A real redirect must not be flattened into the destination."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/guide":
            return httpx.Response(301, headers={"location": "https://example.com/somewhere-else"})
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<html></html>")

    async def run():
        async with _client(handler) as client:
            return await _fetch_page(client, PAGE, None)

    page = asyncio.run(run())

    assert page.status_code == 301
    assert page.indexable is False
    assert page.redirect_url == "https://example.com/somewhere-else"


def test_a_genuine_redirect_loop_is_reported():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(301, headers={"location": str(request.url)})

    async def run():
        async with _client(handler) as client:
            return await _fetch_page(client, PAGE, None)

    page = asyncio.run(run())

    assert page.fetch_error is not None
    assert "loop" in page.fetch_error


def test_robots_disallow_is_recorded_without_fetching():
    from urllib import robotparser

    robots = robotparser.RobotFileParser()
    robots.parse(["User-agent: *", "Disallow: /guide"])

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("a disallowed URL must not be fetched")

    async def run():
        async with _client(handler) as client:
            return await _fetch_page(client, PAGE, robots)

    page = asyncio.run(run())

    assert page.blocked_by_robots is True
    assert page.indexable is False


# --- Budget -----------------------------------------------------------------


def test_the_page_limit_is_bounded():
    assert page_limit_for(None) == 500
    assert page_limit_for(50) == 50
    assert page_limit_for(10**6) == MAX_PAGE_LIMIT
    assert page_limit_for(0) == 500
    assert page_limit_for(-5) == 1


# --- Source isolation -------------------------------------------------------


def _snapshot(client_id, source, url):
    return FactCrawlPageSnapshot(
        id=uuid4(),
        client_id=client_id,
        source=source,
        snapshot_date=date.today(),
        raw_url=url,
        normalized_url=url,
        indexable=True,
        status_code=200,
        inbound_internal_links=0,
        word_count=100,
        in_sitemap=True,
        redirect_count=0,
    )


def test_both_crawl_sources_can_hold_a_row_for_the_same_page(db, client_a):
    """The parallel run depends on this: one page, two sources, no collision."""
    db.add(_snapshot(client_a.id, CRAWL_SOURCE_SE_RANKING, PAGE))
    db.add(_snapshot(client_a.id, CRAWL_SOURCE_FIRST_PARTY, PAGE))
    db.commit()

    rows = (
        db.query(FactCrawlPageSnapshot)
        .filter(FactCrawlPageSnapshot.client_id == client_a.id)
        .all()
    )
    assert {row.source for row in rows} == {CRAWL_SOURCE_SE_RANKING, CRAWL_SOURCE_FIRST_PARTY}


def test_the_lever_reads_one_source_and_does_not_mix_them(db, client_a):
    """
    Both crawls keep writing. Reading unscoped would mix them and make the row
    for a page depend on insert order.
    """
    from app.services.lever_engine import _load_crawl_by_url, active_crawl_source

    db.add(_snapshot(client_a.id, CRAWL_SOURCE_FIRST_PARTY, PAGE))
    db.add(_snapshot(client_a.id, CRAWL_SOURCE_SE_RANKING, PAGE))
    db.commit()

    loaded = _load_crawl_by_url(db, client_a.id)

    assert len(loaded) == 1
    assert loaded[PAGE].source == active_crawl_source()


def test_the_engine_reads_the_first_party_crawl_by_default():
    """The cutover. Flipping crawl_facts_source backs it out without a deploy."""
    from app.services.lever_engine import active_crawl_source

    assert active_crawl_source() == CRAWL_SOURCE_FIRST_PARTY


def test_an_unknown_configured_source_falls_back_rather_than_reading_nothing(monkeypatch):
    from app.core import settings as settings_module
    from app.services import lever_engine

    monkeypatch.setattr(
        lever_engine,
        "get_settings",
        lambda: type("S", (), {"crawl_facts_source": "typo_source"})(),
    )
    assert lever_engine.active_crawl_source() == CRAWL_SOURCE_FIRST_PARTY


def test_the_audit_publish_does_not_wipe_the_first_party_crawl(db, client_a):
    """An unscoped delete here would erase our crawl on every nightly audit."""
    from app.ingestion.seranking.publish_audit import publish_seranking_audit
    from app.models.job import SyncJob, SyncJobStatus

    db.add(_snapshot(client_a.id, CRAWL_SOURCE_FIRST_PARTY, PAGE))
    db.commit()

    job = SyncJob(
        id=uuid4(),
        client_id=client_a.id,
        source="se_ranking_audit",
        start_date=date.today(),
        end_date=date.today(),
        status=SyncJobStatus.QUEUED,
    )
    db.add(job)
    db.commit()

    publish_seranking_audit(db, job)

    survivors = (
        db.query(FactCrawlPageSnapshot)
        .filter(
            FactCrawlPageSnapshot.client_id == client_a.id,
            FactCrawlPageSnapshot.source == CRAWL_SOURCE_FIRST_PARTY,
        )
        .count()
    )
    assert survivors == 1


def test_site_crawl_is_a_registered_job_source():
    from app.services.jobs import _job_handlers

    assert "site_crawl" in _job_handlers()


def test_site_crawl_is_not_in_the_daily_sync():
    """Monthly by design — a daily full crawl of 35 client sites is not wanted."""
    from app.services.daily_sync import _PROVIDER_SOURCES

    scheduled = {s for sources in _PROVIDER_SOURCES.values() for s in sources}
    assert "site_crawl" not in scheduled


# --- Assets are not pages ---------------------------------------------------


def test_asset_urls_are_not_treated_as_pages():
    from app.ingestion.crawler.parse import is_page_url

    assert is_page_url("https://example.com/guide")
    assert is_page_url("https://example.com/guide/")
    assert is_page_url("https://example.com/2026/report.html")
    assert not is_page_url("https://example.com/wp-content/uploads/diver.svg")
    assert not is_page_url("https://example.com/locations.kml")
    assert not is_page_url("https://example.com/brochure.pdf")
    assert not is_page_url("https://example.com/app.js")


def test_asset_links_are_not_followed():
    """
    Aquaman's crawl pulled in .kml, .svg, .png and .jpg URLs and reported them
    as indexable pages carrying no schema — images filed as content defects.
    """
    parsed = parse_page(
        url=PAGE,
        body="""
        <html><body>
          <a href="/real-page">page</a>
          <a href="/wp-content/uploads/diver.svg">image</a>
          <a href="/locations.kml">map</a>
          <a href="/brochure.pdf">pdf</a>
        </body></html>
        """,
    )
    assert parsed.internal_links == ["https://example.com/real-page"]


def test_a_non_html_response_is_dropped_from_the_page_set():
    """Extension checks miss extensionless asset URLs; the content type does not."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "image/png"}, content=b"\x89PNG")

    async def run():
        async with _client(handler) as client:
            return await _fetch_page(client, "https://example.com/media/12345", None)

    page = asyncio.run(run())

    assert page.is_page is False


def test_an_html_error_page_is_still_a_page():
    """A 404 is a finding; it must not be filtered out with the assets."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, headers={"content-type": "text/html"}, text="<html>gone</html>")

    async def run():
        async with _client(handler) as client:
            return await _fetch_page(client, PAGE, None)

    page = asyncio.run(run())

    assert page.is_page is True
    assert page.status_code == 404
    assert page.indexable is False


# --- Crawl boundary ---------------------------------------------------------


def test_subdomains_are_part_of_the_site():
    """
    Deliberate, confirmed 2026-09-22. Subdomain pages rank and can be missing
    schema — Aquaman's twelve uncovered pages all live on `rs.`, and restricting
    the crawl to the exact host would have hidden every one of them.

    The cost is accepted: a client with a large unrelated subdomain spends crawl
    budget on it, which the per-crawl page limit bounds.
    """
    parsed = parse_page(
        url="https://example.com/",
        body="""
        <html><body>
          <a href="https://rs.example.com/landing">subdomain</a>
          <a href="https://www.example.com/page">www</a>
          <a href="https://notexample.com/x">lookalike</a>
          <a href="https://example.com.evil.test/x">suffix attack</a>
        </body></html>
        """,
    )

    assert "https://rs.example.com/landing" in parsed.internal_links
    assert "https://www.example.com/page" in parsed.internal_links
    # A name that merely ends with the domain is a different site.
    assert not any("notexample.com" in link for link in parsed.internal_links)
    assert not any("evil.test" in link for link in parsed.internal_links)
