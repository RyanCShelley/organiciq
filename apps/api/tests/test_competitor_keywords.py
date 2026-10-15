"""Competitor-ranked terms the site has no page about.

The competitor pull costs 100 credits a competitor, so as much of this is
about what it must not buy as about what it finds.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from app.decisions.content_gaps import c2_write_the_page_for_demand
from app.ingestion.seranking import pipeline_competitor_keywords as pipeline
from app.models.job import SyncJob, SyncJobStatus
from app.models.seranking import (
    FactSerCompetitor,
    FactSerCompetitorKeyword,
    FactSerKeyword,
    FactSerKeywordMetric,
)
from app.services.demand_gaps import queries_to_price, scan_demand_gaps
from tests.test_demand_gaps import DAY, TODAY, _shown, _site


def _competitor(db, client, domain, visibility):
    db.add(
        FactSerCompetitor(
            id=uuid4(), client_id=client.id, site_engine_id="1", competitor_id=domain,
            name=domain, url=f"https://www.{domain}/", visibility=Decimal(visibility),
            metric_date=DAY,
        )
    )
    db.commit()


def _ranks(db, client, domain, keyword, *, position=3, volume=900, difficulty=30, fetched=DAY):
    db.add(
        FactSerCompetitorKeyword(
            id=uuid4(), client_id=client.id, competitor_domain=domain, keyword=keyword,
            position=Decimal(position), volume=Decimal(volume),
            difficulty=Decimal(difficulty), fetched_at=fetched,
        )
    )
    db.commit()


def _job(db, client):
    job = SyncJob(
        id=uuid4(), client_id=client.id, source="se_ranking_competitor_keywords",
        start_date=TODAY, end_date=TODAY, status=SyncJobStatus.QUEUED, params_json={},
    )
    db.add(job)
    db.commit()
    return job


# --- Cost controls ----------------------------------------------------------


def test_only_the_three_closest_competitors_are_read(db, client_a):
    for i, domain in enumerate(["a.com", "b.com", "c.com", "d.com", "e.com"]):
        _competitor(db, client_a, domain, 50 - i)
    assert pipeline.closest_competitors(db, client_a) == ["a.com", "b.com", "c.com"]


def test_the_clients_own_domain_is_never_bought_as_a_competitor(db, client_a):
    _competitor(db, client_a, "other.com", 10)
    db.add(
        FactSerCompetitor(
            id=uuid4(), client_id=client_a.id, site_engine_id="1", competitor_id="self",
            name="self", url=f"https://www.{client_a.domain}/", visibility=Decimal(99),
            metric_date=DAY,
        )
    )
    db.commit()
    assert pipeline.closest_competitors(db, client_a) == ["other.com"]


def test_a_competitor_read_this_month_is_not_bought_again(db, client_a):
    _competitor(db, client_a, "a.com", 50)
    _competitor(db, client_a, "b.com", 40)
    _ranks(db, client_a, "a.com", "heat pump installation", fetched=TODAY - timedelta(days=5))
    assert pipeline.competitors_to_pull(db, client_a, today=TODAY) == ["b.com"]
    assert pipeline.competitors_to_pull(db, client_a, today=TODAY + timedelta(days=30)) == [
        "a.com",
        "b.com",
    ]


def test_the_job_makes_one_request_per_competitor_and_keeps_the_top_ten(
    db, client_a, monkeypatch
):
    for domain, visibility in [("a.com", 50), ("b.com", 40), ("c.com", 30), ("d.com", 20)]:
        _competitor(db, client_a, domain, visibility)
    asked: list[str] = []

    def fake(*, api_key, domain, source):
        asked.append(domain)
        return [
            {"keyword": "heat pump installation", "position": 2, "volume": 900, "difficulty": 30},
            {"keyword": "heat pump rebates", "position": 40, "volume": 500, "difficulty": 20},
        ]

    monkeypatch.setattr(pipeline, "list_domain_keywords", fake)
    job = pipeline.run_seranking_competitor_keywords_job(db, _job(db, client_a))

    assert job.status is SyncJobStatus.SUCCESSFUL
    assert asked == ["a.com", "b.com", "c.com"], "three requests, 300 credits, never the fourth"
    stored = db.query(FactSerCompetitorKeyword).all()
    assert {row.keyword for row in stored} == {"heat pump installation"}
    assert job.records_fetched == 6 and job.records_written == 3


def test_a_second_run_buys_nothing(db, client_a, monkeypatch):
    _competitor(db, client_a, "a.com", 50)
    calls: list[str] = []
    monkeypatch.setattr(
        pipeline,
        "list_domain_keywords",
        lambda **kw: calls.append(kw["domain"])
        or [{"keyword": "heat pump installation", "position": 2, "volume": 900, "difficulty": 30}],
    )
    pipeline.run_seranking_competitor_keywords_job(db, _job(db, client_a))
    second = pipeline.run_seranking_competitor_keywords_job(db, _job(db, client_a))
    assert calls == ["a.com"]
    assert second.records_fetched == 0


def test_it_is_a_runnable_source_and_not_in_the_daily_provider_list():
    from app.services.daily_sync import _PROVIDER_SOURCES
    from app.services.jobs import _job_handlers

    assert "se_ranking_competitor_keywords" in _job_handlers()
    scheduled = {s for sources in _PROVIDER_SOURCES.values() for s in sources}
    assert "se_ranking_competitor_keywords" not in scheduled


def test_a_client_with_a_thin_crawl_is_not_enqueued(db, client_a):
    from app.services.daily_sync import enqueue_due_competitor_keywords

    _competitor(db, client_a, "a.com", 50)
    assert enqueue_due_competitor_keywords(db)["due"] == 0


# --- What counts as a gap ---------------------------------------------------


def test_a_term_a_competitor_ranks_for_and_the_site_has_no_page_about_is_a_priced_gap(
    db, client_a
):
    _site(db, client_a)
    _ranks(db, client_a, "a.com", "heat pump installation", position=2)
    _ranks(db, client_a, "b.com", "heat pump installation", position=6, volume=700)
    scan = scan_demand_gaps(db, client_a, today=TODAY)

    assert [g.term for g in scan.gaps] == ["heat pump installation"]
    gap = scan.gaps[0]
    assert gap.impressions == 0 and gap.volume == 900 and gap.difficulty == 30
    assert gap.competitors == (("a.com", 2.0), ("b.com", 6.0))
    assert scan.summary["competitor_gaps"] == 1

    found = c2_write_the_page_for_demand(gap)
    assert found.action_id == "C-2" and found.score == 900 * 0.7
    assert "a.com (#2)" in found.why and "never shown" in found.why
    assert not any("facts_gsc_query_pages" in line for line in found.evidence)
    assert any("facts_ser_competitor_keywords" in line for line in found.evidence)


def test_a_term_the_site_tracks_or_already_holds_is_set_aside(db, client_a):
    _site(db, client_a)
    _ranks(db, client_a, "a.com", "heat pump installation")
    _ranks(db, client_a, "a.com", "geothermal loops")
    db.add(
        FactSerKeyword(
            id=uuid4(), client_id=client_a.id, site_engine_id="1", keyword_id="k",
            keyword="Heat Pump Installation", volume=900,
        )
    )
    db.commit()
    _shown(db, client_a, "geothermal loops", 400, position=4)
    scan = scan_demand_gaps(db, client_a, today=TODAY)
    assert scan.gaps == []
    assert scan.summary["competitor_tracked"] == 1
    assert scan.summary["competitor_earning"] == 1


def test_a_rivals_brand_and_a_term_a_page_covers_are_not_gaps(db, client_a):
    _site(db, client_a)
    _ranks(db, client_a, "keysearch.co", "keysearch vs semrush")
    _ranks(db, client_a, "a.com", "furnace repair")
    scan = scan_demand_gaps(db, client_a, today=TODAY)
    assert scan.gaps == []
    assert scan.summary["competitor_brand"] == 1
    assert scan.summary["competitor_covered"] == 1


def test_a_term_below_the_volume_floor_is_not_worth_a_page(db, client_a):
    _site(db, client_a)
    _ranks(db, client_a, "a.com", "heat pump installation", volume=10)
    scan = scan_demand_gaps(db, client_a, today=TODAY)
    assert scan.gaps == [] and scan.summary["competitor_small"] == 1


def test_search_console_and_competitor_sources_are_one_page(db, client_a):
    _site(db, client_a)
    _shown(db, client_a, "heat pump installation", 400)
    _ranks(db, client_a, "a.com", "heat pump installation", position=3)
    _ranks(db, client_a, "a.com", "heat pump installation cost", position=5, volume=300)
    scan = scan_demand_gaps(db, client_a, today=TODAY)

    assert [g.term for g in scan.gaps] == ["heat pump installation"]
    lead = scan.gaps[0]
    assert lead.impressions == 400 and lead.competitors == (("a.com", 3.0),)
    assert [term for term, _ in lead.also_covers] == ["heat pump installation cost"]
    assert scan.summary["demand_unpriced"] == 0


def test_a_term_a_competitor_priced_is_not_bought_again(db, client_a):
    _site(db, client_a)
    _shown(db, client_a, "heat pump installation", 400)
    assert queries_to_price(db, client_a, today=TODAY) == ["heat pump installation"]
    _ranks(db, client_a, "a.com", "heat pump installation")
    assert queries_to_price(db, client_a, today=TODAY) == []


def test_a_price_the_client_already_bought_wins_over_the_competitors(db, client_a):
    _site(db, client_a)
    _shown(db, client_a, "heat pump installation", 400)
    _ranks(db, client_a, "a.com", "heat pump installation", volume=900, difficulty=30)
    db.add(
        FactSerKeywordMetric(
            id=uuid4(), client_id=client_a.id, keyword="heat pump installation", source="us",
            volume=1200, difficulty=40, data_found=True, fetched_at=DAY,
        )
    )
    db.commit()
    gap = scan_demand_gaps(db, client_a, today=TODAY).gaps[0]
    assert gap.volume == 1200 and gap.difficulty == 40
