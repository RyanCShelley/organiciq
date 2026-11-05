"""The Ads Accelerator report: how a client's Google Ads did in a month, in the order of the report sent to clients.

Overview and the month before, week by week, by ad group, what people searched for, markets, devices, networks, the work done on the account
(notes people write), and, when the account was changed during the month, the days before and after the latest change. The summary is written from
the numbers in plain sentences.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.ads import AdsDaily, AdsNote, AdsSearchTerm
from app.models.client import Client
from app.services.monthly_review import parse_month, previous_month

TERMS_SHOWN = 12
#: A change counts as a split of the month only when it leaves at least this many days on each side.
SPLIT_MIN_DAYS = 3


def enabled(client: Client) -> bool:
    return bool((client.service_reporting or {}).get("ad_accelerator"))


def _f(x: Any) -> float:
    return float(x or 0)


def _totals(rows: list[Any]) -> dict[str, Any]:
    imp = sum(r.impressions for r in rows)
    clk = sum(r.clicks for r in rows)
    cost = sum(_f(r.cost) for r in rows)
    conv = sum(_f(r.conversions) for r in rows)
    eligible = sum(r.eligible_impressions for r in rows)
    return {
        "impressions": imp, "clicks": clk, "cost": round(cost, 2), "conversions": round(conv, 1),
        "ctr": round(100 * clk / imp, 2) if imp else None, "avg_cpc": round(cost / clk, 2) if clk else None,
        "cost_per_conversion": round(cost / conv, 2) if conv else None,
        "share": round(100 * imp / eligible, 1) if eligible else None,
        "missed_budget": round(100 * sum(r.lost_budget for r in rows) / eligible, 1) if eligible else None,
        "missed_rank": round(100 * sum(r.lost_rank for r in rows) / eligible, 1) if eligible else None,
    }


def _by(rows: list[Any], key: str) -> list[dict[str, Any]]:
    groups: dict[str, list[Any]] = defaultdict(list)
    for r in rows:
        groups[getattr(r, key) or "Not split"].append(r)
    out = [{"name": k, **_totals(v)} for k, v in groups.items()]
    out.sort(key=lambda g: (-g["cost"], -g["clicks"], g["name"]))
    return out


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


def _split(rows: list[Any], notes: list[AdsNote], first: date, last: date) -> dict[str, Any] | None:
    """The days before and after the month's latest change to the account, when it leaves enough days on both sides."""
    if not rows:
        return None
    last = min(last, max(r.date for r in rows))  # the days the data covers, not the days the month has
    for note in sorted(notes, key=lambda n: n.date, reverse=True):
        if first + timedelta(days=SPLIT_MIN_DAYS) <= note.date <= last - timedelta(days=SPLIT_MIN_DAYS):
            running = sorted({r.date for r in rows if r.impressions})
            start = running[0] if running else first
            before = [r for r in rows if start <= r.date < note.date]
            after = [r for r in rows if r.date >= note.date]
            if not before or not after:
                continue
            days_before, days_after = (note.date - start).days, (last - note.date).days + 1
            b, a = _totals(before), _totals(after)
            b["clicks_per_day"], a["clicks_per_day"] = round(b["clicks"] / days_before, 1), round(a["clicks"] / days_after, 1)
            return {
                "date": note.date.isoformat(), "label": f"{note.date:%b} {note.date.day}", "note": note.text,
                "before": {**b, "from": start.isoformat(), "days": days_before}, "after": {**a, "from": note.date.isoformat(), "days": days_after},
            }
    return None


def _money(x: float | None) -> str:
    return "—" if x is None else f"${x:,.2f}"


