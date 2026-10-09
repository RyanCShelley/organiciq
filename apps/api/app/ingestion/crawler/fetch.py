"""Breadth-first site crawl over httpx.

asyncio rather than Scrapy on purpose: Scrapy runs a Twisted reactor, and a
reactor can only be started once per process. The worker is a long-lived polling
loop that invokes this repeatedly, which fights that model directly. httpx is
already a dependency and already carries the timeout conventions used elsewhere.
"""

from __future__ import annotations

import asyncio
import gzip
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib import robotparser
from urllib.parse import urldefrag, urljoin, urlsplit
from xml.etree import ElementTree

import httpx

from app.core.urls import normalize_path_prefix, normalize_url, url_in_scope
from app.ingestion.crawler.parse import ParsedPage, is_page_url, parse_page

logger = logging.getLogger("organiciq.crawler")


class Throttle:
    """How long to wait before the next request, and when to wait longer.

    A crawl used to run flat out at four requests in flight until it
    finished. ACC Tek answers 429 under that load, so sixty of its pages came
    back refused, were stored as HTTP 429 and surfaced as sixty findings
    about the client's site. Nine clients have a single page in their latest
    crawl for the same reason.

    So the crawl listens. `robots.txt` may declare a `Crawl-delay`, which is
    the site telling us its rate before we have asked for anything. After
    that, every refusal widens the gap, and the gap never shrinks within a
    run — a site that is struggling does not recover because we would like
    it to.
    """

    def __init__(self, base_delay: float = 0.0) -> None:
        #: What the site asked for in robots.txt. The gap never goes below
        #: it, however well the crawl is going — that rate was stated, not
        #: inferred.
        self.floor = max(0.0, base_delay)
        self.delay = self.floor
        self.throttled = False
        self._clean_runs = 0
        self._lock = asyncio.Lock()
        self._next_at = 0.0

    def back_off(self) -> None:
        """Called after the server turns a request away."""
        self.throttled = True
        self._clean_runs = 0
        self.delay = min(
            MAX_THROTTLE_DELAY,
            max(THROTTLED_MIN_DELAY, self.delay * THROTTLE_GROWTH),
        )

    def succeeded(self) -> None:
        """Called after a page comes back without being turned away.

        Quick to back off and slow to relax, so the crawl converges on the
        rate the site tolerates instead of being held at its worst moment
        for the rest of the run.
        """
        if self.delay <= self.floor:
            return
        self._clean_runs += 1
        if self._clean_runs < RECOVERY_AFTER:
            return
        self._clean_runs = 0
        self.delay = max(self.floor, self.delay * THROTTLE_DECAY)

    async def wait(self) -> None:
        """Space requests out, counting from when the last one started.

        Serialised, so concurrent workers queue behind one another rather
        than each sleeping the same interval and then firing together — which
        is the burst the limiter is there to stop.
        """
        if self.delay <= 0:
            return
        async with self._lock:
            now = asyncio.get_running_loop().time()
            if now < self._next_at:
                await asyncio.sleep(self._next_at - now)
                now = asyncio.get_running_loop().time()
            self._next_at = now + self.delay


def retry_after_seconds(value: str | None) -> float | None:
    """`Retry-After`, which is either seconds or an HTTP date.

    Returns None when it is absent or unparseable, so the caller falls back
    to its own backoff rather than treating a malformed header as zero.
    """
    if not value:
        return None
    text = value.strip()
    try:
        return max(0.0, float(text))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())


class RobotsUnreachable(Exception):
    """robots.txt exists in principle but could not be fetched — not the same as absent."""

USER_AGENT = "OrganicIQBot/1.0 (+https://smamarketing.com/organiciq; SEO monitoring)"

