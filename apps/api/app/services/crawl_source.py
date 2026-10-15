"""Which crawl the engine reads.
"""

from __future__ import annotations

from app.core.settings import get_settings
from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, CRAWL_SOURCE_SE_RANKING


def active_crawl_source() -> str:
    """
    The crawl the engine reads. Both keep writing.

    Settable so a bad crawl can be backed out by flipping one variable rather
    than deploying, and so the two can be compared on the same data.
    """
    configured = (get_settings().crawl_facts_source or "").strip()
    return configured if configured in {CRAWL_SOURCE_FIRST_PARTY, CRAWL_SOURCE_SE_RANKING} else CRAWL_SOURCE_FIRST_PARTY
