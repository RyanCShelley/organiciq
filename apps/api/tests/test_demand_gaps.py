"""Demand the site is shown for and has no page about.

The tracked-term scan can only say the pages somebody thought of exist. This
reads Search Console instead, so it has to be as careful about what it
excludes as about what it finds.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from app.decisions.content_gaps import (
    MIN_DEMAND_IMPRESSIONS,
    DemandGap,
    c2_write_the_page_for_demand,
)
from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSnapshot
from app.models.gsc import FactGscQueryPage
from app.models.seranking import FactSerKeyword, FactSerKeywordMetric
from app.services.content_gap_signals import MIN_CRAWLED_PAGES
from app.services.demand_gaps import (
    PRICING_LIMIT,
    demand_candidates,
    queries_to_price,
    scan_demand_gaps,
)

TODAY = date(2026, 10, 15)
DAY = TODAY - timedelta(days=3)


def _page(db, client_id, slug, title):
    url = f"https://example.com/{slug}"
    db.add(
        FactCrawlPageSnapshot(
            id=uuid4(), client_id=client_id, source=CRAWL_SOURCE_FIRST_PARTY,
            snapshot_date=DAY, raw_url=url, normalized_url=url, status_code=200,
            indexable=True, word_count=800, inbound_internal_links=5,
            inbound_editorial_links=3, redirect_count=0, title=title, sections=[],
        )
    )
    return url


def _site(db, client):
    for i in range(MIN_CRAWLED_PAGES):
        _page(db, client.id, f"filler-{i}", f"Filler {i}")
    _page(db, client.id, "hvac-repair", "Furnace repair")
    db.commit()


def _shown(db, client, query, impressions, *, position=30, url="https://example.com/hvac-repair"):
    db.add(
        FactGscQueryPage(
            id=uuid4(), client_id=client.id, date=DAY, query=query, raw_url=url,
            normalized_url=url, country="", device="", impressions=Decimal(impressions),
            clicks=Decimal(1), ctr=Decimal("0.01"), average_position=Decimal(position),
        )
    )
    db.commit()


def _price(db, client, keyword, volume=400, difficulty=20):
    db.add(
        FactSerKeywordMetric(
            id=uuid4(), client_id=client.id, keyword=keyword, source="us",
            volume=volume, difficulty=difficulty, data_found=True, fetched_at=DAY,
        )
    )
    db.commit()


def _terms(db, client):
    gaps, summary, blocked = demand_candidates(db, client, today=TODAY)
    return {g.term for g in gaps}, summary, blocked


def test_demand_with_no_page_about_it_is_a_candidate(db, client_a):
    _site(db, client_a)
    _shown(db, client_a, "heat pump installation", 400)
    terms, _, _ = _terms(db, client_a)
    assert terms == {"heat pump installation"}


def test_a_query_below_the_impression_floor_is_set_aside_and_counted(db, client_a):
    _site(db, client_a)
    _shown(db, client_a, "heat pump installation", MIN_DEMAND_IMPRESSIONS - 1)
    terms, summary, _ = _terms(db, client_a)
    assert terms == set()
    assert summary["demand_small"] == 1


def test_a_tracked_query_is_not_demand_nobody_has_seen(db, client_a):
    _site(db, client_a)
    _shown(db, client_a, "heat pump installation", 400)
    db.add(
        FactSerKeyword(
            id=uuid4(), client_id=client_a.id, site_engine_id="1", keyword_id="k",
            keyword="Heat Pump Installation", volume=400,
        )
    )
    db.commit()
    terms, summary, _ = _terms(db, client_a)
    assert terms == set() and summary["demand_tracked"] == 1


def test_a_brand_query_is_navigation_not_demand(db, client_a):
    _site(db, client_a)
    _shown(db, client_a, f"{client_a.client_name.lower()} reviews", 400)
    terms, summary, _ = _terms(db, client_a)
    assert terms == set() and summary["demand_brand"] == 1


def test_a_query_already_earning_its_page_is_left_alone(db, client_a):
    _site(db, client_a)
    _shown(db, client_a, "heat pump installation", 400, position=4)
    terms, summary, _ = _terms(db, client_a)
    assert terms == set() and summary["demand_earning"] == 1


def test_a_query_a_page_is_about_is_a_refresh_not_a_new_page(db, client_a):
    _site(db, client_a)
    _shown(db, client_a, "furnace repair", 400)
    terms, summary, _ = _terms(db, client_a)
    assert terms == set() and summary["demand_covered"] == 1


def test_a_crawl_too_small_to_prove_absence_says_nothing(db, client_a):
    _page(db, client_a.id, "only", "Only page")
    db.commit()
    _shown(db, client_a, "heat pump installation", 400)
    gaps, _, blocked = demand_candidates(db, client_a, today=TODAY)
    assert gaps == [] and "too few" in blocked


def test_variants_are_one_page_led_by_the_biggest(db, client_a):
    _site(db, client_a)
    _shown(db, client_a, "heat pump installation", 400)
    _shown(db, client_a, "heat pump installation cost", 150)
    gaps, _, _ = demand_candidates(db, client_a, today=TODAY)
    assert [g.term for g in gaps] == ["heat pump installation"]
    assert gaps[0].also_covers == (("heat pump installation cost", 150.0),)


def test_an_unpriced_gap_is_not_prescribed_and_is_counted(db, client_a):
    _site(db, client_a)
    _shown(db, client_a, "heat pump installation", 400)
    scan = scan_demand_gaps(db, client_a, today=TODAY)
    assert scan.gaps == [] and scan.summary["demand_unpriced"] == 1


def test_a_priced_gap_is_prescribed_with_its_evidence(db, client_a):
    _site(db, client_a)
    _shown(db, client_a, "heat pump installation", 400)
    _price(db, client_a, "heat pump installation", volume=900, difficulty=30)
    scan = scan_demand_gaps(db, client_a, today=TODAY)
    found = c2_write_the_page_for_demand(scan.gaps[0])
    assert found.action_id == "C-2" and found.target_url == ""
    assert found.metric_key == "term_position"
    assert found.score == 900 * 0.7
    assert "400 times" in found.why and "900 searches a month" in found.why
    assert any("facts_gsc_query_pages" in line for line in found.evidence)


def test_a_price_below_the_volume_floor_is_not_prescribed():
    gap = DemandGap(term="x", impressions=500, clicks=0, position=40, volume=10, difficulty=5)
    assert c2_write_the_page_for_demand(gap) is None


def test_the_pricing_job_buys_the_largest_unpriced_once(db, client_a):
    _site(db, client_a)
    for i in range(PRICING_LIMIT + 5):
        _shown(db, client_a, f"zzz{i} widget", 1000 - i)
    _price(db, client_a, "zzz0 widget")
    wanted = queries_to_price(db, client_a, today=TODAY)
    assert len(wanted) == PRICING_LIMIT
    assert "zzz0 widget" not in wanted
    assert wanted[0] == "zzz1 widget"


def test_the_keyword_pricing_list_includes_demand(db, client_a):
    from app.ingestion.seranking.pipeline_keyword_metrics import keywords_to_price

    _site(db, client_a)
    _shown(db, client_a, "heat pump installation", 400)
    assert keywords_to_price(db, client_a.id, today=TODAY) == ["heat pump installation"]


def test_an_untracked_term_is_judged_on_search_console_position(db, client_a):
    from app.services.results import _query_position

    _shown(db, client_a, "heat pump installation", 100, position=40)
    _shown(db, client_a, "heat pump installation", 300, position=20, url="https://example.com/other")
    # Impression-weighted, not a plain average of the two rows.
    assert _query_position(db, client_a.id, "Heat Pump Installation", TODAY).value == 25.0
    assert _query_position(db, client_a.id, "nothing", TODAY).value is None
