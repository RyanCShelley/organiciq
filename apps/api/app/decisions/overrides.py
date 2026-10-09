"""What a person changed, and why.

The engine is arithmetic and the arithmetic is sometimes beside the point.
Boys Electrical's traffic branch failed on a careers page — 52 sessions, no
conversions — which is correct and useless, because nobody is being paid to
recruit electricians this quarter.

Two different objections, so two mechanisms:

* a page the engine should not look at, which is a standing fact about the
  client, and
* a constraint somebody disagrees with, which is a decision about one month.

Both are recorded rather than configured away. The record carries them, so a
plan reads back as what the engine said plus what a person changed — and a
reader in six months can tell the two apart.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Exclusion:
    url_pattern: str
    reason: str


def _path(url_or_pattern: str) -> str:
    """The path, whether given a full URL or a path.

    Patterns are written as paths — "/careers*" is what somebody types — and
    the pages being tested are absolute URLs. Comparing the two without this
    matched nothing at all.
    """
    text = (url_or_pattern or "").strip().lower()
    if not text:
        return ""
    if "://" in text:
        text = urlsplit(text).path or "/"
    if not text.startswith("/"):
        text = "/" + text
    return text.rstrip("/") or "/"


def matches(url: str, pattern: str) -> bool:
    """Whether a page is excluded.

    A pattern ending in `*` excludes a section: `/careers*` takes the careers
    index and everything under it, which is what somebody means when they say
    "we are not working on careers".
    """
    page = _path(url)
    rule = (pattern or "").strip().lower()
    if not page or not rule:
        return False
    if rule.endswith("*"):
        prefix = _path(rule[:-1])
        # A prefix must end at a path boundary. `/car*` should not take
        # `/carbon-fiber`, which is the kind of quiet over-match nobody
        # notices until a real page stops being reported.
        return page == prefix or page.startswith(prefix + "/")
    return page == _path(rule)


def is_excluded(url: str, exclusions: list[Exclusion]) -> Exclusion | None:
    for exclusion in exclusions:
        if matches(url, exclusion.url_pattern):
            return exclusion
    return None


def filter_pages(urls: list[str], exclusions: list[Exclusion]) -> list[str]:
    return [url for url in urls if is_excluded(url, exclusions) is None]
