from __future__ import annotations

from datetime import date
from typing import Any
from urllib.parse import urlparse

from app.core.urls import normalize_url
from app.ingestion.seranking import client as ser_client


def _parse_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def _truthy(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes"}


def parse_audit_page(page: dict[str, Any]) -> dict[str, Any]:
    raw_url = str(page.get("url") or "").strip()
    canonical_raw = str(page.get("canonical_url") or "").strip() or None
    indexable_status = str(page.get("indexable_status") or "").strip().lower()
    indexable = not _truthy(page.get("noindex"))
    if indexable_status and indexable_status != "ok":
        indexable = False

    title = str(page.get("title") or "").strip()
    description = str(page.get("description") or "").strip()
    robots = str(page.get("robots") or page.get("xrobots") or "").strip() or None
    redirect_raw = str(page.get("redirect_url") or "").strip() or None

    return {
        "raw_url": raw_url,
        "normalized_url": normalize_url(raw_url) if raw_url else "",
        "indexable": indexable,
        "status_code": _parse_int(page.get("status")),
        "canonical_url": normalize_url(canonical_raw) if canonical_raw else None,
        "inbound_internal_links": _parse_int(page.get("inlinks")) or 0,
        "word_count": _parse_int(page.get("words_count")) or 0,
        "in_sitemap": _truthy(page.get("sitemap")),
        # Empty string = known missing; None only when column never populated (pre-enrichment).
        "title": title,
        "description": description,
        "title_duplicate": _truthy(page.get("title_duplicate")),
        "description_duplicate": _truthy(page.get("description_duplicate")),
        "robots": robots,
        "blocked_by_robots": _truthy(page.get("blocked_robots")),
        "redirect_url": normalize_url(redirect_raw) if redirect_raw else None,
        "redirect_count": _parse_int(page.get("redirect_count")) or 0,
    }


def _host_matches(a: str, b: str) -> bool:
    left = (urlparse(a if "://" in a else f"https://{a}").hostname or a).lower().removeprefix("www.")
    right = (urlparse(b if "://" in b else f"https://{b}").hostname or b).lower().removeprefix("www.")
    return left == right or left.endswith(f".{right}") or right.endswith(f".{left}")


def resolve_latest_finished_audit(
    *,
    api_key: str,
    site_id: str,
    client_domain: str,
    search: str | None = None,
) -> tuple[int, date]:
    """Return the newest finished Website Audit for the mapped SE Ranking project."""
    site_id_text = str(site_id).strip()
    domain = client_domain.strip()
    search_term = (search or domain).strip()

    candidates: list[dict[str, Any]] = []
    offset = 0
    page_size = 100
    while True:
        payload = ser_client.list_site_audits(
            api_key=api_key,
            limit=page_size,
            offset=offset,
            search=search_term or None,
        )
        items = payload.get("items") or []
        if not isinstance(items, list):
            break
        candidates.extend(item for item in items if isinstance(item, dict))
        total = int(payload.get("total") or 0)
        offset += len(items)
        if offset >= total or not items:
            break

    finished: list[tuple[date, int]] = []
    for item in candidates:
        status = str(item.get("status") or "").strip().lower()
        if status != "finished":
            continue
        audit_site_id = item.get("site_id")
        audit_url = str(item.get("url") or "").strip()
        if audit_site_id is not None and str(audit_site_id) == site_id_text:
            matched = True
        elif audit_site_id is None and audit_url and domain and _host_matches(audit_url, domain):
            matched = True
        else:
            matched = False
        if not matched:
            continue
        audit_id = item.get("id")
        last_update = str(item.get("last_update") or "").strip()
        if audit_id is None or not last_update:
            continue
        try:
            snapshot_date = date.fromisoformat(last_update[:10])
        except ValueError:
            continue
        finished.append((snapshot_date, int(audit_id)))

    if not finished:
        raise RuntimeError(
            "No finished SE Ranking Website Audit found for this project. "
            "Run an audit in SE Ranking, wait until it completes, then retry."
        )

    finished.sort(key=lambda row: (row[0], row[1]), reverse=True)
    snapshot_date, audit_id = finished[0]
    return audit_id, snapshot_date
