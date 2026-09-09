"""Dashboard KPIs from validated facts only — no invented metrics."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.config import ConversionDefinition, OrganicChannel
from app.models.ga4 import FactGa4Event, FactGa4Traffic
from app.models.gsc import FactGscDaily, FactGscPage
from app.models.job import DataWatermark, ValidationStatus
from app.models.seranking import (
    FactSerAiTrackerStats,
    FactSerCompetitor,
    FactSerKeyword,
    FactSerSiteSummary,
)

CHANNEL_LABELS: dict[OrganicChannel, str] = {
    OrganicChannel.ORGANIC_SEARCH: "Organic Search",
    OrganicChannel.AI_REFERRAL: "AI Referral",
    OrganicChannel.DIRECT_UNATTRIBUTED: "Direct / Unattributed",
    OrganicChannel.PAID_SEARCH: "Paid Search",
    OrganicChannel.REFERRAL: "Referral",
    OrganicChannel.SOCIAL: "Social",
    OrganicChannel.EMAIL: "Email",
    OrganicChannel.OTHER: "Other",
}

DASHBOARD_WATERMARK_SOURCES = (
    "ga4",
    "gsc_pages",
    "gsc_queries",
    "se_ranking_search",
    "se_ranking_ai",
)


def previous_period(from_date: date, to_date: date) -> tuple[date, date]:
    days = (to_date - from_date).days + 1
    prev_end = from_date - timedelta(days=1)
    prev_start = prev_end - timedelta(days=days - 1)
    return prev_start, prev_end


DAYS_PER_MONTH = 30


def period_lead_goal(monthly_goal: int | None, from_date: date, to_date: date) -> tuple[int | None, int]:
    """Scale a configured monthly lead goal to the selected dashboard window."""
    period_days = (to_date - from_date).days + 1
    if monthly_goal is None or monthly_goal <= 0:
        return None, period_days
    scaled = round(monthly_goal * period_days / DAYS_PER_MONTH)
    if scaled <= 0:
        scaled = 1
    return scaled, period_days


def _to_float(value: Decimal | int | float | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _period_metric(
    current: float | int | None,
    previous: float | int | None,
    series: list[float] | None = None,
) -> dict[str, Any]:
    change_pct: float | None = None
    if current is not None and previous is not None and previous != 0:
        change_pct = ((current - previous) / previous) * 100
    payload: dict[str, Any] = {
        "current": _to_float(current),
        "previous": _to_float(previous),
        "change_pct": change_pct,
        "series": series or [],
    }
    return payload


def _date_axis(period: tuple[date, date] | None) -> list[date]:
    if period is None:
        return []
    start, end = period
    days = (end - start).days + 1
    if days <= 0:
        return []
    return [start + timedelta(days=i) for i in range(days)]


def _fill_daily(
    period: tuple[date, date] | None,
    by_date: dict[date, float],
    *,
    default: float = 0.0,
    forward_fill: bool = False,
) -> list[float]:
    axis = _date_axis(period)
    if not axis:
        return []
    out: list[float] = []
    last: float | None = None
    for day in axis:
        if day in by_date:
            last = float(by_date[day])
            out.append(last)
        elif forward_fill and last is not None:
            out.append(last)
        else:
            out.append(default)
    return out


def _trailing_month_range(
    to_date: date,
    watermark: DataWatermark | None,
) -> tuple[date, date] | None:
    """Last ~30 calendar days ending at the watermark-capped dashboard end."""
    if watermark is None or watermark.fact_through_date is None:
        return None
    if watermark.validation_status != ValidationStatus.PASSED:
        return None
    end = min(to_date, watermark.fact_through_date)
    start = end - timedelta(days=DAYS_PER_MONTH - 1)
    return _effective_range(start, end, watermark)


def _baseline_comparison(
    client: Client,
    *,
    current_sessions: float | None,
    current_leads: int | None,
    current_lead_rate: float | None,
    current_window: tuple[date, date] | None,
    sessions_series: list[float] | None = None,
    leads_series: list[float] | None = None,
    lead_rate_series: list[float] | None = None,
) -> dict[str, Any]:
    """Compare trailing ~30d GA4 totals 1:1 against the frozen monthly baseline snapshot."""
    has_baseline = (
        client.baseline_monthly_sessions is not None or client.baseline_monthly_leads is not None
    )
    baseline_rate = _to_float(client.baseline_lead_rate_pct)
    if baseline_rate is None and client.baseline_monthly_sessions and client.baseline_monthly_leads:
        if client.baseline_monthly_sessions > 0:
            baseline_rate = (
                client.baseline_monthly_leads / client.baseline_monthly_sessions
            ) * 100

    window_payload: dict[str, Any] | None = None
    if current_window is not None:
        window_from, window_to = current_window
        window_payload = {
            "from": window_from.isoformat(),
            "to": window_to.isoformat(),
            "days": (window_to - window_from).days + 1,
        }

    tier_name = client.tier.tier_name if getattr(client, "tier", None) is not None else None

    return {
        "configured": has_baseline,
        "as_of": client.baseline_as_of.isoformat() if client.baseline_as_of else None,
        "source": client.baseline_source,
        "notes": client.baseline_notes,
        "tier_name": tier_name,
        "current_window": window_payload,
        "monthly_sessions": client.baseline_monthly_sessions,
        "monthly_leads": client.baseline_monthly_leads,
        "lead_rate": baseline_rate,
        "vs_current": {
            # Trailing month totals compare directly to frozen monthly baseline (no period scaling).
            "sessions": _period_metric(
                current_sessions, client.baseline_monthly_sessions, sessions_series
            ),
            "leads": _period_metric(current_leads, client.baseline_monthly_leads, leads_series),
            "lead_rate": _period_metric(current_lead_rate, baseline_rate, lead_rate_series),
        },
    }


def _load_watermarks(db: Session, client_id: UUID) -> dict[str, DataWatermark]:
    rows = db.query(DataWatermark).filter(DataWatermark.client_id == client_id).all()
    return {row.source: row for row in rows}


def _effective_range(
    from_date: date,
    to_date: date,
    watermark: DataWatermark | None,
) -> tuple[date, date] | None:
    if watermark is None or watermark.fact_through_date is None:
        return None
    if watermark.validation_status != ValidationStatus.PASSED:
        return None
    effective_to = min(to_date, watermark.fact_through_date)
    if effective_to < from_date:
        return None
    return from_date, effective_to


def _freshness(watermarks: dict[str, DataWatermark]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in DASHBOARD_WATERMARK_SOURCES:
        watermark = watermarks.get(source)
        rows.append(
            {
                "source": source,
                "fact_through": watermark.fact_through_date.isoformat()
                if watermark and watermark.fact_through_date
                else None,
                "validation": watermark.validation_status.value
                if watermark and watermark.validation_status
                else None,
                "available": watermark is not None
                and watermark.validation_status == ValidationStatus.PASSED
                and watermark.fact_through_date is not None,
            }
        )
    return rows


def _lead_event_names(db: Session, client_id: UUID) -> list[str]:
    rows = (
        db.query(ConversionDefinition.event_name)
        .filter(
            ConversionDefinition.client_id == client_id,
            ConversionDefinition.active.is_(True),
            ConversionDefinition.conversion_type == "lead",
        )
        .all()
    )
    return [row[0] for row in rows]


def _sum_leads(
    db: Session,
    client_id: UUID,
    event_names: list[str],
    period: tuple[date, date] | None,
) -> int | None:
    if not event_names or period is None:
        return None
    start, end = period
    total = (
        db.query(func.coalesce(func.sum(FactGa4Event.event_count), 0))
        .filter(
            FactGa4Event.client_id == client_id,
            FactGa4Event.date >= start,
            FactGa4Event.date <= end,
            FactGa4Event.event_name.in_(event_names),
        )
        .scalar()
    )
    return int(total or 0)


def _sum_sessions(
    db: Session,
    client_id: UUID,
    period: tuple[date, date] | None,
) -> float | None:
    if period is None:
        return None
    start, end = period
    total = (
        db.query(func.coalesce(func.sum(FactGa4Traffic.sessions), 0))
        .filter(
            FactGa4Traffic.client_id == client_id,
            FactGa4Traffic.date >= start,
            FactGa4Traffic.date <= end,
        )
        .scalar()
    )
    return float(total or 0)


def _daily_ga4_traffic_series(
    db: Session,
    client_id: UUID,
    period: tuple[date, date] | None,
) -> tuple[list[float], list[float]]:
    """Return (sessions_series, views_series) for each day in period."""
    if period is None:
        return [], []
    start, end = period
    rows = (
        db.query(
            FactGa4Traffic.date,
            func.coalesce(func.sum(FactGa4Traffic.sessions), 0),
            func.coalesce(func.sum(FactGa4Traffic.views), 0),
        )
        .filter(
            FactGa4Traffic.client_id == client_id,
            FactGa4Traffic.date >= start,
            FactGa4Traffic.date <= end,
        )
        .group_by(FactGa4Traffic.date)
        .all()
    )
    sessions_by_date = {day: float(sessions or 0) for day, sessions, _ in rows}
    views_by_date = {day: float(views or 0) for day, _, views in rows}
    return (
        _fill_daily(period, sessions_by_date),
        _fill_daily(period, views_by_date),
    )


def _daily_leads_series(
    db: Session,
    client_id: UUID,
    event_names: list[str],
    period: tuple[date, date] | None,
) -> list[float]:
    if not event_names or period is None:
        return []
    start, end = period
    rows = (
        db.query(
            FactGa4Event.date,
            func.coalesce(func.sum(FactGa4Event.event_count), 0),
        )
        .filter(
            FactGa4Event.client_id == client_id,
            FactGa4Event.date >= start,
            FactGa4Event.date <= end,
            FactGa4Event.event_name.in_(event_names),
        )
        .group_by(FactGa4Event.date)
        .all()
    )
    by_date = {day: float(total or 0) for day, total in rows}
    return _fill_daily(period, by_date)


def _daily_lead_rate_series(
    sessions_series: list[float],
    leads_series: list[float],
) -> list[float]:
    if not sessions_series or len(sessions_series) != len(leads_series):
        return []
    out: list[float] = []
    for sessions, leads in zip(sessions_series, leads_series, strict=True):
        out.append((leads / sessions) * 100 if sessions > 0 else 0.0)
    return out


def _daily_gsc_series(
    db: Session,
    client_id: UUID,
    period: tuple[date, date] | None,
) -> tuple[list[float], list[float], list[float], list[float]]:
    """Return (impressions, clicks, ctr_pct, avg_position) daily series."""
    if period is None:
        return [], [], [], []
    start, end = period
    daily_count = (
        db.query(func.count())
        .select_from(FactGscDaily)
        .filter(
            FactGscDaily.client_id == client_id,
            FactGscDaily.date >= start,
            FactGscDaily.date <= end,
        )
        .scalar()
    )
    fact_model = FactGscDaily if daily_count else FactGscPage
    rows = (
        db.query(
            fact_model.date,
            func.coalesce(func.sum(fact_model.impressions), 0),
            func.coalesce(func.sum(fact_model.clicks), 0),
            func.coalesce(func.sum(fact_model.average_position * fact_model.impressions), 0),
        )
        .filter(
            fact_model.client_id == client_id,
            fact_model.date >= start,
            fact_model.date <= end,
        )
        .group_by(fact_model.date)
        .all()
    )
    impressions_by: dict[date, float] = {}
    clicks_by: dict[date, float] = {}
    ctr_by: dict[date, float] = {}
    pos_by: dict[date, float] = {}
    for day, impressions, clicks, weighted_pos in rows:
        impr = float(impressions or 0)
        clk = float(clicks or 0)
        wpos = float(weighted_pos or 0)
        impressions_by[day] = impr
        clicks_by[day] = clk
        ctr_by[day] = (clk / impr) * 100 if impr > 0 else 0.0
        if impr > 0:
            pos_by[day] = wpos / impr
    return (
        _fill_daily(period, impressions_by),
        _fill_daily(period, clicks_by),
        _fill_daily(period, ctr_by),
        _fill_daily(period, pos_by, forward_fill=True),
    )


def _daily_ai_presence_series(
    db: Session,
    client_id: UUID,
    period: tuple[date, date] | None,
) -> dict[str, list[float]]:
    empty = {
        "mention_presence": [],
        "link_presence": [],
        "mention_top3": [],
        "link_top3": [],
    }
    if period is None:
        return empty
    start, end = period
    rows = (
        db.query(FactSerAiTrackerStats)
        .filter(
            FactSerAiTrackerStats.client_id == client_id,
            FactSerAiTrackerStats.metric_date >= start,
            FactSerAiTrackerStats.metric_date <= end,
        )
        .order_by(FactSerAiTrackerStats.metric_date.asc())
        .all()
    )
    mention: dict[date, float] = {}
    link: dict[date, float] = {}
    mention_top3: dict[date, float] = {}
    link_top3: dict[date, float] = {}
    for row in rows:
        day = row.metric_date
        if row.mention_presence_pct is not None:
            mention[day] = float(row.mention_presence_pct)
        if row.link_presence_pct is not None:
            link[day] = float(row.link_presence_pct)
        if row.mention_top3_pct is not None:
            mention_top3[day] = float(row.mention_top3_pct)
        if row.link_top3_pct is not None:
            link_top3[day] = float(row.link_top3_pct)
    return {
        "mention_presence": _fill_daily(period, mention, forward_fill=True),
        "link_presence": _fill_daily(period, link, forward_fill=True),
        "mention_top3": _fill_daily(period, mention_top3, forward_fill=True),
        "link_top3": _fill_daily(period, link_top3, forward_fill=True),
    }


def _daily_site_visibility_series(
    db: Session,
    client_id: UUID,
    period: tuple[date, date] | None,
) -> list[float]:
    if period is None:
        return []
    start, end = period
    rows = (
        db.query(FactSerSiteSummary.metric_date, FactSerSiteSummary.visibility_percent)
        .filter(
            FactSerSiteSummary.client_id == client_id,
            FactSerSiteSummary.metric_date.isnot(None),
            FactSerSiteSummary.metric_date >= start,
            FactSerSiteSummary.metric_date <= end,
            FactSerSiteSummary.visibility_percent.isnot(None),
        )
        .order_by(FactSerSiteSummary.metric_date.asc())
        .all()
    )
    by_date = {day: float(vis) for day, vis in rows if day is not None and vis is not None}
    return _fill_daily(period, by_date, forward_fill=True)


def _lead_rate(leads: int | None, sessions: float | None) -> float | None:
    if leads is None or sessions is None or sessions == 0:
        return None
    return (leads / sessions) * 100


def _leads_by_channel(
    db: Session,
    client_id: UUID,
    event_names: list[str],
    period: tuple[date, date] | None,
) -> list[dict[str, Any]]:
    if not event_names or period is None:
        return []
    start, end = period
    rows = (
        db.query(FactGa4Event.channel, func.coalesce(func.sum(FactGa4Event.event_count), 0))
        .filter(
            FactGa4Event.client_id == client_id,
            FactGa4Event.date >= start,
            FactGa4Event.date <= end,
            FactGa4Event.event_name.in_(event_names),
        )
        .group_by(FactGa4Event.channel)
        .all()
    )
    by_channel = {channel: int(total) for channel, total in rows}
    return [
        {
            "channel": channel.value,
            "label": CHANNEL_LABELS[channel],
            "leads": by_channel.get(channel, 0),
        }
        for channel in OrganicChannel
        if by_channel.get(channel, 0) > 0
    ]


def _gsc_property_metrics(
    db: Session,
    client_id: UUID,
    period: tuple[date, date] | None,
) -> tuple[float | None, float | None, float | None, float | None, str]:
    """Return impressions, clicks, ctr, avg_position, and source table name."""
    if period is None:
        return None, None, None, None, "gsc_daily"
    start, end = period

    daily_count = (
        db.query(func.count())
        .select_from(FactGscDaily)
        .filter(
            FactGscDaily.client_id == client_id,
            FactGscDaily.date >= start,
            FactGscDaily.date <= end,
        )
        .scalar()
    )
    fact_model = FactGscDaily if daily_count else FactGscPage
    source = "gsc_daily" if daily_count else "gsc_pages"

    row = (
        db.query(
            func.coalesce(func.sum(fact_model.impressions), 0),
            func.coalesce(func.sum(fact_model.clicks), 0),
            func.coalesce(
                func.sum(fact_model.average_position * fact_model.impressions),
                0,
            ),
        )
        .filter(
            fact_model.client_id == client_id,
            fact_model.date >= start,
            fact_model.date <= end,
        )
        .one()
    )
    impressions = float(row[0] or 0)
    clicks = float(row[1] or 0)
    weighted_pos = float(row[2] or 0)
    avg_position = weighted_pos / impressions if impressions > 0 else None
    ctr = (clicks / impressions) * 100 if impressions > 0 else None
    return impressions, clicks, ctr if ctr is not None else None, avg_position, source


def _gsc_totals(
    db: Session,
    client_id: UUID,
    period: tuple[date, date] | None,
) -> tuple[float | None, float | None, float | None]:
    impressions, clicks, ctr, _, _ = _gsc_property_metrics(db, client_id, period)
    return impressions, clicks, ctr


def _gsc_weighted_position(
    db: Session,
    client_id: UUID,
    period: tuple[date, date] | None,
) -> float | None:
    _, _, _, avg_position, _ = _gsc_property_metrics(db, client_id, period)
    return avg_position


def _tracked_keyword_position(
    db: Session,
    client_id: UUID,
    period: tuple[date, date] | None,
) -> float | None:
    if period is None:
        return None
    start, end = period
    avg = (
        db.query(func.avg(FactSerKeyword.current_position))
        .filter(
            FactSerKeyword.client_id == client_id,
            FactSerKeyword.checked_at.isnot(None),
            FactSerKeyword.checked_at >= start,
            FactSerKeyword.checked_at <= end,
            FactSerKeyword.current_position.isnot(None),
            FactSerKeyword.current_position > 0,
        )
        .scalar()
    )
    return _to_float(avg)


def _tracked_search_visibility(
    db: Session,
    client_id: UUID,
    period: tuple[date, date] | None,
) -> float | None:
    if period is None:
        return None
    start, end = period
    avg = (
        db.query(func.avg(FactSerKeyword.visibility))
        .filter(
            FactSerKeyword.client_id == client_id,
            FactSerKeyword.checked_at.isnot(None),
            FactSerKeyword.checked_at >= start,
            FactSerKeyword.checked_at <= end,
            FactSerKeyword.visibility.isnot(None),
        )
        .scalar()
    )
    return _to_float(avg)


def _ser_visibility_score(value: Decimal | float | int | None) -> float | None:
    """SE Ranking visibility_percent is on a 0–1 scale (UI shows e.g. 0.1, not 10%)."""
    if value is None:
        return None
    return float(value)


def _latest_site_summary(
    db: Session,
    client_id: UUID,
    period: tuple[date, date] | None,
) -> FactSerSiteSummary | None:
    if period is None:
        return None
    start, end = period
    return (
        db.query(FactSerSiteSummary)
        .filter(
            FactSerSiteSummary.client_id == client_id,
            FactSerSiteSummary.metric_date >= start,
            FactSerSiteSummary.metric_date <= end,
        )
        .order_by(FactSerSiteSummary.metric_date.desc())
        .first()
    )


def _site_summary_visibility(
    db: Session,
    client_id: UUID,
    period: tuple[date, date] | None,
) -> float | None:
    row = _latest_site_summary(db, client_id, period)
    if row is None or row.visibility_percent is None:
        return None
    return _ser_visibility_score(row.visibility_percent)


def _resolve_search_visibility(
    db: Session,
    client_id: UUID,
    period: tuple[date, date] | None,
) -> tuple[float | None, str | None]:
    tracked = _tracked_search_visibility(db, client_id, period)
    if tracked is not None:
        return tracked, "keyword_avg"
    site = _site_summary_visibility(db, client_id, period)
    if site is not None:
        return site, "site_summary"
    return None, None


def _search_sov(
    db: Session,
    client_id: UUID,
    period: tuple[date, date] | None,
) -> float | None:
    if period is None:
        return None
    start, end = period
    site = _latest_site_summary(db, client_id, period)
    if site is None or site.visibility_percent is None:
        return None
    our_visibility = float(site.visibility_percent)
    competitor_rows = (
        db.query(FactSerCompetitor)
        .filter(
            FactSerCompetitor.client_id == client_id,
            FactSerCompetitor.metric_date.isnot(None),
            FactSerCompetitor.metric_date >= start,
            FactSerCompetitor.metric_date <= end,
            FactSerCompetitor.visibility.isnot(None),
        )
        .order_by(
            FactSerCompetitor.metric_date.desc(),
            FactSerCompetitor.updated_at.desc(),
        )
        .all()
    )
    seen_competitors: set[str] = set()
    competitor_sum = 0.0
    for row in competitor_rows:
        if row.competitor_id in seen_competitors:
            continue
        seen_competitors.add(row.competitor_id)
        competitor_sum += float(row.visibility)
    if competitor_sum <= 0:
        return None
    total = our_visibility + competitor_sum
    if total <= 0:
        return None
    return (our_visibility / total) * 100


def _keyword_distribution(
    db: Session,
    client_id: UUID,
    period: tuple[date, date] | None,
) -> dict[str, int]:
    empty = {"top_3": 0, "top_10": 0, "top_20": 0, "beyond_20": 0, "not_ranking": 0}
    if period is None:
        return empty
    start, end = period
    rows = (
        db.query(FactSerKeyword.current_position)
        .filter(
            FactSerKeyword.client_id == client_id,
            FactSerKeyword.checked_at.isnot(None),
            FactSerKeyword.checked_at >= start,
            FactSerKeyword.checked_at <= end,
        )
        .all()
    )
    buckets = empty.copy()
    for (position,) in rows:
        if position is None or position <= 0:
            buckets["not_ranking"] += 1
        elif position <= 3:
            buckets["top_3"] += 1
        elif position <= 10:
            buckets["top_10"] += 1
        elif position <= 20:
            buckets["top_20"] += 1
        else:
            buckets["beyond_20"] += 1
    return buckets


def _latest_ai_tracker_stats_row(
    db: Session,
    client_id: UUID,
    period: tuple[date, date] | None,
) -> FactSerAiTrackerStats | None:
    if period is None:
        return None
    start, end = period
    return (
        db.query(FactSerAiTrackerStats)
        .filter(
            FactSerAiTrackerStats.client_id == client_id,
            FactSerAiTrackerStats.metric_date >= start,
            FactSerAiTrackerStats.metric_date <= end,
        )
        .order_by(FactSerAiTrackerStats.metric_date.desc())
        .first()
    )


def _ai_tracker_metrics(
    db: Session,
    client_id: UUID,
    period: tuple[date, date] | None,
) -> dict[str, float | int | None]:
    empty: dict[str, float | int | None] = {
        "prompt_count": None,
        "mention_presence": None,
        "link_presence": None,
        "mention_top3": None,
        "link_top3": None,
    }
    row = _latest_ai_tracker_stats_row(db, client_id, period)
    if row is None:
        return empty

    return {
        "prompt_count": row.prompts_count,
        "mention_presence": float(row.mention_presence_pct) if row.mention_presence_pct is not None else None,
        "link_presence": float(row.link_presence_pct) if row.link_presence_pct is not None else None,
        "mention_top3": float(row.mention_top3_pct) if row.mention_top3_pct is not None else None,
        "link_top3": float(row.link_top3_pct) if row.link_top3_pct is not None else None,
    }


def _ga4_views(
    db: Session,
    client_id: UUID,
    period: tuple[date, date] | None,
) -> float | None:
    if period is None:
        return None
    start, end = period
    total = (
        db.query(func.coalesce(func.sum(FactGa4Traffic.views), 0))
        .filter(
            FactGa4Traffic.client_id == client_id,
            FactGa4Traffic.date >= start,
            FactGa4Traffic.date <= end,
        )
        .scalar()
    )
    return float(total or 0)


def _traffic_by_channel(
    db: Session,
    client_id: UUID,
    period: tuple[date, date] | None,
    lead_events: list[str] | None = None,
) -> list[dict[str, Any]]:
    if period is None:
        return []
    start, end = period
    rows = (
        db.query(
            FactGa4Traffic.channel,
            func.coalesce(func.sum(FactGa4Traffic.sessions), 0),
            func.coalesce(func.sum(FactGa4Traffic.views), 0),
            func.sum(FactGa4Traffic.engaged_sessions),
        )
        .filter(
            FactGa4Traffic.client_id == client_id,
            FactGa4Traffic.date >= start,
            FactGa4Traffic.date <= end,
        )
        .group_by(FactGa4Traffic.channel)
        .all()
    )

    conversions_by_channel: dict[OrganicChannel, int] = {}
    if lead_events:
        lead_rows = (
            db.query(
                FactGa4Event.channel,
                func.coalesce(func.sum(FactGa4Event.event_count), 0),
            )
            .filter(
                FactGa4Event.client_id == client_id,
                FactGa4Event.date >= start,
                FactGa4Event.date <= end,
                FactGa4Event.event_name.in_(lead_events),
            )
            .group_by(FactGa4Event.channel)
            .all()
        )
        conversions_by_channel = {channel: int(total or 0) for channel, total in lead_rows}

    out: list[dict[str, Any]] = []
    for channel, sessions, views, engaged in rows:
        sessions_f = float(sessions or 0)
        views_f = float(views or 0)
        conversions = conversions_by_channel.get(channel, 0)
        bounce_rate: float | None = None
        if engaged is not None and sessions_f > 0:
            bounce_rate = max(0.0, min(100.0, (1.0 - (float(engaged) / sessions_f)) * 100.0))
        if sessions_f <= 0 and views_f <= 0 and conversions <= 0:
            continue
        out.append(
            {
                "channel": channel.value,
                "label": CHANNEL_LABELS[channel],
                "sessions": sessions_f,
                "views": views_f,
                "conversions": conversions,
                "bounce_rate": bounce_rate,
            }
        )
    return out


def _top_pages(
    db: Session,
    client_id: UUID,
    gsc_period: tuple[date, date] | None,
    ga4_period: tuple[date, date] | None,
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    if gsc_period is None:
        return []
    gsc_start, gsc_end = gsc_period
    gsc_rows = (
        db.query(
            FactGscPage.normalized_url,
            func.coalesce(func.sum(FactGscPage.impressions), 0),
            func.coalesce(func.sum(FactGscPage.clicks), 0),
        )
        .filter(
            FactGscPage.client_id == client_id,
            FactGscPage.date >= gsc_start,
            FactGscPage.date <= gsc_end,
        )
        .group_by(FactGscPage.normalized_url)
        .order_by(func.sum(FactGscPage.clicks).desc())
        .limit(limit)
        .all()
    )
    if not gsc_rows:
        return []

    urls = [row[0] for row in gsc_rows]
    ga4_by_url: dict[str, tuple[float, float]] = {}
    if ga4_period is not None:
        ga4_start, ga4_end = ga4_period
        ga4_rows = (
            db.query(
                FactGa4Traffic.normalized_url,
                func.coalesce(func.sum(FactGa4Traffic.sessions), 0),
                func.coalesce(func.sum(FactGa4Traffic.views), 0),
            )
            .filter(
                FactGa4Traffic.client_id == client_id,
                FactGa4Traffic.date >= ga4_start,
                FactGa4Traffic.date <= ga4_end,
                FactGa4Traffic.normalized_url.in_(urls),
            )
            .group_by(FactGa4Traffic.normalized_url)
            .all()
        )
        ga4_by_url = {
            url: (float(sessions or 0), float(views or 0)) for url, sessions, views in ga4_rows
        }

    pages: list[dict[str, Any]] = []
    for url, impressions, clicks in gsc_rows:
        sessions, views = ga4_by_url.get(url, (0.0, 0.0))
        pages.append(
            {
                "page": url,
                "gsc_impressions": float(impressions or 0),
                "gsc_clicks": float(clicks or 0),
                "ga4_sessions": sessions,
                "ga4_views": views,
            }
        )
    return pages


def build_dashboard(db: Session, client: Client, from_date: date, to_date: date) -> dict[str, Any]:
    watermarks = _load_watermarks(db, client.id)
    prev_from, prev_to = previous_period(from_date, to_date)

    ga4_current = _effective_range(from_date, to_date, watermarks.get("ga4"))
    ga4_previous = _effective_range(prev_from, prev_to, watermarks.get("ga4"))
    gsc_current = _effective_range(from_date, to_date, watermarks.get("gsc_pages"))
    gsc_previous = _effective_range(prev_from, prev_to, watermarks.get("gsc_pages"))
    ser_current = _effective_range(from_date, to_date, watermarks.get("se_ranking_search"))
    ser_previous = _effective_range(prev_from, prev_to, watermarks.get("se_ranking_search"))
    ai_current = _effective_range(from_date, to_date, watermarks.get("se_ranking_ai"))
    ai_previous = _effective_range(prev_from, prev_to, watermarks.get("se_ranking_ai"))

    lead_events = _lead_event_names(db, client.id)
    conversions_configured = len(lead_events) > 0

    current_leads = _sum_leads(db, client.id, lead_events, ga4_current)
    previous_leads = _sum_leads(db, client.id, lead_events, ga4_previous)
    current_sessions = _sum_sessions(db, client.id, ga4_current)
    previous_sessions = _sum_sessions(db, client.id, ga4_previous)
    current_lead_rate = _lead_rate(current_leads, current_sessions)
    previous_lead_rate = _lead_rate(previous_leads, previous_sessions)

    gsc_impressions_current, gsc_clicks_current, gsc_ctr_current = _gsc_totals(
        db, client.id, gsc_current
    )
    gsc_impressions_previous, gsc_clicks_previous, gsc_ctr_previous = _gsc_totals(
        db, client.id, gsc_previous
    )

    tracked_position_current = _tracked_keyword_position(db, client.id, ser_current)
    tracked_position_previous = _tracked_keyword_position(db, client.id, ser_previous)
    gsc_position_current = _gsc_weighted_position(db, client.id, gsc_current)
    gsc_position_previous = _gsc_weighted_position(db, client.id, gsc_previous)
    _, _, _, _, gsc_position_source = _gsc_property_metrics(db, client.id, gsc_current)
    average_position_current = tracked_position_current if tracked_position_current is not None else gsc_position_current
    average_position_previous = (
        tracked_position_previous if tracked_position_previous is not None else gsc_position_previous
    )
    average_position_source = (
        "se_ranking_search" if tracked_position_current is not None else gsc_position_source
    )

    ai_current_metrics = _ai_tracker_metrics(db, client.id, ai_current)
    ai_previous_metrics = _ai_tracker_metrics(db, client.id, ai_previous)

    search_visibility_current, search_visibility_source = _resolve_search_visibility(
        db, client.id, ser_current
    )
    search_visibility_previous, _ = _resolve_search_visibility(db, client.id, ser_previous)

    monthly_goal = client.monthly_lead_goal
    period_goal, goal_period_days = period_lead_goal(monthly_goal, from_date, to_date)
    progress_pct: float | None = None
    if period_goal and current_leads is not None:
        progress_pct = (current_leads / period_goal) * 100

    # Baseline panel always uses trailing ~30d GA4, independent of the page date picker.
    baseline_window = _trailing_month_range(to_date, watermarks.get("ga4"))
    baseline_sessions = _sum_sessions(db, client.id, baseline_window)
    baseline_leads = _sum_leads(db, client.id, lead_events, baseline_window)
    baseline_lead_rate = _lead_rate(baseline_leads, baseline_sessions)
    baseline_sessions_series, _ = _daily_ga4_traffic_series(db, client.id, baseline_window)
    baseline_leads_series = _daily_leads_series(db, client.id, lead_events, baseline_window)
    baseline_lead_rate_series = _daily_lead_rate_series(
        baseline_sessions_series, baseline_leads_series
    )
    baseline_payload = _baseline_comparison(
        client,
        current_sessions=baseline_sessions,
        current_leads=baseline_leads,
        current_lead_rate=baseline_lead_rate,
        current_window=baseline_window,
        sessions_series=baseline_sessions_series,
        leads_series=baseline_leads_series,
        lead_rate_series=baseline_lead_rate_series,
    )

    sessions_series, views_series = _daily_ga4_traffic_series(db, client.id, ga4_current)
    leads_series = _daily_leads_series(db, client.id, lead_events, ga4_current)
    lead_rate_series = _daily_lead_rate_series(sessions_series, leads_series)
    gsc_impr_series, gsc_clicks_series, gsc_ctr_series, gsc_pos_series = _daily_gsc_series(
        db, client.id, gsc_current
    )
    ai_series = _daily_ai_presence_series(db, client.id, ai_current)
    visibility_series = _daily_site_visibility_series(db, client.id, ser_current)
    position_series = gsc_pos_series

    return {
        "period": {
            "from": from_date.isoformat(),
            "to": to_date.isoformat(),
            "previous_from": prev_from.isoformat(),
            "previous_to": prev_to.isoformat(),
        },
        "baseline": baseline_payload,
        "freshness": _freshness(watermarks),
        "conversions": {
            "configured": conversions_configured,
            "lead_events": lead_events,
            "leads": _period_metric(current_leads, previous_leads, leads_series),
            "lead_rate": _period_metric(current_lead_rate, previous_lead_rate, lead_rate_series),
            "leads_by_channel": _leads_by_channel(db, client.id, lead_events, ga4_current),
            "monthly_lead_goal": monthly_goal,
            "period_lead_goal": period_goal,
            "goal_period_days": goal_period_days,
            "goal_progress_pct": progress_pct,
            "leads_series": leads_series,
        },
        "visibility": {
            "search": {
                "search_visibility": _period_metric(
                    search_visibility_current,
                    search_visibility_previous,
                    visibility_series,
                ),
                "search_visibility_source": search_visibility_source,
                "search_sov": _period_metric(
                    _search_sov(db, client.id, ser_current),
                    _search_sov(db, client.id, ser_previous),
                    visibility_series,
                ),
                "search_sov_source": "competitor_visibility",
                "gsc_impressions": _period_metric(
                    gsc_impressions_current, gsc_impressions_previous, gsc_impr_series
                ),
                "average_position": _period_metric(
                    average_position_current, average_position_previous, position_series
                ),
                "average_position_source": average_position_source,
                "keyword_distribution": _keyword_distribution(db, client.id, ser_current),
            },
            "ai": {
                "mention_presence": _period_metric(
                    ai_current_metrics["mention_presence"],
                    ai_previous_metrics["mention_presence"],
                    ai_series["mention_presence"],
                ),
                "link_presence": _period_metric(
                    ai_current_metrics["link_presence"],
                    ai_previous_metrics["link_presence"],
                    ai_series["link_presence"],
                ),
                "mention_top3_presence": _period_metric(
                    ai_current_metrics["mention_top3"],
                    ai_previous_metrics["mention_top3"],
                    ai_series["mention_top3"],
                ),
                "link_top3_presence": _period_metric(
                    ai_current_metrics["link_top3"],
                    ai_previous_metrics["link_top3"],
                    ai_series["link_top3"],
                ),
                "prompt_count": ai_current_metrics["prompt_count"],
                "tracked_prompt_source": "airt_statistics",
            },
        },
        "traffic": {
            "gsc_clicks": _period_metric(
                gsc_clicks_current, gsc_clicks_previous, gsc_clicks_series
            ),
            "gsc_ctr": _period_metric(gsc_ctr_current, gsc_ctr_previous, gsc_ctr_series),
            "ga4_sessions": _period_metric(current_sessions, previous_sessions, sessions_series),
            "ga4_views": _period_metric(
                _ga4_views(db, client.id, ga4_current),
                _ga4_views(db, client.id, ga4_previous),
                views_series,
            ),
            "by_channel": _traffic_by_channel(db, client.id, ga4_current, lead_events),
            "top_pages": _top_pages(db, client.id, gsc_current, ga4_current),
        },
    }
