"""Funnel stage on landing pages, and the L3 test it unblocks.

The rule this module has to keep: a model's reading is a suggestion, and only
a stage somebody confirmed is read by the engine. `client_conversion_pages`
exists because guessing a page's role from its URL was wrong often enough to
hide how often it was wrong; replacing a URL guess with a model guess, taken
as fact, would be the same mistake wearing a better coat.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.config import (
    ClientConversionPage,
    ClientPageStage,
    OrganicChannel,
)
from app.models.crawl import FactCrawlInternalLink, FactCrawlPageSnapshot
from app.models.ga4 import FactGa4Traffic
from app.services import page_stage
from app.services.triage_signals import _next_step

TODAY = date(2026, 10, 31)
MONTH_START = date(2026, 10, 1)


def _page(db: Session, client: Client, url: str, *, title: str, sections: list | None = None):
    db.add(
        FactCrawlPageSnapshot(
            client_id=client.id,
            snapshot_date=TODAY,
            raw_url=url,
            normalized_url=url,
            title=title,
            word_count=900,
            sections=sections
            or [{"level": 2, "heading": "What it is", "first_paragraph": "An explainer."}],
        )
    )


def _sessions(db: Session, client: Client, url: str, count: int):
    db.add(
        FactGa4Traffic(
            client_id=client.id,
            date=MONTH_START + timedelta(days=3),
            raw_url=url,
            normalized_url=url,
            channel=OrganicChannel.ORGANIC_SEARCH,
            sessions=count,
        )
    )


def _confirm(db: Session, client: Client, url: str, stage: str):
    page_stage.confirm(db, client, [(url, stage)], user_id=None)


# ── The suggestion never becomes the answer ─────────────────────────────────


def test_a_suggestion_is_not_a_confirmed_stage(db: Session, client_a: Client):
    page_stage.save_suggestions(
        db,
        client_a,
        [page_stage.Suggestion("/guide", "tofu", "high", "Explains a term.")],
        model="test-model",
    )
    assert page_stage.confirmed_stages(db, client_a.id) == {}

    _confirm(db, client_a, "/guide", "tofu")
    assert page_stage.confirmed_stages(db, client_a.id) == {"/guide": "tofu"}


def test_re_suggesting_does_not_revise_a_confirmed_stage(db: Session, client_a: Client):
    _confirm(db, client_a, "/guide", "bofu")
    page_stage.save_suggestions(
        db,
        client_a,
        [page_stage.Suggestion("/guide", "tofu", "high", "Reads as an explainer.")],
        model="test-model",
    )
    row = (
        db.query(ClientPageStage)
        .filter(ClientPageStage.normalized_url == "/guide")
        .one()
    )
    # The disagreement is kept rather than resolved silently.
    assert row.stage == "bofu"
    assert row.suggested_stage == "tofu"


def test_a_reply_about_a_page_we_did_not_ask_about_is_dropped():
    text = """{"pages": [
        {"url": "/real", "stage": "tofu", "confidence": "high", "rationale": "x"},
        {"url": "/invented", "stage": "tofu", "confidence": "high", "rationale": "y"},
        {"url": "/real2", "stage": "sideways", "confidence": "high", "rationale": "z"}
    ]}"""
    out = page_stage._parse_suggestions(text, {"/real", "/real2"})
    assert [s.normalized_url for s in out] == ["/real"]


def test_an_unknown_confidence_falls_back_to_low():
    out = page_stage._parse_suggestions(
        '{"pages": [{"url": "/a", "stage": "mofu", "confidence": "certain", "rationale": ""}]}',
        {"/a"},
    )
    assert out[0].confidence == "low"


def test_a_reply_with_no_json_is_an_error():
    with pytest.raises(page_stage.NotConfigured):
        page_stage._parse_suggestions("I could not read those pages.", {"/a"})


# ── Candidates ──────────────────────────────────────────────────────────────


def test_candidates_are_landing_pages_that_drew_sessions_busiest_first(
    db: Session, client_a: Client
):
    _page(db, client_a, "/quiet", title="Quiet")
    _page(db, client_a, "/busy", title="Busy")
    _page(db, client_a, "/never-visited", title="Unvisited")
    _sessions(db, client_a, "/quiet", 10)
    _sessions(db, client_a, "/busy", 400)
    db.commit()

    found = page_stage.load_candidates(db, client_a, today=TODAY)
    assert [c.normalized_url for c in found] == ["/busy", "/quiet"]
    assert found[0].sessions == 400


def test_a_page_with_nothing_to_read_is_not_offered(db: Session, client_a: Client):
    # No title and no headings: a model would be guessing from the URL, which
    # is the thing this exists to avoid.
    db.add(
        FactCrawlPageSnapshot(
            client_id=client_a.id,
            snapshot_date=TODAY,
            raw_url="/blank",
            normalized_url="/blank",
            title=None,
            word_count=0,
            sections=[],
        )
    )
    _sessions(db, client_a, "/blank", 99)
    db.commit()
    assert page_stage.load_candidates(db, client_a, today=TODAY) == []


# ── L3 ──────────────────────────────────────────────────────────────────────


def test_l3_blocks_until_conversion_pages_exist(db: Session, client_a: Client):
    value, reason = _next_step(db, client_a, MONTH_START, TODAY)
    assert value is None
    assert reason == "no conversion pages declared to route to"


def test_l3_names_the_stage_gap_once_conversion_pages_exist(
    db: Session, client_a: Client
):
    db.add(
        ClientConversionPage(
            client_id=client_a.id, normalized_url="/contact", label="Contact"
        )
    )
    db.commit()
    value, reason = _next_step(db, client_a, MONTH_START, TODAY)
    assert value is None
    assert "no landing page has a confirmed funnel stage" in (reason or "")


def test_l3_reports_coverage_rather_than_a_thin_number(db: Session, client_a: Client):
    db.add(
        ClientConversionPage(
            client_id=client_a.id, normalized_url="/contact", label="Contact"
        )
    )
    _sessions(db, client_a, "/labelled", 10)
    _sessions(db, client_a, "/unlabelled", 990)
    db.commit()
    _confirm(db, client_a, "/labelled", "tofu")

    value, reason = _next_step(db, client_a, MONTH_START, TODAY)
    # 1% covered: the share would be real and say nothing about the site.
    assert value is None
    assert "cover 1% of managed sessions" in (reason or "")


def test_l3_counts_tofu_sessions_with_no_in_content_route_out(
    db: Session, client_a: Client
):
    db.add(
        ClientConversionPage(
            client_id=client_a.id, normalized_url="/contact", label="Contact"
        )
    )
    _sessions(db, client_a, "/dead-end", 300)
    _sessions(db, client_a, "/routed", 100)
    _sessions(db, client_a, "/service", 100)

    # /routed links onward in content; /service is not top of funnel.
    db.add(
        FactCrawlInternalLink(
            client_id=client_a.id,
            snapshot_date=TODAY,
            from_url="/routed",
            to_url="/contact",
            in_content=True,
            is_template=False,
        )
    )
    db.commit()
    _confirm(db, client_a, "/dead-end", "tofu")
    _confirm(db, client_a, "/routed", "tofu")
    _confirm(db, client_a, "/service", "mofu")

    value, reason = _next_step(db, client_a, MONTH_START, TODAY)
    assert reason is None
    # 300 of 500 covered sessions land somewhere with no way onward.
    assert value == pytest.approx(60.0)


def test_a_footer_link_is_not_a_route_onward(db: Session, client_a: Client):
    db.add(
        ClientConversionPage(
            client_id=client_a.id, normalized_url="/contact", label="Contact"
        )
    )
    _sessions(db, client_a, "/guide", 100)
    # Site furniture: it is on every page and says nothing about this one.
    db.add(
        FactCrawlInternalLink(
            client_id=client_a.id,
            snapshot_date=TODAY,
            from_url="/guide",
            to_url="/contact",
            in_content=False,
            is_template=True,
        )
    )
    db.commit()
    _confirm(db, client_a, "/guide", "tofu")

    value, _ = _next_step(db, client_a, MONTH_START, TODAY)
    assert value == pytest.approx(100.0)
