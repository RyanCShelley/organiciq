"""Reading the page a keyword target points at.

Aquaman Leak Detection's homepage was told its term was missing from "any
heading" although it has the term in an H1 and an H2. The target was typed as
`http://…`; the crawl had a row for that URL carrying the 301 and, parsed from
the page it redirected to, the title and description, but no headings, because
headings are only recorded for a 2xx. The engine read the missing headings as a
page without any.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.decisions.catalog import v1_term_in_high_value_spots
from app.decisions.targets import score_candidate
from app.models.client import Client
from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSnapshot
from app.models.decision import KeywordTarget
from app.models.seranking import FactSerKeyword
from app.services.target_signals import load_target_inputs

TERM = "pool leak detection"
TITLE = "Swimming Pool Leak Detection & Repair | Brevard County, FL"
SECTIONS = [
    {"level": 1, "heading": "Florida’s Swimming Pool Leak Detection Experts", "first_paragraph": ""},
    {"level": 2, "heading": "Pool Leak Detection in Brevard County and Beyond", "first_paragraph": ""},
]


def _row(client, normalized, **kw):
    base = dict(
        client_id=client.id,
        source=CRAWL_SOURCE_FIRST_PARTY,
        snapshot_date=date(2026, 10, 1),
        raw_url=normalized,
        normalized_url=normalized,
        title=TITLE,
        description="We find and repair leaks in your pool.",
        word_count=900,
    )
    base.update(kw)
    return FactCrawlPageSnapshot(**base)


def _target(db: Session, client: Client, url: str) -> None:
    db.add(FactSerKeyword(client_id=client.id, site_engine_id="test", keyword_id="term", keyword=TERM, is_tracked=True))
    db.add(
        KeywordTarget(
            client_id=client.id,
            keyword=TERM,
            target_url=url,
            source="confirmed",
            term_role="primary",
            priority=True,
        )
    )


def _v1(db: Session, client: Client, url: str):
    inputs = load_target_inputs(db, client)
    page = inputs.pages[url]
    candidate = inputs.candidates[0]
    return page, v1_term_in_high_value_spots(score_candidate(candidate), page)


def test_a_target_typed_as_http_reads_the_page_it_redirects_to(db: Session, client_a: Client):
    db.add(
        _row(
            client_a,
            "http://aquaman.example/",
            status_code=301,
            redirect_url="https://aquaman.example/",
            sections=None,
        )
    )
    db.add(_row(client_a, "https://aquaman.example/", status_code=200, sections=SECTIONS))
    _target(db, client_a, "http://aquaman.example/")
    db.commit()

    page, found = _v1(db, client_a, "http://aquaman.example/")
    assert page.headings_known
    assert any(TERM in h.lower() for h in page.headings)
    assert found is None


def test_a_www_or_cased_target_still_finds_its_row(db: Session, client_a: Client):
    db.add(_row(client_a, "https://aquaman.example/services", status_code=200, sections=SECTIONS))
    _target(db, client_a, "https://WWW.aquaman.example/services")
    db.commit()

    page, _ = _v1(db, client_a, "https://WWW.aquaman.example/services")
    assert page.crawled and page.headings_known


def test_a_redirect_that_goes_nowhere_readable_is_unknown_not_empty(db: Session, client_a: Client):
    db.add(
        _row(
            client_a,
            "http://aquaman.example/",
            status_code=301,
            redirect_url="https://aquaman.example/",
            sections=None,
        )
    )
    _target(db, client_a, "http://aquaman.example/")
    db.commit()

    page, found = _v1(db, client_a, "http://aquaman.example/")
    assert not page.headings_known
    assert found is None
