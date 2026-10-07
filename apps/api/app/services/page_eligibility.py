"""Page classification and Growth Action eligibility heuristics."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class PageType(str, Enum):
    COMMERCIAL = "commercial"
    CONVERSION = "conversion"
    CONSIDERATION = "consideration"
    INFORMATIONAL = "informational"
    UTILITY = "utility"


UTILITY_PATH_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"/privacy(?:-policy)?(?:/|$)", "privacy_page"),
    (r"/terms(?:-of-(?:service|use))?(?:/|$)", "terms_page"),
    (r"/opt-out(?:-preferences)?(?:/|$)", "opt_out_preferences"),
    (r"/preferences(?:/|$)", "preferences_page"),
    (r"/cookie(?:-policy)?(?:/|$)", "cookie_policy"),
    (r"/login(?:/|$)", "login_page"),
    (r"/sign-in(?:/|$)", "sign_in_page"),
    (r"/account(?:/|$)", "account_page"),
    (r"/wp-admin(?:/|$)", "wp_admin"),
    (r"/wp-login(?:/|$)", "wp_login"),
    (r"/search(?:/|$|\?)", "internal_search"),
    (r"/feed(?:/|$)", "feed"),
    (r"/rss(?:/|$)", "rss"),
    (r"/thank(?:-you)?(?:/|$)", "thank_you_page"),
    (r"/thanks(?:/|$)", "thanks_page"),
    (r"/confirmation(?:/|$)", "confirmation_page"),
)

PAGINATION_PATTERN = re.compile(r"/page/\d+(?:/|$)")


@dataclass(frozen=True)
class PageClassification:
    normalized_url: str
    page_type: PageType
    eligible_for_growth_action: bool
    strategic_priority: int
    commercial_priority: int
    priority_topic: str | None = None
    excluded_reason: str | None = None
    classification_source: str = "heuristic"

    def as_evidence(self) -> dict[str, str | int | bool | None]:
        return {
            "page_type": self.page_type.value,
            "eligible_for_growth_action": self.eligible_for_growth_action,
            "strategic_priority": self.strategic_priority,
            "commercial_priority": self.commercial_priority,
            "priority_topic": self.priority_topic,
            "excluded_reason": self.excluded_reason,
            "classification_source": self.classification_source,
        }


def _commercial_signals(path: str) -> bool:
    return any(
        token in path
        for token in (
            "/services",
            "/service/",
            "/sem",
            "/seo",
            "/pricing",
            "/solutions",
            "/industries",
        )
    )


def _conversion_signals(path: str) -> bool:
    return any(
        token in path
        for token in (
            "/contact",
            "/get-started",
            "/demo",
            "/quote",
            "/consultation",
            "/schedule",
        )
    )


def classify_page_url(
    normalized_url: str, declared: frozenset[str] | None = None
) -> PageClassification:
    """What a page is for.

    `declared` is the client's own list of conversion pages. It wins over
    every guess below, because the guesses are URL fragments written for
    somebody else's site: a client whose offer lives at /get-a-leak-check
    was never going to match /contact, and a /contact page that is a staff
    directory matched anyway.
    """
    if declared and normalized_url in declared:
        return PageClassification(
            normalized_url=normalized_url,
            page_type=PageType.CONVERSION,
            eligible_for_growth_action=True,
            commercial_priority=5,
            strategic_priority=5,
            excluded_reason=None,
        )

    path = normalized_url.lower().rstrip("/")

    for pattern, reason in UTILITY_PATH_PATTERNS:
        if re.search(pattern, path):
            return PageClassification(
                normalized_url=normalized_url,
                page_type=PageType.UTILITY,
                eligible_for_growth_action=False,
                strategic_priority=1,
                commercial_priority=1,
                excluded_reason=reason,
            )

    if PAGINATION_PATTERN.search(path):
        return PageClassification(
            normalized_url=normalized_url,
            page_type=PageType.UTILITY,
            eligible_for_growth_action=False,
            strategic_priority=1,
            commercial_priority=1,
            excluded_reason="pagination",
        )

    if _conversion_signals(path):
        return PageClassification(
            normalized_url=normalized_url,
            page_type=PageType.CONVERSION,
            eligible_for_growth_action=True,
            strategic_priority=5,
            commercial_priority=5,
        )

    if _commercial_signals(path):
        return PageClassification(
            normalized_url=normalized_url,
            page_type=PageType.COMMERCIAL,
            eligible_for_growth_action=True,
            strategic_priority=5,
            commercial_priority=5,
        )

    if "/blog/" in path or path.endswith("/blog"):
        topic = _extract_topic_slug(path, prefix="/blog/")
        return PageClassification(
            normalized_url=normalized_url,
            page_type=PageType.INFORMATIONAL,
            eligible_for_growth_action=True,
            strategic_priority=2,
            commercial_priority=2,
            priority_topic=topic,
        )

    return PageClassification(
        normalized_url=normalized_url,
        page_type=PageType.CONSIDERATION,
        eligible_for_growth_action=True,
        strategic_priority=3,
        commercial_priority=3,
    )


def _extract_topic_slug(path: str, prefix: str) -> str | None:
    """The category a post sits in, or None on a flat blog.

    A topic only exists where the URL has one: `/blog/seo/some-post` is a post
    about SEO, but `/blog/some-post` is just a post, and its slug is not a
    subject it shares with anything.

    This returned the slug either way, so on a flat blog every post got a topic
    of its own. Two things quietly did nothing as a result: findings grouped by
    `topic:<x>` grouped one page each, and topic lead rates averaged a single
    page, which is the page rate with extra steps. Neither looked broken.
    """
    if prefix not in path:
        return None
    segments = [part for part in path.split(prefix, 1)[1].split("/") if part]
    # One segment is the post itself; a category needs something beneath it.
    if len(segments) < 2:
        return None
    return segments[0].replace("-", " ")


def classify_pages(
    normalized_urls: list[str], declared: frozenset[str] | None = None
) -> dict[str, PageClassification]:
    return {url: classify_page_url(url, declared) for url in normalized_urls}
