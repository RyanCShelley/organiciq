"""Pull a client's Bing query statistics into `facts_bing_query_stats`."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.integrations import bing
from app.models.bing_stats import FactBingQueryStat
from app.models.client import Client
from app.models.client_bing_site import ClientBingSite
from app.models.job import DataWatermark, SyncJob, SyncJobStatus, ValidationStatus

#: The source name the job and the watermark go under.
BING_SOURCE = "bing_query_stats"


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


def run_bing_query_stats_job(db: Session, job: SyncJob) -> SyncJob:
    """The scheduled pull: the same sync the Connections screen runs, recorded as a job and a watermark."""
    try:
        client = db.query(Client).filter(Client.id == job.client_id).one()
        job.status = SyncJobStatus.FETCHING
        db.commit()
        result = sync_query_stats(db, client)
        job.records_fetched = job.records_written = result["rows"]
        last_week = date.fromisoformat(result["last_week"]) if result["last_week"] else None
        job.fact_watermark = last_week
        job.validation_status = ValidationStatus.PASSED if result["rows"] else ValidationStatus.FAILED
        job.status = SyncJobStatus.SUCCESSFUL if result["rows"] else SyncJobStatus.PARTIAL
        job.error_message = (
            f"{result['rows']} query rows over {result['weeks']} weeks, through {result['last_week']}"
            if result["rows"]
            else "Bing returned no query statistics for this site"
        )
        job.completed_at = datetime.now(timezone.utc)
        if result["rows"]:
            row = (
                db.query(DataWatermark)
                .filter(DataWatermark.client_id == job.client_id, DataWatermark.source == BING_SOURCE)
                .one_or_none()
            )
            if row is None:
                row = DataWatermark(client_id=job.client_id, source=BING_SOURCE)
                db.add(row)
            row.fact_through_date = last_week
            row.validation_status = ValidationStatus.PASSED
            row.last_successful_sync_at = job.completed_at
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        job = db.get(SyncJob, job.id)
        job.status = SyncJobStatus.FAILED
        job.error_message = str(exc)[:500]
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
    return job
