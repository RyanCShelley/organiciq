"""The Ads Accelerator report: the numbers for how a client's Google Ads did in a month.

Totals and the month before, week by week, by ad group, what people searched for, markets and devices. Numbers only.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.ads import AdsDaily, AdsLsaLead, AdsMarketDaily, AdsSearchTerm, ClientAdsAccount
from app.models.client import Client
from app.services.monthly_review import parse_month, previous_month

TERMS_SHOWN = 12


def enabled(client: Client) -> bool:
    return bool((client.service_reporting or {}).get("ad_accelerator"))


def _f(x: Any) -> float:
    return float(x or 0)


def _totals(rows: list[Any]) -> dict[str, Any]:
    imp = sum(r.impressions for r in rows)
    clk = sum(r.clicks for r in rows)
    cost = sum(_f(r.cost) for r in rows)
    conv = sum(_f(r.conversions) for r in rows)
    eligible = sum(getattr(r, "eligible_impressions", 0) for r in rows)
    return {
        "impressions": imp, "clicks": clk, "cost": round(cost, 2), "conversions": round(conv, 1),
        "ctr": round(100 * clk / imp, 2) if imp else None, "avg_cpc": round(cost / clk, 2) if clk else None,
        "cost_per_conversion": round(cost / conv, 2) if conv else None,
        "share": round(100 * imp / eligible, 1) if eligible else None,
    }


def _by(rows: list[Any], key: str) -> list[dict[str, Any]]:
    groups: dict[str, list[Any]] = defaultdict(list)
    for r in rows:
        groups[getattr(r, key) or "Not split"].append(r)
    out = [{"name": k, **_totals(v)} for k, v in groups.items()]
    out.sort(key=lambda g: (-g["cost"], -g["clicks"], g["name"]))
    return out


def _markets(db: Session, client: Client, first: date, last: date) -> list[dict[str, Any]]:
    """By market. Google reports markets apart from ad groups and devices, so they come from their own table; there is no impression share to show."""
    rows = db.query(AdsMarketDaily).filter(AdsMarketDaily.client_id == client.id, AdsMarketDaily.date >= first, AdsMarketDaily.date <= last).all()
    groups: dict[str, list[Any]] = defaultdict(list)
    for r in rows:
        groups[r.market or "Not split"].append(r)
    out = [{"name": k, **_totals(v)} for k, v in groups.items()]
    out.sort(key=lambda g: (-g["cost"], -g["clicks"], g["name"]))
    return out


def _words(value: str) -> str:
    return (value or "Not stated").replace("_", " ").capitalize()


def _lsa(db: Session, client: Client, first: date, last: date, prev_first: date, prev_last: date) -> dict[str, Any] | None:
    """Local Services Ads: the leads created in the month (how many, how they came in, what became of them), and what the account spent."""
    accounts = {a.customer_id for a in db.query(ClientAdsAccount).filter(ClientAdsAccount.client_id == client.id, ClientAdsAccount.kind == "lsa")}
    in_month = db.query(AdsLsaLead).filter(AdsLsaLead.client_id == client.id, AdsLsaLead.date >= first, AdsLsaLead.date <= last).all()
    before = db.query(AdsLsaLead).filter(AdsLsaLead.client_id == client.id, AdsLsaLead.date >= prev_first, AdsLsaLead.date <= prev_last).all()
    if not accounts and not in_month and not before:
        return None
    spend = _totals(db.query(AdsDaily).filter(AdsDaily.client_id == client.id, AdsDaily.account_id.in_(accounts), AdsDaily.date >= first, AdsDaily.date <= last).all()) if accounts else _totals([])
    charged = sum(1 for l in in_month if l.charged)

    def counted(key: str) -> list[dict[str, Any]]:
        n: dict[str, int] = defaultdict(int)
        for l in in_month:
            n[_words(getattr(l, key))] += 1
        return [{"name": k, "leads": v} for k, v in sorted(n.items(), key=lambda kv: (-kv[1], kv[0]))]

    weekly = []
    cursor = first
    while cursor <= last:
        end = min(cursor + timedelta(days=6 - cursor.weekday()), last)
        part = [l for l in in_month if cursor <= l.date <= end]
        if part:
            weekly.append({"week": _week_label(cursor, end), "leads": len(part), "charged": sum(1 for l in part if l.charged)})
        cursor = end + timedelta(days=1)
    return {
        "leads": len(in_month), "charged": charged, "previous": {"leads": len(before), "charged": sum(1 for l in before if l.charged)} if before else None,
        "cost": spend["cost"], "impressions": spend["impressions"], "clicks": spend["clicks"], "cost_per_charged_lead": round(spend["cost"] / charged, 2) if charged and spend["cost"] else None,
        "by_status": counted("lead_status"), "by_type": counted("lead_type"), "weekly": weekly,
    }


def _week_label(start: date, end: date) -> str:
    return f"{start:%b} {start.day}–{end.day}" if start.month == end.month else f"{start:%b} {start.day}–{end:%b} {end.day}"


def _weekly(rows: list[Any], first: date, last: date) -> list[dict[str, Any]]:
    out = []
    cursor = first
    while cursor <= last:
        end = min(cursor + timedelta(days=6 - cursor.weekday()), last)
        part = [r for r in rows if cursor <= r.date <= end]
        if part:
            t = _totals(part)
            out.append({"week": _week_label(cursor, end), "impressions": t["impressions"], "clicks": t["clicks"], "cost": t["cost"], "avg_cpc": t["avg_cpc"]})
        cursor = end + timedelta(days=1)
    return out


def _window(db: Session, client: Client, first: date, last: date) -> list[Any]:
    return db.query(AdsDaily).filter(AdsDaily.client_id == client.id, AdsDaily.date >= first, AdsDaily.date <= last).all()


def report(db: Session, client: Client, month: str) -> dict[str, Any]:
    first, last = parse_month(month)
    if not enabled(client):
        return {"enabled": False, "month": month}
    held = db.query(func.count(AdsDaily.id), func.max(AdsDaily.date), func.max(AdsDaily.source)).filter(AdsDaily.client_id == client.id).one()
    if not held[0]:
        return {"enabled": True, "available": False, "month": month, "reason": "No Google Ads data has been pulled for this client yet."}
    rows = _window(db, client, first, last)
    prev_first, prev_last = parse_month(previous_month(month))
    prev_rows = _window(db, client, prev_first, prev_last)
    terms = (
        db.query(AdsSearchTerm.term, AdsSearchTerm.ad_group, func.sum(AdsSearchTerm.clicks), func.sum(AdsSearchTerm.cost))
        .filter(AdsSearchTerm.client_id == client.id, AdsSearchTerm.date >= first, AdsSearchTerm.date <= last)
        .group_by(AdsSearchTerm.term, AdsSearchTerm.ad_group).order_by(func.sum(AdsSearchTerm.clicks).desc(), func.sum(AdsSearchTerm.cost).desc()).all()
    )
    return {
        "enabled": True, "available": bool(rows), "month": month, "period": {"from": first.isoformat(), "to": last.isoformat(), "through": held[1].isoformat() if held[1] else None},
        "source": held[2], "reason": None if rows else "The ads did not run this month.",
        "totals": _totals(rows), "previous": _totals(prev_rows) if prev_rows else None, "weekly": _weekly(rows, first, last), "groups": _by(rows, "ad_group"),
        "terms": [{"term": t, "ad_group": g, "clicks": int(c or 0), "cost": round(_f(cost), 2)} for t, g, c, cost in terms[:TERMS_SHOWN]],
        "markets": _markets(db, client, first, last), "devices": _by(rows, "device"), "lsa": _lsa(db, client, first, last, prev_first, prev_last),
    }


def summary(db: Session, client: Client, month: str) -> dict[str, Any]:
    """The month's numbers beside the month before, for Organic Insights."""
    full = report(db, client, month)
    if not full.get("enabled") or not full.get("available"):
        return {k: full.get(k) for k in ("enabled", "available", "month", "reason")}
    return {"enabled": True, "available": True, "month": month, "source": full["source"], "totals": full["totals"], "previous": full["previous"]}
