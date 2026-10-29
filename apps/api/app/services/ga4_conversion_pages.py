"""Where on the site GA4 sees a conversion event fire.

The warehouse's event table is keyed by the visit's landing page, which says where
people entered, not where they filled the form in. A conversion page is the second
thing, and only GA4 can say it, so this asks GA4 directly for `pagePath` by event.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.core.urls import normalize_landing_page, normalize_url
from app.ingestion.ga4.client import run_report
from app.ingestion.google_credentials import access_token_for_client, client_has_google_credentials
from app.models.client import Client
from app.models.config import ClientConversionPage
from app.models.integration import Integration, IntegrationProvider

MAX_PAGES = 200


class Ga4NotReady(Exception):
    """GA4 is not connected or has no property chosen."""


def pages_for_events(
    db: Session,
    client: Client,
    events: list[str],
    *,
    days: int = 90,
    today: date | None = None,
) -> list[dict]:
    """`[{url, path, total, events: {name: count}, declared}]`, busiest page first."""
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
        raise Ga4NotReady("Connect GA4 and choose a property first (Settings → Connections).")

    end = (today or date.today()) - timedelta(days=1)
    rows = run_report(
        access_token=access_token_for_client(db, client.id),
        property_id=integration.external_property_id,
        start_date=end - timedelta(days=days),
        end_date=end,
        dimensions=["pagePath", "eventName"],
        metrics=["eventCount"],
        dimension_filter={"filter": {"fieldName": "eventName", "inListFilter": {"values": events}}},
        limit=10000,
    )

    by_page: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in rows:
        dims = row.get("dimensionValues") or []
        metrics = row.get("metricValues") or []
        if len(dims) < 2 or not metrics:
            continue
        path, event = str(dims[0].get("value") or ""), str(dims[1].get("value") or "")
        if not path or not event:
            continue
        by_page[path][event] += int(float(metrics[0].get("value") or 0))

    declared = {
        normalize_url(r.normalized_url)
        for r in db.query(ClientConversionPage).filter(ClientConversionPage.client_id == client.id)
    }
    out = []
    for path, counts in by_page.items():
        url = normalize_landing_page(path, client.domain)
        out.append(
            {
                "url": url,
                "path": path,
                "total": sum(counts.values()),
                "events": dict(counts),
                "declared": normalize_url(url) in declared,
            }
        )
    out.sort(key=lambda page: page["total"], reverse=True)
    return out[:MAX_PAGES]
