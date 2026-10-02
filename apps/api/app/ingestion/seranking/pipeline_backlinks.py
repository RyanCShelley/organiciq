"""Per-URL backlink counts, from SE Ranking into facts.

Three rules in the Decision Engine need to know whether a page has link
equity: whether a 404 is worth reclaiming, which donor page has authority to
lend, and whether a page with no current traffic is still worth checking. None
could be built because nothing stored backlinks.

`first_seen` comes along too, so a new referring domain reads as an event — a
PR push landing — rather than a number that silently went up.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.core.urls import normalize_url
from app.ingestion.seranking.client import list_backlink_pages
from app.models.client import Client
from app.models.job import SyncJob, SyncJobStatus
from app.models.seranking import FactSerBacklinkPage

logger = logging.getLogger("organiciq.seranking.backlinks")

#: SE Ranking returns up to 10,000; a client's linked pages are far fewer, and
#: the long tail of single-link pages is not worth the payload.
PAGE_LIMIT = 2000


def _as_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _backlink_key(raw: str) -> str:
    """Normalized URL, with the scheme forced to https.

    `normalize_url` deliberately preserves http vs https, and everywhere else
    that is harmless because Search Console and GA4 both report the canonical
    scheme. A backlink index does not: it reports whatever the linking page
    pointed at, so one page arrives as two rows. Only this source needs the
    coercion, so only this source does it.
    """
    normalized = normalize_url(raw)
    if normalized.startswith("http://"):
        return "https://" + normalized[len("http://") :]
    return normalized


def collapse_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Merge the scheme variants SE Ranking reports separately.

    `http://example.com/` and `https://example.com/` come back as two rows for
    one page — on smamarketing.com, 39 and 37 referring domains. Stored as-is
    they would double count, and read back by normalized URL only one of them
    would ever be found. Counts are summed, and the earliest first_seen wins
    because that is when the page was first linked, whichever scheme carried it.
    """
    merged: dict[str, dict[str, Any]] = {}
    for row in rows:
        raw = str(row.get("url") or "").strip()
        key = _backlink_key(raw)
        if not key:
            continue
        first_seen = _as_date(row.get("first_seen"))
        last_visited = _as_date(row.get("last_visited"))
        existing = merged.get(key)
        if existing is None:
            merged[key] = {
                "raw_url": raw[:1024],
                "backlinks": _as_int(row.get("backlinks")),
                "refdomains": _as_int(row.get("refdomains")),
                "dofollow_backlinks": _as_int(row.get("dofollow_backlinks")),
                "nofollow_backlinks": _as_int(row.get("nofollow_backlinks")),
                "first_seen": first_seen,
                "last_visited": last_visited,
            }
            continue
        existing["backlinks"] += _as_int(row.get("backlinks"))
        existing["refdomains"] += _as_int(row.get("refdomains"))
        existing["dofollow_backlinks"] += _as_int(row.get("dofollow_backlinks"))
        existing["nofollow_backlinks"] += _as_int(row.get("nofollow_backlinks"))
        if first_seen and (existing["first_seen"] is None or first_seen < existing["first_seen"]):
            existing["first_seen"] = first_seen
        if last_visited and (
            existing["last_visited"] is None or last_visited > existing["last_visited"]
        ):
            existing["last_visited"] = last_visited
    return merged


def run_seranking_backlinks_job(db: Session, job: SyncJob) -> SyncJob:
    try:
        api_key = get_settings().se_ranking_api_key
        if not api_key:
            raise RuntimeError("SE_RANKING_API_KEY is not configured")
        client = db.query(Client).filter(Client.id == job.client_id).one()
        domain = (client.domain or "").strip()
        if not domain:
            raise RuntimeError("Client has no domain set")

        job.status = SyncJobStatus.FETCHING
        db.commit()
        rows = list_backlink_pages(api_key, domain, mode="domain", limit=PAGE_LIMIT)
        job.records_fetched = len(rows)

        merged = collapse_rows(rows)
        snapshot = job.end_date or date.today()
        payloads = [
            {
                "id": uuid4(),
                "client_id": job.client_id,
                "normalized_url": url,
                "snapshot_date": snapshot,
                **values,
            }
            for url, values in merged.items()
        ]

        if payloads:
            stmt = insert(FactSerBacklinkPage).values(payloads)
            db.execute(
                stmt.on_conflict_do_update(
                    constraint="uq_ser_backlink_pages_grain",
                    set_={
                        "backlinks": stmt.excluded.backlinks,
                        "refdomains": stmt.excluded.refdomains,
                        "dofollow_backlinks": stmt.excluded.dofollow_backlinks,
                        "nofollow_backlinks": stmt.excluded.nofollow_backlinks,
                        "last_visited": stmt.excluded.last_visited,
                        "snapshot_date": stmt.excluded.snapshot_date,
                        # first_seen is deliberately not overwritten: the whole
                        # value of the column is that it records when a link
                        # arrived, and a later fetch must not restate it.
                    },
                )
            )
        job.records_published = len(payloads)
        job.status = SyncJobStatus.SUCCEEDED
        job.error_message = (
            f"{len(payloads)} linked pages, "
            f"{sum(v['refdomains'] for v in merged.values())} referring domains"
        )
        db.commit()
        logger.info("Backlinks for %s: %d pages", domain, len(payloads))
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        job.status = SyncJobStatus.FAILED
        job.error_message = str(exc)[:1000]
        db.commit()
    return job