DEFAULT_PAGE_LIMIT = 500
#: Ceiling no per-client setting may exceed. A faceted site is effectively
#: infinite, and an unbounded crawl is the failure mode to design against.
MAX_PAGE_LIMIT = 5000
DEFAULT_CONCURRENCY = 4
REQUEST_TIMEOUT = 20.0
#: Statuses that mean "not now" rather than "not here". A page that answers
#: one of these has told us nothing about itself.
RATE_LIMIT_STATUSES = frozenset({429, 503})
#: How many times to come back to a page a server is turning away. Three is
#: enough for a burst limiter to reset and short enough that a site which is
#: genuinely refusing us does not hold the crawl open.
MAX_RATE_LIMIT_RETRIES = 3
#: First wait after a 429 with no Retry-After, doubling each time.
RATE_LIMIT_BASE_DELAY = 2.0
#: A server asking for longer than this is asking us to come back another
#: day, and waiting it out would hold a worker for the whole crawl window.
MAX_RETRY_AFTER = 60.0
#: Once a site rate-limits us, every later request waits at least this long.
#: ACC Tek answered 429 on sixty pages in one run: the crawl kept four
#: requests in flight the whole way down and never slowed.
THROTTLED_MIN_DELAY = 1.0
#: And the delay grows each time it happens again.
THROTTLE_GROWTH = 1.5
MAX_THROTTLE_DELAY = 10.0
#: Consecutive pages that have to come back cleanly before the gap narrows
#: again. A crawl of acctek.com fetched 106 pages with nothing refused and
#: still finished at the 10-second ceiling, because a handful of early
#: blips — all absorbed by the retries — widened the gap and nothing ever
#: brought it back.
RECOVERY_AFTER = 20
#: How much it narrows when they do. Slower to relax than to back off, so
#: the crawl settles near the rate the site actually tolerates rather than
#: oscillating around it.
THROTTLE_DECAY = 0.7
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
#: Tried in order when robots.txt declares no sitemap. Covers Yoast, Rank Math,
#: WordPress core and the plain default.
SITEMAP_CANDIDATES = (
    "/sitemap_index.xml",
    "/sitemap.xml",
    "/wp-sitemap.xml",
    "/sitemap-index.xml",
    "/sitemap1.xml",
    "/sitemaps.xml",
)


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
    #: Scripts and stylesheets this page loads that robots.txt disallows.
    #: Google renders without them and sees a different page than a visitor.
    blocked_resources: int = 0
    #: The server answered 429 or 503 every time we asked. This is us being
    #: turned away, not the page being broken, and the two must not share a
    #: status code: sixty of ACC Tek's pages were reported as "HTTP 429 on
    #: page with demand", which read as sixty faults on the client's site.
    rate_limited: bool = False

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
    #: AI crawlers robots.txt turns away. A page an answer engine cannot
    #: fetch cannot be cited by it, however well it answers the question.
    ai_crawlers_blocked: list[str] = field(default_factory=list)
    #: A sitemap was declared or found but could not be read.
    sitemap_unreadable: bool = False
    #: Where the sitemap was actually found, for the operator.
    sitemap_location: str | None = None
    hit_page_limit: bool = False
    #: Pages the server turned away for the whole crawl. Reported as a
    #: condition of the run, not as findings about the site.
    rate_limited_pages: int = 0
    #: Whether the site asked us to slow down at any point.
    throttled: bool = False
    #: `Crawl-delay` from robots.txt, when the site declares one.
    crawl_delay: float | None = None
    links: list[InternalLink] = field(default_factory=list)


def page_limit_for(client_limit: int | None) -> int:
    requested = client_limit if client_limit else DEFAULT_PAGE_LIMIT
    return max(1, min(int(requested), MAX_PAGE_LIMIT))


def _start_url(domain: str, path_prefix: str | None = None) -> str:
    value = (domain or "").strip()
    if not value:
        raise ValueError("Client has no domain set")
    if "://" not in value:
        value = f"https://{value}"
    parts = urlsplit(value)
    # A scoped client starts at its own folder, not the parent brand's homepage,
    # which would otherwise be the only page reachable before the scope filter
    # rejected everything linked from it.
    path = path_prefix or parts.path or "/"
    return f"{parts.scheme}://{parts.netloc}{path}"


def _same_site(host: str, other: str) -> bool:
    a = (host or "").lower().removeprefix("www.")
    b = (other or "").lower().removeprefix("www.")
    return bool(a) and (a == b or b.endswith(f".{a}"))


#: The agents that read pages for answer engines. Blocking one of these is
#: a decision about whether the brand can appear in that engine's answers,
#: and it is usually made by accident in a plugin's default rule.
AI_CRAWLERS: tuple[str, ...] = (
    "GPTBot",
    "OAI-SearchBot",
    "ChatGPT-User",
    "PerplexityBot",
    "ClaudeBot",
    "Claude-Web",
    "Google-Extended",
    "CCBot",
    "Applebot-Extended",
)


def blocked_ai_crawlers(
    parser: robotparser.RobotFileParser | None, root: str
) -> list[str]:
    if parser is None:
        return []
    return [agent for agent in AI_CRAWLERS if not parser.can_fetch(agent, root)]


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

    # Some servers answer every unknown path with the site's HTML. Parsing that
    # as robots.txt is garbage in, and reports a robots file that is not there.
    content_type = response.headers.get("content-type", "").lower()
    text = response.text
    looks_like_robots = any(
        line.strip().lower().startswith(("user-agent:", "disallow:", "allow:", "sitemap:"))
        for line in text.splitlines()
    )
    if "html" in content_type or not looks_like_robots:
        logger.info("robots.txt at %s is not a robots file; treating it as absent", root)
        return None, []

    parser.parse(text.splitlines())
    sitemaps = [
        line.split(":", 1)[1].strip()
        for line in text.splitlines()
        if line.lower().startswith("sitemap:")
    ]
    return parser, sitemaps


