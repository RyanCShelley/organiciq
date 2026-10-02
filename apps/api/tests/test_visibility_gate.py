"""Gate 2: core terms that rank and bring nothing.

Visibility earns traffic and traffic earns leads, so a ranking that produces no
demand breaks the chain at the top. The keyword rules watch for a term
*falling*; a term sitting at position three delivering nothing never moves, so
nothing fired and the watchlist looked healthy.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from app.models.seranking import FactSerKeyword
from app.services.decision_impact import SiteBusinessContext
from app.services.lever_engine import (
    VISIBILITY_MIN_VOLUME,
    PageDemand,
    _visibility_without_traffic_findings,
)

def _site(rate=2.0, leads=40, goal=50):
    """A site that converts, so impact can be expressed in leads."""
    return SiteBusinessContext(
        site_lead_rate_pct=rate,
        period_sessions=2000.0,
        period_leads=leads,
        period_lead_goal=goal,
        p90_page_sessions=500.0,
    )


END = date(2026, 8, 31)
START = END - timedelta(days=29)
PERIOD = (START, END)
URL = "https://example.com/services/roofing"


def _keyword(db, client_id, *, keyword="metal roofing", position=3, volume=1000, url=URL):
    db.add(
        FactSerKeyword(
            id=uuid4(),
            client_id=client_id,
            site_engine_id="se1",
            keyword_id=uuid4().hex[:12],
            keyword=keyword,
            volume=Decimal(volume) if volume is not None else None,
            current_position=Decimal(position) if position is not None else None,
            ranking_url=url,
        )
    )
    db.commit()


def _pages(impressions, url=URL, clicks=0.0):
    return [
        PageDemand(
            normalized_url=url,
            impressions=float(impressions),
            clicks=float(clicks),
            average_position=3.0,
            ctr_percent=0.0,
        )
    ]


def test_a_top_three_ranking_that_draws_nothing_is_found(db, client_a):
    _keyword(db, client_a.id, volume=1000, position=3)

    findings = _visibility_without_traffic_findings(
        db, client_a, _pages(20), period=PERIOD
    , site=_site())

    assert len(findings) == 1
    evidence = findings[0].evidence_json
    assert evidence["actual_impressions"] == 20
    assert evidence["search_volume"] == 1000
    assert "Ranking 3" in findings[0].diagnosis
    assert "Check the term before the page" in findings[0].recommended_action


def test_a_ranking_that_is_working_is_left_alone(db, client_a):
    """Earning the clicks the position should earn is the ranking doing its job."""
    _keyword(db, client_a.id, volume=1000, position=3)

    # Position 3 on the shared curve earns 3.9%, so a thousand searches should
    # bring about 39 clicks. Earning 35 is the ranking working.
    assert (
        _visibility_without_traffic_findings(
            db, client_a, _pages(800, clicks=35), period=PERIOD, site=_site()
        )
        == []
    )


def test_a_small_term_drawing_little_is_not_a_finding(db, client_a):
    """Below the volume floor, silence says nothing about the ranking."""
    _keyword(db, client_a.id, volume=50, position=2)

    assert _visibility_without_traffic_findings(db, client_a, _pages(0), period=PERIOD, site=_site()) == []
    assert 50 < VISIBILITY_MIN_VOLUME


def test_a_term_off_page_one_is_not_this_rule(db, client_a):
    """Thin impressions at position 40 is just the ranking, not a puzzle."""
    _keyword(db, client_a.id, volume=5000, position=40)

    assert _visibility_without_traffic_findings(db, client_a, _pages(5), period=PERIOD, site=_site()) == []


def test_a_page_absent_from_search_console_entirely_is_the_strongest_case(db, client_a):
    _keyword(db, client_a.id, volume=2000, position=1)

    findings = _visibility_without_traffic_findings(
        db, client_a, _pages(500, url="https://example.com/other"), period=PERIOD
    , site=_site())

    assert len(findings) == 1
    assert findings[0].evidence_json["actual_impressions"] == 0


def test_no_search_console_data_means_no_findings(db, client_a):
    """Otherwise every ranking looks broken when it is the data that is missing."""
    _keyword(db, client_a.id, volume=5000, position=1)

    assert _visibility_without_traffic_findings(db, client_a, [], period=PERIOD, site=_site()) == []
    assert _visibility_without_traffic_findings(db, client_a, _pages(0), period=None, site=_site()) == []


def test_the_more_valuable_term_scores_higher(db, client_a):
    _keyword(db, client_a.id, keyword="small term", volume=200, position=3, url=URL)
    small = _visibility_without_traffic_findings(db, client_a, _pages(0), period=PERIOD, site=_site())

    _keyword(db, client_a.id, keyword="big term", volume=5000, position=3, url=URL)
    both = _visibility_without_traffic_findings(db, client_a, _pages(0), period=PERIOD, site=_site())

    assert len(small) == 1
    assert len(both) == 2
    by_keyword = {row.evidence_json["keyword"]: row.impact for row in both}
    assert by_keyword["big term"] > by_keyword["small term"]


def test_a_keyword_with_no_ranking_url_is_skipped(db, client_a):
    _keyword(db, client_a.id, volume=5000, position=1, url=None)

    assert _visibility_without_traffic_findings(db, client_a, _pages(0), period=PERIOD, site=_site()) == []


def test_the_window_scales_the_expectation(db, client_a):
    """A seven-day window should not expect a month of searches."""
    _keyword(db, client_a.id, volume=1000, position=3)
    week = (END - timedelta(days=6), END)

    # 1,000/month over 7 days expects ~230 searches and 9 clicks at position 3,
    # so 10 clicks clears the half-of-expected bar.
    assert (
        _visibility_without_traffic_findings(
            db, client_a, _pages(200, clicks=10), period=week, site=_site()
        )
        == []
    )
    # Over 30 days the same 10 clicks is a quarter of the 38 expected.
    assert (
        len(
            _visibility_without_traffic_findings(
                db, client_a, _pages(200, clicks=10), period=PERIOD, site=_site()
            )
        )
        == 1
    )
