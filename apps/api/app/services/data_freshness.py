"""How current each data source is for a client: the newest fact it holds, read from the facts themselves.

A watermark is a claim about what was fetched; the newest stored row is what the screens actually read,
so that is what is reported.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.bing_stats import FactBingQueryStat
from app.models.client import Client
from app.models.crawl import FactCrawlPageSnapshot
from app.models.ga4 import FactGa4Traffic
from app.models.gsc import FactGscPage

#: (key, label, newest-fact column, days after which it is overdue).
#: Search Console finalises two to three days late, Bing reports by week, the crawl runs weekly.
SOURCES = (
    ("gsc", "Search Console", FactGscPage.date, FactGscPage.client_id, 6),
    ("ga4", "GA4", FactGa4Traffic.date, FactGa4Traffic.client_id, 3),
    ("bing", "Bing", FactBingQueryStat.week_start, FactBingQueryStat.client_id, 16),
    ("crawl", "Site crawl", FactCrawlPageSnapshot.snapshot_date, FactCrawlPageSnapshot.client_id, 14),
)


def build(db: Session, client: Client, today: date | None = None) -> list[dict[str, Any]]:
    today = today or date.today()
    rows = []
    for key, label, column, owner, overdue_after in SOURCES:
        through = db.query(func.max(column)).filter(owner == client.id).scalar()
        age = (today - through).days if through else None
        rows.append(
            {
                "key": key,
                "label": label,
                "through": through.isoformat() if through else None,
                "age_days": age,
                "overdue": age is None or age > overdue_after,
            }
        )
    return rows
