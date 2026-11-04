"""Where on the site GA4 sees a conversion event fire.

The warehouse's event table is keyed by the visit's landing page, which says where
people entered, not where they filled the form in. A conversion page is the second
thing, and only GA4 can say it, so this asks GA4 directly for `pagePath` by event.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.core.urls import normalize_landing_page, normalize_url
from app.ingestion.ga4.client import run_report
from app.ingestion.google_credentials import access_token_for_client, client_has_google_credentials
from app.models.client import Client
from app.models.client_completion_pattern import ClientCompletionPattern
from app.models.config import ClientConversionPage
from app.models.integration import Integration, IntegrationProvider

MAX_PAGES = 200

#: Tail segments that mean "this visitor finished", as e-commerce checkouts and form
#: thank-you screens spell them. Only used to *suggest* a pattern; a person confirms it.
_COMPLETION = re.compile(
    r"/(thank[-_]?you|order[-_]?(?:confirmation|complete|received)|confirmation|success)(?=/|$|\?)",
    re.IGNORECASE,
)


def clean_pattern(raw: str) -> str:
    """`Thank-You` -> `/thank-you`: lower case, one leading slash, no spaces."""
    text = (raw or "").strip().lower()
    if not text or " " in text or "\n" in text:
        raise ValueError("A pattern is part of a page address, such as /thank-you.")
    return text if text.startswith("/") else "/" + text


def suggest_patterns(pages: list[dict]) -> list[dict]:
    """Group pages whose address ends in a completion word: `[{pattern, total, pages}]`."""
    found: dict[str, dict] = {}
    for page in pages:
        match = _COMPLETION.search(page["path"].split("?")[0])
        if not match:
            continue
        pattern = "/" + match.group(1).lower()
        entry = found.setdefault(pattern, {"pattern": pattern, "total": 0, "pages": 0})
        entry["total"] += page["total"]
        entry["pages"] += 1
    return sorted(found.values(), key=lambda e: e["total"], reverse=True)


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
    """Every page the events fired on, busiest first, as `{url, path, total, events, declared, tracked_by}`."""
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
    tracked = [
        p.pattern for p in db.query(ClientCompletionPattern).filter(ClientCompletionPattern.client_id == client.id)
    ]
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
                "tracked_by": next((t for t in tracked if t in path.lower()), None),
            }
        )
    out.sort(key=lambda page: page["total"], reverse=True)
    return out


def summarise(pages: list[dict], *, limit: int = MAX_PAGES) -> dict:
    """What the screen needs, counted over every page before anything is trimmed.

    Pages that match a tracked pattern are folded into `tracked`, so one thank-you
    pattern stands for hundreds of one-off order addresses instead of burying the list.
    """
    tracked: dict[str, dict] = {}
    rest = []
    for page in pages:
        pattern = page["tracked_by"]
        if pattern is None:
            rest.append(page)
            continue
        entry = tracked.setdefault(pattern, {"pattern": pattern, "total": 0, "pages": 0})
        entry["total"] += page["total"]
        entry["pages"] += 1
    return {
        "pages": rest[:limit],
        "pages_not_shown": max(len(rest) - limit, 0),
        "tracked": sorted(tracked.values(), key=lambda e: e["total"], reverse=True),
        "suggested": suggest_patterns(rest),
    }
