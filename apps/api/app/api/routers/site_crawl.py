"""What the first-party crawl found, for the Site crawl views.

Read-only. The Decision Engine already consumes this data as findings; these
endpoints exist so the underlying crawl can be looked at directly — which page
is orphaned, which carries no structured data — without querying the database.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_staff
from app.models.client import Client
from app.models.crawl import (
    CRAWL_SOURCE_FIRST_PARTY,
    FactCrawlInternalLink,
    FactCrawlPageIssue,
    FactCrawlPageSchema,
    FactCrawlPageSnapshot,
)
from app.services.lever_engine import BOILERPLATE_SCHEMA_TYPES

router = APIRouter(prefix="/site-crawl", tags=["site-crawl"])

#: Enough to work through a site without returning a whole catalogue at once.
DEFAULT_LIMIT = 500
MAX_LIMIT = 5000


def _schema_by_url(db: Session, client_id) -> dict[str, list[FactCrawlPageSchema]]:
    rows: dict[str, list[FactCrawlPageSchema]] = {}
    for row in db.query(FactCrawlPageSchema).filter(FactCrawlPageSchema.client_id == client_id):
        rows.setdefault(row.normalized_url, []).append(row)
    return rows


def _crawled_at(db: Session, client_id) -> str | None:
    value = (
        db.query(func.max(FactCrawlPageSnapshot.snapshot_date))
        .filter(
            FactCrawlPageSnapshot.client_id == client_id,
            FactCrawlPageSnapshot.source == CRAWL_SOURCE_FIRST_PARTY,
        )
        .scalar()
    )
    return value.isoformat() if value else None


@router.get("/pages")
def crawled_pages(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
) -> dict[str, Any]:
    """Every page the crawl reached, worst first."""
    rows = (
        db.query(FactCrawlPageSnapshot)
        .filter(
            FactCrawlPageSnapshot.client_id == client.id,
            FactCrawlPageSnapshot.source == CRAWL_SOURCE_FIRST_PARTY,
        )
        .all()
    )
    schema = _schema_by_url(db, client.id)

    def sort_key(row: FactCrawlPageSnapshot) -> tuple:
        # Problems first: not indexable, then no editorial links, then thin.
        return (
            row.indexable,
            row.inbound_editorial_links,
            row.word_count,
        )

    ordered = sorted(rows, key=sort_key)
    items = [
        {
            "url": row.normalized_url,
            "status_code": row.status_code,
            "indexable": row.indexable,
            "title": row.title,
            "word_count": row.word_count,
            "inbound_internal_links": row.inbound_internal_links,
            "inbound_editorial_links": row.inbound_editorial_links,
            "in_sitemap": row.in_sitemap,
            "redirect_count": row.redirect_count,
            "schema_blocks": len(schema.get(row.normalized_url, [])),
        }
        for row in ordered[:limit]
    ]

    indexable = [row for row in rows if row.indexable]
    # "Missing from the sitemap" is only a statement when a sitemap was found.
    # Without one, every page would read as missing, when the real finding is
    # the site-level sitemap_missing the crawl already records.
    sitemap_missing = (
        db.query(FactCrawlPageIssue)
        .filter(
            FactCrawlPageIssue.client_id == client.id,
            FactCrawlPageIssue.source == CRAWL_SOURCE_FIRST_PARTY,
            FactCrawlPageIssue.issue_code == "sitemap_missing",
        )
        .first()
        is not None
    )
    pages_in_sitemap = sum(1 for row in rows if row.in_sitemap)
    return {
        "crawled_at": _crawled_at(db, client.id),
        "total_pages": len(rows),
        "indexable_pages": len(indexable),
        "sitemap_found": not sitemap_missing and pages_in_sitemap > 0,
        "pages_in_sitemap": pages_in_sitemap,
        "orphaned_pages": sum(1 for row in indexable if row.inbound_editorial_links == 0),
        "items": items,
        "truncated": len(ordered) > len(items),
    }


@router.get("/schema")
def structured_data(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
) -> dict[str, Any]:
    """Structured-data coverage, and the pages that need attention."""
    pages = (
        db.query(FactCrawlPageSnapshot)
        .filter(
            FactCrawlPageSnapshot.client_id == client.id,
            FactCrawlPageSnapshot.source == CRAWL_SOURCE_FIRST_PARTY,
            FactCrawlPageSnapshot.indexable.is_(True),
        )
        .all()
    )
    schema = _schema_by_url(db, client.id)

    type_counts: dict[str, int] = {}
    for blocks in schema.values():
        for block in blocks:
            if block.schema_type:
                type_counts[block.schema_type] = type_counts.get(block.schema_type, 0) + 1

    gaps: list[dict[str, Any]] = []
    with_descriptive = 0
    for page in pages:
        blocks = schema.get(page.normalized_url, [])
        types = {b.schema_type for b in blocks if b.schema_type}
        descriptive = types - BOILERPLATE_SCHEMA_TYPES
        invalid = [b for b in blocks if b.parse_error]

        if descriptive and not invalid:
            with_descriptive += 1
            continue

        # Ordered by how wrong it is: broken markup, then none, then boilerplate.
        if invalid:
            issue, detail = "invalid", invalid[0].parse_error
        elif not blocks:
            issue, detail = "missing", None
        else:
            issue, detail = "boilerplate_only", ", ".join(sorted(types))
        gaps.append(
            {
                "url": page.normalized_url,
                "title": page.title,
                "issue": issue,
                "detail": detail,
                "types": sorted(types),
            }
        )

    rank = {"invalid": 0, "missing": 1, "boilerplate_only": 2}
    gaps.sort(key=lambda row: (rank[row["issue"]], row["url"]))

    return {
        "crawled_at": _crawled_at(db, client.id),
        "indexable_pages": len(pages),
        "pages_with_descriptive_schema": with_descriptive,
        "total_blocks": sum(len(b) for b in schema.values()),
        "invalid_blocks": sum(1 for b in schema.values() for x in b if x.parse_error),
        "types": [
            {"type": name, "count": count}
            for name, count in sorted(type_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        "gaps": gaps[:limit],
        "truncated": len(gaps) > limit,
    }


@router.get("/page")
def page_detail(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    url: str = Query(..., description="Normalized page URL"),
) -> dict[str, Any]:
    """
    One page: what links to it, what it links to, and its structured data.

    The link graph and the raw schema blocks are both stored and were both
    invisible — this is the view that makes them usable.
    """
    page = (
        db.query(FactCrawlPageSnapshot)
        .filter(
            FactCrawlPageSnapshot.client_id == client.id,
            FactCrawlPageSnapshot.source == CRAWL_SOURCE_FIRST_PARTY,
            FactCrawlPageSnapshot.normalized_url == url,
        )
        .one_or_none()
    )
    if page is None:
        return {"found": False, "url": url}

    def link_payload(rows, attribute: str) -> list[dict[str, Any]]:
        # Editorial links first: those are the ones worth reading.
        ordered = sorted(rows, key=lambda r: (r.is_template, getattr(r, attribute)))
        return [
            {
                "url": getattr(row, attribute),
                "anchor_text": row.anchor_text,
                "is_template": row.is_template,
                "in_content": row.in_content,
                "occurrences": row.occurrences,
            }
            for row in ordered
        ]

    inbound = (
        db.query(FactCrawlInternalLink)
        .filter(
            FactCrawlInternalLink.client_id == client.id,
            FactCrawlInternalLink.source == CRAWL_SOURCE_FIRST_PARTY,
            FactCrawlInternalLink.to_url == url,
        )
        .all()
    )
    outbound = (
        db.query(FactCrawlInternalLink)
        .filter(
            FactCrawlInternalLink.client_id == client.id,
            FactCrawlInternalLink.source == CRAWL_SOURCE_FIRST_PARTY,
            FactCrawlInternalLink.from_url == url,
        )
        .all()
    )
    blocks = (
        db.query(FactCrawlPageSchema)
        .filter(
            FactCrawlPageSchema.client_id == client.id,
            FactCrawlPageSchema.normalized_url == url,
        )
        .all()
    )

    return {
        "found": True,
        "url": page.normalized_url,
        "raw_url": page.raw_url,
        "title": page.title,
        "description": page.description,
        "status_code": page.status_code,
        "indexable": page.indexable,
        "canonical_url": page.canonical_url,
        "robots": page.robots,
        "word_count": page.word_count,
        "in_sitemap": page.in_sitemap,
        "redirect_url": page.redirect_url,
        "inbound_internal_links": page.inbound_internal_links,
        "inbound_editorial_links": page.inbound_editorial_links,
        "inbound": link_payload(inbound, "from_url"),
        "outbound": link_payload(outbound, "to_url"),
        "schema_blocks": [
            {
                "syntax": block.syntax,
                "schema_type": block.schema_type,
                "parse_error": block.parse_error,
                "raw": block.raw,
                "raw_text": block.raw_text,
            }
            for block in sorted(
                blocks, key=lambda b: (b.parse_error is None, b.schema_type or "")
            )
        ],
    }
