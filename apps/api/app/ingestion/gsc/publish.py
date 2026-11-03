from __future__ import annotations

import logging
from collections.abc import Sequence
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.urls import normalize_path_prefix, url_in_scope, normalize_url, rewrite_url_host
from app.models.client import Client
from app.models.gsc import (
    FactGscDaily,
    FactGscPage,
    FactGscQueryPage,
    StagingGscDaily,
    StagingGscPage,
    StagingGscQueryPage,
)
from app.models.integration import Integration, IntegrationProvider
from app.models.job import SyncJob

# psycopg limit is 65535 bind params; keep batches well under that.
UPSERT_BATCH_SIZE = 1000
logger = logging.getLogger("organiciq.gsc.publish")
STREAM_BATCH_SIZE = 20000
#: Postgres will not index a row over 2,704 bytes. A unique index on (search, address, site, country, device) breaks on the one
#: Search Console row with a very long search or address, and that one row used to fail the whole pull (SMA Marketing's year of
#: searches never saved). Rows whose key would not fit are skipped, and counted on the job.
MAX_KEY_BYTES = 2000
INSERT_BATCH_SIZE = 5000


def _chunked(items: Sequence[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [list(items[i : i + size]) for i in range(0, len(items), size)]


def _as_decimal(value: Decimal | int | float | str | None) -> Decimal:
    if value is None:
        return Decimal(0)
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _merge_gsc_metrics(existing: dict[str, Any], incoming: dict[str, Any]) -> None:
    old_impressions = _as_decimal(existing["impressions"])
    new_impressions = _as_decimal(incoming["impressions"])
    old_clicks = _as_decimal(existing["clicks"])
    new_clicks = _as_decimal(incoming["clicks"])
    old_position = _as_decimal(existing["average_position"])
    new_position = _as_decimal(incoming["average_position"])

    total_impressions = old_impressions + new_impressions
    total_clicks = old_clicks + new_clicks
    if total_impressions > 0:
        weighted_position = (
            old_position * old_impressions + new_position * new_impressions
        ) / total_impressions
        ctr = total_clicks / total_impressions
    else:
        weighted_position = Decimal(0)
        ctr = Decimal(0)

    existing["impressions"] = total_impressions
    existing["clicks"] = total_clicks
    existing["ctr"] = ctr
    existing["average_position"] = weighted_position


def _page_grain_key(payload: dict[str, Any]) -> tuple[Any, ...]:
    return (
        payload["client_id"],
        payload["date"],
        payload["normalized_url"],
        payload["country"],
        payload["device"],
        payload.get("gsc_site_url", ""),
    )


def _query_grain_key(payload: dict[str, Any]) -> tuple[Any, ...]:
    return (
        payload["client_id"],
        payload["date"],
        payload["query"],
        payload["normalized_url"],
        payload["country"],
        payload["device"],
        payload.get("gsc_site_url", ""),
    )


def _daily_grain_key(payload: dict[str, Any]) -> tuple[Any, ...]:
    return (payload["client_id"], payload["date"], payload.get("gsc_site_url", ""))


def _dedupe_payloads(
    payloads: list[dict[str, Any]],
    grain_key,
) -> list[dict[str, Any]]:
    """Merge same-grain rows. Primary-source rows win over secondary; same-priority rows sum."""
    merged: dict[tuple[Any, ...], dict[str, Any]] = {}
    for payload in payloads:
        key = grain_key(payload)
        existing = merged.get(key)
        if existing is None:
            merged[key] = {k: v for k, v in payload.items() if k != "is_primary"}
            merged[key]["_is_primary"] = bool(payload.get("is_primary"))
            continue

        incoming_primary = bool(payload.get("is_primary"))
        existing_primary = bool(existing.get("_is_primary"))
        if incoming_primary and not existing_primary:
            replacement = {k: v for k, v in payload.items() if k != "is_primary"}
            replacement["_is_primary"] = True
            merged[key] = replacement
            continue
        if existing_primary and not incoming_primary:
            continue
        _merge_gsc_metrics(existing, payload)

    out: list[dict[str, Any]] = []
    for value in merged.values():
        value.pop("_is_primary", None)
        out.append(value)
    return out


def _primary_site_url(db: Session, client_id: UUID) -> str | None:
    integration = (
        db.query(Integration)
        .filter(
            Integration.client_id == client_id,
            Integration.provider == IntegrationProvider.GSC,
        )
        .one_or_none()
    )
    if integration is None:
        return None
    primary = (integration.external_property_id or "").strip()
    return primary or None


def _client_scope(db: Session, client_id: UUID) -> str | None:
    """Path this client occupies, when its site is a folder of a larger domain.

    A URL-prefix Search Console property is already scoped at source, so this
    only bites for a client verified with a domain property — where every
    sibling brand's pages arrive too.
    """
    client = db.query(Client).filter(Client.id == client_id).one_or_none()
    return normalize_path_prefix(client.path_prefix) if client else None


def _client_domain(db: Session, client_id: UUID) -> str | None:
    client = db.query(Client).filter(Client.id == client_id).one_or_none()
    if client is None:
        return None
    domain = (client.domain or "").strip()
    return domain or None


def _canonical_page_url(
    raw_page: str,
    *,
    gsc_site_url: str | None,
    primary_site_url: str | None,
    client_domain: str | None,
) -> tuple[str, str]:
    page = raw_page
    is_secondary = bool(
        gsc_site_url and primary_site_url and gsc_site_url.strip() != primary_site_url.strip()
    )
    if is_secondary and client_domain:
        page = rewrite_url_host(page, client_domain)
    return page, normalize_url(page)


def _replace_scope(db, model, job, payloads):
    """Retire legacy combined rows when source-tagged rows replace this window.

    Full restatement is explicit, used by a controlled rebuild after complete
    source extraction. Ordinary ingestion never erases an empty source report.
    """
    if not payloads:
        return
    query = db.query(model).filter(model.client_id == job.client_id,
        model.date >= job.start_date, model.date <= job.end_date)
    if not (job.params_json or {}).get("replace_gsc_window"):
        query = query.filter(model.gsc_site_url == "")
    query.delete(synchronize_session=False)


def _write_daily(db: Session, payloads: list[dict[str, Any]], job: SyncJob | None = None) -> int:
    if not payloads:
        return 0

    payloads = _dedupe_payloads(payloads, _daily_grain_key)
    if job is not None and any(p.get("gsc_site_url") for p in payloads):
        _replace_scope(db, FactGscDaily, job, payloads)

    for batch in _chunked(payloads, UPSERT_BATCH_SIZE):
        stmt = insert(FactGscDaily).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_facts_gsc_daily_grain",
            set_={
                "impressions": stmt.excluded.impressions,
                "clicks": stmt.excluded.clicks,
                "ctr": stmt.excluded.ctr,
                "average_position": stmt.excluded.average_position,
            },
        )
        db.execute(stmt)
    db.commit()
    return len(payloads)


def _daily_from_scoped_pages(db: Session, job: SyncJob, scope: str) -> list[dict[str, Any]]:
    """Daily totals rebuilt from the pages inside this client's folder.

    Search Console's own daily rows carry no URL, so on a domain property they
    are the whole parent site — which would put the parent brand's impressions,
    clicks and position on this client's dashboard while its page-level facts
    were correctly scoped. Rebuilding the totals from the scoped page rows is
    the only way to keep the two telling the same story.

    It is an estimate: summing the page dimension does not reproduce Search
    Console's site total exactly, because the two are deduplicated differently.
    For a client that occupies part of a domain there is no exact figure to be
    had, and a close one about the right pages beats an exact one about the
    wrong site.
    """
    rows = (
        db.query(StagingGscPage)
        .filter(StagingGscPage.job_id == job.id, StagingGscPage.client_id == job.client_id)
        .all()
    )
    totals: dict[Any, dict[str, Decimal]] = {}
    for row in rows:
        if row.date is None or not row.page:
            continue
        if not url_in_scope(normalize_url(row.page), scope):
            continue
        impressions = row.impressions or Decimal(0)
        bucket = totals.setdefault(
            row.date,
            {"impressions": Decimal(0), "clicks": Decimal(0), "position_weighted": Decimal(0)},
        )
        bucket["impressions"] += impressions
        bucket["clicks"] += row.clicks or Decimal(0)
        # Position is an average, so it is weighted by impressions rather than
        # summed; adding averages together invents a number.
        bucket["position_weighted"] += (row.average_position or Decimal(0)) * impressions

    payloads: list[dict[str, Any]] = []
    for day, bucket in totals.items():
        impressions = bucket["impressions"]
        payloads.append(
            {
                "client_id": job.client_id,
                "date": day,
                "impressions": impressions,
                "clicks": bucket["clicks"],
                "ctr": (bucket["clicks"] / impressions) if impressions else Decimal(0),
                "average_position": (
                    bucket["position_weighted"] / impressions if impressions else Decimal(0)
                ),
                "is_primary": True,
            }
        )
    return payloads


def publish_gsc_daily(db: Session, job: SyncJob) -> int:
    scope = _client_scope(db, job.client_id)
    if scope:
        payloads = _daily_from_scoped_pages(db, job, scope)
        return _write_daily(db, payloads, job)

    rows = (
        db.query(StagingGscDaily)
        .filter(StagingGscDaily.job_id == job.id, StagingGscDaily.client_id == job.client_id)
        .all()
    )
    if not rows:
        return 0

    primary_site_url = _primary_site_url(db, job.client_id)
    payloads: list[dict[str, Any]] = []
    for row in rows:
        if row.date is None:
            continue
        site = (row.gsc_site_url or "").strip()
        is_primary = not primary_site_url or not site or site == primary_site_url
        payloads.append(
            {
                "client_id": job.client_id,
                "date": row.date,
                "impressions": row.impressions or Decimal(0),
                "clicks": row.clicks or Decimal(0),
                "ctr": row.ctr or Decimal(0),
                "average_position": row.average_position or Decimal(0),
                "is_primary": is_primary,
                "gsc_site_url": site,
            }
        )

    return _write_daily(db, payloads, job)


class _UrlCache:
    """Each distinct page address is canonicalised once. A property has far fewer pages than rows."""

    def __init__(self, *, primary_site_url: str | None, client_domain: str | None, scope: str | None) -> None:
        self.primary_site_url, self.client_domain, self.scope = primary_site_url, client_domain, scope
        self._seen: dict[tuple[str, str], str | None] = {}

    def normalized(self, page: str, site: str) -> str | None:
        key = (page, site)
        if key not in self._seen:
            _, normalized = _canonical_page_url(
                page, gsc_site_url=site or None, primary_site_url=self.primary_site_url, client_domain=self.client_domain
            )
            self._seen[key] = normalized if normalized and url_in_scope(normalized, self.scope) else None
        return self._seen[key]

    def is_primary(self, site: str) -> bool:
        return not self.primary_site_url or not site or site == self.primary_site_url


def _upsert(db: Session, model, constraint: str, columns: tuple[str, ...], payloads: list[dict[str, Any]]) -> None:
    """One statement, many parameter sets: compiled once. Passing each batch to .values() recompiled it every time."""
    stmt = insert(model)
    stmt = stmt.on_conflict_do_update(constraint=constraint, set_={c: getattr(stmt.excluded, c) for c in columns})
    for batch in _chunked(payloads, INSERT_BATCH_SIZE):
        db.execute(stmt, batch)


def _oversize(*parts: str) -> bool:
    return sum(len((p or "").encode("utf-8")) for p in parts) > MAX_KEY_BYTES


def _note_skipped(job: SyncJob, skipped: int) -> None:
    if skipped:
        logger.warning("GSC publish skipped %d rows whose key is too long to index (job %s)", skipped, job.id)
        job.params_json = {**(job.params_json or {}), "skipped_oversize_rows": skipped}


def publish_gsc_pages(db: Session, job: SyncJob) -> int:
    urls = _UrlCache(
        primary_site_url=_primary_site_url(db, job.client_id),
        client_domain=_client_domain(db, job.client_id),
        scope=_client_scope(db, job.client_id),
    )
    payloads: list[dict[str, Any]] = []
    seen_any = False
    skipped = 0
    # Only the columns used, streamed, not the raw JSON copy of every row loaded as an object.
    for row in (
        db.query(
            StagingGscPage.date, StagingGscPage.page, StagingGscPage.country, StagingGscPage.device, StagingGscPage.gsc_site_url,
            StagingGscPage.impressions, StagingGscPage.clicks, StagingGscPage.ctr, StagingGscPage.average_position,
        )
        .filter(StagingGscPage.job_id == job.id, StagingGscPage.client_id == job.client_id)
        .yield_per(STREAM_BATCH_SIZE)
    ):
        seen_any = True
        if row.date is None or not row.page:
            continue
        site = (row.gsc_site_url or "").strip()
        normalized_url = urls.normalized(row.page, site)
        if not normalized_url:
            continue
        if _oversize(row.page, normalized_url, site, row.country, row.device):
            skipped += 1
            continue
        payloads.append(
            {
                "client_id": job.client_id,
                "date": row.date,
                "raw_url": row.page,
                "normalized_url": normalized_url,
                "country": row.country or "",
                "device": row.device or "",
                "impressions": row.impressions or Decimal(0),
                "clicks": row.clicks or Decimal(0),
                "ctr": row.ctr or Decimal(0),
                "average_position": row.average_position or Decimal(0),
                "is_primary": urls.is_primary(site),
                "gsc_site_url": site,
            }
        )
    _note_skipped(job, skipped)
    if not seen_any or not payloads:
        return 0

    payloads = _dedupe_payloads(payloads, _page_grain_key)
    _replace_scope(db, FactGscPage, job, payloads)
    _upsert(db, FactGscPage, "uq_facts_gsc_pages_grain", ("raw_url", "impressions", "clicks", "ctr", "average_position"), payloads)
    db.commit()
    return len(payloads)


def publish_gsc_queries(db: Session, job: SyncJob) -> int:
    urls = _UrlCache(
        primary_site_url=_primary_site_url(db, job.client_id),
        client_domain=_client_domain(db, job.client_id),
        scope=_client_scope(db, job.client_id),
    )
    payloads: list[dict[str, Any]] = []
    skipped = 0
    for row in (
        db.query(
            StagingGscQueryPage.date, StagingGscQueryPage.query, StagingGscQueryPage.page, StagingGscQueryPage.country,
            StagingGscQueryPage.device, StagingGscQueryPage.gsc_site_url, StagingGscQueryPage.impressions,
            StagingGscQueryPage.clicks, StagingGscQueryPage.ctr, StagingGscQueryPage.average_position,
        )
        .filter(StagingGscQueryPage.job_id == job.id, StagingGscQueryPage.client_id == job.client_id)
        .yield_per(STREAM_BATCH_SIZE)
    ):
        query = (row.query or "").strip()
        if row.date is None or not query or not row.page:
            continue
        site = (row.gsc_site_url or "").strip()
        normalized_url = urls.normalized(row.page, site)
        if not normalized_url:
            continue
        if _oversize(query, row.page, normalized_url, site, row.country, row.device):
            skipped += 1
            continue
        payloads.append(
            {
                "client_id": job.client_id,
                "date": row.date,
                "query": query,
                "raw_url": row.page,
                "normalized_url": normalized_url,
                "country": row.country or "",
                "device": row.device or "",
                "impressions": row.impressions or Decimal(0),
                "clicks": row.clicks or Decimal(0),
                "ctr": row.ctr or Decimal(0),
                "average_position": row.average_position or Decimal(0),
                "is_primary": urls.is_primary(site),
                "gsc_site_url": site,
            }
        )
    _note_skipped(job, skipped)
    if not payloads:
        return 0

    payloads = _dedupe_payloads(payloads, _query_grain_key)
    _replace_scope(db, FactGscQueryPage, job, payloads)
    _upsert(db, FactGscQueryPage, "uq_facts_gsc_query_pages_grain", ("raw_url", "impressions", "clicks", "ctr", "average_position"), payloads)
    db.commit()
    return len(payloads)