async def _load_sitemap_urls(
    client: httpx.AsyncClient,
    sitemaps: list[str],
    *,
    host: str,
    budget: int,
    scope: str | None = None,
) -> set[str]:
    """URLs listed in the sitemaps, following index files one level down.

    `scope` keeps a path-scoped client to its own folder. It was being read
    from the caller's frame rather than passed, which raised NameError the
    moment a sitemap listed a single page — so every crawl that found a
    sitemap failed, for every client, scoped or not.
    """
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
            body = response.content
            # WordPress and Yoast both serve .xml.gz, and httpx only
            # decompresses what the server declares in Content-Encoding. A
            # gzipped sitemap arrives as bytes that fail to parse, and the
            # site reads as having no sitemap at all.
            if body[:2] == b"\x1f\x8b":
                body = gzip.decompress(body)
            root = ElementTree.fromstring(body)
        except (httpx.HTTPError, ElementTree.ParseError, OSError, EOFError) as exc:
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
                if (
                    parts.hostname
                    and _same_site(host, parts.hostname)
                    and is_page_url(value)
                    and url_in_scope(normalize_url(value), scope)
                ):
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
    sitemap_url: str | None = None,
    path_prefix: str | None = None,
    extra_hosts: tuple[str, ...] = (),
) -> CrawlResult:
    """Crawl a site breadth-first from its root, bounded by `page_limit`.

    `path_prefix` confines the crawl to one folder, for a client whose site is a
    section of a larger domain. Without it the crawl follows the parent brand's
    navigation and reports its pages as this client's.

    `extra_hosts` are subdomains to crawl as well as the apex. The link graph
    only reaches a subdomain the main site links to, and the ones that matter
    often have no inbound link at all — a landing-page host like
    `offer.example.com` is built precisely so campaigns can point at it
    directly. Search Console knows those hosts, so the caller passes them in
    rather than the crawler guessing.
    """
    root = _start_url(domain, path_prefix)
    scope = normalize_path_prefix(path_prefix)
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
        result.ai_crawlers_blocked = blocked_ai_crawlers(robots, root)

        # The site's own stated rate, if it has one. This is the only rate
        # we get before asking for anything, so it is the place to start.
        declared_delay: float | None = None
        if robots is not None:
            try:
                raw = robots.crawl_delay(USER_AGENT)
                declared_delay = float(raw) if raw is not None else None
            except (TypeError, ValueError):
                declared_delay = None
        result.crawl_delay = declared_delay
        throttle = Throttle(declared_delay or 0.0)
        if robots is not None and not robots.can_fetch(USER_AGENT, root):
            result.robots_disallows_site = True

        # A sitemap the client told us about wins: it is the one case where we
        # know better than discovery.
        declared_sitemaps = bool(sitemap_locations) or bool(sitemap_url)
        if sitemap_url:
            sitemap_locations = [sitemap_url, *sitemap_locations]
        result.sitemap_urls = await _load_sitemap_urls(
            client, sitemap_locations, host=host, budget=page_limit * 4, scope=scope
        )

        # Nothing declared, or what was declared yielded nothing: try the usual
        # locations before concluding the site has no sitemap. Plenty of sites
        # have one and simply never mention it in robots.txt.
        #
        # Every host gets asked, not just the apex. A landing-page subdomain
        # usually runs its own CMS with its own sitemap, and the apex's
        # robots.txt says nothing about it.
        roots = [root, *(f"https://{h}/" for h in extra_hosts if h and h != host)]
        if not result.sitemap_urls:
            for base in roots:
                for candidate in SITEMAP_CANDIDATES:
                    found = await _load_sitemap_urls(
                        client,
                        [urljoin(base, candidate)],
                        host=host,
                        budget=page_limit * 4,
                        scope=scope,
                    )
                    if found:
                        result.sitemap_urls |= found
                        result.sitemap_location = (
                            result.sitemap_location or urljoin(base, candidate)
                        )
                        break
        elif sitemap_locations:
            result.sitemap_location = sitemap_locations[0]

        # Declared but yielding nothing is broken, which is a different finding
        # from having none at all.
        result.sitemap_unreadable = declared_sitemaps and not result.sitemap_urls

        # Sitemap URLs are seeded alongside the root: a page nothing links to is
        # exactly the kind of page worth knowing about.
        queue: list[str] = [*roots, *sorted(result.sitemap_urls)]
        queued: set[str] = {normalize_url(base) for base in roots} | set(
            result.sitemap_urls
        )
        inbound: dict[str, int] = {}
        edges: dict[tuple[str, str], InternalLink] = {}
        pages: dict[str, CrawledPage] = {}
        semaphore = asyncio.Semaphore(concurrency)

        async def fetch_one(url: str) -> CrawledPage:
            async with semaphore:
                return await _fetch_page(
                    client, url, robots if respect_robots else None, throttle
                )

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
                    if (
                        target != page.normalized_url
                        and target not in queued
                        and url_in_scope(target, scope)
                    ):
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
                    if (
                        key not in queued
                        and len(queued) < page_limit * 4
                        and url_in_scope(key, scope)
                    ):
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
        # A condition of the run, reported once, rather than one finding per
        # page about a site that is answering us perfectly well when asked
        # more slowly.
        result.rate_limited_pages = sum(1 for p in result.pages if p.rate_limited)
        result.throttled = throttle.throttled
        if result.rate_limited_pages:
            logger.warning(
                "%s rate limited the crawl: %d pages turned away for good, "
                "final delay %.2fs between requests",
                host, result.rate_limited_pages, throttle.delay,
            )
        elif result.throttled:
            # Backed off, absorbed it, finished clean. Worth a line for
            # anyone reading why a crawl took longer than usual, but it is
            # not a warning: "rate limited the crawl: 0 pages turned away"
            # is a sentence that stops a reader for no reason.
            logger.info(
                "%s asked the crawl to slow down; every page came back, "
                "settled at %.2fs between requests",
                host, throttle.delay,
            )
        # Only edges between pages we actually crawled: an edge to a URL we never
        # fetched cannot be reasoned about and would bloat the table.
        result.links = [e for e in all_edges if e.to_url in crawled]

    return result


