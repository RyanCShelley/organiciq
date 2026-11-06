"""Ask Google Ads, account by account, what it will give us, and say what works, what comes back empty, and what is refused.

Each check is one read-only query over the last 30 days. A check is "ok" when rows come back, "empty" when the query worked but there was nothing
to return (no spend, no leads, no search terms), and "error" when Google refused it, with Google's own reason. Nothing is stored.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.integrations import google_ads
from app.models.ads import ClientAdsAccount
from app.models.client import Client
from app.services import ads_pull

DAYS = 30
SAMPLE_CHARS = 500

ACCOUNT = "SELECT customer.id, customer.descriptive_name, customer.currency_code, customer.manager, customer.test_account FROM customer"
CAMPAIGNS = "SELECT campaign.id, campaign.name, campaign.status, campaign.advertising_channel_type FROM campaign"
LEADS = (
    "SELECT local_services_lead.id, local_services_lead.lead_type, local_services_lead.lead_status, local_services_lead.lead_charged, local_services_lead.category_id, "
    "local_services_lead.creation_date_time FROM local_services_lead WHERE local_services_lead.creation_date_time >= '{start} 00:00:00'"
)


def _money(x: float) -> str:
    return f"${x:,.2f}"


def _counts(rows: list[dict[str, Any]], pick: Callable[[dict[str, Any]], str]) -> str:
    return ", ".join(f"{n} {k}" for k, n in Counter(pick(r) for r in rows).most_common())


def _account(rows: list[dict[str, Any]]) -> str:
    c = rows[0].get("customer") or {}
    flags = [f for f, on in (("a manager account", c.get("manager")), ("a test account", c.get("testAccount"))) if on]
    return f"{c.get('descriptiveName') or c.get('id')} ({c.get('currencyCode') or 'currency unknown'})" + (f", {' and '.join(flags)}" if flags else "")


def _campaigns(rows: list[dict[str, Any]]) -> str:
    kinds = _counts(rows, lambda r: str((r.get("campaign") or {}).get("advertisingChannelType") or "unknown").replace("_", " ").title())
    enabled = sum(1 for r in rows if (r.get("campaign") or {}).get("status") == "ENABLED")
    return f"{kinds}; {enabled} enabled"


def _performance(rows: list[dict[str, Any]]) -> str:
    imp = sum(int(float((r.get("metrics") or {}).get("impressions") or 0)) for r in rows)
    clk = sum(int(float((r.get("metrics") or {}).get("clicks") or 0)) for r in rows)
    cost = sum(float((r.get("metrics") or {}).get("costMicros") or 0) for r in rows) / 1_000_000
    days = len({(r.get("segments") or {}).get("date") for r in rows})
    return f"{days} days, {imp:,} impressions, {clk:,} clicks, {_money(cost)}"


def _terms(rows: list[dict[str, Any]]) -> str:
    clk = sum(int(float((r.get("metrics") or {}).get("clicks") or 0)) for r in rows)
    return f"{len({(r.get('searchTermView') or {}).get('searchTerm') for r in rows})} searches behind {clk:,} clicks"


def _markets(rows: list[dict[str, Any]]) -> str:
    return f"{len({(r.get('geographicView') or {}).get('countryCriterionId') for r in rows})} countries"


def _leads(rows: list[dict[str, Any]]) -> str:
    lead = lambda r: r.get("localServicesLead") or {}  # noqa: E731
    charged = sum(1 for r in rows if lead(r).get("leadCharged"))
    return f"{len(rows)} leads: {_counts(rows, lambda r: str(lead(r).get('leadType') or 'unknown').replace('_', ' ').lower())}; {_counts(rows, lambda r: str(lead(r).get('leadStatus') or 'unknown').replace('_', ' ').lower())}; {charged} charged"


def _check(name: str, token: str, customer: str, query: str, say: Callable[[list[dict[str, Any]]], str], empty: str) -> dict[str, Any]:
    try:
        rows = google_ads.search(token, customer, query)
    except google_ads.GoogleAdsError as exc:
        return {"name": name, "status": "error", "detail": str(exc), "rows": 0, "sample": None}
    if not rows:
        return {"name": name, "status": "empty", "detail": empty, "rows": 0, "sample": None}
    return {"name": name, "status": "ok", "detail": say(rows), "rows": len(rows), "sample": json.dumps(rows[0], separators=(",", ":"))[:SAMPLE_CHARS]}


def diagnose_account(token: str, account: ClientAdsAccount, *, today: date) -> dict[str, Any]:
    customer = google_ads.digits(account.customer_id)
    span = {"start": (today - timedelta(days=DAYS)).isoformat(), "end": today.isoformat()}
    checks = [_check("The account", token, customer, ACCOUNT, _account, "Google returned nothing for this account.")]
    campaigns = _check("Campaigns", token, customer, CAMPAIGNS, _campaigns, "The account has no campaigns.")
    checks.append(campaigns)
    has_lsa = account.kind == "lsa" or "LOCAL_SERVICES" in (campaigns.get("sample") or "")
    if has_lsa:
        checks.append(_check("Local Services campaigns", token, customer, ads_pull.LSA_DAILY.format(**span), _performance, f"No Local Services campaign had activity in the last {DAYS} days."))
        checks.append(_check("Local Services leads", token, customer, LEADS.format(**span), _leads, f"No Local Services leads in the last {DAYS} days, or this account does not report them."))
    if account.kind != "lsa":
        checks.append(_check("Daily performance", token, customer, ads_pull.DAILY.format(**span), _performance, f"No ad group had impressions in the last {DAYS} days."))
        checks.append(_check("What people searched for", token, customer, ads_pull.TERMS.format(**span), _terms, f"Google listed no individual searches in the last {DAYS} days (searches made by only a few people are not shown)."))
        checks.append(_check("Markets", token, customer, ads_pull.MARKETS.format(**span), _markets, f"No market had impressions in the last {DAYS} days."))
    return {"customer_id": account.customer_id, "name": account.name, "kind": account.kind, "checks": checks}


def diagnose(db: Session, client: Client, *, today: date | None = None) -> dict[str, Any]:
    """Every account the client has. Raises `GoogleAdsError` only when Google gives no access token at all."""
    accounts = ads_pull.accounts_of(db, client)
    if not accounts:
        raise google_ads.GoogleAdsError("No Google Ads account is chosen for this client.")
    token = google_ads.access_token(db)
    today = today or datetime.now(timezone.utc).date()
    return {"checked_at": datetime.now(timezone.utc).isoformat(), "days": DAYS, "accounts": [diagnose_account(token, a, today=today) for a in accounts]}
