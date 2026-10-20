"""Which crawl the engine reads.
"""

from __future__ import annotations

from datetime import date

from app.core.settings import get_settings
from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, CRAWL_SOURCE_SE_RANKING

MAX_RECOMMENDATION_CRAWL_AGE_DAYS = 14


def crawl_evidence_limit(snapshot_date: date | None, *, checked_on: date | None = None) -> str | None:
    """Age page evidence against generation time, even for a backdated assessment."""
    checked_on = checked_on or date.today()
    if snapshot_date is None:
        return "No successful page crawl is available. New crawl-dependent recommendations are withheld."
    age = (checked_on - snapshot_date).days
    if age < 0 or age > MAX_RECOMMENDATION_CRAWL_AGE_DAYS:
        return (
            f"The successful crawl is dated {snapshot_date.isoformat()} (checked {checked_on.isoformat()}). "
            "Page evidence must be no more than 14 days old. New crawl-dependent recommendations "
            "are withheld until a successful crawl refreshes the evidence. Existing approved work is retained."
        )
    return None


def supported_without_crawl(prescription) -> bool:
    # Positive allowlist: new rules must declare that they do not use page
    # inspection before stale crawl evidence can support them. These rules
    # use GSC, GA4, prompt observations or an explicit human strategy decision.
    return prescription.action_id in {"T-1", "T-3", "G-1", "C-P"}


def active_crawl_source() -> str:
    """
    The crawl the engine reads. Both keep writing.

    Settable so a bad crawl can be backed out by flipping one variable rather
    than deploying, and so the two can be compared on the same data.
    """
    configured = (get_settings().crawl_facts_source or "").strip()
    return configured if configured in {CRAWL_SOURCE_FIRST_PARTY, CRAWL_SOURCE_SE_RANKING} else CRAWL_SOURCE_FIRST_PARTY
