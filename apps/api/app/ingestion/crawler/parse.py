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
from typing import Any
from urllib.parse import urldefrag, urljoin, urlsplit

from lxml import html as lxml_html

from app.core.urls import normalize_url

#: Elements whose text is markup or chrome, never page content.
_NON_CONTENT_TAGS = ("script", "style", "noscript", "template", "svg")

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
_NOFOLLOW = re.compile(r"\bnone\b|\bnofollow\b", re.IGNORECASE)


@dataclass
class SchemaBlock:
    syntax: str
    schema_type: str | None
    raw: Any | None
    raw_text: str | None
    parse_error: str | None


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
    internal_links: list[str] = field(default_factory=list)
    schema_blocks: list[SchemaBlock] = field(default_factory=list)


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


def _bare_type(value: str) -> str:
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
            blocks.append(
                SchemaBlock(
                    syntax="json_ld",
                    schema_type=None,
                    raw=payload,
                    raw_text=None,
                    parse_error="no @type",
                )
            )
            continue
        for schema_type in dict.fromkeys(types):
            blocks.append(
                SchemaBlock(
                    syntax="json_ld",
                    schema_type=_bare_type(schema_type),
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
                schema_type=_bare_type(itemtype.split()[0]),
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
                schema_type=_bare_type(typeof.split()[0]),
                raw={"typeof": typeof},
                raw_text=None,
                parse_error=None,
            )
        )
    return blocks


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

    # Word count over visible body content: <head> carries the title and meta,
    # which are measured separately and would otherwise be counted twice.
    for tag in _NON_CONTENT_TAGS:
        for node in doc.xpath(f"//{tag}"):
            if node.getparent() is not None:
                node.getparent().remove(node)
    body = doc.find("body")
    word_count = len(_WORD.findall((body if body is not None else doc).text_content() or ""))

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
    internal: list[str] = []
    seen: set[str] = set()
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
        if absolute not in seen:
            seen.add(absolute)
            internal.append(absolute)

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
        internal_links=internal,
        schema_blocks=schema_blocks,
    )
