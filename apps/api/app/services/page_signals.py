"""Read the Traffic and Leads candidates out of the warehouse.

One page, every fact the T and L triggers test. Managed channels only, per
rule 4 — a session that arrived from a paid ad is not evidence about the
organic work, and counting it is how a page scored well on traffic nobody
here earned.

Where a fact is absent the field stays None and the trigger that needs it does
not fire. That is the point: an action nobody can justify is worse than a slot
that says why it is empty.
"""

from __future__ import annotations

import statistics
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.decisions.ctr_curve import expected_ctr_percent
from app.decisions.page_targets import PageCandidate
from app.models.client import Client
from app.models.config import ClientConversionPage
from app.models.crawl import FactCrawlInternalLink, FactCrawlPageSnapshot
from app.models.ga4 import FactGa4Traffic
from app.models.gsc import FactGscPage, FactGscQueryPage
from app.services.page_stage import confirmed_stages
from app.services.triage_signals import MANAGED_CHANNELS

#: The window the traffic and lead facts are read over.
WINDOW_DAYS = 28

#: Which offers suit a reader at each stage, matching the catalog's own rule.
from app.decisions.catalog import STAGE_FIT  # noqa: E402


def _gsc_pages(db: Session, client_id: UUID, start: date, end: date) -> dict[str, dict]:
    rows = (
        db.query(
            FactGscPage.normalized_url,
            func.coalesce(func.sum(FactGscPage.clicks), 0),
            func.coalesce(func.sum(FactGscPage.impressions), 0),
            # Impression-weighted, because a plain average over days gives a
            # day with four impressions the same say as a day with four
            # hundred.
            func.coalesce(
                func.sum(FactGscPage.average_position * FactGscPage.impressions), 0
            ),
        )
        .filter(
            FactGscPage.client_id == client_id,
            FactGscPage.date >= start,
            FactGscPage.date <= end,
        )
        .group_by(FactGscPage.normalized_url)
        .all()
    )
    out: dict[str, dict] = {}
    for url, clicks, impressions, weighted in rows:
        impressions = float(impressions or 0)
        position = float(weighted or 0) / impressions if impressions else None
        out[url] = {
            "clicks": float(clicks or 0),
            "impressions": impressions,
            "position": position,
        }
    return out


def _top_queries(db: Session, client_id: UUID, start: date, end: date) -> dict[str, str]:
    """The query drawing the most impressions on each page."""
    rows = (
        db.query(
            FactGscQueryPage.normalized_url,
            FactGscQueryPage.query,
            func.coalesce(func.sum(FactGscQueryPage.impressions), 0).label("imp"),
        )
        .filter(
            FactGscQueryPage.client_id == client_id,
            FactGscQueryPage.date >= start,
            FactGscQueryPage.date <= end,
        )
        .group_by(FactGscQueryPage.normalized_url, FactGscQueryPage.query)
        .order_by(FactGscQueryPage.normalized_url, func.sum(FactGscQueryPage.impressions).desc())
        .all()
    )
    best: dict[str, str] = {}
    for url, query, _ in rows:
        best.setdefault(url, query)
    return best


def _sessions(
    db: Session, client_id: UUID, start: date, end: date
) -> dict[str, tuple[float, float | None]]:
    rows = (
        db.query(
            FactGa4Traffic.normalized_url,
            func.coalesce(func.sum(FactGa4Traffic.sessions), 0),
            func.sum(FactGa4Traffic.engaged_sessions),
        )
        .filter(
            FactGa4Traffic.client_id == client_id,
            FactGa4Traffic.date >= start,
            FactGa4Traffic.date <= end,
            FactGa4Traffic.channel.in_(MANAGED_CHANNELS),
        )
        .group_by(FactGa4Traffic.normalized_url)
        .all()
    )
    return {
        url: (
            float(sessions or 0),
            float(engaged) if engaged is not None else None,
        )
        for url, sessions, engaged in rows
    }


def load_page_candidates(
    db: Session, client: Client, *, today: date | None = None
) -> list[PageCandidate]:
    today = today or date.today()
    start = today - timedelta(days=WINDOW_DAYS - 1)

    gsc = _gsc_pages(db, client.id, start, today)
    queries = _top_queries(db, client.id, start, today)
    sessions = _sessions(db, client.id, start, today)
    stages = confirmed_stages(db, client.id)

    newest_crawl = (
        db.query(func.max(FactCrawlPageSnapshot.snapshot_date))
        .filter(FactCrawlPageSnapshot.client_id == client.id)
        .scalar()
    )
    crawl: dict[str, FactCrawlPageSnapshot] = {}
    if newest_crawl:
        crawl = {
            row.normalized_url: row
            for row in db.query(FactCrawlPageSnapshot).filter(
                FactCrawlPageSnapshot.client_id == client.id,
                FactCrawlPageSnapshot.snapshot_date == newest_crawl,
            )
        }

    offers = {
        (row.normalized_url or "").strip(): (row.stage or "").strip().lower() or None
        for row in db.query(ClientConversionPage).filter(
            ClientConversionPage.client_id == client.id
        )
        if (row.normalized_url or "").strip()
    }

    # Every in-content, non-template edge from a page to a declared offer.
    routes: dict[str, set[str]] = {}
    if offers:
        for from_url, to_url in (
            db.query(FactCrawlInternalLink.from_url, FactCrawlInternalLink.to_url)
            .filter(
                FactCrawlInternalLink.client_id == client.id,
                FactCrawlInternalLink.to_url.in_(offers),
                FactCrawlInternalLink.in_content.is_(True),
                FactCrawlInternalLink.is_template.is_(False),
            )
            .distinct()
        ):
            stage = offers.get(to_url)
            if stage:
                routes.setdefault(from_url, set()).add(stage)

    # The site's own median engagement, over pages with enough sessions for
    # the rate to mean anything.
    rates = [
        engaged / total
        for total, engaged in sessions.values()
        if engaged is not None and total >= 30
    ]
    median_engagement = statistics.median(rates) if len(rates) >= 5 else None

    urls = set(gsc) | set(sessions)
    out: list[PageCandidate] = []
    for url in sorted(urls):
        page = gsc.get(url, {})
        position = page.get("position")
        impressions = page.get("impressions", 0.0)
        expected = (
            expected_ctr_percent(position) / 100.0 * impressions
            if position and impressions
            else None
        )
        total_sessions, engaged = sessions.get(url, (0.0, None))
        snapshot = crawl.get(url)
        stage = stages.get(url)
        fits = STAGE_FIT.get(stage or "", ())
        out.append(
            PageCandidate(
                url=url,
                title=snapshot.title if snapshot else None,
                description=snapshot.description if snapshot else None,
                impressions=impressions,
                clicks=page.get("clicks", 0.0),
                position=position,
                expected_clicks=expected,
                top_query=queries.get(url),
                sessions=total_sessions,
                engaged_sessions=engaged,
                site_median_engagement=median_engagement,
                stage=stage,
                linked_offer_stages=frozenset(routes.get(url, set())),
                matched_offers=tuple(
                    sorted(u for u, s in offers.items() if s in fits)
                ),
                conversion_elements=(
                    snapshot.conversion_elements if snapshot else None
                ),
            )
        )
    return out
