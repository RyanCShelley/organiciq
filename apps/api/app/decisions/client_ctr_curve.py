"""A click-through curve built from one client's own Search Console data.

The shared curve is an aggregate across the whole web. A local service company
and a B2B manufacturer do not earn the same share of clicks at position three,
so judging either against the average mis-states the gap in both directions.

Where a client has enough history, its own curve is the better yardstick.
Where it does not, the shared one is used — a curve fitted to two hundred
impressions would be noise wearing a client's name.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.decisions.ctr_curve import expected_ctr_percent
from app.models.gsc import FactGscPage

#: Below this the client's own data says less than the aggregate does.
MIN_IMPRESSIONS_FOR_OWN_CURVE = 1000
#: And it needs breadth, not only volume. A curve fitted to a handful of pages
#: is dominated by the very pages it is then used to judge, so each one comes
#: out exactly as expected by construction — the comparison measures nothing.
MIN_PAGES_FOR_OWN_CURVE = 20
#: Positions beyond this are too sparse to fit and too far back to matter.
MAX_CURVE_POSITION = 20


def build_client_ctr_curve(
    db: Session, client_id, period: tuple[date, date] | None
) -> tuple[dict[int, float], str]:
    """Return (curve by whole position, source).

    Source is "client" or "default", and it travels with the finding so a
    reader can tell whether the comparison was against this site or the web.
    """
    if period is None:
        return {}, "default"
    start, end = period
    rows = (
        db.query(
            func.round(FactGscPage.average_position).label("position"),
            func.sum(FactGscPage.impressions).label("impressions"),
            func.sum(FactGscPage.clicks).label("clicks"),
        )
        .filter(
            FactGscPage.client_id == client_id,
            FactGscPage.date >= start,
            FactGscPage.date <= end,
            FactGscPage.average_position > 0,
            FactGscPage.average_position <= MAX_CURVE_POSITION,
        )
        .group_by("position")
        .all()
    )
    distinct_pages = (
        db.query(func.count(func.distinct(FactGscPage.normalized_url)))
        .filter(
            FactGscPage.client_id == client_id,
            FactGscPage.date >= start,
            FactGscPage.date <= end,
        )
        .scalar()
        or 0
    )
    if distinct_pages < MIN_PAGES_FOR_OWN_CURVE:
        return {}, "default"

    totals: dict[int, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for position, impressions, clicks in rows:
        if position is None:
            continue
        bucket = totals[int(position)]
        bucket[0] += float(impressions or 0)
        bucket[1] += float(clicks or 0)

    overall = sum(bucket[0] for bucket in totals.values())
    if overall < MIN_IMPRESSIONS_FOR_OWN_CURVE:
        return {}, "default"

    # Only positions with their own weight are taken from the client; the rest
    # fall through to the shared curve, so one busy position cannot define the
    # whole shape.
    curve = {
        position: (clicks / impressions) * 100.0
        for position, (impressions, clicks) in totals.items()
        if impressions >= 100
    }
    return (curve, "client") if curve else ({}, "default")


def ctr_at(position: float, curve: dict[int, float]) -> float:
    """Expected CTR at a position, preferring the client's own figure."""
    if position <= 0:
        return 0.0
    whole = int(round(position))
    if whole in curve:
        return curve[whole]
    return expected_ctr_percent(position)
