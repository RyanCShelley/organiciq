"""Pull a client's Bing query statistics into `facts_bing_query_stats`."""

from __future__ import annotations

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.integrations import bing
from app.models.bing_stats import FactBingQueryStat
from app.models.client import Client
from app.models.client_bing_site import ClientBingSite


class BingNotReady(Exception):
    """No API key on this install, or no Bing site saved for the client."""


def sync_query_stats(db: Session, client: Client) -> dict:
    """Fetch and upsert every week Bing still has. Safe to run again: a week is overwritten."""
    key = get_settings().bing_webmaster_api_key.strip()
    if not key:
        raise BingNotReady("BING_WEBMASTER_API_KEY is not set on this install.")
    site = db.query(ClientBingSite).filter(ClientBingSite.client_id == client.id).one_or_none()
    if site is None:
        raise BingNotReady("Save this client's Bing site first (Settings → Connections).")

    rows = bing.query_stats(key, site.site_url)
    # One row per (week, query): Bing can repeat a query within a week with different casing.
    merged: dict[tuple, dict] = {}
    for row in rows:
        k = (row["week_start"], row["query"].lower())
        entry = merged.get(k)
        if entry is None:
            merged[k] = {**row, "query_key": row["query"].lower()}
        else:
            entry["impressions"] += row["impressions"]
            entry["clicks"] += row["clicks"]

    if merged:
        statement = insert(FactBingQueryStat).values(
            [{"client_id": client.id, **row} for row in merged.values()]
        )
        db.execute(
            statement.on_conflict_do_update(
                constraint="uq_facts_bing_query_stats_grain",
                set_={
                    "impressions": statement.excluded.impressions,
                    "clicks": statement.excluded.clicks,
                    "avg_impression_position": statement.excluded.avg_impression_position,
                    "avg_click_position": statement.excluded.avg_click_position,
                },
            )
        )
    db.commit()
    weeks = sorted({r["week_start"] for r in merged.values()})
    return {
        "rows": len(merged),
        "weeks": len(weeks),
        "first_week": weeks[0].isoformat() if weeks else None,
        "last_week": weeks[-1].isoformat() if weeks else None,
    }
