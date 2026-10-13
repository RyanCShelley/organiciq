"""Turn a fetched HTML document into the facts the Decision Engine reads.

Deliberately parses the HTML as served, without executing JavaScript. Anything
a page only produces after JS is genuinely absent as far as AI answer engines
are concerned — they fetch HTML and do not render — so a page whose schema or
canonical is client-side should read as missing here. That is a finding, not a
crawl failure.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from collections.abc import Iterable
from typing import Any
from urllib.parse import urldefrag, urljoin, urlsplit

from lxml import html as lxml_html

from app.core.urls import normalize_url

#: Elements whose text is markup or chrome, never page content.
#:
#: nav/header/footer/menu match the exclusions in the team's Screaming Frog
#: content-audit config. Site-wide furniture appears on every page, so counting
#: it inflates every word count by the same amount and makes a thin page look
#: substantial — which is exactly the judgement the low-content threshold makes.
_NON_CONTENT_TAGS = (
    "script",
    "style",
    "noscript",
    "template",
    "svg",
    "nav",
    "header",
    "footer",
    "menu",
)

#: Extensions that are never a page. Crawling them wastes budget and, worse,
#: they land in the page set as indexable URLs carrying no title and no schema —
#: an image reported as a content defect.
NON_PAGE_EXTENSIONS = frozenset(
    """
    jpg jpeg png gif webp avif svg ico bmp tif tiff
    pdf doc docx xls xlsx ppt pptx csv rtf txt
    zip gz tar rar 7z dmg exe pkg
    mp3 mp4 m4a m4v mov avi wmv webm ogg wav
    css js json xml rss atom kml woff woff2 ttf eot
    """.split()
)


def is_page_url(url: str) -> bool:
    """Whether a URL looks like an HTML page rather than an asset or feed."""
    path = urlsplit(url).path.rsplit("/", 1)[-1]
    if "." not in path:
        return True
    return path.rsplit(".", 1)[-1].lower() not in NON_PAGE_EXTENSIONS


_WORD = re.compile(r"[\w'’-]+", re.UNICODE)
_NOINDEX = re.compile(r"\bnone\b|\bnoindex\b", re.IGNORECASE)
#: What a page says when it is an error dressed as a success. Deliberately
#: narrow: "not found" inside a sentence is ordinary prose, so this only
#: matches a title or H1 that is *about* being missing.
_NOT_FOUND = re.compile(
    r"^\s*(404|error\s*404)\b"
    r"|\b(page|file|content)\s+not\s+found\b"
    r"|^\s*not\s+found\s*$"
    r"|\bdoes\s*n[o']?t\s+exist\b"
    r"|\bno\s+longer\s+(available|exists)\b",
    re.IGNORECASE,
)
#: Button and link text that asks for the next step.
_CTA_TEXT = re.compile(
    r"\b(contact|call|book|schedule|request|get\s+(a\s+)?(quote|started|in\s+touch))"
    r"|\b(free\s+(quote|consultation|trial|demo|audit))"
    r"|\b(sign\s*up|subscribe|apply|enquire|inquire|buy|order|add\s+to\s+cart)\b",
    re.IGNORECASE,
)
_NOFOLLOW = re.compile(r"\bnone\b|\bnofollow\b", re.IGNORECASE)


#: Ancestors that make a link site furniture rather than editorial.
_FURNITURE_ANCESTORS = frozenset({"nav", "header", "footer", "menu", "aside"})
#: Anchor text longer than this is a paragraph, not an anchor.
_MAX_ANCHOR = 300


@dataclass
class PageLink:
    """One internal link, with what a cluster analysis needs to use it."""

    target: str
    anchor: str
    #: Outside nav/header/footer/menu/aside. The primary template signal, though
    #: it only works on sites that use those elements — see the prevalence pass
    #: in the crawler for sites whose navigation is plain divs.
    in_content: bool
    occurrences: int = 1


@dataclass
class SchemaBlock:
    syntax: str
    schema_type: str | None
    raw: Any | None
    raw_text: str | None
    parse_error: str | None


@dataclass
class PageSection:
    """A heading and the first paragraph beneath it.

    The pair is the unit, not the heading: the answer-first test is about
    what comes immediately after a heading, and a heading on its own says
    nothing about whether the page answers the question it poses.
    """

    level: int
    heading: str
    first_paragraph: str
    #: Whether the passage under this heading holds something an engine can
    #: lift whole. V-5 asks for a table, a bullet summary or a stat block
    #: under the heading that matches the query — a paragraph of prose is
    #: what it is prescribing a way out of, so "there is text here" does not
    #: answer it.
    has_table: bool = False
    has_list: bool = False
    has_stat: bool = False

    @property
    def extractable(self) -> bool:
        return self.has_table or self.has_list or self.has_stat


@dataclass
class ParsedPage:
    title: str
    description: str
    h1: str
    word_count: int
    canonical_url: str | None
    #: The canonical exactly as served, before normalization flattens it.
    canonical_raw: str | None
    robots: str | None
    meta_noindex: bool
    meta_nofollow: bool
    internal_links: list[PageLink] = field(default_factory=list)
    schema_blocks: list[SchemaBlock] = field(default_factory=list)
    #: Scripts and stylesheets the page loads, absolute. Rendering depends on
    #: these, so one of them being disallowed in robots.txt means Google sees
    #: a different page than a visitor does.
    resource_urls: list[str] = field(default_factory=list)
    #: Anything a visitor could convert through: a form, a phone number, an
    #: email link, or a button that asks for the next step.
    conversion_elements: int = 0
    #: The page says it is a 404 while returning 200.
    says_not_found: bool = False
    #: Every heading with the first paragraph under it, in document order.
    #: 3a asks whether the passage that answers a query answers it first,
    #: which cannot be judged from a title and a word count.
    sections: list["PageSection"] = field(default_factory=list)
    #: Questions a visitor can see as questions: FAQPage schema entries and
    #: headings that read as questions. 3b asks what is not covered.
    faq_questions: list[str] = field(default_factory=list)
    #: When the page says it was last updated, and which of the sources said
    #: so. None where none of them carried a date — "unknown", not "never".
    content_updated_on: date | None = None
    content_updated_source: str | None = None


#: A heading that reads as a question. Matches the engine's `is_question`
#: so a visible FAQ heading and a Search Console query are judged the same
#: way; defined here because the crawler has no access to that module.
_QUESTION_OPENERS = frozenset(
    "what how why when where which who can does do is are should".split()
)


def _looks_like_a_question(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if stripped.endswith("?"):
        return True
    first = re.split(r"[^a-z']+", stripped.lower(), maxsplit=1)[0]
    return first in _QUESTION_OPENERS


#: A quantity somebody could quote: a percent, a measurement, a count with a
#: unit, or a figure with a separator. A bare four-digit year is excluded —
#: every copyright footer and blog date would otherwise read as a statistic.
_STAT = re.compile(
    r"(?<!\d)(?:"
    r"\d{1,3}(?:,\d{3})+"          # 1,200
    r"|\d+(?:\.\d+)?\s?%"          # 40%, 12.5 %
    r"|[$£€]\s?\d+(?:\.\d+)?"      # $40
    r"|\d+(?:\.\d+)?\s?"
    r"(?:x|×|mm|cm|m|km|in|ft|kg|lb|lbs|g|oz|hrs?|hours?|mins?|minutes?|days?|"
    r"weeks?|months?|years?|psi|gpa|mpa|ksi|°[cf])\b"
    r")",
    re.IGNORECASE,
)


def _looks_like_a_stat(text: str) -> bool:
    return bool(_STAT.search(text or ""))


def extract_sections(doc: Any) -> list[PageSection]:
    """Every heading with the first paragraph under it, in document order.

    Walks the document rather than querying each heading, because "the
    paragraph under this heading" is a statement about order, not about
    nesting: on most pages the `<p>` is a sibling of the `<h2>`, not a
    child of anything that contains both.
    """
    sections: list[PageSection] = []
    pending: PageSection | None = None
    for node in doc.iter():
        tag = str(getattr(node, "tag", "") or "").lower()
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            if pending is not None:
                sections.append(pending)
            heading = " ".join((node.text_content() or "").split())
            pending = PageSection(level=int(tag[1]), heading=heading, first_paragraph="")
        elif pending is None:
            continue
        elif tag == "table":
            pending.has_table = True
        elif tag in {"ul", "ol", "dl"}:
            pending.has_list = True
        elif tag == "p":
            text = " ".join((node.text_content() or "").split())
            if text and not pending.first_paragraph:
                pending.first_paragraph = text
            if text and _looks_like_a_stat(text):
                pending.has_stat = True
    if pending is not None:
        sections.append(pending)
    return [s for s in sections if s.heading]


def extract_faq_questions(doc: Any, schema_blocks: list[SchemaBlock]) -> list[str]:
    """Questions the page already answers, as a visitor would see them.

    Two sources, because either alone is wrong. FAQPage schema is what
    engines read and is often absent on pages that plainly have an FAQ;
    a question-shaped heading is what a visitor reads and is often present
    without any markup at all.
    """
    found: list[str] = []

    for block in schema_blocks:
        raw = block.raw
        if not isinstance(raw, (dict, list)):
            continue

        def walk(node: Any) -> None:
            if isinstance(node, list):
                for item in node:
                    walk(item)
                return
            if not isinstance(node, dict):
                return
            declared = node.get("@type")
            types = declared if isinstance(declared, list) else [declared]
            if any(isinstance(t, str) and t.endswith("Question") for t in types):
                name = node.get("name") or node.get("headline")
                if isinstance(name, str) and name.strip():
                    found.append(" ".join(name.split()))
            for key in ("@graph", "mainEntity", "itemListElement", "acceptedAnswer"):
                if key in node:
                    walk(node[key])

        walk(raw)

    for node in doc.xpath("//h2|//h3|//h4|//summary|//dt"):
        text = " ".join((node.text_content() or "").split())
        if text and _looks_like_a_question(text):
            found.append(text)

    seen: set[str] = set()
    unique: list[str] = []
    for question in found:
        key = question.lower()
        if key not in seen:
            seen.add(key)
            unique.append(question)
    return unique


def _same_site(host: str, other: str) -> bool:
    a = host.lower().removeprefix("www.")
    b = other.lower().removeprefix("www.")
    return a == b or b.endswith(f".{a}")


def _schema_types(node: Any) -> list[str]:
    """Every @type in a JSON-LD block, including nested @graph entries."""
    found: list[str] = []
    if isinstance(node, dict):
        raw_type = node.get("@type")
        if isinstance(raw_type, str):
            found.append(raw_type)
        elif isinstance(raw_type, list):
            found.extend(str(t) for t in raw_type if isinstance(t, str))
        for key in ("@graph", "mainEntity", "itemListElement"):
            if key in node:
                found.extend(_schema_types(node[key]))
    elif isinstance(node, list):
        for item in node:
            found.extend(_schema_types(item))
    return found


def bare_type(value: str) -> str:
    """`https://schema.org/LocalBusiness` and `LocalBusiness` are the same type."""
    text = str(value).strip()
    if "/" in text:
        text = text.rstrip("/").rsplit("/", 1)[-1]
    if ":" in text and not text.startswith("http"):
        text = text.rsplit(":", 1)[-1]
    return text[:128]


def extract_json_ld(doc: Any) -> list[SchemaBlock]:
    blocks: list[SchemaBlock] = []
    for node in doc.xpath('//script[@type="application/ld+json"]'):
        text = (node.text_content() or "").strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            # Present but unparseable is the same as absent to any consumer, and
            # is the one schema failure nothing else in the stack reports.
            blocks.append(
                SchemaBlock(
                    syntax="json_ld",
                    schema_type=None,
                    raw=None,
                    raw_text=text[:20000],
                    parse_error=f"invalid JSON: {exc.msg} (line {exc.lineno}, col {exc.colno})",
                )
            )
            continue

        types = _schema_types(payload)
        if not types:
            # Parsed fine, says nothing. Recorded with no type so it counts as a
            # block without contributing a descriptive type.
            blocks.append(
                SchemaBlock(
                    syntax="json_ld",
                    schema_type=None,
                    raw=payload,
                    raw_text=None,
                    parse_error=None,
                )
            )
            continue
        for schema_type in dict.fromkeys(types):
            blocks.append(
                SchemaBlock(
                    syntax="json_ld",
                    schema_type=bare_type(schema_type),
                    raw=payload,
                    raw_text=None,
                    parse_error=None,
                )
            )
    return blocks


def extract_microdata(doc: Any) -> list[SchemaBlock]:
    """Top-level itemscope elements. Enough to answer "is there any schema here"."""
    blocks: list[SchemaBlock] = []
    for node in doc.xpath("//*[@itemscope][@itemtype]"):
        itemtype = (node.get("itemtype") or "").strip()
        if not itemtype:
            continue
        blocks.append(
            SchemaBlock(
                syntax="microdata",
                schema_type=bare_type(itemtype.split()[0]),
                raw={"itemtype": itemtype},
                raw_text=None,
                parse_error=None,
            )
        )
    return blocks


def extract_rdfa(doc: Any) -> list[SchemaBlock]:
    blocks: list[SchemaBlock] = []
    for node in doc.xpath("//*[@typeof]"):
        typeof = (node.get("typeof") or "").strip()
        if not typeof:
            continue
        blocks.append(
            SchemaBlock(
                syntax="rdfa",
                schema_type=bare_type(typeof.split()[0]),
                raw={"typeof": typeof},
                raw_text=None,
                parse_error=None,
            )
        )
    return blocks


#: Where a page says when it was last touched, best first.
#:
#: Schema is the publisher's own statement and is what Google reads. The
#: OpenGraph meta is the same claim from the same plugins, and is present on
#: sites whose schema carries no date at all — ACCTek has a date in neither
#: its JSON-LD nor anywhere else we looked, and serves
#: `article:modified_time` on every page.
#:
#: The HTTP `Last-Modified` header is deliberately absent. ACCTek's
#: /managed-it-services-syracuse-ny returns 11 October while its own
#: `article:modified_time` says 16 May: the header describes when the server
#: last rendered the page, not when anybody changed it, and reading it would
#: report an untouched site as entirely fresh.
_DATE_META = ("article:modified_time", "og:updated_time", "article:published_time")

_SCHEMA_DATE_KEYS = ("dateModified", "datePublished")


def _as_date(value: object) -> date | None:
    """A date out of whatever the page wrote.

    ISO 8601 with an offset, with a `Z`, or a bare date — all three are in
    the wild, often on the same site.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def newest_schema_date(raws: "Iterable[object]") -> date | None:
    """The newest `dateModified`, else the newest `datePublished`.

    Newest rather than first: a page carrying both an Article and a
    BreadcrumbList gets one block per type, and a WordPress page often
    repeats the site's own dates alongside the post's. SMA's homepage
    carries 2025-03-18 and 2026-09-07 in one graph, and taking the first
    would report the site as eighteen months stale.

    Takes the raw payloads rather than blocks, so the backfill can read the
    same answer out of `facts_crawl_page_schema` without re-crawling.
    """
    found: dict[str, list[date]] = {key: [] for key in _SCHEMA_DATE_KEYS}

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in found:
                    parsed = _as_date(value)
                    if parsed is not None:
                        found[key].append(parsed)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for raw in raws:
        if raw is not None:
            walk(raw)
    for key in _SCHEMA_DATE_KEYS:
        if found[key]:
            return max(found[key])
    return None


