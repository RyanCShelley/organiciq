"""What is set up for a client, and what has to happen next.

Read from the data every time, never stored. A stored "step 4 complete" flag
is a claim that goes stale the moment somebody deletes a conversion
definition, and the thing it describes — is this client ready to run — is
cheap to measure directly.

**The order is the dependency order, not a preference.** Each step names what
it is waiting for, and a step is blocked exactly when something it reads has
not happened:

  1 account record         → nothing
  2 data sources           → 1 (GA4 & Search Console)
  3 first pull             → 2
  4 lead definitions       → 3 (the event list comes out of GA4's own facts)
  5 baseline               → 4, and GA4 sessions. It *writes* monthly_lead_goal,
                             which is why the add-client form does not ask for one
  6 watchlist              → nothing hard (in-app editor, GSC suggestions, or CSV)
  7 execution / advisory   → GA4 and Search Console data (Engine task or Consulting)

Optional enrichment steps (marked `optional=True`, such as `competitors`)
never inflate `total`, lower `done / total`, or block setup completion.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.client_bing_site import ClientBingSite
from app.models.client_focus import ClientFocus
from app.models.consulting import (
    ConsultingProfile,
    ConsultingRecommendation,
    ConsultingReport,
)
from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSnapshot
from app.models.decision import MonthlyRecord
from app.models.engine_task import EngineTask
from app.models.ga4 import FactGa4Traffic
from app.models.gsc import FactGscPage
from app.models.integration import ConnectionStatus, Integration
from app.models.seranking import FactSerKeyword
from app.models.watchlist import WatchlistBucket, WatchlistKeyword
from app.services import lead_conversions

#: Where each step is done in `apps/web-v2`, as `(scope, slug_relative_link)`.
#:
#: `scope` is `"settings"` for client configuration under `/[clientSlug]/settings/*`
#: or `"tool"` for workspace tools under `/[clientSlug]/*`. Every `link` is a
#: slug-relative path under `/[clientSlug]/`.
LINKS: dict[str, tuple[str, str]] = {
    "account": ("settings", "settings"),
    "sources": ("settings", "settings/connections"),
    "pull": ("settings", "settings/connections"),
    "leads": ("settings", "settings/conversions"),
    "baseline": ("settings", "settings/baseline"),
    "watchlist": ("tool", "watchlist"),
    "competitors": ("settings", "settings/competitors"),
    "first_run": ("tool", "engine"),
    "consulting_profile": ("tool", "consulting"),
    "consulting_deliverable": ("tool", "consulting/recommendations"),
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
    #: Optional enrichment steps do not count toward required `done / total` or `next`.
    optional: bool = False

    def as_dict(self) -> dict[str, Any]:
        scope, link = LINKS.get(self.key, ("settings", "settings"))
        return {
            "key": self.key,
            "title": self.title,
            "detail": self.detail,
            "done": self.done,
            "blocked_by": self.blocked_by,
            "optional": self.optional,
            "scope": scope,
            "link": link,
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
    is_consulting = client.service_mode == "consulting"

    # 1 — the record itself.
    account_parts = [client.client_name, client.domain]
    if client.business_model:
        account_parts.append(client.business_model)
    else:
        account_parts.append("business type not set")
    if is_consulting:
        account_parts.append("consulting")
    steps.append(
        Step(
            key="account",
            title="General information",
            detail=" · ".join(p for p in account_parts if p),
            done=bool(client.client_name and client.domain and client.tier_id),
        )
    )

    # 2 — the core connections (GA4 & Search Console; Bing / SE Ranking optional).
    integrations = (
        db.query(Integration).filter(Integration.client_id == client.id).all()
    )
    connected = [
        i
        for i in integrations
        if i.connection_status == ConnectionStatus.CONNECTED and i.external_property_id
    ]
    connected_names = sorted(i.provider.value for i in connected)
    bing_site = (
        db.query(ClientBingSite)
        .filter(ClientBingSite.client_id == client.id, ClientBingSite.status == "connected")
        .first()
    )
    source_labels = list(connected_names)
    if bing_site and "bing" not in source_labels:
        source_labels.append("bing")
    steps.append(
        Step(
            key="sources",
            title="Connect GA4 & Search Console",
            detail=(
                ", ".join(source_labels) if source_labels else "none connected yet"
            ),
            done={"ga4", "gsc"}.issubset(connected_names),
        )
    )

    # 3 — data actually in the warehouse. A connection that has never pulled
    # is the state that looks finished and is not.
    ga4_through = _newest(db, FactGa4Traffic, FactGa4Traffic.date, client.id)
    gsc_through = _newest(db, FactGscPage, FactGscPage.date, client.id)
    crawl_through = (
        db.query(func.max(FactCrawlPageSnapshot.snapshot_date))
        .filter(
            FactCrawlPageSnapshot.client_id == client.id,
            FactCrawlPageSnapshot.source == CRAWL_SOURCE_FIRST_PARTY,
        )
        .scalar()
    )
    ser_count = _count(db, FactSerKeyword, client.id)
    pulled = [
        label
        for label, value in (
            (f"GA4 through {ga4_through}", ga4_through),
            (f"Search Console through {gsc_through}", gsc_through),
            (f"Site crawl {crawl_through}", crawl_through),
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

    # 4 — which GA4 events are leads/conversions. The screen offers the client's
    # own event names, so it has nothing to show before the GA4 pull.
    leads = len(lead_conversions.active_conversion_events(db, client))
    steps.append(
        Step(
            key="leads",
            title="Conversion & lead definitions",
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
    has_baseline = bool(
        client.baseline_as_of and client.baseline_monthly_sessions is not None
    )
    steps.append(
        Step(
            key="baseline",
            title="Baseline snapshot",
            detail=(
                f"as of {client.baseline_as_of}"
                + (
                    f" · goal {client.monthly_lead_goal}/mo"
                    if client.monthly_lead_goal is not None
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

    # 6 — tracked watchlist terms (read-only query on WatchlistKeyword & WatchlistBucket).
    kw_count = _count(db, WatchlistKeyword, client.id)
    bucket_count = _count(db, WatchlistBucket, client.id)
    steps.append(
        Step(
            key="watchlist",
            title="Watchlist keywords",
            detail=(
                f"{_plural(kw_count, 'keyword')} in {_plural(bucket_count, 'bucket')}"
                if kw_count
                else "no keywords added yet"
            ),
            done=kw_count > 0,
        )
    )

    # 7 — mode-specific activation step(s).
    if is_consulting:
        has_profile = (
            db.query(ConsultingProfile.id)
            .filter(ConsultingProfile.client_id == client.id)
            .first()
            is not None
        )
        steps.append(
            Step(
                key="consulting_profile",
                title="Consulting workspace profile",
                detail=(
                    "business context saved"
                    if has_profile
                    else "no profile saved yet"
                ),
                done=has_profile,
            )
        )

        recs = _count(db, ConsultingRecommendation, client.id)
        reports = _count(db, ConsultingReport, client.id)
        has_deliverable = (recs + reports) > 0
        steps.append(
            Step(
                key="consulting_deliverable",
                title="First recommendation or report",
                detail=(
                    f"{_plural(recs, 'recommendation')}, {_plural(reports, 'report')}"
                    if has_deliverable
                    else "no recommendation or report created yet"
                ),
                done=has_deliverable,
                blocked_by=(
                    None
                    if ga4_through and gsc_through
                    else "needs GA4 and Search Console data"
                ),
            )
        )
    else:
        tasks = _count(db, EngineTask, client.id)
        focuses = _count(db, ClientFocus, client.id)
        runs = _count(db, MonthlyRecord, client.id)
        steps.append(
            Step(
                key="first_run",
                title="First Decision Engine task",
                detail=(
                    f"{_plural(tasks, 'task')} confirmed"
                    if tasks
                    else f"{_plural(runs, 'run')} saved"
                    if runs
                    else "monthly focus set — confirm a task in Engine"
                    if focuses
                    else "no task confirmed yet"
                ),
                done=bool(tasks or runs),
                blocked_by=(
                    None
                    if ga4_through and gsc_through
                    else "needs GA4 and Search Console data"
                ),
            )
        )

    # Optional enrichment — never counted in required done / total or `next`.
    competitors = [d for d in (client.competitor_domains or []) if d]
    steps.append(
        Step(
            key="competitors",
            title="Competitors",
            detail=(
                ", ".join(competitors)
                if competitors
                else "none listed yet (up to 3 for content gaps & AI SoV)"
            ),
            done=len(competitors) > 0,
            optional=True,
        )
    )

    return steps


def setup_state(db: Session, client: Client) -> dict[str, Any]:
    steps = setup_steps(db, client)
    required = [s for s in steps if not s.optional]
    # The next thing to do: the first required step that is neither done nor blocked.
    # A blocked step is not the next action — the thing blocking it is.
    nxt = next((s for s in required if not s.done and not s.blocked_by), None)
    return {
        "done": sum(1 for s in required if s.done),
        "total": len(required),
        "next": nxt.key if nxt else None,
        "service_mode": client.service_mode,
        "steps": [s.as_dict() for s in steps],
    }
