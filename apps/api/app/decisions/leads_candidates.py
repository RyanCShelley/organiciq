"""Leads candidates: pages whose organic visitors convert or engage less than the site's own norm.

From the plan, which tested this on 54 live sites:

- Conversion and engagement vary too much between sites for a fixed threshold (key-event rates ran from
  0.9% to 35.4% depending on what each site counts), so every page is compared with *its own site's*
  median, never with an outside benchmark.
- Pages with 50+ organic sessions over the quarter qualify. They are ranked by **missed conversions**:
  sessions x (the site's median conversion rate - the page's rate).
- **Strong**: the page is in the worst quartile of its site on both conversion and engagement, with 100+
  sessions. Everything else that qualifies stays on the list as **possible**, with the reason.
- Bounce rate is not shown: it is 100% minus engagement.
- Conversions are the client's own conversion definitions (events marked as a lead, an order, or any
  non-engagement type), never GA4's generic key-event flag. With none defined there is nothing to
  measure, and the engine says so instead of guessing.

Organic search sessions only, over the three months to the chosen month. For an ecommerce client a
"conversion" is an order; the screen words it from the client's business type.
"""

from __future__ import annotations

from datetime import date, timedelta
from statistics import median
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.decisions.traffic_candidates import ORGANIC, add_months, bucket_pages, is_real_page
from app.models.client import Client
from app.models.config import ConversionDefinition
from app.models.ga4 import FactGa4Event, FactGa4Traffic
from app.models.watchlist import WatchlistBucket, WatchlistKeyword

LIST_SIZE = 20
PAGE_MIN_SESSIONS = 50.0
#: The all-pages table lists any page with this many organic sessions over the quarter, compared or not.
ALL_PAGES_MIN_SESSIONS = 10.0
ALL_PAGES_SIZE = 100
STRONG_MIN_SESSIONS = 100.0
WORST_SHARE = 0.25


def conversion_events(db: Session, client_id: UUID) -> list[str]:
    """The events this client counts as a conversion: active, and not mere engagement."""
    rows = (
        db.query(ConversionDefinition.event_name)
        .filter(
            ConversionDefinition.client_id == client_id,
            ConversionDefinition.active.is_(True),
            ConversionDefinition.conversion_type != "engagement",
        )
        .all()
    )
    return sorted({r[0] for r in rows})