def _schema_date(blocks: list["SchemaBlock"]) -> date | None:
    return newest_schema_date(block.raw for block in blocks)


def _meta_date(doc) -> date | None:
    """`article:modified_time` and its neighbours, by @property.

    `parse_page` queried meta by `@name` only, so every OpenGraph and
    article tag on every page we have ever crawled was invisible.
    """
    for key in _DATE_META:
        for node in doc.xpath(f'//meta[@property="{key}"]'):
            parsed = _as_date(node.get("content"))
            if parsed is not None:
                return parsed
    return None


def parse_page(*, url: str, body: str, headers: dict[str, str] | None = None) -> ParsedPage:
    doc = lxml_html.fromstring(body)

    title = " ".join((doc.findtext(".//title") or "").split())
    description = ""
    for node in doc.xpath('//meta[translate(@name,"DESCRIPTION","description")="description"]'):
        description = " ".join((node.get("content") or "").split())
        if description:
            break

    h1 = ""
    for node in doc.xpath("//h1"):
        h1 = " ".join((node.text_content() or "").split())
        if h1:
            break

    # Structured data first: JSON-LD lives in <script>, which the word-count
    # strip below removes from the tree.
    schema_blocks = extract_json_ld(doc) + extract_microdata(doc) + extract_rdfa(doc)

    # Headings and their opening paragraphs, read before the strip below
    # removes script and style text from the tree.
    sections = extract_sections(doc)
    faq_questions = extract_faq_questions(doc, schema_blocks)

    content_updated_on = _schema_date(schema_blocks)
    content_updated_source = "schema" if content_updated_on else None
    if content_updated_on is None:
        content_updated_on = _meta_date(doc)
        content_updated_source = "meta" if content_updated_on else None

    canonical_raw = None
    for node in doc.xpath('//link[translate(@rel,"CANONICAL","canonical")="canonical"]'):
        href = (node.get("href") or "").strip()
        if href:
            canonical_raw = urljoin(url, href)
            break

    robots_values: list[str] = []
    for node in doc.xpath('//meta[translate(@name,"ROBTS","robots")="robots"]'):
        content = (node.get("content") or "").strip()
        if content:
            robots_values.append(content)
    # X-Robots-Tag carries the same directives and is just as binding.
    header_robots = (headers or {}).get("x-robots-tag", "").strip()
    if header_robots:
        robots_values.append(header_robots)
    robots = ", ".join(robots_values) or None

    host = urlsplit(url).hostname or ""
    internal: dict[str, PageLink] = {}
    for node in doc.xpath("//a[@href]"):
        href = (node.get("href") or "").strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        absolute, _ = urldefrag(urljoin(url, href))
        parts = urlsplit(absolute)
        if parts.scheme not in {"http", "https"}:
            continue
        if not parts.hostname or not _same_site(host, parts.hostname):
            continue
        if not is_page_url(absolute):
            continue

        in_content = not any(
            (ancestor.tag if isinstance(ancestor.tag, str) else "") in _FURNITURE_ANCESTORS
            for ancestor in node.iterancestors()
        )
        anchor = " ".join((node.text_content() or "").split())[:_MAX_ANCHOR]

        existing = internal.get(absolute)
        if existing is None:
            internal[absolute] = PageLink(
                target=absolute, anchor=anchor, in_content=in_content
            )
        else:
            existing.occurrences += 1
            # One editorial placement is enough to make the link editorial, and
            # a real anchor beats an empty one from an image link.
            if in_content and not existing.in_content:
                existing.in_content = True
                existing.anchor = anchor or existing.anchor
            elif not existing.anchor:
                existing.anchor = anchor

    # Resources and conversion elements, both read before the strip below
    # removes <script> and the navigation that usually holds the phone number.
    resources: list[str] = []
    for node in doc.xpath("//script[@src]"):
        src = (node.get("src") or "").strip()
        if src:
            resources.append(urljoin(url, src))
    for node in doc.xpath('//link[contains(translate(@rel,"STYLESHEE","styleshee"),"stylesheet")]'):
        href = (node.get("href") or "").strip()
        if href:
            resources.append(urljoin(url, href))

    conversion_elements = len(doc.xpath("//form"))
    conversion_elements += len(
        doc.xpath('//a[starts-with(@href,"tel:") or starts-with(@href,"mailto:")]')
    )
    for node in doc.xpath("//a | //button | //input[@type='submit']"):
        text = " ".join(
            (node.get("value") or node.text_content() or "").split()
        )
        if text and _CTA_TEXT.search(text):
            conversion_elements += 1

    # Destructive, so it runs last: removing these elements is what previously
    # ate the JSON-LD blocks, and then the navigation links.
    for tag in _NON_CONTENT_TAGS:
        for node in doc.xpath(f"//{tag}"):
            if node.getparent() is not None:
                node.getparent().remove(node)
    body = doc.find("body")
    word_count = len(_WORD.findall((body if body is not None else doc).text_content() or ""))

    return ParsedPage(
        title=title,
        description=description,
        h1=h1,
        word_count=word_count,
        canonical_url=normalize_url(canonical_raw) if canonical_raw else None,
        canonical_raw=canonical_raw,
        robots=robots,
        meta_noindex=bool(robots and _NOINDEX.search(robots)),
        meta_nofollow=bool(robots and _NOFOLLOW.search(robots)),
        internal_links=list(internal.values()),
        schema_blocks=schema_blocks,
        sections=sections,
        faq_questions=faq_questions,
        resource_urls=sorted(set(resources)),
        conversion_elements=conversion_elements,
        says_not_found=bool(_NOT_FOUND.search(title) or _NOT_FOUND.search(h1)),
        content_updated_on=content_updated_on,
        content_updated_source=content_updated_source,
    )
