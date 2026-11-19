"""3-Pillar Baseline Snapshot: Visibility + Traffic + Leads (30-day avg + 90-day total).

Captured inside `BaselineVersion.snapshot["pillars"]` when a baseline is locked,
and previewable live before locking with CSV export.
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.llm_visibility import report as llm_report
from app.models.bing_stats import FactBingQueryStat
from app.models.client import Client
from app.models.config import OrganicChannel
from app.models.ga4 import FactGa4Event, FactGa4Traffic
from app.models.gsc import FactGscDaily
from app.models.llm_visibility import LlmResponse, LlmRun
from app.models.seranking import FactSerRanking
from app.models.site_health import SiteHealthSnapshot
from app.models.watchlist import WatchlistKeyword
from app.services import lead_conversions


def _pair(val_30d: float, val_90d: float) -> dict[str, float]:
    return {
        "avg_30d": round(val_90d / 3.0, 2),
        "recent_30d": round(val_30d, 2),
        "total_90d": round(val_90d, 2),
    }


def _weighted_avg(num: float, den: float) -> float | None:
    return round(num / den, 2) if den > 0 else None


def _gsc_pillar(db: Session, client_id: Any, start_30d: date, start_90d: date, end_date: date) -> dict[str, Any]:
    rows = (
        db.query(
            FactGscDaily.date,
            func.sum(FactGscDaily.clicks).label("clicks"),
            func.sum(FactGscDaily.impressions).label("impressions"),
            func.sum(FactGscDaily.average_position * FactGscDaily.impressions).label("pos_weighted"),
        )
        .filter(FactGscDaily.client_id == client_id, FactGscDaily.date >= start_90d, FactGscDaily.date <= end_date)
        .group_by(FactGscDaily.date)
        .all()
    )
    c30 = i30 = pw30 = 0.0
    c90 = i90 = pw90 = 0.0
    for row in rows:
        clicks = float(row.clicks or 0)
        impr = float(row.impressions or 0)
        pw = float(row.pos_weighted or 0)
        c90 += clicks
        i90 += impr
        pw90 += pw
        if row.date >= start_30d:
            c30 += clicks
            i30 += impr
            pw30 += pw
    return {
        "clicks": _pair(c30, c90),
        "impressions": _pair(i30, i90),
        "ctr_30d_pct": round((c30 / i30) * 100.0, 2) if i30 > 0 else None,
        "ctr_90d_pct": round((c90 / i90) * 100.0, 2) if i90 > 0 else None,
        "avg_position_30d": _weighted_avg(pw30, i30),
        "avg_position_90d": _weighted_avg(pw90, i90),
    }


def _bing_pillar(db: Session, client_id: Any, start_30d: date, start_90d: date, end_date: date) -> dict[str, Any]:
    rows = (
        db.query(
            FactBingQueryStat.week_start,
            FactBingQueryStat.clicks,
            FactBingQueryStat.impressions,
            FactBingQueryStat.avg_impression_position,
        )
        .filter(
            FactBingQueryStat.client_id == client_id,
            FactBingQueryStat.week_start >= start_90d,
            FactBingQueryStat.week_start <= end_date,
        )
        .all()
    )
    c30 = i30 = pw30 = 0.0
    c90 = i90 = pw90 = 0.0
    for row in rows:
        clicks = float(row.clicks or 0)
        impr = float(row.impressions or 0)
        pos = float(row.avg_impression_position) if row.avg_impression_position is not None else None
        c90 += clicks
        i90 += impr
        if pos is not None:
            pw90 += pos * impr
        if row.week_start >= start_30d:
            c30 += clicks
            i30 += impr
            if pos is not None:
                pw30 += pos * impr
    return {
        "clicks": _pair(c30, c90),
        "impressions": _pair(i30, i90),
        "avg_position_30d": _weighted_avg(pw30, i30),
        "avg_position_90d": _weighted_avg(pw90, i90),
    }


def _watchlist_pillar(db: Session, client_id: Any, end_date: date) -> dict[str, Any]:
    keywords = db.query(WatchlistKeyword).filter(WatchlistKeyword.client_id == client_id).all()
    paired = sum(1 for kw in keywords if (kw.paired_ai_prompt or "").strip())
    latest_date = (
        db.query(func.max(FactSerRanking.date))
        .filter(FactSerRanking.client_id == client_id, FactSerRanking.date <= end_date)
        .scalar()
    )
    ranked = top_3 = top_10 = 0
    avg_position: float | None = None
    if latest_date is not None:
        ranks = (
            db.query(FactSerRanking.position)
            .filter(FactSerRanking.client_id == client_id, FactSerRanking.date == latest_date)
            .all()
        )
        positions = [float(r.position) for r in ranks if r.position is not None and float(r.position) > 0]
        ranked = len(positions)
        top_3 = sum(1 for p in positions if p <= 3)
        top_10 = sum(1 for p in positions if p <= 10)
        avg_position = round(sum(positions) / len(positions), 2) if positions else None
    return {
        "tracked_keywords": len(keywords),
        "paired_ai_prompts": paired,
        "rankings_date": latest_date.isoformat() if latest_date else None,
        "ranked_keywords": ranked,
        "top_3": top_3,
        "top_10": top_10,
        "avg_position": avg_position,
    }


def _llm_pillar(db: Session, client: Client, end_date: date) -> dict[str, Any]:
    cutoff = datetime.combine(end_date, time.max, tzinfo=timezone.utc)
    run = (
        db.query(LlmRun)
        .filter(LlmRun.client_id == client.id, LlmRun.status == "completed", LlmRun.started_at <= cutoff)
        .order_by(LlmRun.started_at.desc())
        .first()
    )
    if run is None:
        return {
            "run_date": None,
            "visibility_rate_pct": None,
            "mentions": None,
            "citations": None,
            "share_of_voice_pct": None,
        }
    rows = db.query(LlmResponse).filter(LlmResponse.run_id == run.id).all()
    summary = llm_report.summary(rows, None)
    valid = [r for r in rows if not r.error and not r.asked_by_name]
    sov_pct = (
        round((sum(1 for r in valid if r.brand_mentioned) / len(valid)) * 100.0, 1)
        if valid
        else None
    )
    return {
        "run_date": run.started_at.date().isoformat(),
        "visibility_rate_pct": round(float(summary["visibility_rate"]["current"]) * 100.0, 1),
        "mentions": int(summary["mentions"]["current"]),
        "citations": int(summary["citations"]["current"]),
        "share_of_voice_pct": sov_pct,
    }


def _site_health_pillar(db: Session, client_id: Any, end_date: date) -> dict[str, Any]:
    snap = (
        db.query(SiteHealthSnapshot)
        .filter(SiteHealthSnapshot.client_id == client_id, SiteHealthSnapshot.crawl_date <= end_date)
        .order_by(SiteHealthSnapshot.crawl_date.desc())
        .first()
    )
    if snap is None:
        return {"month": None, "crawl_date": None, "seo_score": None, "geo_score": None}
    payload = snap.payload or {}
    return {
        "month": snap.month,
        "crawl_date": snap.crawl_date.isoformat(),
        "seo_score": (payload.get("seo") or {}).get("score"),
        "geo_score": (payload.get("geo") or {}).get("score"),
    }


def _traffic_pillar(db: Session, client_id: Any, start_30d: date, start_90d: date, end_date: date) -> dict[str, Any]:
    channel_rows = (
        db.query(
            FactGa4Traffic.channel,
            FactGa4Traffic.date,
            func.sum(FactGa4Traffic.sessions).label("sessions"),
        )
        .filter(
            FactGa4Traffic.client_id == client_id,
            FactGa4Traffic.date >= start_90d,
            FactGa4Traffic.date <= end_date,
        )
        .group_by(FactGa4Traffic.channel, FactGa4Traffic.date)
        .all()
    )
    by_channel: dict[str, list[float]] = {}
    tot30 = tot90 = org30 = org90 = 0.0
    for row in channel_rows:
        ch = row.channel.value if hasattr(row.channel, "value") else str(row.channel)
        sess = float(row.sessions or 0)
        bucket = by_channel.setdefault(ch, [0.0, 0.0])
        bucket[1] += sess
        tot90 += sess
        if ch == OrganicChannel.ORGANIC_SEARCH.value:
            org90 += sess
        if row.date >= start_30d:
            bucket[0] += sess
            tot30 += sess
            if ch == OrganicChannel.ORGANIC_SEARCH.value:
                org30 += sess

    channels = [
        {"channel": ch, **_pair(vals[0], vals[1])}
        for ch, vals in sorted(by_channel.items(), key=lambda kv: kv[1][1], reverse=True)
    ]

    page_rows = (
        db.query(
            FactGa4Traffic.normalized_url,
            FactGa4Traffic.date,
            func.sum(FactGa4Traffic.sessions).label("sessions"),
        )
        .filter(
            FactGa4Traffic.client_id == client_id,
            FactGa4Traffic.date >= start_90d,
            FactGa4Traffic.date <= end_date,
        )
        .group_by(FactGa4Traffic.normalized_url, FactGa4Traffic.date)
        .all()
    )
    by_page: dict[str, list[float]] = {}
    for row in page_rows:
        sess = float(row.sessions or 0)
        bucket = by_page.setdefault(row.normalized_url, [0.0, 0.0])
        bucket[1] += sess
        if row.date >= start_30d:
            bucket[0] += sess

    top_pages = [
        {"url": url, **_pair(vals[0], vals[1])}
        for url, vals in sorted(by_page.items(), key=lambda kv: kv[1][1], reverse=True)[:20]
    ]
    return {
        "total_sessions": _pair(tot30, tot90),
        "organic_sessions": _pair(org30, org90),
        "channels": channels,
        "top_pages": top_pages,
    }


def _leads_pillar(
    db: Session,
    client_id: Any,
    events: list[str],
    start_30d: date,
    start_90d: date,
    end_date: date,
    sessions_30d: float,
    sessions_90d: float,
) -> dict[str, Any]:
    if not events:
        return {
            "lead_events": [],
            "total": _pair(0.0, 0.0),
            "lead_rate_30d_pct": None,
            "lead_rate_90d_pct": None,
            "by_event": [],
        }
    rows = (
        db.query(
            FactGa4Event.event_name,
            FactGa4Event.date,
            func.sum(FactGa4Event.event_count).label("events"),
        )
        .filter(
            FactGa4Event.client_id == client_id,
            FactGa4Event.event_name.in_(events),
            FactGa4Event.date >= start_90d,
            FactGa4Event.date <= end_date,
        )
        .group_by(FactGa4Event.event_name, FactGa4Event.date)
        .all()
    )
    by_event: dict[str, list[float]] = {name: [0.0, 0.0] for name in events}
    tot30 = tot90 = 0.0
    for row in rows:
        cnt = float(row.events or 0)
        bucket = by_event.setdefault(row.event_name, [0.0, 0.0])
        bucket[1] += cnt
        tot90 += cnt
        if row.date >= start_30d:
            bucket[0] += cnt
            tot30 += cnt
    return {
        "lead_events": list(events),
        "total": _pair(tot30, tot90),
        "lead_rate_30d_pct": round((tot30 / sessions_30d) * 100.0, 2) if sessions_30d > 0 else None,
        "lead_rate_90d_pct": round((tot90 / sessions_90d) * 100.0, 2) if sessions_90d > 0 else None,
        "by_event": [
            {"event_name": name, **_pair(vals[0], vals[1])}
            for name, vals in sorted(by_event.items(), key=lambda kv: kv[1][1], reverse=True)
        ],
    }


def build_pillars_snapshot(
    db: Session,
    client: Client,
    *,
    as_of: date | None = None,
    lead_events: list[str] | None = None,
) -> dict[str, Any]:
    """Capture starting Visibility, Traffic, and Leads (30-day avg + 90-day total)."""
    end_date = as_of or date.today()
    start_30d = end_date - timedelta(days=29)
    start_90d = end_date - timedelta(days=89)
    events = lead_events if lead_events is not None else lead_conversions.active_lead_events(db, client.id)

    traffic = _traffic_pillar(db, client.id, start_30d, start_90d, end_date)
    leads = _leads_pillar(
        db,
        client.id,
        events,
        start_30d,
        start_90d,
        end_date,
        traffic["total_sessions"]["recent_30d"],
        traffic["total_sessions"]["total_90d"],
    )
    visibility = {
        "gsc": _gsc_pillar(db, client.id, start_30d, start_90d, end_date),
        "bing": _bing_pillar(db, client.id, start_30d, start_90d, end_date),
        "watchlist": _watchlist_pillar(db, client.id, end_date),
        "llm": _llm_pillar(db, client, end_date),
        "site_health": _site_health_pillar(db, client.id, end_date),
    }
    return {
        "window": {
            "as_of": end_date.isoformat(),
            "start_30d": start_30d.isoformat(),
            "start_90d": start_90d.isoformat(),
        },
        "visibility": visibility,
        "traffic": traffic,
        "leads": leads,
    }


def pillars_to_csv(pillars: dict[str, Any]) -> str:
    """Serialize a 3-pillar baseline snapshot to CSV."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Pillar", "Category", "Metric / Item", "30-Day Avg", "Last 30 Days", "90-Day Total", "Notes"])

    vis = pillars.get("visibility") or {}
    gsc = vis.get("gsc") or {}
    for key, label in [("clicks", "Clicks"), ("impressions", "Impressions")]:
        m = gsc.get(key) or {}
        writer.writerow(["Visibility", "GSC", label, m.get("avg_30d"), m.get("recent_30d"), m.get("total_90d"), ""])
    writer.writerow([
        "Visibility",
        "GSC",
        "CTR (%)",
        "",
        gsc.get("ctr_30d_pct"),
        gsc.get("ctr_90d_pct"),
        "",
    ])
    writer.writerow([
        "Visibility",
        "GSC",
        "Avg Position",
        "",
        gsc.get("avg_position_30d"),
        gsc.get("avg_position_90d"),
        "",
    ])

    bing = vis.get("bing") or {}
    for key, label in [("clicks", "Clicks"), ("impressions", "Impressions")]:
        m = bing.get(key) or {}
        writer.writerow(["Visibility", "Bing", label, m.get("avg_30d"), m.get("recent_30d"), m.get("total_90d"), ""])
    writer.writerow([
        "Visibility",
        "Bing",
        "Avg Position",
        "",
        bing.get("avg_position_30d"),
        bing.get("avg_position_90d"),
        "",
    ])

    wl = vis.get("watchlist") or {}
    writer.writerow([
        "Visibility",
        "Watchlist",
        "Tracked Keywords",
        "",
        wl.get("tracked_keywords"),
        "",
        f"Paired AI prompts: {wl.get('paired_ai_prompts')}; Top 3: {wl.get('top_3')}; Top 10: {wl.get('top_10')}; Avg pos: {wl.get('avg_position')}",
    ])

    llm = vis.get("llm") or {}
    writer.writerow([
        "Visibility",
        "LLM & SoV",
        "Visibility Rate (%)",
        "",
        llm.get("visibility_rate_pct"),
        "",
        f"Run: {llm.get('run_date')}; SoV: {llm.get('share_of_voice_pct')}%; Mentions: {llm.get('mentions')}; Citations: {llm.get('citations')}",
    ])

    sh = vis.get("site_health") or {}
    writer.writerow([
        "Visibility",
        "Site Health",
        "SEO / GEO Score",
        "",
        sh.get("seo_score"),
        "",
        f"GEO: {sh.get('geo_score')}; Crawl: {sh.get('crawl_date')}",
    ])

    traf = pillars.get("traffic") or {}
    for key, label in [("total_sessions", "Total Sessions"), ("organic_sessions", "Organic Search Sessions")]:
        m = traf.get(key) or {}
        writer.writerow(["Traffic", "Summary", label, m.get("avg_30d"), m.get("recent_30d"), m.get("total_90d"), ""])
    for ch in traf.get("channels") or []:
        writer.writerow(["Traffic", "Channel", ch.get("channel"), ch.get("avg_30d"), ch.get("recent_30d"), ch.get("total_90d"), ""])
    for pg in traf.get("top_pages") or []:
        writer.writerow(["Traffic", "Top Page", pg.get("url"), pg.get("avg_30d"), pg.get("recent_30d"), pg.get("total_90d"), ""])

    leads = pillars.get("leads") or {}
    tot = leads.get("total") or {}
    writer.writerow([
        "Leads",
        "Summary",
        "Total Leads",
        tot.get("avg_30d"),
        tot.get("recent_30d"),
        tot.get("total_90d"),
        f"Lead rate 30d: {leads.get('lead_rate_30d_pct')}%; 90d: {leads.get('lead_rate_90d_pct')}%",
    ])
    for ev in leads.get("by_event") or []:
        writer.writerow(["Leads", "Event", ev.get("event_name"), ev.get("avg_30d"), ev.get("recent_30d"), ev.get("total_90d"), ""])

    return buf.getvalue()
