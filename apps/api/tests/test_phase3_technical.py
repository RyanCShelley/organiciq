"""Phase 3: technical rule additions and the two Gate 0 anomalies.

Soft 404s and robots-blocked render resources are not here. SE Ranking's
Website Audit has no check for either — the full code list from a live audit
was read before deciding — and nothing else stores page resources. Building
them would have meant inventing a signal.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from app.models.config import ConversionDefinition, OrganicChannel
from app.models.crawl import FactCrawlPageSnapshot
from app.models.ga4 import FactGa4Event, FactGa4Traffic
from app.models.gsc import FactGscPage
from app.models.job import DataWatermark, ValidationStatus
from app.services.lever_engine import (
    GrowthAction,
    detect_technical_signal,
    diagnose,
    is_core_work_signal,
    signal_lever,
)
from tests.conftest import seed_required_sources

END = date(2026, 8, 31)


def _crawl(**kwargs) -> FactCrawlPageSnapshot:
    defaults = dict(
        id=uuid4(),
        client_id=uuid4(),
        source="se_ranking",
        snapshot_date=END,
        raw_url="https://example.com/p",
        normalized_url="https://example.com/p",
        indexable=True,
        status_code=200,
        canonical_url=None,
        inbound_internal_links=5,
        word_count=800,
        in_sitemap=True,
        inbound_editorial_links=2,
        title="A title",
        description="A description",
        title_duplicate=False,
        description_duplicate=False,
        robots=None,
        blocked_by_robots=False,
        redirect_url=None,
        redirect_count=0,
        soft_404=False,
        blocked_resources=0,
        conversion_elements=5,
    )
    defaults.update(kwargs)
    return FactCrawlPageSnapshot(**defaults)


# ── Titles move to SERP CTR, descriptions stay core work ──


@pytest.mark.parametrize(
    "kwargs,expected",
    [
        ({"title": ""}, "title_missing"),
        ({"title_duplicate": True}, "title_duplicate"),
        ({"description": ""}, "description_missing"),
        ({"description_duplicate": True}, "description_duplicate"),
    ],
)
def test_title_and_description_are_separate_signals(kwargs, expected):
    """They were one signal, so a missing title could not be promoted."""
    detected = detect_technical_signal("https://example.com/p", _crawl(**kwargs))
    assert detected is not None
    assert detected.audit_signal == expected


def test_a_title_problem_is_serp_ctr_work_and_can_be_promoted():
    """A title is the listing. It earns clicks, so it competes for an action."""
    assert signal_lever("title_missing") == GrowthAction.SERP_CTR.value
    assert signal_lever("title_duplicate") == GrowthAction.SERP_CTR.value
    assert not is_core_work_signal("title_missing")
    assert not is_core_work_signal("title_duplicate")


def test_a_description_problem_stays_monthly_upkeep():
    assert signal_lever("description_missing") == GrowthAction.TECHNICAL_SEO.value
    assert is_core_work_signal("description_missing")
    assert is_core_work_signal("description_duplicate")


def test_a_missing_title_outranks_a_missing_description_on_the_same_page():
    """One signal per page, so the one that can be promoted has to win."""
    detected = detect_technical_signal(
        "https://example.com/p", _crawl(title="", description="")
    )
    assert detected is not None
    assert detected.audit_signal == "title_missing"


# ── Orphan pages ──


def test_an_orphan_page_with_demand_is_blocking():
    detected = detect_technical_signal(
        "https://example.com/p",
        _crawl(inbound_internal_links=0),
        impressions=50.0,
        thresholds={"orphan_min_impressions": 30},
    )
    assert detected is not None
    assert detected.audit_signal == "orphan_page"
    assert not is_core_work_signal("orphan_page")


def test_an_orphan_page_nobody_searches_for_is_not_a_finding():
    """Most orphans are drafts and thank-you pages. Demand is what makes it one."""
    assert (
        detect_technical_signal(
            "https://example.com/p",
            _crawl(inbound_internal_links=0),
            impressions=2.0,
            thresholds={"orphan_min_impressions": 30},
        )
        is None
    )


def test_a_linked_page_is_not_an_orphan():
    assert (
        detect_technical_signal(
            "https://example.com/p",
            _crawl(inbound_internal_links=1),
            impressions=500.0,
            thresholds={"orphan_min_impressions": 30},
        )
        is None
    )


def test_a_broken_orphan_reports_the_break_first():
    """A 404 is the bigger problem; being unlinked is why nobody noticed."""
    detected = detect_technical_signal(
        "https://example.com/p",
        _crawl(inbound_internal_links=0, status_code=404),
        impressions=500.0,
        thresholds={"orphan_min_impressions": 30},
    )
    assert detected is not None
    assert detected.audit_signal == "status_error"


# ── Gate 0's two non-silence failures ──


def _lead_def(db, client_id):
    db.add(
        ConversionDefinition(
            id=uuid4(),
            client_id=client_id,
            event_name="generate_lead",
            conversion_name="Lead",
            conversion_type="lead",
            is_primary=True,
            active=True,
        )
    )


def _traffic(db, client_id, day, url, sessions):
    db.add(
        FactGa4Traffic(
            id=uuid4(),
            client_id=client_id,
            date=day,
            raw_url=url,
            normalized_url=url,
            session_source="google",
            session_medium="organic",
            channel=OrganicChannel.ORGANIC_SEARCH,
            sessions=Decimal(str(sessions)),
            active_users=Decimal(str(sessions)),
            views=Decimal(str(sessions)),
        )
    )


def _leads(db, client_id, day, url, count):
    db.add(
        FactGa4Event(
            id=uuid4(),
            client_id=client_id,
            date=day,
            raw_url=url,
            normalized_url=url,
            session_source="google",
            session_medium="organic",
            channel=OrganicChannel.ORGANIC_SEARCH,
            event_name="generate_lead",
            event_count=count,
        )
    )


def _gsc(db, client_id, day, url, impressions=200):
    db.add(
        FactGscPage(
            id=uuid4(),
            client_id=client_id,
            date=day,
            raw_url=url,
            normalized_url=url,
            country="",
            device="",
            impressions=Decimal(str(impressions)),
            clicks=Decimal("10"),
            ctr=Decimal("0.05"),
            average_position=Decimal("9"),
        )
    )


def _watermarks(db, client_id, end):
    for source in ("ga4", "gsc_pages"):
        db.add(
            DataWatermark(
                id=uuid4(),
                client_id=client_id,
                source=source,
                fact_through_date=end,
                validation_status=ValidationStatus.PASSED,
            )
        )


CONTACT = "https://example.com/contact"
QUOTE = "https://example.com/quote"


def _two_forms(db, client_a, *, quote_still_converts: bool):
    """Two forms with history; one may go quiet inside the window."""
    _lead_def(db, client_a.id)
    _watermarks(db, client_a.id, END)
    _gsc(db, client_a.id, END, CONTACT)

    # 60 days of history before the 14-day window, both forms converting.
    window_start = END - timedelta(days=13)
    for offset in range(14, 74):
        day = END - timedelta(days=offset)
        _traffic(db, client_a.id, day, CONTACT, 100)
        _leads(db, client_a.id, day, CONTACT, 2)
        _leads(db, client_a.id, day, QUOTE, 1)

    # The window: contact keeps converting, quote may not.
    for offset in range(14):
        day = window_start + timedelta(days=offset)
        _traffic(db, client_a.id, day, CONTACT, 100)
        _leads(db, client_a.id, day, CONTACT, 2)
        if quote_still_converts:
            _leads(db, client_a.id, day, QUOTE, 1)
    db.commit()
    seed_required_sources(db, client_a.id, END)


def test_one_form_going_quiet_is_found_while_the_site_still_converts(db, client_a):
    """The site total hides this: contact alone keeps the number healthy."""
    _two_forms(db, client_a, quote_still_converts=False)

    result = diagnose(db, client_a, from_date=END - timedelta(days=29), to_date=END)
    partial = [
        row for row in result.findings
        if row.evidence_json.get("gate") == "tracking_partial"
    ]
    assert len(partial) == 1
    assert partial[0].page_url == QUOTE
    # It does not suppress: the rest of the site's numbers are still real.
    assert all(row.suppressed_by is None for row in result.findings)


def test_a_form_that_is_still_converting_is_not_reported(db, client_a):
    _two_forms(db, client_a, quote_still_converts=True)

    result = diagnose(db, client_a, from_date=END - timedelta(days=29), to_date=END)
    assert not [
        row for row in result.findings
        if row.evidence_json.get("gate") == "tracking_partial"
    ]


def test_a_form_too_small_to_expect_leads_from_is_not_reported(db, client_a):
    """One lead a month stopping is a quiet month, not a broken form."""
    _lead_def(db, client_a.id)
    _watermarks(db, client_a.id, END)
    _gsc(db, client_a.id, END, CONTACT)
    for offset in range(14, 74):
        day = END - timedelta(days=offset)
        _traffic(db, client_a.id, day, CONTACT, 100)
        _leads(db, client_a.id, day, CONTACT, 2)
    # Two leads in sixty days: under half a lead expected in a fortnight.
    _leads(db, client_a.id, END - timedelta(days=60), QUOTE, 1)
    _leads(db, client_a.id, END - timedelta(days=30), QUOTE, 1)
    for offset in range(14):
        day = END - timedelta(days=13) + timedelta(days=offset)
        _traffic(db, client_a.id, day, CONTACT, 100)
        _leads(db, client_a.id, day, CONTACT, 2)
    db.commit()
    seed_required_sources(db, client_a.id, END)

    result = diagnose(db, client_a, from_date=END - timedelta(days=29), to_date=END)
    assert not [
        row for row in result.findings
        if row.evidence_json.get("gate") == "tracking_partial"
    ]


def test_leads_well_above_the_usual_rate_are_flagged_as_suspect(db, client_a):
    """Double firing and form spam both look like a very good fortnight."""
    _lead_def(db, client_a.id)
    _watermarks(db, client_a.id, END)
    _gsc(db, client_a.id, END, CONTACT)
    for offset in range(14, 74):
        day = END - timedelta(days=offset)
        _traffic(db, client_a.id, day, CONTACT, 100)
        _leads(db, client_a.id, day, CONTACT, 1)
    for offset in range(14):
        day = END - timedelta(days=13) + timedelta(days=offset)
        _traffic(db, client_a.id, day, CONTACT, 100)
        _leads(db, client_a.id, day, CONTACT, 5)
    db.commit()
    seed_required_sources(db, client_a.id, END)

    result = diagnose(db, client_a, from_date=END - timedelta(days=29), to_date=END)
    spike = [
        row for row in result.findings
        if row.evidence_json.get("gate") == "tracking_spike"
    ]
    assert len(spike) == 1
    assert spike[0].evidence_json["multiple"] >= 3.0
    # The excess is the number of recorded leads that may not exist, which is
    # a real quantity in leads rather than a severity invented for the row.
    assert spike[0].evidence_json["suspect_leads"] > 0
    assert all(row.suppressed_by is None for row in result.findings)


def test_a_normal_fortnight_is_not_a_spike(db, client_a):
    _lead_def(db, client_a.id)
    _watermarks(db, client_a.id, END)
    _gsc(db, client_a.id, END, CONTACT)
    for offset in range(74):
        day = END - timedelta(days=offset)
        _traffic(db, client_a.id, day, CONTACT, 100)
        _leads(db, client_a.id, day, CONTACT, 2)
    db.commit()
    seed_required_sources(db, client_a.id, END)

    result = diagnose(db, client_a, from_date=END - timedelta(days=29), to_date=END)
    assert not [
        row for row in result.findings
        if row.evidence_json.get("gate") == "tracking_spike"
    ]
