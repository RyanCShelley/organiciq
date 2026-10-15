"""Which page should link to which: two pages ranking for one query.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.crawl import FactCrawlInternalLink
from app.models.gsc import FactGscQueryPage
from app.models.seranking import FactSerBacklinkPage
from app.services.crawl_source import active_crawl_source


#: Queries worth considering as a bridge between two pages. Below this the
#: overlap is usually incidental rather than a shared subject.
LINK_GAP_MIN_IMPRESSIONS = 50.0


#: A source has to be meaningfully stronger than the target, or the link is
#: being asked for in the wrong direction.
LINK_GAP_SOURCE_CLICK_RATIO = 2.0


@dataclass(frozen=True)
class LinkGap:
    """A link that should exist and does not."""

    source_url: str
    shared_query: str
    source_clicks: float
    #: Referring domains pointing at the donor. A page with links of its own
    #: has more to lend than one that merely gets clicks.
    source_refdomains: int = 0


def link_gaps(
    db: Session,
    client_id: UUID,
    *,
    period: tuple[date, date] | None,
    targets: set[str],
    max_donors: int = 3,
) -> dict[str, list[LinkGap]]:
    """For each under-linked page, the best page that should link to it.

    "This page has fewer than five inbound links" is a symptom. It tells a
    strategist that something is wrong and leaves them to work out what to do,
    which on a four-hundred-page site is most of the job.

    Two pages ranking for the same query are, by definition, about the same
    thing — and the one already earning clicks for it has the authority the
    other needs. If no editorial link runs between them, that is a specific
    link from a named page, which is ten minutes of work rather than an
    afternoon of judgement.

    Direction matters: the link has to come from the stronger page. Pointing it
    the other way asks the page with nothing to give to give it.
    """
    if period is None or not targets:
        return {}

    start, end = period
    rows = (
        db.query(
            FactGscQueryPage.query,
            FactGscQueryPage.normalized_url,
            func.sum(FactGscQueryPage.impressions).label("impressions"),
            func.sum(FactGscQueryPage.clicks).label("clicks"),
        )
        .filter(
            FactGscQueryPage.client_id == client_id,
            FactGscQueryPage.date >= start,
            FactGscQueryPage.date <= end,
        )
        .group_by(FactGscQueryPage.query, FactGscQueryPage.normalized_url)
        .having(func.sum(FactGscQueryPage.impressions) >= LINK_GAP_MIN_IMPRESSIONS)
        .all()
    )

    by_query: dict[str, list[tuple[str, float]]] = {}
    for query, url, _impressions, clicks in rows:
        by_query.setdefault(query, []).append((url, float(clicks or 0)))

    # Editorial edges only. A target already in the navigation still needs a
    # reference from a page about the same subject — that is the whole reason
    # the floor counts editorial links and not every link.
    existing = {
        (row.from_url, row.to_url)
        for row in db.query(FactCrawlInternalLink)
        .filter(
            FactCrawlInternalLink.client_id == client_id,
            FactCrawlInternalLink.source == active_crawl_source(),
            FactCrawlInternalLink.is_template.is_(False),
            FactCrawlInternalLink.to_url.in_(targets),
        )
        .all()
    }

    # Referring domains per donor, so authority is measured by what links to
    # the page and not only by what it earns. T4.
    refdomains = {
        row.normalized_url: row.refdomains
        for row in db.query(FactSerBacklinkPage).filter(
            FactSerBacklinkPage.client_id == client_id
        )
    }

    candidates: dict[str, dict[str, LinkGap]] = {}
    for query, entries in by_query.items():
        if len(entries) < 2:
            continue
        for target_url, target_clicks in entries:
            if target_url not in targets:
                continue
            for source_url, source_clicks in entries:
                if source_url == target_url:
                    continue
                if source_clicks < max(target_clicks * LINK_GAP_SOURCE_CLICK_RATIO, 1.0):
                    continue
                if (source_url, target_url) in existing:
                    continue
                found = candidates.setdefault(target_url, {})
                existing_gap = found.get(source_url)
                if existing_gap is None or source_clicks > existing_gap.source_clicks:
                    found[source_url] = LinkGap(
                        source_url=source_url,
                        shared_query=query,
                        source_clicks=source_clicks,
                        source_refdomains=refdomains.get(source_url, 0),
                    )

    return {
        target: sorted(
            donors.values(),
            key=lambda gap: (-gap.source_refdomains, -gap.source_clicks),
        )[:max_donors]
        for target, donors in candidates.items()
    }
