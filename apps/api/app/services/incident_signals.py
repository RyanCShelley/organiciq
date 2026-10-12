"""Read the three incident checks out of the warehouse."""

from __future__ import annotations

import re
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.decisions.incidents import IncidentSignals
from app.models.client import Client
from app.models.config import ConversionDefinition
from app.models.crawl import FactCrawlPageSchema, FactCrawlPageSnapshot
from app.models.ga4 import FactGa4Event

#: How far back "a history of leads" looks, before the silent fortnight.
PRIOR_WINDOW_DAYS = 90

#: Enough pages carrying a foreign brand to be the site rather than one page.
FOREIGN_BRAND_MIN_PAGES = 3


def _norm(text: str | None) -> str:
    """Letters and digits only, lowercased — so "SMA Marketing, LLC" and
    "SMA Marketing" are the same company and not two."""
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def _organization_names(raw: object) -> list[str]:
    """Every Organization name in a JSON-LD document.

    Walks the whole document: reading only the top made `@context` look like
    an Organization block once already.
    """
    found: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        types = node.get("@type")
        types = types if isinstance(types, list) else [types]
        if any(
            isinstance(t, str) and t.strip().lower() in ("organization", "localbusiness")
            for t in types
        ):
            name = node.get("name")
            if isinstance(name, str) and name.strip():
                found.append(name.strip())
        for value in node.values():
            walk(value)

    walk(raw)
    return found


def read_incident_signals(
    db: Session, client: Client, *, today: date | None = None
) -> IncidentSignals:
    today = today or date.today()

    # ── Leads stopped ──
    lead_events = [
        d.event_name
        for d in db.query(ConversionDefinition).filter(
            ConversionDefinition.client_id == client.id,
            ConversionDefinition.active.is_(True),
            ConversionDefinition.conversion_type == "lead",
        )
    ]
    days_since_last_lead: int | None = None
    prior_leads = 0.0
    if lead_events:
        last = (
            db.query(func.max(FactGa4Event.date))
            .filter(
                FactGa4Event.client_id == client.id,
                FactGa4Event.event_name.in_(lead_events),
                FactGa4Event.event_count > 0,
                FactGa4Event.date <= today,
            )
            .scalar()
        )
        if last is not None:
            days_since_last_lead = (today - last).days
            prior_leads = float(
                db.query(func.coalesce(func.sum(FactGa4Event.event_count), 0))
                .filter(
                    FactGa4Event.client_id == client.id,
                    FactGa4Event.event_name.in_(lead_events),
                    FactGa4Event.date >= last - timedelta(days=PRIOR_WINDOW_DAYS),
                    FactGa4Event.date <= last,
                )
                .scalar()
                or 0
            )

    # ── Pages vanished ──
    dates = [
        row[0]
        for row in db.query(FactCrawlPageSnapshot.snapshot_date)
        .filter(
            FactCrawlPageSnapshot.client_id == client.id,
            FactCrawlPageSnapshot.snapshot_date <= today,
        )
        .distinct()
        .order_by(FactCrawlPageSnapshot.snapshot_date.desc())
        .limit(2)
        .all()
    ]

    def indexable_on(when: date) -> int:
        return int(
            db.query(func.count(FactCrawlPageSnapshot.id))
            .filter(
                FactCrawlPageSnapshot.client_id == client.id,
                FactCrawlPageSnapshot.snapshot_date == when,
                FactCrawlPageSnapshot.indexable.is_(True),
            )
            .scalar()
            or 0
        )

    indexable_now = indexable_on(dates[0]) if dates else None
    indexable_before = indexable_on(dates[1]) if len(dates) > 1 else None

    # ── The markup names somebody else ──
    foreign: dict[str, int] = {}
    pages_with_org = 0
    if dates:
        ours = {_norm(client.client_name)}
        # The domain's own name counts as ours: "smamarketing.com" and
        # "SMA Marketing" are the same company.
        ours.add(_norm((client.domain or "").split(".")[0]))
        ours.discard("")
        for row in db.query(FactCrawlPageSchema).filter(
            FactCrawlPageSchema.client_id == client.id,
            FactCrawlPageSchema.snapshot_date == dates[0],
        ):
            names = _organization_names(row.raw)
            if not names:
                continue
            pages_with_org += 1
            for name in names:
                key = _norm(name)
                if not key or any(key in o or o in key for o in ours):
                    continue
                foreign[name] = foreign.get(name, 0) + 1

    return IncidentSignals(
        days_since_last_lead=days_since_last_lead,
        leads_in_prior_window=prior_leads,
        indexable_now=indexable_now,
        indexable_before=indexable_before,
        crawl_before_date=dates[1].isoformat() if len(dates) > 1 else None,
        foreign_brands=tuple(
            sorted(
                ((name, count) for name, count in foreign.items()
                 if count >= FOREIGN_BRAND_MIN_PAGES),
                key=lambda kv: -kv[1],
            )
        ),
        pages_with_organization=pages_with_org,
    )
