"""Read the eleven tests' inputs out of the warehouse.

`triage.py` holds the tests and knows nothing about the database. This is the
other half: one function per branch that turns facts into the signals those
tests take.

Every reading is managed-channel only, per the spec's rule 4. `build_dashboard`
applies no channel filter anywhere, so nothing here reads from it — a lead that
arrived from a referral is not evidence about organic search, and counting it
is how a page with four of five leads from elsewhere scored as converting well.

Where an input is absent the signal stays None and the test blocks. That is the
point: a test we could not run has to say so rather than pass.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.decisions.triage import LeadSignals, TrafficSignals, VisibilitySignals
from app.models.client import Client
from app.models.config import ClientConversionPage, ConversionDefinition, OrganicChannel
from app.models.crawl import FactCrawlInternalLink
from app.models.decision import KeywordTarget
from app.models.ga4 import FactGa4Event, FactGa4Traffic
from app.models.gsc import FactGscDaily
from app.models.seranking import (
    FactSerAiCheck,
    FactSerAiTrackerStats,
    FactSerKeyword,
    FactSerSiteSummary,
)

#: The channels a client's organic work actually produces.
#:
#: The spec says organic search and AI referrals only. Measured against the
#: warehouse that discards most of the outcome: of SMA's six leads in a
#: month, zero were organic_search — five were direct and one unattributed.
#: Boys Electrical's split is 25 direct, 11 organic, 11 other. A lead rate
#: built on organic alone was reporting 0 of 35 for a client that got six.
#:
#: Direct is in because it is mostly misattributed — a brand search after an
#: AI answer, a phone typed from a Maps listing, a link pasted into Slack.
#: SMA's own research on GA4 direct traffic is the argument for it.
#:
#: Paid search is out: a separate service with its own attribution, and
#: Aquaman's eleven paid leads are not organic work. So is `other`, which is
#: what GA4 could not attribute at all — 2,992 sessions a month of (not set).
#: Counting those would mean a lead rate that includes traffic nobody can
#: trace to anyone, including us.
MANAGED_CHANNELS = (
    OrganicChannel.ORGANIC_SEARCH,
    OrganicChannel.AI_REFERRAL,
    OrganicChannel.DIRECT_UNATTRIBUTED,
    OrganicChannel.REFERRAL,
)

#: The comparison window the trend tests use.
TREND_DAYS = 28
#: How far back "90 days ago" reaches when looking for a comparable reading.
TREND_TOLERANCE_DAYS = 10


def _rank(value: object) -> float | None:
    try:
        position = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    # SE Ranking uses 0 or 101 for "not in the results we checked".
    return position if 0 < position <= 100 else None


def _nearest_reading(
    db: Session, client_id: UUID, model, column, when: date, tolerance: int
) -> float | None:
    """A reading from around `when`, for a trend that needs a 'before'.

    Nothing lands on an exact date. Asking for one and getting nothing is how
    a trend test blocks forever on a client whose sync runs weekly.
    """
    row = (
        db.query(column)
        .filter(
            model.client_id == client_id,
            model.metric_date >= when - timedelta(days=tolerance),
            model.metric_date <= when + timedelta(days=tolerance),
            column.isnot(None),
        )
        # Postgres subtracts two dates into an integer day count, not an
        # interval, so this is just "nearest by days".
        .order_by(func.abs(model.metric_date - when))
        .first()
    )
    return float(row[0]) if row and row[0] is not None else None


def _managed_sessions(db: Session, client_id: UUID, start: date, end: date) -> float:
    return float(
        db.query(func.coalesce(func.sum(FactGa4Traffic.sessions), 0))
        .filter(
            FactGa4Traffic.client_id == client_id,
            FactGa4Traffic.date >= start,
            FactGa4Traffic.date <= end,
            FactGa4Traffic.channel.in_(MANAGED_CHANNELS),
        )
        .scalar()
        or 0
    )


def visibility_signals(
    db: Session, client: Client, *, today: date, ai_period: tuple[date, date] | None
) -> VisibilitySignals:
    from app.services.watchlist import read as read_watchlist
    from app.services.decision_measurements import keyword_readings
    watch_keywords = [item for item in read_watchlist(db, client)
                      if item["kind"] == "keyword" and item["state"] != "excluded"]
    priority_terms = {item["text"].strip().lower() for item in watch_keywords}
    readings = keyword_readings(db, client.id, today)
    judged = {term: row for term, row in readings.items()
              if term in priority_terms and row["position"] is not None}
    in_top_10 = sum(1 for row in judged.values() if 0 < row["position"] <= 10)
    targets = db.query(KeywordTarget).filter(
        KeywordTarget.client_id == client.id,
        KeywordTarget.source.in_(("confirmed", "auto")),
    ).all()
    targets = [target for target in targets if target.keyword.strip().lower() in priority_terms]
    tracked = readings

    # V4 — a declared target page with no tracked term inside the top 20.
    declared_pages = {
        (t.target_url or "").strip() for t in targets if (t.target_url or "").strip()
    }
    declared_pages |= {
        (p.normalized_url or "").strip()
        for p in db.query(ClientConversionPage).filter(
            ClientConversionPage.client_id == client.id
        )
        if (p.normalized_url or "").strip()
    }
    from app.core.urls import normalize_url
    all_targets = targets
    declared_pages = {normalize_url(url) for url in declared_pages}
    mapped_pages = {normalize_url(t.target_url) for t in all_targets if t.target_url}
    # Reach can only be assessed for mapped pages; unmapped is a setup gap.
    assessed_pages = declared_pages & mapped_pages
    reached: set[str] = set()
    for term, row in tracked.items():
        position = _rank(row["position"])
        if position is None or position > 20:
            continue
        target = next((t.target_url for t in all_targets if t.keyword == term), None)
        if target and row["ranking_url"] and normalize_url(row["ranking_url"]) == normalize_url(target):
            reached.add(normalize_url(target))
    without_reach = len(assessed_pages - reached)

    # V2 — SE Ranking's own visibility score, now against ninety days ago.
    latest_summary = (
        db.query(FactSerSiteSummary.visibility_percent)
        .filter(
            FactSerSiteSummary.client_id == client.id,
            FactSerSiteSummary.visibility_percent.isnot(None),
            FactSerSiteSummary.metric_date <= today,
        )
        .order_by(FactSerSiteSummary.metric_date.desc())
        .first()
    )

    # V3 — managed impressions, last 28 days against the 28 before.
    def impressions(start: date, end: date) -> float | None:
        total = (
            db.query(func.coalesce(func.sum(FactGscDaily.impressions), 0))
            .filter(
                FactGscDaily.client_id == client.id,
                FactGscDaily.date >= start,
                FactGscDaily.date <= end,
            )
            .scalar()
        )
        return float(total) if total else None

    recent_end = today
    recent_start = recent_end - timedelta(days=TREND_DAYS - 1)
    prior_end = recent_start - timedelta(days=1)
    prior_start = prior_end - timedelta(days=TREND_DAYS - 1)

    # V5 — the AI tracker's own presence figure, and share of voice over time.
    stats = (
        db.query(FactSerAiTrackerStats)
        .filter(FactSerAiTrackerStats.client_id == client.id, FactSerAiTrackerStats.metric_date <= today)
        .order_by(FactSerAiTrackerStats.metric_date.desc())
        .first()
    )
    prompts = 0
    if ai_period is not None:
        prompts = (
            db.query(func.count(func.distinct(FactSerAiCheck.prompt_id)))
            .filter(
                FactSerAiCheck.client_id == client.id,
                FactSerAiCheck.date >= ai_period[0],
                FactSerAiCheck.date <= ai_period[1],
            )
            .scalar()
            or 0
        )

    from app.services.decision_measurements import monthly_keyword_trend
    return VisibilitySignals(
        monthly_keyword_trend=monthly_keyword_trend(db, client, today),
        priority_keywords=len(judged),
        priority_in_top_10=in_top_10,
        priority_group_set=bool(priority_terms),
        visibility_percent=float(latest_summary[0]) if latest_summary else None,
        visibility_percent_90d_ago=_nearest_reading(
            db,
            client.id,
            FactSerSiteSummary,
            FactSerSiteSummary.visibility_percent,
            today - timedelta(days=90),
            TREND_TOLERANCE_DAYS,
        ),
        impressions_28d=impressions(recent_start, recent_end),
        impressions_prior_28d=impressions(prior_start, prior_end),
        priority_pages=len(assessed_pages),
        priority_pages_without_reach=without_reach,
        priority_pages_declared=bool(assessed_pages),
        page_reach_missing=("no target or conversion pages declared" if not declared_pages
                            else "declared pages have no Watch List keyword mappings" if not assessed_pages else None),
        ai_mention_pct=(
            float(stats.mention_presence_pct)
            if stats and stats.mention_presence_pct is not None
            else None
        ),
        tracked_prompts=int(prompts),
    )


def traffic_signals(
    db: Session, client: Client, *, today: date, gsc_period: tuple[date, date] | None
) -> TrafficSignals:
    from app.services.ctr_diagnostic import read as read_ctr
    ctr = read_ctr(db, client.id, *(gsc_period or (today - timedelta(days=27), today)))

    recent_end = today
    recent_start = recent_end - timedelta(days=TREND_DAYS - 1)
    prior_end = recent_start - timedelta(days=1)
    prior_start = prior_end - timedelta(days=TREND_DAYS - 1)

    def change(now: float | None, before: float | None) -> float | None:
        if now is None or not before:
            return None
        return (now - before) / before * 100.0

    def impressions(start: date, end: date) -> float | None:
        total = (
            db.query(func.coalesce(func.sum(FactGscDaily.impressions), 0))
            .filter(
                FactGscDaily.client_id == client.id,
                FactGscDaily.date >= start,
                FactGscDaily.date <= end,
            )
            .scalar()
        )
        return float(total) if total else None

    # T3 — engaged rate on managed sessions, and the client's own median.
    engaged_rate = None
    totals = (
        db.query(
            func.coalesce(func.sum(FactGa4Traffic.sessions), 0),
            func.coalesce(func.sum(FactGa4Traffic.engaged_sessions), 0),
        )
        .filter(
            FactGa4Traffic.client_id == client.id,
            FactGa4Traffic.date >= recent_start,
            FactGa4Traffic.date <= recent_end,
            FactGa4Traffic.channel.in_(MANAGED_CHANNELS),
            FactGa4Traffic.engaged_sessions.isnot(None),
        )
        .first()
    )
    if totals and float(totals[0] or 0) > 0:
        engaged_rate = float(totals[1] or 0) / float(totals[0]) * 100.0

    median_rate = None
    six_months = (
        db.query(
            func.coalesce(func.sum(FactGa4Traffic.sessions), 0),
            func.coalesce(func.sum(FactGa4Traffic.engaged_sessions), 0),
        )
        .filter(
            FactGa4Traffic.client_id == client.id,
            FactGa4Traffic.date >= today - timedelta(days=182),
            FactGa4Traffic.date <= today,
            FactGa4Traffic.channel.in_(MANAGED_CHANNELS),
            FactGa4Traffic.engaged_sessions.isnot(None),
        )
        .first()
    )
    if six_months and float(six_months[0] or 0) > 0:
        median_rate = float(six_months[1] or 0) / float(six_months[0]) * 100.0

    # T0 uses all measured visits. T2 keeps an organic-search-only session
    # comparison because its other half is Search Console impressions.
    from app.services.decision_measurements import session_totals
    all_now = session_totals(db, client.id, recent_start, recent_end)
    all_before = session_totals(db, client.id, prior_start, prior_end)
    organic_now = all_now["channels"].get("organic_search")
    organic_before = all_before["channels"].get("organic_search")
    return TrafficSignals(
        sessions=all_now["total"], prior_sessions=all_before["total"],
        missed_clicks=ctr["missed_clicks"], actual_clicks=ctr["actual_clicks"],
        ctr_context_matched=ctr["matched"], ctr_missing=ctr["missing"], ctr_evidence=ctr["evidence"],
        impressions_change_pct=change(
            impressions(recent_start, recent_end), impressions(prior_start, prior_end)
        ),
        sessions_change_pct=change(organic_now, organic_before),
        engaged_rate=engaged_rate,
        engaged_rate_median=median_rate,
    )


#: How much of the month's managed traffic has to sit on a page with a
#: confirmed stage before L3's share means anything. A judgement, not a
#: measurement: below it the number would be real and unrepresentative, which
#: is the kind of number that reads as fact and is not. The actual coverage is
#: reported either way, so the gap is a progress bar rather than a wall.
NEXT_STEP_COVERAGE_FLOOR = 0.6


def _next_step(
    db: Session, client: Client, start: date, end: date
) -> tuple[float | None, str | None]:
    """L3: the share of covered sessions landing with nowhere to go.

    Three inputs, all now present: which landing pages are top of funnel
    (confirmed, never guessed from the URL), the in-content link graph, and
    the declared conversion pages. A page counts as a dead end when it is top
    of funnel and has no in-content, non-template link to a conversion page.

    The denominator is sessions on pages with a *confirmed* stage, not all
    managed sessions. Dividing by everything would let an unlabelled site
    score well by being unlabelled.
    """
    conversion_pages = {
        (p.normalized_url or "").strip()
        for p in db.query(ClientConversionPage).filter(
            ClientConversionPage.client_id == client.id
        )
        if (p.normalized_url or "").strip()
    }
    if not conversion_pages:
        return None, "no conversion pages declared to route to"

    # Imported here: page_stage reads MANAGED_CHANNELS from this module, so a
    # top-level import would close the circle.
    from app.services.page_stage import confirmed_stages

    stages = confirmed_stages(db, client.id)
    if not stages:
        return None, (
            f"{len(conversion_pages)} conversion "
            f"{'page' if len(conversion_pages) == 1 else 'pages'} declared, but no "
            "landing page has a confirmed funnel stage yet — label them on the "
            "Page stages screen"
        )

    sessions_by_page = dict(
        db.query(
            FactGa4Traffic.normalized_url,
            func.coalesce(func.sum(FactGa4Traffic.sessions), 0),
        )
        .filter(
            FactGa4Traffic.client_id == client.id,
            FactGa4Traffic.date >= start,
            FactGa4Traffic.date <= end,
            FactGa4Traffic.channel.in_(MANAGED_CHANNELS),
        )
        .group_by(FactGa4Traffic.normalized_url)
        .all()
    )
    total = sum(float(v or 0) for v in sessions_by_page.values())
    if not total:
        return None, "no managed sessions in the month to judge"

    covered = sum(
        float(sessions_by_page.get(url, 0) or 0) for url in stages
    )
    coverage = covered / total
    if coverage < NEXT_STEP_COVERAGE_FLOOR:
        return None, (
            f"funnel stages cover {coverage * 100:.0f}% of managed sessions — "
            f"{NEXT_STEP_COVERAGE_FLOOR * 100:.0f}% is needed before the share "
            "means anything"
        )

    # One query for every in-content route out of a page we care about.
    tofu_pages = {url for url, stage in stages.items() if stage == "tofu"}
    if not tofu_pages:
        return None, None if covered else "no top-of-funnel pages among those labelled"

    routed = {
        row[0]
        for row in db.query(FactCrawlInternalLink.from_url)
        .filter(
            FactCrawlInternalLink.client_id == client.id,
            FactCrawlInternalLink.from_url.in_(tofu_pages),
            FactCrawlInternalLink.to_url.in_(conversion_pages),
            FactCrawlInternalLink.in_content.is_(True),
            FactCrawlInternalLink.is_template.is_(False),
        )
        .distinct()
    }
    dead_end_sessions = sum(
        float(sessions_by_page.get(url, 0) or 0)
        for url in tofu_pages
        if url not in routed
    )
    return dead_end_sessions / covered * 100.0, None


def lead_signals(db: Session, client: Client, *, today: date) -> LeadSignals:
    events = [
        d.event_name
        for d in db.query(ConversionDefinition).filter(
            ConversionDefinition.client_id == client.id,
            ConversionDefinition.active.is_(True),
            ConversionDefinition.conversion_type == "lead",
        )
    ]
    configured = bool(events)

    month_start = today.replace(day=1)
    leads_mtd = None
    if configured:
        leads_mtd = float(
            db.query(func.coalesce(func.sum(FactGa4Event.event_count), 0))
            .filter(
                FactGa4Event.client_id == client.id,
                FactGa4Event.event_name.in_(events),
                FactGa4Event.date >= month_start,
                FactGa4Event.date <= today,
                FactGa4Event.channel.in_(MANAGED_CHANNELS),
            )
            .scalar()
            or 0
        )

    # The goal, pro-rated to the day. Judging day three against a monthly
    # target fails everyone, which is a statement about the calendar.
    monthly_goal = float(client.monthly_lead_goal) if client.monthly_lead_goal else None
    goal_to_date = None
    if monthly_goal:
        days_in_month = calendar.monthrange(today.year, today.month)[1]
        goal_to_date = monthly_goal * today.day / days_in_month

    # Rate numerator and denominator use the same all-channel scope and period.
    from app.services.decision_measurements import measure
    measured = measure(db, client, end=today)["leads"]
    lead_rate = measured["rate_pct"]

    baseline = getattr(client, "baseline_lead_rate_pct", None)

    tofu_share, next_step_blocked_by = _next_step(db, client, month_start, today)

    return LeadSignals(
        target_lead_rate=measured["target_rate_pct"],
        conversions_configured=configured,
        leads_month_to_date=leads_mtd,
        goal_to_date=goal_to_date,
        monthly_goal=monthly_goal,
        lead_rate=lead_rate,
        baseline_lead_rate=float(baseline) if baseline else None,
        tofu_sessions_share=tofu_share,
        next_step_measurable=tofu_share is not None,
        next_step_blocked_by=next_step_blocked_by,
    )
