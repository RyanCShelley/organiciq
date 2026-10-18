"""Explain observed outcomes without collapsing them into a branch score.

Session totals are GA4 visits, not search clicks. Keyword and prompt readings
stay separate. No rank observation, no traffic rows and zero are distinct.
"""
from datetime import date, timedelta

from sqlalchemy import func

from app.models.config import ConversionDefinition
from app.models.ga4 import FactGa4Event, FactGa4Traffic
from app.models.seranking import FactSerKeyword, FactSerRanking
from app.services.lead_goals import current_lead_goal
from app.services.watchlist import read
from app.models.decision import DecisionThreshold
from app.decisions.ctr_curve import ai_overview_curve


def lead_rate_target(db, client_id):
    row = db.query(DecisionThreshold).filter_by(client_id=client_id).one_or_none()
    return (row.thresholds or {}).get("target_lead_rate_pct") if row else None


def session_totals(db, client_id, start, end):
    rows = db.query(FactGa4Traffic.channel, func.sum(FactGa4Traffic.sessions)).filter(
        FactGa4Traffic.client_id == client_id, FactGa4Traffic.date >= start,
        FactGa4Traffic.date <= end,
    ).group_by(FactGa4Traffic.channel).all()
    channels = {channel.value: float(total or 0) for channel, total in rows}
    return {"total": sum(channels.values()) if rows else None, "channels": channels}


def keyword_readings(db, client_id, end):
    """Newest dated observation per term, never a later snapshot in a past run."""
    tracked = {}
    for row in db.query(FactSerRanking).filter(FactSerRanking.client_id == client_id,
            FactSerRanking.date <= end).order_by(FactSerRanking.date.desc()):
        tracked.setdefault((row.keyword or "").strip().lower(), {
            "position": float(row.position) if row.position is not None else None,
            "ranking_url": row.ranking_url, "observed_on": row.date.isoformat()})
    for row in db.query(FactSerKeyword).filter(FactSerKeyword.client_id == client_id,
            FactSerKeyword.checked_at <= end):
        key = (row.keyword or "").strip().lower()
        if key not in tracked or row.checked_at.isoformat() > tracked[key]["observed_on"]:
            tracked[key] = {"position": float(row.current_position) if row.current_position is not None else None,
                "ranking_url": row.ranking_url, "observed_on": row.checked_at.isoformat()}
    return tracked


def measure(db, client, *, end: date):
    start = end.replace(day=1)
    days = (end - start).days + 1
    prior_end = start - timedelta(days=1)
    prior_start = prior_end - timedelta(days=days - 1)
    current = session_totals(db, client.id, start, end)
    previous = session_totals(db, client.id, prior_start, prior_end)
    tracked = keyword_readings(db, client.id, end)
    keywords, prompts = [], []
    for target in read(db, client):
        if target["state"] == "excluded":
            continue
        if target["kind"] == "keyword":
            row = tracked.get(target["text"].strip().lower())
            position = row["position"] if row else None
            # 0/101 are vendor sentinels, an observed absence from the top 100.
            status = "not_measured" if position is None else "top_10" if 0 < position <= 10 else "top_100" if 0 < position <= 100 else "not_in_top_100"
            keywords.append({"text": target["text"], "priority": target["priority"],
                "position": position if position and 0 < position <= 100 else None,
                "status": status, "target_url": target["target_url"],
                "ranking_url": row["ranking_url"] if row else None,
                "observed_on": row["observed_on"] if row else None})
        else:
            observation = target.get("observation") or {}
            observed = observation.get("observed_on")
            usable = bool(observed and observed[:10] <= end.isoformat())
            prompts.append({"text": target["text"], "provider": target["provider"],
                "observed_on": observed if usable else None,
                "mentioned": observation.get("brand_mentioned") if usable else None,
                "cited": observation.get("brand_cited") if usable else None})
    events = [row.event_name for row in db.query(ConversionDefinition).filter(
        ConversionDefinition.client_id == client.id, ConversionDefinition.active.is_(True),
        ConversionDefinition.conversion_type == "lead")]
    leads = None
    if events and current["total"] is not None:
        # Absence of event rows is not proof of zero. An event sync has to
        # provide an observation before this summary calls it measured.
        count, total = db.query(func.count(FactGa4Event.id), func.sum(FactGa4Event.event_count)).filter(
            FactGa4Event.client_id == client.id, FactGa4Event.date >= start,
            FactGa4Event.date <= end, FactGa4Event.event_name.in_(events)).one()
        leads = float(total or 0) if count else None
    goal, checkpoint = current_lead_goal(client, on=end)
    sessions = current["total"]
    return {"version": 2, "start": start.isoformat(), "end": end.isoformat(),
        "prior_start": prior_start.isoformat(), "prior_end": prior_end.isoformat(),
        "visibility": {"keywords": keywords, "prompts": prompts,
            "note": "Each keyword uses its newest dated observation on or before the assessment date. The observation date is shown; older readings may be stale. Unmeasured terms are not treated as absent. Multiple tracker engines currently use the newest reading per term."},
        "traffic": {"current": current, "previous": previous,
            "ctr_reference": {"scope": "Desktop · AI Overviews · industry averages supplied by the account lead",
                "period": "Aug 2026 (CSV column label)",
                "positions": [{"position": p, "ctr_pct": ctr} for p, ctr in ai_overview_curve().items()]},
            "source": "GA4 sessions, all ingested channels. Direct remains direct/unattributed; it is not proof of organic or AI attribution."},
        "leads": {"count": leads, "sessions": sessions,
            "rate_pct": leads / sessions * 100 if leads is not None and sessions else None,
            "monthly_goal": goal, "goal_checkpoint": checkpoint.month if checkpoint else None,
            "target_rate_pct": lead_rate_target(db, client.id),
            "source": "Configured GA4 lead event counts / all-channel GA4 sessions in the same period. Events may include repeats; this is not a unique-lead or qualified-lead rate."}}
