"""Which page Search Console already shows for a query.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.gsc import FactGscQueryPage


def rank_position(value: Any) -> float | None:
    if value is None:
        return None
    try:
        position = float(value)
    except (TypeError, ValueError):
        return None
    if position <= 0:
        return None
    return position


@dataclass(frozen=True)
class ExistingPageForQuery:
    page_url: str
    impressions: float
    average_position: float | None


def pages_for_queries(
    db: Session,
    client_id: UUID,
    *,
    period: tuple[date, date] | None,
    only: set[str] | None = None,
) -> dict[str, ExistingPageForQuery]:
    """The page Search Console already shows for each query.

    Keyed on the lowercased query, because a watchlist entry and a Search
    Console query differ in case far more often than in substance.

    `only` limits it to those (lowercased) queries. A caller that will look up
    a few hundred terms should not summarise the thousands of queries a site
    has ever shown and carry all of them into Python to use a handful.
    """
    if period is None:
        return {}
    if only is not None and not only:
        return {}
    start, end = period
    query = db.query(
        FactGscQueryPage.query,
        FactGscQueryPage.normalized_url,
        func.sum(FactGscQueryPage.impressions).label("impressions"),
        func.avg(FactGscQueryPage.average_position).label("position"),
    ).filter(
        FactGscQueryPage.client_id == client_id,
        FactGscQueryPage.date >= start,
        FactGscQueryPage.date <= end,
    )
    if only is not None:
        query = query.filter(func.lower(func.trim(FactGscQueryPage.query)).in_(sorted(only)))
    rows = query.group_by(FactGscQueryPage.query, FactGscQueryPage.normalized_url).all()
    best: dict[str, ExistingPageForQuery] = {}
    for query, url, impressions, position in rows:
        key = (query or "").strip().lower()
        if not key or not url:
            continue
        found = ExistingPageForQuery(
            page_url=url,
            impressions=float(impressions or 0),
            average_position=float(position) if position is not None else None,
        )
        current = best.get(key)
        if current is None or found.impressions > current.impressions:
            best[key] = found
    return best
