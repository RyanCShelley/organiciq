"""Pages that used to perform and no longer do.

Every other rule reads a snapshot: what is wrong with this page now. Decay is
only visible across time, so a page that quietly lost three quarters of its
traffic over a year looked healthy to all of them — correct status, fine meta,
decent links, still ranking somewhere.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from app.models.gsc import FactGscPage
from app.services.lever_engine import (
    DECAY_MIN_PRIOR_CLICKS,
    _decay_comparison_window,
    _decaying_page_findings,
)

END = date(2026, 8, 31)
START = END - timedelta(days=29)
PERIOD = (START, END)
LAST_YEAR = START - timedelta(days=365)
PAGE = "https://example.com/blog/metal-roofing-guide"
OTHER = "https://example.com/blog/tile-roofing"


def _fact(db, client_id, url, on, clicks, impressions):
    db.add(
        FactGscPage(
            id=uuid4(),
            client_id=client_id,
            date=on,
            raw_url=url,
            normalized_url=url,
            country="",
            device="",
            impressions=Decimal(impressions),
            clicks=Decimal(clicks),
            ctr=Decimal("0.05"),
            average_position=Decimal("8"),
        )
    )


# --- Which window to compare against ---------------------------------------


def test_a_year_back_is_preferred_because_it_reads_through_seasonality():
    window = _decay_comparison_window(PERIOD, date(2024, 1, 1))

    assert window is not None
    assert (START - window[0]).days == 365


def test_a_shorter_history_falls_back_to_the_nearest_distant_window():
    """Compared with last month, a page is being asked about noise."""
    window = _decay_comparison_window(PERIOD, date(2026, 1, 1))

    assert window is not None
    assert (START - window[1]).days == 90


def test_too_little_history_compares_against_nothing():
    """Otherwise the shape of the backfill is reported as the shape of the site."""
    assert _decay_comparison_window(PERIOD, date(2026, 8, 1)) is None
    assert _decay_comparison_window(PERIOD, None) is None


# --- The rule ---------------------------------------------------------------


def test_a_page_that_lost_most_of_its_traffic_is_found(db, client_a):
    _fact(db, client_a.id, PAGE, LAST_YEAR, 400, 8000)
    _fact(db, client_a.id, PAGE, END, 40, 2000)
    # A steady page, so the site has not simply fallen with it.
    _fact(db, client_a.id, OTHER, LAST_YEAR, 300, 6000)
    _fact(db, client_a.id, OTHER, END, 300, 6000)
    db.commit()

    findings = _decaying_page_findings(db, client_a, period=PERIOD, fact_min=date(2024, 1, 1))

    assert len(findings) == 1
    evidence = findings[0].evidence_json
    assert evidence["prior_clicks"] == 400
    assert evidence["current_clicks"] == 40
    assert evidence["year_over_year"] is True
    assert "Deep refresh this page" in findings[0].recommended_action


def test_a_site_wide_fall_does_not_flag_every_page(db, client_a):
    """A seasonal trough is the loudest possible false alarm."""
    for url in (PAGE, OTHER):
        _fact(db, client_a.id, url, LAST_YEAR, 400, 8000)
        _fact(db, client_a.id, url, END, 40, 2000)
    db.commit()

    assert _decaying_page_findings(db, client_a, period=PERIOD, fact_min=date(2024, 1, 1)) == []


def test_a_page_falling_further_than_the_site_still_shows(db, client_a):
    """Losing ground the neighbours are not is the signal."""
    # Site down ~50%, this page down ~95%.
    _fact(db, client_a.id, PAGE, LAST_YEAR, 400, 8000)
    _fact(db, client_a.id, PAGE, END, 20, 500)
    _fact(db, client_a.id, OTHER, LAST_YEAR, 400, 8000)
    _fact(db, client_a.id, OTHER, END, 320, 7000)
    db.commit()

    findings = _decaying_page_findings(db, client_a, period=PERIOD, fact_min=date(2024, 1, 1))

    assert [row.page_url for row in findings] == [PAGE]


def test_clicks_falling_while_impressions_hold_is_a_listing_problem(db, client_a):
    """That is the CTR rule's finding, and two rules on one page is noise."""
    _fact(db, client_a.id, PAGE, LAST_YEAR, 400, 8000)
    _fact(db, client_a.id, PAGE, END, 40, 8500)
    _fact(db, client_a.id, OTHER, LAST_YEAR, 300, 6000)
    _fact(db, client_a.id, OTHER, END, 300, 6000)
    db.commit()

    assert _decaying_page_findings(db, client_a, period=PERIOD, fact_min=date(2024, 1, 1)) == []


def test_a_page_that_never_performed_cannot_have_decayed(db, client_a):
    _fact(db, client_a.id, PAGE, LAST_YEAR, 5, 400)
    _fact(db, client_a.id, PAGE, END, 0, 50)
    _fact(db, client_a.id, OTHER, LAST_YEAR, 300, 6000)
    _fact(db, client_a.id, OTHER, END, 300, 6000)
    db.commit()

    assert _decaying_page_findings(db, client_a, period=PERIOD, fact_min=date(2024, 1, 1)) == []
    assert 5 < DECAY_MIN_PRIOR_CLICKS


def test_a_small_dip_is_not_decay(db, client_a):
    _fact(db, client_a.id, PAGE, LAST_YEAR, 400, 8000)
    _fact(db, client_a.id, PAGE, END, 330, 7000)
    _fact(db, client_a.id, OTHER, LAST_YEAR, 300, 6000)
    _fact(db, client_a.id, OTHER, END, 300, 6000)
    db.commit()

    assert _decaying_page_findings(db, client_a, period=PERIOD, fact_min=date(2024, 1, 1)) == []


def test_the_biggest_loss_leads(db, client_a):
    third = "https://example.com/blog/slate"
    _fact(db, client_a.id, PAGE, LAST_YEAR, 400, 8000)
    _fact(db, client_a.id, PAGE, END, 10, 500)
    _fact(db, client_a.id, third, LAST_YEAR, 100, 2000)
    _fact(db, client_a.id, third, END, 5, 200)
    _fact(db, client_a.id, OTHER, LAST_YEAR, 600, 9000)
    _fact(db, client_a.id, OTHER, END, 600, 9000)
    db.commit()

    findings = _decaying_page_findings(db, client_a, period=PERIOD, fact_min=date(2024, 1, 1))

    assert [row.page_url for row in findings] == [PAGE, third]


def test_no_period_means_no_findings(db, client_a):
    assert _decaying_page_findings(db, client_a, period=None, fact_min=date(2024, 1, 1)) == []
