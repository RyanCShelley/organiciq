"""The monthly review: one month at a glance against the month before.

A thin layer over `build_dashboard`, which already measures conversions against the
baseline goal, traffic by channel, search and AI visibility, and the agency-service
split. This adds what a monthly review needs and the dashboard does not give:

- a comparison with the previous *calendar* month (the dashboard compares with an
  equal-length window, so September would be set against 2 to 31 August);
- revenue for ecommerce clients, asked of GA4 live, since the stored pull has none;
- a plain-language summary built from the numbers alone. It states what moved and
  what is missing; it does not guess why.
"""

from __future__ import annotations

import calendar
import re
import time
from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.ingestion.ga4.client import run_report
from app.ingestion.google_credentials import access_token_for_client, client_has_google_credentials
from app.models.client import Client
from app.models.integration import Integration, IntegrationProvider
from app.services.dashboard import build_dashboard

_MONTH = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
ORGANIC = "Organic Search"
_REVENUE_CACHE: dict[tuple[str, str], tuple[float, dict]] = {}
REVENUE_TTL_SECONDS = 600


def parse_month(value: str) -> tuple[date, date]:
    """`2026-09` -> (2026-09-01, 2026-09-30). Raises ValueError for anything else."""
    match = _MONTH.match(value or "")
    if not match:
        raise ValueError("Month must look like 2026-09.")
    year, month = int(match.group(1)), int(match.group(2))
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def previous_month(value: str) -> str:
    first, _ = parse_month(value)
    prior = first - timedelta(days=1)
    return f"{prior.year:04d}-{prior.month:02d}"


def last_complete_month(today: date | None = None) -> str:
    today = today or date.today()
    prior = today.replace(day=1) - timedelta(days=1)
    return f"{prior.year:04d}-{prior.month:02d}"


def pct_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous == 0:
        return None
    return round((current - previous) / previous * 100, 1)


def _pair(current: float | None, previous: float | None) -> dict[str, float | None]:
    return {"current": current, "previous": previous, "change_pct": pct_change(current, previous)}


def _get(source: dict | None, *path: str) -> Any:
    for key in path:
        if not isinstance(source, dict):
            return None
        source = source.get(key)
    return source


def _num(value: Any) -> float | None:
    return None if value is None else float(value)


def _channel(rows: list[dict] | None, key: str) -> dict:
    return next((r for r in rows or [] if r.get("channel") == key), {})


# ── revenue ──────────────────────────────────────────────────────────────────


def _month_revenue(db: Session, client: Client, integration: Integration, first: date, last: date) -> dict:
    rows = run_report(
        access_token=access_token_for_client(db, client.id),
        property_id=integration.external_property_id or "",
        start_date=first,
        end_date=last,
        dimensions=["sessionDefaultChannelGroup"],
        metrics=["purchaseRevenue", "transactions"],
        limit=1000,
    )
    total_revenue = organic_revenue = 0.0
    total_orders = organic_orders = 0.0
    for row in rows:
        dims, metrics = row.get("dimensionValues") or [], row.get("metricValues") or []
        if not dims or len(metrics) < 2:
            continue
        revenue, orders = float(metrics[0].get("value") or 0), float(metrics[1].get("value") or 0)
        total_revenue += revenue
        total_orders += orders
        if str(dims[0].get("value")) == ORGANIC:
            organic_revenue += revenue
            organic_orders += orders
    return {
        "revenue": round(total_revenue, 2),
        "orders": total_orders,
        "organic_revenue": round(organic_revenue, 2),
        "organic_orders": organic_orders,
        "average_order_value": round(total_revenue / total_orders, 2) if total_orders else None,
    }


def revenue_for(db: Session, client: Client, month: str, *, now=time.monotonic) -> dict:
    """`{status: "measured", current, previous, ...}` or `{status: "unavailable", reason}`."""
    integration = (
        db.query(Integration)
        .filter(Integration.client_id == client.id, Integration.provider == IntegrationProvider.GA4)
        .one_or_none()
    )
    if (
        integration is None
        or not integration.external_property_id
        or not client_has_google_credentials(db, client.id)
    ):
        return {"status": "unavailable", "reason": "GA4 is not connected for this client."}

    key = (str(client.id), month)
    cached = _REVENUE_CACHE.get(key)
    if cached and now() - cached[0] < REVENUE_TTL_SECONDS:
        return cached[1]
    try:
        first, last = parse_month(month)
        prev_first, prev_last = parse_month(previous_month(month))
        current = _month_revenue(db, client, integration, first, last)
        previous = _month_revenue(db, client, integration, prev_first, prev_last)
    except Exception as exc:  # noqa: BLE001
        return {"status": "unavailable", "reason": f"GA4 did not return revenue: {exc}"}

    result = {
        "status": "measured",
        "currency_note": "As GA4 reports it; the property's currency.",
        "revenue": _pair(current["revenue"], previous["revenue"]),
        "organic_revenue": _pair(current["organic_revenue"], previous["organic_revenue"]),
        "orders": _pair(current["orders"], previous["orders"]),
        "average_order_value": _pair(current["average_order_value"], previous["average_order_value"]),
    }
    _REVENUE_CACHE[key] = (now(), result)
    return result


