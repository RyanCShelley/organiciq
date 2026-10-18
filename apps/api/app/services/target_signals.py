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

import re

from dataclasses import dataclass
from datetime import date
from statistics import median
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.urls import normalize_url
from app.decisions.catalog import PageFacts, SectionFacts
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

#: Schema types that declare a page's questions as questions.
_FAQ_TYPES = ("faqpage", "qapage")

#: A heading that reads as a question. Matches the crawler's own test, so a
#: heading counted here is the one a visitor sees as a question.
_QUESTION_OPENERS = frozenset(
    "what how why when where which who can does do is are should".split()
)


def _is_question(text: str) -> bool:
    import re

    stripped = (text or "").strip()
    if not stripped:
        return False
    if stripped.endswith("?"):
        return True
    first = re.split(r"[^a-z']+", stripped.lower(), maxsplit=1)[0]
    return first in _QUESTION_OPENERS


#: A heading that announces an FAQ section. Narrow on purpose: a page that
#: says this has one, and a page that does not is a guess.
_FAQ_HEADING = re.compile(
    r"^\s*(?:faqs?|frequently\s+asked(?:\s+questions?)?|common\s+questions?"
    r"|questions?\s+(?:and|&)\s+answers?)\b",
    re.IGNORECASE,
)


def _has_faq_section(sections: list[dict]) -> bool:
    """Whether a heading says the page has an FAQ.

    Read rather than inferred. Two passes at inferring it from
    question-shaped headings were wrong in both directions on SMA's
    /capabilities/local-seo: they caught three marketing headings and missed
    the actual "Frequently asked questions" section, whose Q&A pairs sit in
    an accordion and so are not headings at all.
    """
    return any(
        _FAQ_HEADING.match(str(section.get("heading") or "")) for section in sections
    )


def _declares_faq(raw: object) -> bool:
    """Whether the page's JSON-LD declares an FAQ.

    Walks the document for the same reason `_entity_properties` does: a
    graph has to be walked rather than read off the top.
    """
    found = False

    def walk(node: object) -> None:
        nonlocal found
        if found:
            return
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        declared = node.get("@type")
        types = declared if isinstance(declared, list) else [declared]
        if any(isinstance(t, str) and t.strip().lower() in _FAQ_TYPES for t in types):
            found = True
            return
        for value in node.values():
            walk(value)

    walk(raw)
    return found


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


#: Redirect hops followed to reach the page that actually serves a target.
_MAX_REDIRECT_HOPS = 5


def _snapshot_for(crawl: dict, url: str):
    """The crawl row for the page a target URL really lands on.

    A target is typed by a person: `http://`, `www.`, a missing trailing slash.
    The crawl keys its rows on the normalized form, and records a redirecting
    URL as a row of its own with the status of the redirect, so its headings
    and the other checks that need a 2xx page are null. Reading the row for
    the typed URL gave a title and a description (parsed from the page it
    redirected to) and no headings: a page that looked as if it had none.

    So the URL is normalized, and a row that only redirects is followed to the
    row that serves. Where the chain ends on nothing readable the last row is
    returned, and its null headings say "unknown".
    """
    row = crawl.get(normalize_url(url))
    for _ in range(_MAX_REDIRECT_HOPS):
        if row is None or not row.redirect_url:
            break
        status = row.status_code
        if status is not None and 200 <= status < 300:
            break
        nxt = crawl.get(normalize_url(row.redirect_url))
        if nxt is None or nxt is row:
            break
        row = nxt
    return row


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
    # Read, never pulled — the monthly job does the spending.
    from app.services.serp_features import load as load_serp_features

    serp = load_serp_features(db, client)

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
    faq_schema_urls: set[str] = set()
    if snapshot_date:
        for row in db.query(FactCrawlPageSchema).filter(
            FactCrawlPageSchema.client_id == client.id,
            FactCrawlPageSchema.snapshot_date == snapshot_date,
        ):
            schema_by_url.setdefault(row.normalized_url, set()).update(
                _entity_properties(row.raw)
            )
            if (row.schema_type or "").strip().lower() in _FAQ_TYPES or _declares_faq(
                row.raw
            ):
                faq_schema_urls.add(row.normalized_url)

    candidates: list[Candidate] = []
    pages: dict[str, PageFacts] = {}
    excluded: list[dict[str, str]] = []
    from app.models.watch_target import WatchTarget
    from app.services.watchlist import item_key
    watch_states = {x.item_key: x.state for x in db.query(WatchTarget).filter(
        WatchTarget.client_id == client.id, WatchTarget.kind == "keyword")}

    for target in targets:
        # Exclusions are explicit strategy decisions, not low scores.
        state = watch_states.get(item_key("keyword", target.keyword))
        if state in ("excluded", "planned", "unmapped"):
            continue
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
        snapshot = _snapshot_for(crawl, url) if url else None

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
                volume=float(metric.volume) if metric and metric.volume is not None else (
                    float(tracked_row.volume) if tracked_row and tracked_row.volume is not None else None
                ),
                difficulty=float(metric.difficulty)
                if metric and metric.difficulty
                else None,
                priority=bool(target.priority),
                term_role=target.term_role,
                target_page_type=(
                    classify_page_url(url).page_type.value if url else None
                ),
                group_name=target.group_name,
                serp_features=frozenset(
                    serp[target.keyword.strip().lower()].item_types
                )
                if target.keyword.strip().lower() in serp
                else frozenset(),
                serp_pulled=target.keyword.strip().lower() in serp,
            )
        )

        if url and url not in pages:
            headings = ()
            faqs = ()
            raw_sections: list[dict] = []
            sections: tuple[SectionFacts, ...] = ()
            if snapshot is not None:
                raw_sections = [
                    sec for sec in (snapshot.sections or []) if isinstance(sec, dict)
                ]
                headings = tuple(
                    str(sec.get("heading") or "") for sec in raw_sections
                )
                # Only where the crawl captured the flags. A crawl that
                # predates them would otherwise read as a page with no
                # structure anywhere, and V-5 would prescribe a table for
                # the whole site.
                if any("has_table" in sec for sec in raw_sections):
                    sections = tuple(
                        SectionFacts(
                            heading=str(sec.get("heading") or ""),
                            has_table=bool(sec.get("has_table")),
                            has_list=bool(sec.get("has_list")),
                            has_stat=bool(sec.get("has_stat")),
                        )
                        for sec in raw_sections
                    )
                faqs = tuple(str(q) for q in (snapshot.faq_questions or []))
            pages[url] = PageFacts(
                url=url,
                title=getattr(snapshot, "title", None),
                description=getattr(snapshot, "description", None),
                headings=headings,
                crawled=snapshot is not None,
                headings_known=snapshot is not None and snapshot.sections is not None,
                sections=sections,
                has_faq_section=_has_faq_section(raw_sections),
                has_faq_schema=(snapshot.normalized_url if snapshot else url) in faq_schema_urls,
                faq_questions=faqs,
                entity_properties=frozenset(
                    schema_by_url.get(snapshot.normalized_url if snapshot else url, set())
                ),
                inbound_editorial_links=int(
                    getattr(snapshot, "inbound_editorial_links", 0) or 0
                ),
                site_median_links=site_median,
                page_type=(classify_page_url(url).page_type.value if url else None),
            )

    return TargetInputs(candidates=candidates, pages=pages, excluded=excluded)