def _summary(month_label: str, t: dict[str, Any], prev: dict[str, Any] | None, split: dict[str, Any] | None, groups: list[dict[str, Any]], terms_clicks: int) -> list[str]:
    if not t["impressions"]:
        return [f"The ads did not run in {month_label}."]
    first = (
        f"In {month_label} the ads showed {t['impressions']:,} times and brought {t['clicks']:,} click{'' if t['clicks'] == 1 else 's'} to the site"
        + (f", at an average cost of {_money(t['avg_cpc'])} a click, for {_money(t['cost'])} in all." if t["clicks"] else f". They cost {_money(t['cost'])}.")
    )
    if prev and prev["clicks"] and t["clicks"]:
        change = round(100 * (t["clicks"] / prev["clicks"] - 1))
        first += f" That is {abs(change)}% {'more' if change >= 0 else 'fewer'} clicks than the month before."
    out = [first]
    if split and split["before"]["share"] is not None and split["after"]["share"] is not None:
        b, a = split["before"], split["after"]
        out.append(
            f"After the {split['label']} changes, the ads appeared on {a['share']:.0f}% of the searches they could have shown on, against {b['share']:.0f}% before, "
            f"and daily clicks went from {b['clicks_per_day']:g} to {a['clicks_per_day']:g}."
        )
    if groups and t["cost"] and len(groups) > 1:
        top = groups[0]
        out.append(f"{top['name']} took {round(100 * top['cost'] / t['cost'])}% of the spend and {top['clicks']:,} of the clicks.")
    if t["conversions"]:
        out.append(f"The ads brought {t['conversions']:g} conversion{'' if t['conversions'] == 1 else 's'}" + (f", at {_money(t['cost_per_conversion'])} each." if t["cost_per_conversion"] else "."))
    elif t["clicks"]:
        out.append("No conversions were recorded from the ads this month. If that is unexpected, check that conversion tracking is passing leads back to Google Ads.")
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
    notes = db.query(AdsNote).filter(AdsNote.client_id == client.id, AdsNote.date >= first, AdsNote.date <= last).order_by(AdsNote.date, AdsNote.created_at).all()
    totals = _totals(rows)
    prev = _totals(prev_rows) if prev_rows else None
    groups = _by(rows, "ad_group")
    terms = (
        db.query(AdsSearchTerm.term, AdsSearchTerm.ad_group, func.sum(AdsSearchTerm.clicks), func.sum(AdsSearchTerm.cost))
        .filter(AdsSearchTerm.client_id == client.id, AdsSearchTerm.date >= first, AdsSearchTerm.date <= last)
        .group_by(AdsSearchTerm.term, AdsSearchTerm.ad_group).order_by(func.sum(AdsSearchTerm.clicks).desc(), func.sum(AdsSearchTerm.cost).desc()).all()
    )
    listed_clicks = sum(int(c or 0) for _, _, c, _ in terms)
    split = _split(rows, notes, first, last)
    networks = _by(rows, "network")
    return {
        "enabled": True, "available": bool(rows), "month": month, "period": {"from": first.isoformat(), "to": last.isoformat(), "through": held[1].isoformat() if held[1] else None},
        "source": held[2], "reason": None if rows else "The ads did not run this month.",
        "totals": totals, "previous": prev, "weekly": _weekly(rows, first, last), "groups": groups,
        "terms": [{"term": t, "ad_group": g, "clicks": int(c or 0), "cost": round(_f(cost), 2)} for t, g, c, cost in terms[:TERMS_SHOWN]],
        "terms_note": f"Google lists the individual searches behind {listed_clicks:,} of the {totals['clicks']:,} clicks; searches made by only a few people are not shown." if totals["clicks"] else None,
        "markets": _by(rows, "market"), "devices": _by(rows, "device"), "networks": networks,
        "only_search": len(networks) == 1 and networks[0]["name"].lower() == "search",
        "notes": [{"id": str(n.id), "date": n.date.isoformat(), "text": n.text, "by": n.created_by} for n in notes],
        "split": split,
        "summary": _summary(f"{first:%B}", totals, prev, split, groups, listed_clicks),
    }


def summary(db: Session, client: Client, month: str) -> dict[str, Any]:
    """The few numbers the monthly review and Organic Insights show: the month, the month before, and what drove it."""
    full = report(db, client, month)
    if not full.get("enabled") or not full.get("available"):
        return {k: full.get(k) for k in ("enabled", "available", "month", "reason")}
    return {
        "enabled": True, "available": True, "month": month, "source": full["source"], "totals": full["totals"], "previous": full["previous"],
        "top_group": full["groups"][0] if full["groups"] else None, "top_term": full["terms"][0] if full["terms"] else None,
        "text": full["summary"][0] if full["summary"] else None,
    }