# ── assembling ───────────────────────────────────────────────────────────────


def noun_for(model: str | None) -> str:
    return {"ecommerce": "orders", "both": "conversions"}.get(model or "", "leads")


def assemble(current: dict, previous: dict, *, month: str, model: str | None, revenue: dict | None) -> dict:
    """Everything the screen shows, from two dashboards. Pure, so it is easy to test."""
    leads = _pair(_num(_get(current, "conversions", "leads", "current")), _num(_get(previous, "conversions", "leads", "current")))
    sessions = _pair(_num(_get(current, "traffic", "ga4_sessions", "current")), _num(_get(previous, "traffic", "ga4_sessions", "current")))

    org_now = _channel(_get(current, "traffic", "by_channel"), "organic_search")
    org_then = _channel(_get(previous, "traffic", "by_channel"), "organic_search")
    organic_sessions = _pair(_num(org_now.get("sessions")), _num(org_then.get("sessions")))
    lead_now = _channel(_get(current, "conversions", "leads_by_channel"), "organic_search")
    lead_then = _channel(_get(previous, "conversions", "leads_by_channel"), "organic_search")
    organic_leads = _pair(_num(lead_now.get("leads")), _num(lead_then.get("leads")))

    rate = _pair(_num(_get(current, "conversions", "lead_rate", "current")), _num(_get(previous, "conversions", "lead_rate", "current")))
    search = {
        "clicks": _pair(_num(_get(current, "traffic", "gsc_clicks", "current")), _num(_get(previous, "traffic", "gsc_clicks", "current"))),
        "impressions": _pair(
            _num(_get(current, "visibility", "search", "gsc_impressions", "current")),
            _num(_get(previous, "visibility", "search", "gsc_impressions", "current")),
        ),
        "average_position": _pair(
            _num(_get(current, "visibility", "search", "average_position", "current")),
            _num(_get(previous, "visibility", "search", "average_position", "current")),
        ),
        "keywords": _get(current, "visibility", "search", "keyword_distribution"),
    }
    has_search = bool(search["clicks"]["current"] or search["impressions"]["current"])

    goal = {
        "period_goal": _get(current, "conversions", "period_lead_goal"),
        "progress_pct": _num(_get(current, "conversions", "goal_progress_pct")),
        "final_goal": _get(current, "conversions", "final_lead_goal"),
        "checkpoint": _get(current, "conversions", "goal_checkpoint"),
        "baseline_version": _get(current, "baseline", "projection", "baseline_version"),
    }

    services = _get(current, "service_reporting") or {}
    out = {
        "month": month,
        "previous_month": previous_month(month),
        "model": model,
        "noun": noun_for(model),
        "conversions": leads,
        "conversion_rate": rate,
        "organic_conversions": organic_leads,
        "sessions": sessions,
        "organic_sessions": organic_sessions,
        "search": search,
        "has_search_data": has_search,
        "goal": goal,
        "channels": [
            {"label": c.get("label"), "sessions": c.get("sessions"), "conversions": c.get("conversions")}
            for c in (_get(current, "traffic", "by_channel") or [])
        ],
        "top_pages": [
            {
                "page": p.get("page"),
                "sessions": p.get("ga4_sessions"),
                "previous_sessions": p.get("previous_ga4_sessions"),
                "conversions": p.get("ga4_key_events"),
                "clicks": p.get("gsc_clicks"),
            }
            for p in (_get(current, "traffic", "top_pages") or [])[:5]
        ],
        "services": {
            "settings": services.get("settings"),
            "rows": services.get("rows") or [],
            "outside": services.get("outside_services"),
            "note": services.get("note"),
        },
        "freshness": _get(current, "freshness") or [],
        "revenue": revenue,
    }
    out["summary"] = summarise(out)
    return out


def _fmt(n: float | None, digits: int = 0) -> str:
    return "–" if n is None else f"{n:,.{digits}f}"


def _move(change: float | None) -> str:
    if change is None:
        return ""
    if abs(change) < 1:
        return "flat"
    return f"{'up' if change > 0 else 'down'} {abs(change):.0f}%"


