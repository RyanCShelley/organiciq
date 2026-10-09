"""Build Decision 2's candidates, and the page facts the catalog reads.

Decision 2 scores a keyword-page pair and the catalog decides what to do
about it. Both are pure functions over explicit inputs; this is the join that
assembles those inputs from the warehouse.

Candidates come from `keyword_targets` rather than from everything the rank
tracker follows. That is the point of the map: a term somebody declared a
page for is a term somebody intends to win, and the engine stops guessing
which page it meant.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from statistics import median
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.decisions.catalog import PageFacts
from app.decisions.overrides import Exclusion, is_excluded
from app.decisions.targets import Candidate
from app.models.client import Client
from app.models.crawl import (
    CRAWL_SOURCE_FIRST_PARTY,
    FactCrawlPageSchema,
    FactCrawlPageSnapshot,
)
from app.models.decision import KeywordTarget
from app.models.seranking import FactSerKeyword, FactSerKeywordMetric
from app.services.page_eligibility import classify_page_url

#: Entity properties V-3 looks for, as they appear in JSON-LD.
_ENTITY_KEYS = ("about", "mentions", "sameAs")


@dataclass(frozen=True)
class TargetInputs:
    candidates: list[Candidate]
    pages: dict[str, PageFacts]
    #: Terms dropped because their page is excluded, with the reason. Carried
    #: so the record can say a target was skipped on purpose rather than
    #: leaving a silent absence.
    excluded: list[dict[str, str]]


def _rank(value: object) -> float | None:
    try:
        position = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return position if 0 < position <= 100 else None


def _entity_properties(raw: object) -> set[str]:
    """Which entity properties the page's JSON-LD carries.

    The crawl stores the whole document per row, so a graph has to be walked
    rather than read off the top — reading the top is what made an `@context`
    wrapper look like an Organization block and failed an entity check on
    every site.
    """
    found: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in _ENTITY_KEYS and value:
                    found.add(key)
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(raw)
    return found


def _latest_crawl_date(db: Session, client_id: UUID) -> date | None:
    return (
        db.query(func.max(FactCrawlPageSnapshot.snapshot_date))
        .filter(
            FactCrawlPageSnapshot.client_id == client_id,
            FactCrawlPageSnapshot.source == CRAWL_SOURCE_FIRST_PARTY,
        )
        .scalar()
    )


def load_target_inputs(
    db: Session, client: Client, *, exclusions: list[Exclusion] | None = None
) -> TargetInputs:
    exclusions = exclusions or []

    targets = (
        db.query(KeywordTarget)
        .filter(
            KeywordTarget.client_id == client.id,
            KeywordTarget.source == "confirmed",
        )
        .all()
    )
    tracked = {
        (row.keyword or "").strip().lower(): row
        for row in db.query(FactSerKeyword).filter(FactSerKeyword.client_id == client.id)
    }
    metrics = {
        (row.keyword or "").strip().lower(): row
        for row in db.query(FactSerKeywordMetric).filter(
            FactSerKeywordMetric.client_id == client.id
        )
    }

    snapshot_date = _latest_crawl_date(db, client.id)
    crawl = {
        row.normalized_url: row
        for row in db.query(FactCrawlPageSnapshot).filter(
            FactCrawlPageSnapshot.client_id == client.id,
            FactCrawlPageSnapshot.source == CRAWL_SOURCE_FIRST_PARTY,
            FactCrawlPageSnapshot.snapshot_date == snapshot_date,
        )
    } if snapshot_date else {}

    # "Under-linked" is relative to this site: a five-page site links
    # everything from everywhere for legitimate reasons.
    link_counts = [
        int(row.inbound_editorial_links or 0) for row in crawl.values()
    ]
    site_median = float(median(link_counts)) if link_counts else 0.0

    schema_by_url: dict[str, set[str]] = {}
    if snapshot_date:
        for row in db.query(FactCrawlPageSchema).filter(
            FactCrawlPageSchema.client_id == client.id,
            FactCrawlPageSchema.snapshot_date == snapshot_date,
        ):
            schema_by_url.setdefault(row.normalized_url, set()).update(
                _entity_properties(row.raw)
            )

    candidates: list[Candidate] = []
    pages: dict[str, PageFacts] = {}
    excluded: list[dict[str, str]] = []

    for target in targets:
        url = (target.target_url or "").strip()
        if url:
            skip = is_excluded(url, exclusions)
            if skip is not None:
                excluded.append(
                    {"keyword": target.keyword, "target_url": url, "reason": skip.reason}
                )
                continue

        tracked_row = tracked.get(target.keyword)
        metric = metrics.get(target.keyword)
        snapshot = crawl.get(url) if url else None

        candidates.append(
            Candidate(
                keyword=target.keyword,
                target_url=url or None,
                ranking_url=(getattr(tracked_row, "ranking_url", None) or None)
                if tracked_row
                else None,
                position=_rank(getattr(tracked_row, "current_position", None))
                if tracked_row
                else None,
                volume=float(metric.volume) if metric and metric.volume else None,
                difficulty=float(metric.difficulty)
                if metric and metric.difficulty
                else None,
                priority=bool(target.priority),
                term_role=target.term_role,
                target_page_type=(
                    classify_page_url(url).page_type.value if url else None
                ),
                group_name=target.group_name,
            )
        )

        if url and url not in pages:
            headings = ()
            faqs = ()
            if snapshot is not None:
                headings = tuple(
                    str(section.get("heading") or "")
                    for section in (snapshot.sections or [])
                    if isinstance(section, dict)
                )
                faqs = tuple(str(q) for q in (snapshot.faq_questions or []))
            pages[url] = PageFacts(
                url=url,
                title=getattr(snapshot, "title", None),
                description=getattr(snapshot, "description", None),
                headings=headings,
                faq_questions=faqs,
                entity_properties=frozenset(schema_by_url.get(url, set())),
                inbound_editorial_links=int(
                    getattr(snapshot, "inbound_editorial_links", 0) or 0
                ),
                site_median_links=site_median,
                page_type=(classify_page_url(url).page_type.value if url else None),
            )

    return TargetInputs(candidates=candidates, pages=pages, excluded=excluded)
