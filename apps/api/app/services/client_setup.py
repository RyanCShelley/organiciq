"""What is set up for a client, and what has to happen next.

Read from the data every time, never stored. A stored "step 4 complete" flag
is a claim that goes stale the moment somebody deletes a conversion
definition, and the thing it describes — is this client ready to run — is
cheap to measure directly.

**The order is the dependency order, not a preference.** Each step names what
it is waiting for, and a step is blocked exactly when something it reads has
not happened:

  1 account record   → nothing
  2 data sources     → 1
  3 first pull       → 2
  4 lead definitions → 3 (the event list comes out of GA4's own facts)
  5 baseline         → 4, and GA4 sessions. It *writes* monthly_lead_goal,
                       which is why the add-client form does not ask for one
  6 conversion pages → nothing hard; the crawl makes it easy
  7 page stages      → 6, the crawl, and GA4 sessions
  8 keyword targets  → SE Ranking's pull
  9 first engine run → the constraint needs 3; the slots need 8
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.config import (
    ClientConversionPage,
    ClientPageStage,
    ConversionDefinition,
)
from app.models.decision import KeywordTarget, MonthlyRecord
from app.models.ga4 import FactGa4Traffic
from app.models.gsc import FactGscPage
from app.models.integration import ConnectionStatus, Integration
from app.models.seranking import FactSerKeyword

#: Where each step is done, so the checklist can send somebody straight there.
#: Relative to the client workspace.
LINKS = {
    "account": "",
    "sources": "integrations",
    "pull": "jobs",
    "leads": "conversions",
    "baseline": "",
    "conversion_pages": "conversions",
    "page_stages": "conversions",
    "keyword_targets": "conversions",
    "first_run": "",
}


@dataclass
class Step:
    key: str
    title: str
    #: What is true now — a count, a date, a name. Never a restatement of the
    #: title, which tells a reader nothing they cannot already see.
    detail: str
    done: bool
    #: Named when the step cannot be started yet. A blocked step that does not
    #: say what it waits for sends somebody looking.
    blocked_by: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "title": self.title,
            "detail": self.detail,
            "done": self.done,
            "blocked_by": self.blocked_by,
            "link": LINKS.get(self.key, ""),
        }


def _count(db: Session, model, client_id) -> int:
    return int(
        db.query(func.count(model.id)).filter(model.client_id == client_id).scalar() or 0
    )


def _newest(db: Session, model, column, client_id) -> date | None:
    return db.query(func.max(column)).filter(model.client_id == client_id).scalar()


def _plural(count: int, one: str, many: str | None = None) -> str:
    return f"{count} {one if count == 1 else (many or one + 's')}"


def setup_steps(db: Session, client: Client) -> list[Step]:
    """The ordered steps, each measured rather than remembered."""
    steps: list[Step] = []

    # 1 — the record itself.
    steps.append(
        Step(
            key="account",
            title="Account record",
            detail=f"{client.client_name} · {client.domain}",
            done=bool(client.client_name and client.domain and client.tier_id),
        )
    )

    # 2 — the connections.
    integrations = (
        db.query(Integration).filter(Integration.client_id == client.id).all()
    )
    connected = [
        i for i in integrations if i.connection_status == ConnectionStatus.CONNECTED
    ]
    connected_names = sorted(i.provider.value for i in connected)
    steps.append(
        Step(
            key="sources",
            title="Connect GA4, Search Console and SE Ranking",
            detail=(
                ", ".join(connected_names) if connected_names else "none connected yet"
            ),
            done=len(connected) >= 3,
        )
    )

    # 3 — data actually in the warehouse. A connection that has never pulled
    # is the state that looks finished and is not.
    ga4_through = _newest(db, FactGa4Traffic, FactGa4Traffic.date, client.id)
    gsc_through = _newest(db, FactGscPage, FactGscPage.date, client.id)
    ser_count = _count(db, FactSerKeyword, client.id)
    pulled = [
        label
        for label, value in (
            (f"GA4 through {ga4_through}", ga4_through),
            (f"Search Console through {gsc_through}", gsc_through),
            (f"SE Ranking {ser_count} keywords", ser_count or None),
        )
        if value
    ]
    steps.append(
        Step(
            key="pull",
            title="First data pull",
            detail=" · ".join(pulled) if pulled else "nothing pulled yet",
            done=bool(ga4_through and gsc_through),
            blocked_by=None if connected else "connect a data source first",
        )
    )

    # 4 — which GA4 events are leads. The screen offers the client's own
    # event names, so it has nothing to show before the GA4 pull.
    leads = (
        db.query(func.count(ConversionDefinition.id))
        .filter(
            ConversionDefinition.client_id == client.id,
            ConversionDefinition.active.is_(True),
        )
        .scalar()
        or 0
    )
    steps.append(
        Step(
            key="leads",
            title="Lead definitions",
            detail=(
                f"{_plural(int(leads), 'event')} marked as leads"
                if leads
                else "no GA4 event is counted as a lead yet"
            ),
            done=bool(leads),
            blocked_by=None if ga4_through else "needs the GA4 pull",
        )
    )

    # 5 — the baseline. It writes monthly_lead_goal, so it is where the goal
    # comes from rather than something typed when the client was created.
    has_baseline = bool(client.baseline_as_of and client.baseline_monthly_sessions)
    steps.append(
        Step(
            key="baseline",
            title="Baseline snapshot",
            detail=(
                f"as of {client.baseline_as_of}"
                + (
                    f" · goal {client.monthly_lead_goal}/mo"
                    if client.monthly_lead_goal
                    else ""
                )
                if has_baseline
                else "ready to build from GA4"
                if leads and ga4_through
                else "not set"
            ),
            done=has_baseline,
            blocked_by=(
                None
                if leads and ga4_through
                else "needs lead definitions"
                if ga4_through
                else "needs the GA4 pull"
            ),
        )
    )

    # 6 — where a visitor is meant to end up.
    pages = _count(db, ClientConversionPage, client.id)
    steps.append(
        Step(
            key="conversion_pages",
            title="Conversion pages",
            detail=(
                _plural(pages, "page") + " declared"
                if pages
                else "none declared — the engine will not guess from the URL"
            ),
            done=bool(pages),
        )
    )

    # 7 — funnel stage on the landing pages, which is what the next-step test
    # reads. Measured in sessions, because rows ticked is not coverage.
    confirmed = (
        db.query(func.count(ClientPageStage.id))
        .filter(
            ClientPageStage.client_id == client.id,
            ClientPageStage.confirmed_at.isnot(None),
        )
        .scalar()
        or 0
    )
    steps.append(
        Step(
            key="page_stages",
            title="Page stages",
            detail=(
                f"{_plural(int(confirmed), 'page')} confirmed"
                if confirmed
                else "no landing page has a confirmed stage"
            ),
            done=bool(confirmed),
            blocked_by=(
                None
                if pages and ga4_through
                else "needs conversion pages"
                if ga4_through
                else "needs the GA4 pull"
            ),
        )
    )

    # 8 — the terms, and the page each one belongs to.
    targets = _count(db, KeywordTarget, client.id)
    steps.append(
        Step(
            key="keyword_targets",
            title="Keyword targets",
            detail=(
                _plural(targets, "term") + " mapped to a page"
                if targets
                else "no term is mapped to a page"
            ),
            done=bool(targets),
            blocked_by=None if ser_count else "needs the SE Ranking pull",
        )
    )

    # 9 — the payoff.
    runs = _count(db, MonthlyRecord, client.id)
    newest_run = (
        db.query(func.max(MonthlyRecord.month))
        .filter(MonthlyRecord.client_id == client.id)
        .scalar()
    )
    steps.append(
        Step(
            key="first_run",
            title="First engine run",
            detail=(
                f"{_plural(runs, 'run')} saved · newest {newest_run}"
                if runs
                else "no run saved yet"
            ),
            done=bool(runs),
            blocked_by=(
                None
                if ga4_through and gsc_through
                else "needs GA4 and Search Console data"
            ),
        )
    )

    return steps


def setup_state(db: Session, client: Client) -> dict[str, Any]:
    steps = setup_steps(db, client)
    # The next thing to do: the first step that is neither done nor blocked.
    # A blocked step is not the next action — the thing blocking it is.
    nxt = next((s for s in steps if not s.done and not s.blocked_by), None)
    return {
        "done": sum(1 for s in steps if s.done),
        "total": len(steps),
        "next": nxt.key if nxt else None,
        "steps": [s.as_dict() for s in steps],
    }