def summarise(review: dict) -> list[str]:
    """Plain sentences from the numbers. What moved, against what, and what is missing."""
    lines: list[str] = []
    noun, month, prior = review["noun"], review["month"], review["previous_month"]
    conv = review["conversions"]

    if conv["current"] is not None:
        line = f"{noun.capitalize()}: {_fmt(conv['current'])} in {month}"
        if conv["previous"] is not None:
            move = _move(conv["change_pct"])
            line += f", {move} on {prior} ({_fmt(conv['previous'])})" if move and move != "flat" else f", flat on {prior} ({_fmt(conv['previous'])})"
        goal = review["goal"]
        if goal["period_goal"] and goal["progress_pct"] is not None:
            line += f". That is {goal['progress_pct']:.0f}% of this period's goal of {_fmt(goal['period_goal'])}"
        lines.append(line + ".")

    rev = review.get("revenue")
    if rev and rev.get("status") == "measured":
        total, organic = rev["revenue"], rev["organic_revenue"]
        line = f"Revenue: {_fmt(total['current'])} in {month}"
        move = _move(total["change_pct"])
        if total["previous"] is not None and move:
            line += f", {move} on {prior}"
        if organic["current"] is not None:
            line += f"; {_fmt(organic['current'])} of it came through organic search"
        lines.append(line + ".")
    elif rev and rev.get("status") == "unavailable":
        lines.append(f"Revenue could not be read: {rev.get('reason')}")

    sessions, organic = review["sessions"], review["organic_sessions"]
    if sessions["current"] is not None:
        line = f"Sessions: {_fmt(sessions['current'])}"
        if sessions["change_pct"] is not None:
            line += f", {_move(sessions['change_pct'])} on {prior}"
        if organic["current"] is not None:
            line += f". Organic search brought {_fmt(organic['current'])}"
            if organic["change_pct"] is not None:
                line += f" ({_move(organic['change_pct'])})"
        lines.append(line + ".")

    if review["has_search_data"]:
        clicks = review["search"]["clicks"]
        line = f"Search Console: {_fmt(clicks['current'])} clicks"
        if clicks["change_pct"] is not None:
            line += f", {_move(clicks['change_pct'])} on {prior}"
        lines.append(line + ".")
    else:
        lines.append("There is no Search Console data for this month, so search clicks and impressions are not shown.")

    vis = review.get("visibility")
    if vis:
        s = vis["summary"]
        line = (
            f"Watchlist visibility: {s['showing_in_google']} of {s['terms']} terms showed in Google in {month} "
            f"({_fmt(s['google_impressions'])} impressions, {_fmt(s['google_clicks'])} clicks); "
            f"{s['on_page_one']} averaged page one"
        )
        if vis["bing"]["has_data"]:
            line += f"; {s['showing_in_bing']} showed in Bing"
        lines.append(line + ".")
        llm = vis.get("llm")
        if llm:
            m, c, r = llm["summary"]["mentions"], llm["summary"]["citations"], llm["summary"]["visibility_rate"]
            when = f"in the {llm['run_date']} run" if llm["in_month"] else f"in the latest run ({llm['run_date']}, after {month})"
            ai = f"AI platforms: {round((r['current'] or 0) * 100)}% of discovery answers named or cited the brand {when} ({m['current']} mentions, {c['current']} citations)"
            if r["delta"] is not None:
                ai += f", {'up' if r['delta'] > 0 else 'down' if r['delta'] < 0 else 'unchanged'}" + (f" {abs(round(r['delta'] * 100))} points" if r["delta"] else "") + " on the run before"
            lines.append(ai + ".")

    stale = [f["source"] for f in review.get("freshness", []) if not f.get("available")]
    if stale:
        lines.append("No data yet from: " + ", ".join(stale) + ".")
    return lines


def build_review(db: Session, client: Client, month: str) -> dict:
    first, last = parse_month(month)
    yesterday = date.today() - timedelta(days=1)
    last = min(last, yesterday) if first <= yesterday else last
    prev_first, prev_last = parse_month(previous_month(month))
    current = build_dashboard(db, client, first, last)
    previous = build_dashboard(db, client, prev_first, prev_last)
    db.commit()

    revenue = None
    if client.business_model in ("ecommerce", "both"):
        revenue = revenue_for(db, client, month)
    result = assemble(current, previous, month=month, model=client.business_model, revenue=revenue)

    from app.services.review_visibility import build_visibility  # imported here: it imports this module

    result["visibility"] = build_visibility(db, client, month)
    result["summary"] = summarise(result)
    return result