def _blocked_resource_count(
    parsed: ParsedPage | None, robots: robotparser.RobotFileParser | None
) -> int:
    """Scripts and stylesheets this page loads that robots.txt forbids.

    Rendering is what Google indexes now, so a disallowed stylesheet or
    bundle means it renders the page without them and judges what is left.
    Nothing in the page's own status code says this is happening.

    Only resources on hosts this robots.txt governs are counted — a CDN has
    its own rules and we have not read them, and guessing would turn every
    site using one into a finding.
    """
    if parsed is None or robots is None:
        return 0
    root = urlsplit(getattr(robots, "url", "") or "")
    blocked = 0
    for resource in parsed.resource_urls:
        parts = urlsplit(resource)
        if parts.netloc and root.netloc and parts.netloc != root.netloc:
            continue
        if not robots.can_fetch(USER_AGENT, resource):
            blocked += 1
    return blocked


async def _fetch_page(
    client: httpx.AsyncClient,
    url: str,
    robots: robotparser.RobotFileParser | None,
    throttle: Throttle | None = None,
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

    attempts = 0
    try:
        while True:
            if throttle is not None:
                await throttle.wait()
            response = await client.get(current)

            # "Not now" is not "not here". Wait as long as the server asks,
            # or back off on our own, and come back to the same URL — and
            # slow every later request in this crawl, because a site that
            # refused once at this rate will refuse again.
            if response.status_code in RATE_LIMIT_STATUSES:
                if throttle is not None:
                    throttle.back_off()
                if attempts < MAX_RATE_LIMIT_RETRIES:
                    asked = retry_after_seconds(response.headers.get("retry-after"))
                    if asked is not None and asked > MAX_RETRY_AFTER:
                        # Being told to come back in an hour is a refusal.
                        # Holding a worker open for it would stall the crawl.
                        return CrawledPage(
                            raw_url=url,
                            normalized_url=normalized,
                            status_code=None,
                            redirect_url=None,
                            redirect_count=0,
                            blocked_by_robots=False,
                            fetch_error=(
                                f"rate limited; asked to wait {int(asked)}s"
                            ),
                            parsed=None,
                            rate_limited=True,
                        )
                    wait = (
                        asked
                        if asked is not None
                        else RATE_LIMIT_BASE_DELAY * (2**attempts)
                    )
                    attempts += 1
                    await asyncio.sleep(wait)
                    continue
                # Out of retries. The status is deliberately not kept: stored
                # as 429 it becomes "HTTP 429 on page with demand", which
                # reads as a fault on the client's site rather than as our
                # crawler being turned away.
                logger.info("rate limited after %d attempts: %s", attempts, current)
                return CrawledPage(
                    raw_url=url,
                    normalized_url=normalized,
                    status_code=None,
                    redirect_url=None,
                    redirect_count=0,
                    blocked_by_robots=False,
                    fetch_error=f"rate limited (HTTP {response.status_code})",
                    parsed=None,
                    rate_limited=True,
                )

            if throttle is not None:
                throttle.succeeded()
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
        blocked_resources=_blocked_resource_count(parsed, robots),
    )
