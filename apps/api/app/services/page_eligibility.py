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


def classify_page_url(normalized_url: str) -> PageClassification:
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
    if prefix not in path:
        return None
    slug = path.split(prefix, 1)[1].split("/")[0]
    return slug.replace("-", " ") if slug else None


def classify_pages(normalized_urls: list[str]) -> dict[str, PageClassification]:
    return {url: classify_page_url(url) for url in normalized_urls}
