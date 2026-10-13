"""When a page says it was last updated.

A refresh queue ranks on what a page is losing and how long since anybody
touched it, and the second half was recorded nowhere: `parse_page` read
`meta` by `@name` only, so every `article:modified_time` on every page we
had ever crawled was invisible, and the sitemap loop read `<loc>` and
stepped past `<lastmod>`.

Three sources, because no one of them covers a book of clients. Measured
before this was built: SMA carries a date in stored JSON-LD on 273 of 382
indexable pages; ACCTek on 0 of 184, while serving `article:modified_time`
on the page and `<lastmod>` in its sitemap.
"""

from __future__ import annotations

import asyncio
from datetime import date

import httpx

from app.ingestion.crawler.fetch import _load_sitemap_urls, _sitemap_date
from app.ingestion.crawler.parse import parse_page


def _page(head: str) -> str:
    return f"<html><head><title>T</title>{head}</head><body><h1>H</h1><p>x</p></body></html>"


# ── The page's own statement ──


def test_schema_is_read_first():
    """The publisher's own dateModified, which is what Google reads."""
    parsed = parse_page(
        url="https://e.test/a",
        body=_page(
            '<script type="application/ld+json">'
            '{"@type":"Article","dateModified":"2026-09-07T11:20:00+00:00"}'
            "</script>"
            '<meta property="article:modified_time" content="2024-01-01T00:00:00+00:00"/>'
        ),
    )
    assert parsed.content_updated_on == date(2026, 9, 7)
    assert parsed.content_updated_source == "schema"


def test_the_newest_schema_date_wins():
    """A WordPress page repeats the site's dates beside the post's.

    SMA's homepage carries 2025-03-18 and 2026-09-07 in the same graph.
    Taking the first would report the site as eighteen months stale.
    """
    parsed = parse_page(
        url="https://e.test/a",
        body=_page(
            '<script type="application/ld+json">'
            '{"@graph":[{"@type":"WebPage","dateModified":"2025-03-18"},'
            '{"@type":"Article","dateModified":"2026-09-07"}]}'
            "</script>"
        ),
    )
    assert parsed.content_updated_on == date(2026, 9, 7)


def test_modified_beats_published():
    parsed = parse_page(
        url="https://e.test/a",
        body=_page(
            '<script type="application/ld+json">'
            '{"@type":"Article","datePublished":"2020-01-01",'
            '"dateModified":"2026-02-02"}'
            "</script>"
        ),
    )
    assert parsed.content_updated_on == date(2026, 2, 2)


def test_the_article_meta_is_read_when_schema_carries_no_date():
    """ACCTek's shape: schema present, no dates in it, meta on every page."""
    parsed = parse_page(
        url="https://e.test/a",
        body=_page(
            '<script type="application/ld+json">{"@type":"WebPage","name":"x"}</script>'
            '<meta property="article:modified_time" content="2026-05-16T10:25:15+00:00"/>'
        ),
    )
    assert parsed.content_updated_on == date(2026, 5, 16)
    assert parsed.content_updated_source == "meta"


def test_a_page_with_no_date_anywhere_says_so():
    """None is "unknown", not "never updated".

    A queue that read a missing date as ancient would put every page
    without an SEO plugin at the top of the refresh list.
    """
    parsed = parse_page(url="https://e.test/a", body=_page(""))
    assert parsed.content_updated_on is None
    assert parsed.content_updated_source is None


def test_an_unparseable_date_is_no_date():
    parsed = parse_page(
        url="https://e.test/a",
        body=_page('<meta property="article:modified_time" content="last Tuesday"/>'),
    )
    assert parsed.content_updated_on is None


# ── The sitemap's statement ──


def test_lastmod_is_kept():
    sitemap = (
        '<?xml version="1.0"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        "<url><loc>https://e.test/a</loc><lastmod>2026-09-22T07:44:46+00:00</lastmod></url>"
        "<url><loc>https://e.test/b</loc></url>"
        "</urlset>"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "application/xml"}, text=sitemap)

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await _load_sitemap_urls(
                client, ["https://e.test/sitemap.xml"], host="e.test", budget=100
            )

    assert asyncio.run(run()) == {
        "https://e.test/a": date(2026, 9, 22),
        "https://e.test/b": None,
    }


def test_lastmod_is_read_both_ways_sitemaps_write_it():
    assert _sitemap_date("2026-09-22T07:44:46+00:00") == date(2026, 9, 22)
    assert _sitemap_date("2026-09-22") == date(2026, 9, 22)
    assert _sitemap_date("2026-09-22T07:44:46Z") == date(2026, 9, 22)
    assert _sitemap_date("") is None
    assert _sitemap_date(None) is None
    assert _sitemap_date("whenever") is None


def test_the_http_header_is_not_a_source():
    """Deliberately not read.

    ACCTek's /managed-it-services-syracuse-ny returns Last-Modified of 11
    October while its own article:modified_time says 16 May. The header
    says when the server last rendered the page, not when anybody changed
    it, and reading it would report an untouched site as entirely fresh.
    """
    parsed = parse_page(
        url="https://e.test/a",
        body=_page(""),
        headers={"last-modified": "Sun, 11 Oct 2026 06:46:48 GMT"},
    )
    assert parsed.content_updated_on is None