def _worst_quarter(values: dict[str, float]) -> set[str]:
    """The lowest quarter of pages by rank (at least one). By rank, so a pile of ties at the cutoff
    cannot pull half the site into the worst quarter."""
    count = max(1, -(-len(values) // 4))  # ceil(n / 4)
    return {url for url, _ in sorted(values.items(), key=lambda kv: (kv[1], kv[0]))[:count]}


def noun_for(model: str | None) -> dict[str, str]:
    return {"ecommerce": {"plural": "orders", "singular": "order"}, "both": {"plural": "conversions", "singular": "conversion"}}.get(
        model or "", {"plural": "leads", "singular": "lead"}
    )


def build(db: Session, client: Client, month: str, bucket_id: UUID | None = None, *, list_size: int | None = LIST_SIZE) -> dict[str, Any]:
    year, mon = int(month[:4]), int(month[5:7])
    month_start = date(year, mon, 1)
    start = add_months(month_start, -2)
    end = add_months(month_start, 1) - timedelta(days=1)
    noun = noun_for(client.business_model)

    chosen = None
    scope: set[str] | None = None
    if bucket_id is not None:
        chosen = db.query(WatchlistBucket).filter(WatchlistBucket.id == bucket_id, WatchlistBucket.client_id == client.id).one_or_none()
        if chosen is None:
            raise LookupError("That bucket is not on this client's watchlist.")

    events = conversion_events(db, client.id)
    base: dict[str, Any] = {
        "month": month,
        "window": {"from": start.isoformat(), "to": end.isoformat(), "months": 3},
        "noun": noun,
        "conversion_events": events,
    }
    if not events:
        return {**base, "needs": "conversions", "candidates": [], "counts": {"strong": 0, "possible": 0, "listed": 0}, "notes": []}

    if chosen is not None:
        terms = sorted({" ".join(k.keyword.lower().split()) for k in db.query(WatchlistKeyword).filter(WatchlistKeyword.bucket_id == chosen.id)})
        scope = bucket_pages(db, client, month_start, terms)

    traffic = {
        url: (float(sessions or 0), float(engaged or 0))
        for url, sessions, engaged in db.query(
            FactGa4Traffic.normalized_url, func.sum(FactGa4Traffic.sessions), func.sum(FactGa4Traffic.engaged_sessions)
        )
        .filter(
            FactGa4Traffic.client_id == client.id,
            FactGa4Traffic.channel == ORGANIC,
            FactGa4Traffic.date >= start,
            FactGa4Traffic.date <= end,
        )
        .group_by(FactGa4Traffic.normalized_url)
        .all()
    }
    converted = {
        url: float(n or 0)
        for url, n in db.query(FactGa4Event.normalized_url, func.sum(FactGa4Event.event_count))
        .filter(
            FactGa4Event.client_id == client.id,
            FactGa4Event.channel == ORGANIC,
            FactGa4Event.event_name.in_(events),
            FactGa4Event.date >= start,
            FactGa4Event.date <= end,
        )
        .group_by(FactGa4Event.normalized_url)
        .all()
    }

    # The site's norm comes from every qualifying page, not only the ones in a chosen bucket.
    qualifying = {u: v for u, v in traffic.items() if v[0] >= PAGE_MIN_SESSIONS and is_real_page(u)}
    rows = {
        u: {
            "sessions": s,
            "conv_rate": converted.get(u, 0.0) / s,
            "engagement": eng / s,
            "conversions": converted.get(u, 0.0),
        }
        for u, (s, eng) in qualifying.items()
    }
    out: list[dict[str, Any]] = []
    site_conv = site_eng = None
    if rows:
        site_conv = median(r["conv_rate"] for r in rows.values())
        site_eng = median(r["engagement"] for r in rows.values())
        worst_conv = _worst_quarter({u: r["conv_rate"] for u, r in rows.items()})
        worst_eng = _worst_quarter({u: r["engagement"] for u, r in rows.items()})

        for url, r in rows.items():
            if scope is not None and url not in scope:
                continue
            missed = r["sessions"] * max(0.0, site_conv - r["conv_rate"])
            low_conv, low_eng = url in worst_conv, url in worst_eng
            strong = low_conv and low_eng and r["sessions"] >= STRONG_MIN_SESSIONS
            if strong:
                reason = None
            elif low_conv and low_eng:
                reason = f"only {round(r['sessions'])} sessions, under the {int(STRONG_MIN_SESSIONS)} a strong flag needs"
            elif low_conv:
                reason = "in the worst quarter of the site on conversion, but not on engagement"
            elif low_eng:
                reason = "in the worst quarter of the site on engagement, but not on conversion"
            else:
                reason = "not in the worst quarter of the site on conversion or engagement"
            out.append(
                {
                    "page": url,
                    "sessions": round(r["sessions"]),
                    "conversions": round(r["conversions"]),
                    "conversion_rate": round(r["conv_rate"] * 100, 2),
                    "engagement_rate": round(r["engagement"] * 100, 1),
                    "missed_conversions": round(missed, 1),
                    "worst_conversion": low_conv,
                    "worst_engagement": low_eng,
                    "strength": "strong" if strong else "possible",
                    "reason": reason,
                }
            )
    all_pages: list[dict[str, Any]] = []
    for url, (sessions, engaged) in traffic.items():
        if sessions < ALL_PAGES_MIN_SESSIONS or not is_real_page(url) or (scope is not None and url not in scope):
            continue
        conversions = converted.get(url, 0.0)
        rate = conversions / sessions
        all_pages.append(
            {
                "page": url,
                "sessions": round(sessions),
                "conversions": round(conversions),
                "conversion_rate": round(rate * 100, 2),
                "engagement_rate": round(engaged / sessions * 100, 1),
                "missed_conversions": round(sessions * max(0.0, site_conv - rate), 1) if site_conv is not None else 0.0,
                "compared": url in rows,
            }
        )
    all_pages.sort(key=lambda r: (-r["missed_conversions"], -r["sessions"]))

    out.sort(key=lambda c: (c["strength"] != "strong", -c["missed_conversions"], -c["sessions"]))
    listed = out if list_size is None else out[:list_size]

    return {
        **base,
        "scope": chosen.name if chosen else "the whole site",
        "bucket": None if chosen is None else {"id": str(chosen.id), "name": chosen.name},
        "site": {
            "qualifying_pages": len(rows),
            "median_conversion_rate": None if site_conv is None else round(site_conv * 100, 2),
            "median_engagement_rate": None if site_eng is None else round(site_eng * 100, 1),
            "organic_sessions": round(sum(v[0] for v in traffic.values())),
        },
        "counts": {
            "strong": sum(1 for c in out if c["strength"] == "strong"),
            "possible": sum(1 for c in out if c["strength"] == "possible"),
            "listed": len(listed),
            "found": len(out),
        },
        "candidates": listed,
        "all_pages": all_pages[:ALL_PAGES_SIZE],
        "all_pages_total": len(all_pages),
        "notes": [
            f"A page needs {int(PAGE_MIN_SESSIONS)}+ organic sessions over the three months to be listed. Each page is compared with this site's own median, never an outside benchmark.",
            f"Missed {noun['plural']} = sessions x (the site's median conversion rate - the page's rate). Strong means the worst quarter of the site on both conversion and engagement, with {int(STRONG_MIN_SESSIONS)}+ sessions.",
            "Conversions are the events set up on Settings → Conversions & goals. Bounce rate is not shown: it is 100% minus engagement.",
            "When a bucket is chosen, its pages are the ones Search Console shows for a search containing one of its terms; the site's norm still comes from every qualifying page.",
        ],
    }


def conversion_path(db: Session, client: Client, page: str) -> dict[str, Any]:
    """Whether a page leads anywhere: in-content links to the pages the client declared as conversion pages."""
    from app.core.urls import normalize_url
    from app.models.config import ClientConversionPage
    from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlInternalLink
    from app.services.target_signals import _latest_crawl_date

    declared = [normalize_url(p.normalized_url) for p in db.query(ClientConversionPage).filter(ClientConversionPage.client_id == client.id)]
    day = _latest_crawl_date(db, client.id)
    linked: list[str] = []
    if declared and day is not None:
        targets = {normalize_url(r.to_url) for r in db.query(FactCrawlInternalLink.to_url).filter(
            FactCrawlInternalLink.client_id == client.id,
            FactCrawlInternalLink.source == CRAWL_SOURCE_FIRST_PARTY,
            FactCrawlInternalLink.snapshot_date == day,
            FactCrawlInternalLink.from_url.in_([page, normalize_url(page)]),
            FactCrawlInternalLink.in_content.is_(True),
            FactCrawlInternalLink.is_template.is_(False),
        )}
        linked = sorted(t for t in declared if t in targets)
    return {"declared": len(declared), "crawl": day is not None, "linked_to": linked}
