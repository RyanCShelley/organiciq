"""Breadth-first site crawl over httpx.

asyncio rather than Scrapy on purpose: Scrapy runs a Twisted reactor, and a
reactor can only be started once per process. The worker is a long-lived polling
loop that invokes this repeatedly, which fights that model directly. httpx is
already a dependency and already carries the timeout conventions used elsewhere.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from urllib import robotparser
from urllib.parse import urldefrag, urljoin, urlsplit
from xml.etree import ElementTree

import httpx

from app.core.urls import normalize_url
from app.ingestion.crawler.parse import PageLink, ParsedPage, is_page_url, parse_page

logger = logging.getLogger("organiciq.crawler")


class RobotsUnreachable(Exception):
    """robots.txt exists in principle but could not be fetched — not the same as absent."""

USER_AGENT = "OrganicIQBot/1.0 (+https://smamarketing.com/organiciq; SEO monitoring)"

DEFAULT_PAGE_LIMIT = 500
#: Ceiling no per-client setting may exceed. A faceted site is effectively
#: infinite, and an unbounded crawl is the failure mode to design against.
MAX_PAGE_LIMIT = 5000
DEFAULT_CONCURRENCY = 4
REQUEST_TIMEOUT = 20.0
#: A redirect run longer than this is a loop as far as we are concerned.
MAX_REDIRECT_HOPS = 5
MAX_BODY_BYTES = 5_000_000
#: A target linked from at least this share of crawled pages is template
#: navigation, whatever markup it sits in. Position alone is not enough: on
#: element6composites.com the navigation is plain divs, so every nav link looks
#: editorial, while on smamarketing.com it is a <nav> and only 12% of inbound
#: links are editorial. Prevalence catches both.
TEMPLATE_LINK_PREVALENCE = 0.5
#: Below this many pages, prevalence is meaningless — a five-page site links
#: everything from everywhere for legitimate reasons.
TEMPLATE_PREVALENCE_MIN_PAGES = 10


@dataclass
class InternalLink:
    """One edge of the internal link graph."""

    from_url: str
    to_url: str
    anchor: str
    in_content: bool
    occurrences: int
    #: Site furniture rather than an editorial reference. Set after the crawl,
    #: once prevalence across all pages is known.
    is_template: bool = False


@dataclass
class CrawledPage:
    raw_url: str
    normalized_url: str
    status_code: int | None
    redirect_url: str | None
    redirect_count: int
    blocked_by_robots: bool
    fetch_error: str | None
    parsed: ParsedPage | None
    #: False when the response was a 2xx of some non-HTML type.
    is_page: bool = True
    in_sitemap: bool = False
    inbound_internal_links: int = 0
    #: Inbound links that are neither navigation nor site-wide. This is the
    #: number that says whether anyone actually references the page.
    inbound_editorial_links: int = 0

    @property
    def indexable(self) -> bool:
        """
        Whether this URL can hold rankings itself.

        A redirect is not indexable — the destination is — and neither is an
        error page or one the robots meta excludes. Callers distinguish *why*;
        a 3xx is normal, a noindexed 200 with demand is not.
        """
        if self.status_code is None or not (200 <= self.status_code < 300):
            return False
        if self.blocked_by_robots:
            return False
        return not (self.parsed is not None and self.parsed.meta_noindex)


@dataclass
class CrawlResult:
    pages: list[CrawledPage] = field(default_factory=list)
    sitemap_urls: set[str] = field(default_factory=set)
    robots_txt_found: bool = False
    #: Set when robots.txt could not be fetched at all, as opposed to absent.
    robots_txt_error: str | None = None
    #: robots.txt tells our agent not to crawl the site at all.
    robots_disallows_site: bool = False
    #: A sitemap was declared or found but could not be read.
    sitemap_unreadable: bool = False
    hit_page_limit: bool = False
    links: list[InternalLink] = field(default_factory=list)


def page_limit_for(client_limit: int | None) -> int:
    requested = client_limit if client_limit else DEFAULT_PAGE_LIMIT
    return max(1, min(int(requested), MAX_PAGE_LIMIT))


def _start_url(domain: str) -> str:
    value = (domain or "").strip()
    if not value:
        raise ValueError("Client has no domain set")
    if "://" not in value:
        value = f"https://{value}"
    parts = urlsplit(value)
    return f"{parts.scheme}://{parts.netloc}{parts.path or '/'}"


def _same_site(host: str, other: str) -> bool:
    a = (host or "").lower().removeprefix("www.")
    b = (other or "").lower().removeprefix("www.")
    return bool(a) and (a == b or b.endswith(f".{a}"))


async def _load_robots(client: httpx.AsyncClient, root: str) -> tuple[robotparser.RobotFileParser | None, list[str]]:
    """Return (parser, sitemap urls). A missing robots.txt means crawl freely."""
    parser = robotparser.RobotFileParser()
    try:
        response = await client.get(urljoin(root, "/robots.txt"), follow_redirects=True)
    except httpx.HTTPError as exc:
        logger.info("robots.txt unreachable for %s: %s", root, exc)
        raise RobotsUnreachable(str(exc)) from exc
    if response.status_code >= 400:
        return None, []
    text = response.text
    parser.parse(text.splitlines())
    sitemaps = [
        line.split(":", 1)[1].strip()
        for line in text.splitlines()
        if line.lower().startswith("sitemap:")
    ]
    return parser, sitemaps


async def _load_sitemap_urls(
    client: httpx.AsyncClient, sitemaps: list[str], *, host: str, budget: int
) -> set[str]:
    """URLs listed in the sitemaps, following index files one level down."""
    found: set[str] = set()
    queue = list(sitemaps)
    seen: set[str] = set()
    while queue and len(found) < budget:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            response = await client.get(url, follow_redirects=True)
            if response.status_code >= 400:
                continue
            root = ElementTree.fromstring(response.content)
        except (httpx.HTTPError, ElementTree.ParseError) as exc:
            logger.info("sitemap %s unreadable: %s", url, exc)
            continue
        tag = root.tag.rsplit("}", 1)[-1]
        for loc in root.iter():
            if loc.tag.rsplit("}", 1)[-1] != "loc" or not (loc.text or "").strip():
                continue
            value = loc.text.strip()
            if tag == "sitemapindex":
                queue.append(value)
            else:
                parts = urlsplit(value)
                if parts.hostname and _same_site(host, parts.hostname) and is_page_url(value):
                    found.add(normalize_url(value))
            if len(found) >= budget:
                break
    return found


async def crawl_site(
    domain: str,
    *,
    page_limit: int = DEFAULT_PAGE_LIMIT,
    concurrency: int = DEFAULT_CONCURRENCY,
    respect_robots: bool = True,
) -> CrawlResult:
    """Crawl a site breadth-first from its root, bounded by `page_limit`."""
    root = _start_url(domain)
    host = urlsplit(root).hostname or ""
    result = CrawlResult()

    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)

    async with httpx.AsyncClient(
        headers=headers,
        timeout=REQUEST_TIMEOUT,
        follow_redirects=False,
        limits=limits,
    ) as client:
        try:
            robots, sitemap_locations = await _load_robots(client, root)
        except RobotsUnreachable as exc:
            robots, sitemap_locations = None, []
            result.robots_txt_error = str(exc)[:300]
        result.robots_txt_found = robots is not None
        if robots is not None and not robots.can_fetch(USER_AGENT, root):
            result.robots_disallows_site = True

        declared_sitemaps = bool(sitemap_locations)
        if not sitemap_locations:
            sitemap_locations = [urljoin(root, "/sitemap.xml")]
        result.sitemap_urls = await _load_sitemap_urls(
            client, sitemap_locations, host=host, budget=page_limit * 4
        )
        # Declared in robots.txt but yielding nothing means it is broken, which
        # is a different finding from having no sitemap at all.
        result.sitemap_unreadable = declared_sitemaps and not result.sitemap_urls

        # Sitemap URLs are seeded alongside the root: a page nothing links to is
        # exactly the kind of page worth knowing about.
        queue: list[str] = [root, *sorted(result.sitemap_urls)]
        queued: set[str] = {normalize_url(root)} | set(result.sitemap_urls)
        inbound: dict[str, int] = {}
        edges: dict[tuple[str, str], InternalLink] = {}
        pages: dict[str, CrawledPage] = {}
        semaphore = asyncio.Semaphore(concurrency)

        async def fetch_one(url: str) -> CrawledPage:
            async with semaphore:
                return await _fetch_page(client, url, robots if respect_robots else None)

        while queue and len(pages) < page_limit:
            batch = queue[: max(1, concurrency)]
            del queue[: len(batch)]
            batch = [u for u in batch if normalize_url(u) not in pages]
            if not batch:
                continue

            for page in await asyncio.gather(*(fetch_one(url) for url in batch)):
                if page.normalized_url in pages:
                    continue
                if not page.is_page:
                    # An asset that slipped past the extension check. Not a page,
                    # and not something the Technical lever should report on.
                    continue
                pages[page.normalized_url] = page

                if page.redirect_url:
                    target = normalize_url(page.redirect_url)
                    if target != page.normalized_url and target not in queued:
                        queued.add(target)
                        queue.append(page.redirect_url)

                if page.parsed is None:
                    continue
                for link in page.parsed.internal_links:
                    key = normalize_url(link.target)
                    inbound[key] = inbound.get(key, 0) + 1
                    # Links are deduped per page by absolute URL, but `/x` and
                    # `/x/` normalize to one target — so merge again on the
                    # normalized pair, which is the grain we store.
                    edge_key = (page.normalized_url, key)
                    existing_edge = edges.get(edge_key)
                    if existing_edge is None:
                        edges[edge_key] = InternalLink(
                            from_url=page.normalized_url,
                            to_url=key,
                            anchor=link.anchor,
                            in_content=link.in_content,
                            occurrences=link.occurrences,
                        )
                    else:
                        existing_edge.occurrences += link.occurrences
                        if link.in_content and not existing_edge.in_content:
                            existing_edge.in_content = True
                            existing_edge.anchor = link.anchor or existing_edge.anchor
                        elif not existing_edge.anchor:
                            existing_edge.anchor = link.anchor
                    if key not in queued and len(queued) < page_limit * 4:
                        queued.add(key)
                        queue.append(link.target)

        if queue:
            result.hit_page_limit = True

        # Template links are decided once the whole crawl is in: a target linked
        # from most pages is navigation, whatever element it sits in.
        crawled = set(pages)
        # Prevalence is measured over in-content links only. Counting every
        # placement would mark a page that merely sits in the menu as fully
        # templated, discarding a genuine body reference to it — and a body
        # reference to a menu page is exactly the link worth knowing about.
        all_edges = list(edges.values())
        content_sources: dict[str, set[str]] = {}
        for edge in all_edges:
            if edge.in_content:
                content_sources.setdefault(edge.to_url, set()).add(edge.from_url)

        use_prevalence = len(crawled) >= TEMPLATE_PREVALENCE_MIN_PAGES
        editorial: dict[str, int] = {}
        for edge in all_edges:
            templated_in_content = use_prevalence and (
                len(content_sources.get(edge.to_url, ())) / len(crawled)
                >= TEMPLATE_LINK_PREVALENCE
            )
            edge.is_template = templated_in_content or not edge.in_content
            if not edge.is_template:
                editorial[edge.to_url] = editorial.get(edge.to_url, 0) + 1

        for key, page in pages.items():
            page.inbound_internal_links = inbound.get(key, 0)
            page.inbound_editorial_links = editorial.get(key, 0)
            page.in_sitemap = key in result.sitemap_urls
        result.pages = list(pages.values())
        # Only edges between pages we actually crawled: an edge to a URL we never
        # fetched cannot be reasoned about and would bloat the table.
        result.links = [e for e in all_edges if e.to_url in crawled]

    return result


async def _fetch_page(
    client: httpx.AsyncClient,
    url: str,
    robots: robotparser.RobotFileParser | None,
) -> CrawledPage:
    normalized = normalize_url(url)

    if robots is not None and not robots.can_fetch(USER_AGENT, url):
        return CrawledPage(
            raw_url=url,
            normalized_url=normalized,
            status_code=None,
            redirect_url=None,
            redirect_count=0,
            blocked_by_robots=True,
            fetch_error=None,
            parsed=None,
        )

    current = url
    hops = 0
    first_status: int | None = None
    first_redirect: str | None = None
    # Exact URLs, not normalized ones. `/a` -> `/a/` normalizes to the same
    # string but is an ordinary trailing-slash redirect, not a loop; comparing
    # normalized URLs here reported every such page as unreachable.
    visited: set[str] = {url}

    try:
        while True:
            response = await client.get(current)
            if first_status is None:
                first_status = response.status_code

            if 300 <= response.status_code < 400 and response.headers.get("location"):
                target, _ = urldefrag(urljoin(current, response.headers["location"]))
                if first_redirect is None:
                    first_redirect = target
                hops += 1
                if hops > MAX_REDIRECT_HOPS or target in visited:
                    return CrawledPage(
                        raw_url=url,
                        normalized_url=normalized,
                        status_code=first_status,
                        redirect_url=first_redirect,
                        redirect_count=hops,
                        blocked_by_robots=False,
                        fetch_error="redirect loop or too many hops",
                        parsed=None,
                    )
                visited.add(target)
                current = target
                continue
            break
    except httpx.HTTPError as exc:
        return CrawledPage(
            raw_url=url,
            normalized_url=normalized,
            status_code=first_status,
            redirect_url=first_redirect,
            redirect_count=hops,
            blocked_by_robots=False,
            fetch_error=f"{type(exc).__name__}: {exc}"[:500],
            parsed=None,
        )

    content_type = response.headers.get("content-type", "").lower()
    served_ok = 200 <= response.status_code < 300
    is_page = not (served_ok and content_type and "html" not in content_type)
    parsed = None
    if "html" in content_type and served_ok:
        body = response.text[:MAX_BODY_BYTES]
        try:
            parsed = parse_page(
                url=str(response.url),
                body=body,
                headers={k.lower(): v for k, v in response.headers.items()},
            )
        except Exception as exc:  # noqa: BLE001 — one unparseable page must not end the crawl
            logger.info("could not parse %s: %s", current, exc)

    final_url = str(response.url)
    # A redirect that lands on the same normalized URL is a slash, case or www
    # variant — the two are one page, and the row has to describe the one that
    # serves. Recording the 301 here is precisely the defect that started this:
    # Search Console demand joins on the normalized key and would land on a row
    # marked non-indexable for a page that returns 200.
    cosmetic_redirect = hops > 0 and normalize_url(final_url) == normalized

    return CrawledPage(
        raw_url=final_url if cosmetic_redirect else url,
        normalized_url=normalized,
        # Otherwise the status of the URL itself, so a real redirect to another
        # page stays visible as a redirect.
        status_code=response.status_code if cosmetic_redirect else first_status,
        redirect_url=first_redirect,
        redirect_count=hops,
        blocked_by_robots=False,
        fetch_error=None,
        parsed=parsed,
        is_page=is_page,
    )
