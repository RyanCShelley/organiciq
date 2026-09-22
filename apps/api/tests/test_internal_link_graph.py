"""
The internal link graph, and editorial versus template links.

The crawler always built this graph and reduced it to a count. The count was
also misleading: on smamarketing.com only 12% of inbound links are editorial,
so pages cleared the internal-linking threshold on menu links alone.
"""

from __future__ import annotations

import asyncio

import httpx

from app.ingestion.crawler.fetch import (
    TEMPLATE_LINK_PREVALENCE,
    TEMPLATE_PREVALENCE_MIN_PAGES,
    USER_AGENT,
    crawl_site,
)
from app.ingestion.crawler.parse import parse_page


def _page(body: str) -> str:
    return f"<html><head><title>T</title></head><body>{body}</body></html>"


def _site(pages: dict[str, str]):
    """
    A mock site whose nav links every page, as a real template does. That also
    makes every page reachable, the way a menu does on a live site.
    """
    nav = "".join(f'<a href="{path}">{path}</a>' for path in pages)

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/robots.txt":
            return httpx.Response(404)
        if path.endswith("sitemap.xml"):
            return httpx.Response(404)
        if path not in pages:
            return httpx.Response(404, headers={"content-type": "text/html"}, text="gone")
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text=_page(f"<nav>{nav}</nav><main>{pages[path]}</main>"),
        )

    return handler


# --- Parsing ----------------------------------------------------------------


def test_anchor_text_and_position_are_kept():
    """Both are needed for cluster work and both were being discarded."""
    parsed = parse_page(
        url="https://example.com/post",
        body=_page(
            '<nav><a href="/hub">Hub</a></nav>'
            '<main><p>Read the <a href="/guide">carbon fiber guide</a>.</p></main>'
            '<footer><a href="/contact">Contact us</a></footer>'
        ),
    )
    by_target = {link.target: link for link in parsed.internal_links}

    guide = by_target["https://example.com/guide"]
    assert guide.anchor == "carbon fiber guide"
    assert guide.in_content is True

    assert by_target["https://example.com/hub"].in_content is False
    assert by_target["https://example.com/contact"].in_content is False


def test_furniture_links_survive_the_word_count_strip():
    """
    The strip removes nav and footer. Collecting links after it made every
    furniture link vanish rather than be classified — the same trap that once
    ate the JSON-LD.
    """
    parsed = parse_page(
        url="https://example.com/post",
        body=_page('<nav><a href="/hub">Hub</a></nav><main><p>words here</p></main>'),
    )
    assert [link.target for link in parsed.internal_links] == ["https://example.com/hub"]


def test_a_link_in_both_nav_and_body_counts_as_editorial():
    parsed = parse_page(
        url="https://example.com/post",
        body=_page(
            '<nav><a href="/hub">Hub</a></nav>'
            '<main><p>see the <a href="/hub">hub page</a></p></main>'
        ),
    )
    link = parsed.internal_links[0]
    assert link.in_content is True
    assert link.occurrences == 2
    assert link.anchor == "hub page"


# --- Classification ---------------------------------------------------------


def _crawl(pages: dict[str, str], monkeypatch):
    handler = _site(pages)
    original = httpx.AsyncClient

    def patched(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched)
    return asyncio.run(crawl_site("example.com", page_limit=40))


def test_site_wide_links_are_template_even_in_body_markup(monkeypatch):
    """
    Position alone is not enough. On element6composites.com the navigation is
    plain divs, so every nav link looks editorial; prevalence catches it.
    """
    pages = {f"/p{i}": f'<p>text <a href="/services">our services</a></p>' for i in range(14)}
    pages["/"] = "<p>home</p>"
    pages["/services"] = "<p>services</p>"
    pages["/blog"] = "<p>blog</p>"

    result = _crawl(pages, monkeypatch)
    services = [p for p in result.pages if p.normalized_url.endswith("/services")][0]

    assert services.inbound_internal_links > TEMPLATE_PREVALENCE_MIN_PAGES
    assert services.inbound_editorial_links == 0, "a link on every page is navigation"


def test_a_single_editorial_reference_is_kept(monkeypatch):
    pages = {f"/p{i}": "<p>plain</p>" for i in range(14)}
    pages["/"] = "<p>home</p>"
    pages["/services"] = "<p>services</p>"
    pages["/blog"] = "<p>blog</p>"
    pages["/p0"] = '<p>see the <a href="/p7">detail page</a></p>'

    result = _crawl(pages, monkeypatch)
    target = [p for p in result.pages if p.normalized_url.endswith("/p7")][0]

    assert target.inbound_editorial_links == 1
    edge = [e for e in result.links if e.to_url.endswith("/p7") and not e.is_template][0]
    assert edge.anchor == "detail page"
    assert edge.from_url.endswith("/p0")


def test_prevalence_is_not_applied_to_a_tiny_site(monkeypatch):
    """On a five-page site everything links to everything for good reasons."""
    pages = {"/": '<p><a href="/about">about</a></p>', "/about": "<p>about</p>"}

    result = _crawl(pages, monkeypatch)
    about = [p for p in result.pages if p.normalized_url.endswith("/about")][0]

    assert len(result.pages) < TEMPLATE_PREVALENCE_MIN_PAGES
    assert about.inbound_editorial_links == 1


def test_the_threshold_is_a_majority_of_pages():
    assert 0 < TEMPLATE_LINK_PREVALENCE <= 0.5


def test_edges_to_uncrawled_urls_are_dropped(monkeypatch):
    """An edge to a URL we never fetched cannot be reasoned about."""
    pages = {"/": '<p><a href="/missing">nowhere</a></p>'}

    result = _crawl(pages, monkeypatch)

    assert all(e.to_url in {p.normalized_url for p in result.pages} for e in result.links)


def test_slash_variants_of_the_same_target_become_one_edge(monkeypatch):
    """
    Links are deduped per page by absolute URL, but `/x` and `/x/` normalize to
    one target. Without merging on the stored grain the crawl writes two rows for
    one pair and the whole job fails on the unique constraint — which is how this
    was found, on a page linking both forms of /contact.
    """
    pages = {f"/p{i}": "<p>plain</p>" for i in range(12)}
    pages["/"] = '<p>a <a href="/contact">contact</a> and <a href="/contact/">contact us</a></p>'
    pages["/contact"] = "<p>contact</p>"

    result = _crawl(pages, monkeypatch)
    to_contact = [
        e for e in result.links if e.from_url.rstrip("/").endswith("example.com") and "contact" in e.to_url
    ]

    assert len(to_contact) == 1, "one pair, one edge"
    # Three placements merged: the nav link plus both body forms.
    assert to_contact[0].occurrences == 3
    assert to_contact[0].in_content is True, "an editorial placement wins over the nav one"
