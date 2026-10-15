"""Why a declared sitemap did not work.

SMA's robots.txt declares https://smamarketing.com/sitemap_index.xml and that
URL returns 404. The crawl reported "no sitemap found", which sent somebody
looking for a sitemap that was never missing — the job is to fix the dead
address something is pointing crawlers at.
"""

from __future__ import annotations

import asyncio

import httpx

from app.ingestion.crawler.fetch import _load_sitemap_urls
from app.ingestion.crawler.pipeline import _sitemap_failure_note


class _Result:
    def __init__(self, failures):
        self.sitemap_failures = failures


def _run(handler, urls):
    async def go():
        failures: list[tuple[str, str]] = []
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            found = await _load_sitemap_urls(
                client, urls, host="x.test", budget=100, failures=failures
            )
        return found, failures

    return asyncio.run(go())


def test_a_declared_sitemap_that_404s_says_so():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="<!DOCTYPE html><html>Not found</html>")

    found, failures = _run(handler, ["https://x.test/sitemap_index.xml"])
    assert found == {}
    assert failures == [("https://x.test/sitemap_index.xml", "returns 404")]
    assert (
        _sitemap_failure_note(_Result(failures))
        == "sitemap declared at https://x.test/sitemap_index.xml returns 404"
    )


def test_a_sitemap_that_is_not_xml_says_that_instead():
    def handler(request: httpx.Request) -> httpx.Response:
        # The real shape: a 200 HTML error page. An unclosed <meta> is what
        # breaks the parse, and every HTML page has one.
        return httpx.Response(
            200,
            text='<!DOCTYPE html><html><head><meta charset="UTF-8"><title>404</title></head></html>',
        )

    _, failures = _run(handler, ["https://x.test/sitemap.xml"])
    assert failures == [("https://x.test/sitemap.xml", "is not valid XML")]


def test_a_soft_404_that_happens_to_parse_is_not_a_sitemap():
    """Well-formed XHTML gets past the parser.

    Without checking the root element it reads as a sitemap with no URLs in
    it, rather than as the wrong document entirely.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html><body>Not found</body></html>")

    found, failures = _run(handler, ["https://x.test/sitemap.xml"])
    assert found == {}
    assert failures == [
        ("https://x.test/sitemap.xml", "is a <html> document, not a sitemap")
    ]


def test_a_working_sitemap_records_no_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=(
                '<?xml version="1.0"?><urlset '
                'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                "<url><loc>https://x.test/a</loc></url></urlset>"
            ),
        )

    found, failures = _run(handler, ["https://x.test/sitemap.xml"])
    assert failures == []
    assert found


def test_no_failures_means_no_note():
    # "Not found" is still the right words when nothing was declared.
    assert _sitemap_failure_note(_Result([])) is None
