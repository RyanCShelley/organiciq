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


def resolve_project_audit(*, api_key: str, site_id: str) -> tuple[int, date]:
    """
    Return (audit_id, snapshot_date) for the audit attached to an SE Ranking project.

    Our clients' audits live on their projects, addressed by the project id — not in
    the standalone Site Audit tool, which is a separate product with its own list.
    Searching that list by domain found nothing and failed every audit sync, so the
    project id from the integration mapping is the identifier to use.
    """
    audit_id = _parse_int(site_id)
    if audit_id is None:
        raise RuntimeError(
            "SE Ranking project id is missing or not numeric; reconnect the integration"
        )

    status = ser_client.get_audit_status(api_key=api_key, audit_id=audit_id)
    state = str(status.get("status") or "").strip().lower()
    if not state:
        raise RuntimeError(
            f"SE Ranking project {audit_id} has no website audit. "
            "Run an audit in SE Ranking, wait for it to finish, then retry."
        )
    if state != "finished":
        raise RuntimeError(
            f"SE Ranking website audit for project {audit_id} is {state}; "
            "wait for it to finish, then retry."
        )

    audit_time = str(status.get("audit_time") or "").strip()
    try:
        snapshot_date = date.fromisoformat(audit_time[:10])
    except ValueError as exc:
        raise RuntimeError(
            f"SE Ranking website audit for project {audit_id} reported an unreadable "
            f"completion time ({audit_time!r})"
        ) from exc

    return audit_id, snapshot_date
