"""Pull a client's Google Ads numbers into the Ads tables, and the once-a-day run that does it for every client on Ads Accelerator.

The first pull goes back 90 days; after that, 14, because Google restates the last days (conversions arrive late). A pulled window replaces what the
tables held for it, and the first real pull also clears the client's demo rows.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.integrations import google_ads
from app.models.ads import AdsDaily, AdsMarketDaily, AdsSearchTerm
from app.models.client import Client
from app.models.scheduler import SchedulerCheckpoint
from app.services import ads_report

logger = logging.getLogger("organiciq.ads_pull")

FIRST_PULL_DAYS = 90
REFRESH_DAYS = 14
CHECKPOINT = "ads_pull"
DEVICES = {"DESKTOP": "Desktop", "MOBILE": "Mobile", "TABLET": "Tablet", "CONNECTED_TV": "Connected TV", "OTHER": "Other"}
#: Google's country criterion IDs for the markets most often named. Any other is looked up from Google.
COUNTRIES = {"2840": "United States", "2124": "Canada", "2826": "United Kingdom", "2036": "Australia", "2702": "Singapore", "2344": "Hong Kong"}

DAILY = (
    "SELECT segments.date, campaign.name, ad_group.name, segments.device, metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions, metrics.search_impression_share "
    "FROM ad_group WHERE segments.date BETWEEN '{start}' AND '{end}' AND metrics.impressions > 0"
)
TERMS = (
    "SELECT segments.date, search_term_view.search_term, ad_group.name, metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions "
    "FROM search_term_view WHERE segments.date BETWEEN '{start}' AND '{end}' AND metrics.impressions > 0"
)
MARKETS = (
    "SELECT segments.date, campaign.name, geographic_view.country_criterion_id, metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions "
    "FROM geographic_view WHERE segments.date BETWEEN '{start}' AND '{end}' AND metrics.impressions > 0"
)
COUNTRY_NAMES = "SELECT geo_target_constant.id, geo_target_constant.name FROM geo_target_constant WHERE geo_target_constant.id IN ({ids})"


def _int(x: Any) -> int:
    try:
        return int(float(x or 0))
    except (TypeError, ValueError):
        return 0


def _money(micros: Any) -> Decimal:
    return (Decimal(str(micros or 0)) / Decimal(1_000_000)).quantize(Decimal("0.01"))


def _conv(x: Any) -> Decimal:
    return Decimal(str(round(float(x or 0), 2)))


def _window(db: Session, client: Client, today: date) -> tuple[date, date]:
    held = db.query(func.count(AdsDaily.id)).filter(AdsDaily.client_id == client.id, AdsDaily.source == "google_ads").scalar()
    return today - timedelta(days=REFRESH_DAYS if held else FIRST_PULL_DAYS), today


def _daily(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: dict[tuple, dict[str, Any]] = {}
    for r in rows:
        m, seg = r.get("metrics") or {}, r.get("segments") or {}
        share = float(m.get("searchImpressionShare") or 0)
        imp = _int(m.get("impressions"))
        key = (seg.get("date"), (r.get("campaign") or {}).get("name") or "", (r.get("adGroup") or {}).get("name") or "", DEVICES.get(str(seg.get("device")), str(seg.get("device") or "").title()))
        row = out.setdefault(key, {"impressions": 0, "clicks": 0, "cost": Decimal(0), "conversions": Decimal(0), "eligible": 0})
        row["impressions"] += imp
        row["clicks"] += _int(m.get("clicks"))
        row["cost"] += _money(m.get("costMicros"))
        row["conversions"] += _conv(m.get("conversions"))
        row["eligible"] += round(imp / share) if share > 0 else 0
    return [{"date": k[0], "campaign": k[1], "ad_group": k[2], "device": k[3], **v} for k, v in out.items() if k[0]]


def _terms(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: dict[tuple, dict[str, Any]] = {}
    for r in rows:
        m, seg = r.get("metrics") or {}, r.get("segments") or {}
        term = ((r.get("searchTermView") or {}).get("searchTerm") or "").strip()
        key = (seg.get("date"), term, (r.get("adGroup") or {}).get("name") or "")
        row = out.setdefault(key, {"impressions": 0, "clicks": 0, "cost": Decimal(0), "conversions": Decimal(0)})
        row["impressions"] += _int(m.get("impressions"))
        row["clicks"] += _int(m.get("clicks"))
        row["cost"] += _money(m.get("costMicros"))
        row["conversions"] += _conv(m.get("conversions"))
    return [{"date": k[0], "term": k[1], "ad_group": k[2], **v} for k, v in out.items() if k[0] and k[1]]


def _markets(rows: list[dict[str, Any]], names: dict[str, str]) -> list[dict[str, Any]]:
    out: dict[tuple, dict[str, Any]] = {}
    for r in rows:
        m, seg = r.get("metrics") or {}, r.get("segments") or {}
        country = str((r.get("geographicView") or {}).get("countryCriterionId") or "")
        key = (seg.get("date"), (r.get("campaign") or {}).get("name") or "", names.get(country) or COUNTRIES.get(country) or (f"Country {country}" if country else "Not split"))
        row = out.setdefault(key, {"impressions": 0, "clicks": 0, "cost": Decimal(0), "conversions": Decimal(0)})
        row["impressions"] += _int(m.get("impressions"))
        row["clicks"] += _int(m.get("clicks"))
        row["cost"] += _money(m.get("costMicros"))
        row["conversions"] += _conv(m.get("conversions"))
    return [{"date": k[0], "campaign": k[1], "market": k[2], **v} for k, v in out.items() if k[0]]


def pull(db: Session, client: Client, *, today: date | None = None) -> dict[str, Any]:
    """Pull the window and replace what the tables held for it. Raises `GoogleAdsError` with a reason a person can act on."""
    customer = google_ads.digits(client.google_ads_customer_id)
    if not customer:
        raise google_ads.GoogleAdsError("No Google Ads account is chosen for this client.")
    today = today or datetime.now(timezone.utc).date()
    start, end = _window(db, client, today)
    token = google_ads.access_token(db)
    span = {"start": start.isoformat(), "end": end.isoformat()}
    daily = _daily(google_ads.search(token, customer, DAILY.format(**span)))
    terms = _terms(google_ads.search(token, customer, TERMS.format(**span)))
    market_rows = google_ads.search(token, customer, MARKETS.format(**span))
    ids = sorted({str((r.get("geographicView") or {}).get("countryCriterionId") or "") for r in market_rows} - {""} - set(COUNTRIES))
    names: dict[str, str] = {}
    if ids:
        for r in google_ads.search(token, customer, COUNTRY_NAMES.format(ids=", ".join(ids))):
            c = r.get("geoTargetConstant") or {}
            names[str(c.get("id"))] = str(c.get("name") or "")
    markets = _markets(market_rows, names)

    for model in (AdsDaily, AdsMarketDaily, AdsSearchTerm):
        db.query(model).filter(model.client_id == client.id, model.date >= start, model.date <= end).delete(synchronize_session=False)
        db.query(model).filter(model.client_id == client.id, model.source == "demo").delete(synchronize_session=False)  # demo rows go with the first real pull
    for r in daily:
        db.add(AdsDaily(client_id=client.id, date=date.fromisoformat(r["date"]), campaign=r["campaign"], ad_group=r["ad_group"], device=r["device"], impressions=r["impressions"], clicks=r["clicks"],
                        cost=r["cost"], conversions=r["conversions"], eligible_impressions=r["eligible"], source="google_ads"))
    for r in markets:
        db.add(AdsMarketDaily(client_id=client.id, date=date.fromisoformat(r["date"]), campaign=r["campaign"], market=r["market"], impressions=r["impressions"], clicks=r["clicks"], cost=r["cost"],
                              conversions=r["conversions"], source="google_ads"))
    for r in terms:
        db.add(AdsSearchTerm(client_id=client.id, date=date.fromisoformat(r["date"]), term=r["term"], ad_group=r["ad_group"], impressions=r["impressions"], clicks=r["clicks"], cost=r["cost"], conversions=r["conversions"]))
    client.google_ads_last_pull_at = datetime.now(timezone.utc)
    client.google_ads_last_error = None
    db.commit()
    return {"from": span["start"], "to": span["end"], "days": len({r["date"] for r in daily}), "rows": len(daily), "markets": len(markets), "terms": len(terms)}


def _record_failure(db: Session, client: Client, message: str) -> None:
    db.rollback()
    client.google_ads_last_error = message[:500]
    db.commit()


def maybe_pull_ads(db: Session) -> bool:
    """Once a day, after the morning sync: every client on Ads Accelerator with an account chosen. One client failing does not stop the rest."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    if now.hour < settings.ads_pull_hour_utc:
        return False
    checkpoint = db.query(SchedulerCheckpoint).filter(SchedulerCheckpoint.name == CHECKPOINT).with_for_update().one_or_none()
    if checkpoint is None:
        checkpoint = SchedulerCheckpoint(name=CHECKPOINT, last_run_date=None)
        db.add(checkpoint)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return False
    today = now.date()
    if checkpoint.last_run_date == today:
        db.rollback()
        return False
    checkpoint.last_run_date = today
    checkpoint.updated_at = now
    db.commit()
    for client in db.query(Client).filter(Client.google_ads_customer_id.isnot(None)).all():
        if not ads_report.enabled(client):
            continue
        try:
            stats = pull(db, client, today=today)
            logger.info("Google Ads pulled for %s: %s", client.slug, stats)
        except google_ads.GoogleAdsError as exc:
            logger.warning("Google Ads pull failed for %s: %s", client.slug, exc)
            _record_failure(db, client, str(exc))
        except Exception as exc:  # noqa: BLE001 — one client must not stop the rest
            logger.exception("Google Ads pull failed for %s", client.slug)
            _record_failure(db, client, f"Unexpected error: {exc}")
    return True
