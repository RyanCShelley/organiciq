from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from app.core.settings import get_settings
from app.ingestion.seranking.pipeline import run_seranking_search_job
from app.ingestion.seranking.publish import publish_seranking_search
from app.models.integration import ConnectionStatus, Integration, IntegrationProvider
from app.models.job import DataWatermark, SyncJob, SyncJobStatus, ValidationStatus
from app.models.seranking import FactSerKeyword, FactSerRanking, StagingSerCompetitor, StagingSerKeyword, StagingSerPosition


def _window(days: int = 14):
    end = date.today()
    start = end - timedelta(days=days - 1)
    return start, end


def _connect_ser(db, client):
    integration = (
        db.query(Integration)
        .filter(
            Integration.client_id == client.id,
            Integration.provider == IntegrationProvider.SE_RANKING,
        )
        .one()
    )
    integration.connection_status = ConnectionStatus.CONNECTED
    integration.external_property_id = "12345"
    integration.external_account_id = "SMA Marketing"
    db.commit()
    return integration


def test_blank_keyword_never_published(db, client_a):
    start, end = _window(2)
    job = SyncJob(
        id=uuid4(),
        client_id=client_a.id,
        source="se_ranking_search",
        start_date=start,
        end_date=end,
        status=SyncJobStatus.QUEUED,
    )
    db.add(job)
    db.flush()
    db.add(
        StagingSerKeyword(
            job_id=job.id,
            client_id=client_a.id,
            raw={},
            site_engine_id="1",
            keyword_id="99",
            keyword="   ",
            volume=Decimal("100"),
        )
    )
    db.add(
        StagingSerKeyword(
            job_id=job.id,
            client_id=client_a.id,
            raw={},
            site_engine_id="1",
            keyword_id="100",
            keyword="carbon fiber tubes",
            volume=None,
        )
    )
    db.commit()

    kw, rankings, comps, summaries = publish_seranking_search(db, job)
    assert kw == 1
    assert rankings == 0
    assert comps == 0
    fact = db.query(FactSerKeyword).one()
    assert fact.keyword == "carbon fiber tubes"
    assert fact.volume is None


def test_keyword_upsert_idempotent_with_positions(db, client_a):
    start, end = _window(3)
    job = SyncJob(
        id=uuid4(),
        client_id=client_a.id,
        source="se_ranking_search",
        start_date=start,
        end_date=end,
        status=SyncJobStatus.QUEUED,
    )
    db.add(job)
    db.flush()
    db.add(
        StagingSerKeyword(
            job_id=job.id,
            client_id=client_a.id,
            raw={},
            site_engine_id="7",
            keyword_id="55",
            keyword="industrial hose",
            group_name="Core",
            volume=Decimal("240"),
        )
    )
    db.add(
        StagingSerPosition(
            job_id=job.id,
            client_id=client_a.id,
            raw={},
            date=start,
            site_engine_id="7",
            keyword_id="55",
            keyword="industrial hose",
            position=Decimal("12"),
            position_change=Decimal("0"),
            volume=Decimal("240"),
        )
    )
    db.add(
        StagingSerPosition(
            job_id=job.id,
            client_id=client_a.id,
            raw={},
            date=end,
            site_engine_id="7",
            keyword_id="55",
            keyword="industrial hose",
            position=Decimal("8"),
            position_change=Decimal("4"),
            volume=Decimal("240"),
        )
    )
    db.commit()

    assert publish_seranking_search(db, job)[0] == 1
    assert publish_seranking_search(db, job)[0] == 1
    fact = db.query(FactSerKeyword).one()
    assert fact.current_position == Decimal("8")
    assert fact.previous_position == Decimal("12")
    assert fact.volume == Decimal("240")
    assert fact.earned_serp_features is None
    assert db.query(FactSerRanking).count() == 2


def test_seranking_pipeline_with_mocked_api(db, client_a, monkeypatch):
    monkeypatch.setenv("SE_RANKING_API_KEY", "test-key")
    get_settings.cache_clear()
    _connect_ser(db, client_a)
    start, end = _window(3)
    job = SyncJob(
        id=uuid4(),
        client_id=client_a.id,
        source="se_ranking_search",
        start_date=start,
        end_date=end,
        status=SyncJobStatus.QUEUED,
    )
    db.add(job)
    db.commit()

    positions_payload = [
        {
            "site_engine_id": "1",
            "keywords": [
                {
                    "id": "10",
                    "name": "sma marketing",
                    "volume": 100,
                    "features": {"sitelinks": True, "reviews": False},
                    "positions": [
                        {"date": start.isoformat(), "pos": 5, "change": 0, "volume": 100, "url": "https://smamarketing.net/"},
                        {"date": end.isoformat(), "pos": 3, "change": 2, "volume": 100, "url": "https://smamarketing.net/"},
                    ],
                }
            ],
        }
    ]

    with (
        patch("app.ingestion.seranking.fetch.ser_client.list_search_engines", return_value=[{"id": "1"}]),
        patch(
            "app.ingestion.seranking.fetch.ser_client.list_keyword_groups",
            return_value=[{"id": "g1", "name": "Brand"}],
        ),
        patch(
            "app.ingestion.seranking.fetch.ser_client.list_keywords",
            return_value=[
                {"id": "10", "name": "sma marketing", "group_id": "g1", "volume": 100, "site_engine_id": "1"}
            ],
        ),
        patch("app.ingestion.seranking.fetch.ser_client.list_positions", return_value=positions_payload),
        patch("app.ingestion.seranking.fetch.ser_client.list_competitors", return_value=[]),
        patch("app.ingestion.seranking.fetch.ser_client.competitor_metrics", return_value=[]),
    ):
        result = run_seranking_search_job(db, job)

    assert result.status in {SyncJobStatus.SUCCESSFUL, SyncJobStatus.PARTIAL}
    assert result.validation_status == ValidationStatus.PASSED
    assert db.query(FactSerKeyword).filter(FactSerKeyword.client_id == client_a.id).count() == 1
    fact = db.query(FactSerKeyword).one()
    assert fact.keyword == "sma marketing"
    assert fact.group_name == "Brand"
    assert fact.current_position == Decimal("3")
    assert fact.earned_serp_features == ["sitelinks"]
    wm = (
        db.query(DataWatermark)
        .filter(DataWatermark.client_id == client_a.id, DataWatermark.source == "se_ranking_search")
        .one()
    )
    assert wm.fact_through_date is not None
    assert wm.validation_status == ValidationStatus.PASSED
    get_settings.cache_clear()


def test_flatten_positions_handles_engine_keyword_wrapper():
    from app.ingestion.seranking.fetch import _flatten_positions

    payload = [
        {
            "site_engine_id": 1315387,
            "keywords": [
                {
                    "id": "149676985",
                    "name": "SMA Marketing",
                    "volume": 110,
                    "positions": [
                        {"date": "2026-08-30", "pos": 2, "change": 0},
                        {"date": "2026-08-31", "pos": 2, "change": 0},
                    ],
                }
            ],
        }
    ]

    rows = _flatten_positions(payload, "1315387")
    assert len(rows) == 2
    assert rows[0]["keyword_id"] == "149676985"
    assert rows[0]["keyword"] == "SMA Marketing"
    assert rows[0]["site_engine_id"] == "1315387"
    assert rows[0]["position"] == Decimal("2")
    assert rows[0]["volume"] == Decimal("110")
    assert rows[1]["date"].isoformat() == "2026-08-31"


def test_extract_features_by_keyword():
    from app.ingestion.seranking.features import extract_features_by_keyword, label_earned_serp_features

    payload = [
        {
            "site_engine_id": 1315387,
            "keywords": [
                {
                    "id": "1",
                    "features": {"sge": True, "reviews": False},
                    "positions": [{"date": "2026-08-31", "pos": 2, "is_map": 0, "map_position": 0}],
                },
                {
                    "id": "2",
                    "features": {"reviews": True, "gmb": True},
                    "positions": [{"date": "2026-08-31", "pos": 1, "is_map": 1, "map_position": 2}],
                },
            ],
        }
    ]

    features = extract_features_by_keyword(payload)
    assert features[("1315387", "1")] == ["sge"]
    assert features[("1315387", "2")] == ["reviews", "gmb", "local_pack"]
    assert label_earned_serp_features(features[("1315387", "2")]) == [
        "Reviews",
        "Business Profile",
        "Local Pack",
    ]


def test_competitor_metrics_matched_by_domain():
    from app.ingestion.seranking.fetch import (
        _index_metrics_by_domain,
        _lookup_competitor_metric,
        _normalize_ser_domain,
    )

    assert _normalize_ser_domain("https://www.webfx.com/path") == "webfx.com"
    assert _normalize_ser_domain("straightnorth.com") == "straightnorth.com"

    metrics = _index_metrics_by_domain(
        [
            {"domain": "www.webfx.com", "visibility": 57.01},
            {"domain": "straightnorth.com", "visibility": 16.26},
        ]
    )
    assert metrics["webfx.com"]["visibility"] == 57.01

    comp = {"id": "999", "url": "https://webfx.com", "name": "WebFX"}
    matched = _lookup_competitor_metric(comp, metrics)
    assert matched["visibility"] == 57.01

    missing = _lookup_competitor_metric({"id": "1", "url": "https://smartsites.com"}, metrics)
    assert missing == {}


def test_fetch_maps_competitor_metrics_by_domain(db, client_a, monkeypatch):
    monkeypatch.setenv("SE_RANKING_API_KEY", "test-key")
    get_settings.cache_clear()
    _connect_ser(db, client_a)
    start, end = _window(3)
    job = SyncJob(
        id=uuid4(),
        client_id=client_a.id,
        source="se_ranking_search",
        start_date=start,
        end_date=end,
        status=SyncJobStatus.QUEUED,
    )
    db.add(job)
    db.commit()

    from app.ingestion.seranking.fetch import fetch_seranking_search

    with (
        patch("app.ingestion.seranking.fetch.ser_client.list_search_engines", return_value=[{"id": "1"}]),
        patch("app.ingestion.seranking.fetch.ser_client.list_keyword_groups", return_value=[]),
        patch("app.ingestion.seranking.fetch.ser_client.list_keywords", return_value=[]),
        patch("app.ingestion.seranking.fetch.ser_client.list_positions", return_value=[]),
        patch(
            "app.ingestion.seranking.fetch.ser_client.list_competitors",
            return_value=[
                {"id": "101", "url": "https://www.webfx.com"},
                {"id": "102", "url": "https://straightnorth.com"},
            ],
        ),
        patch(
            "app.ingestion.seranking.fetch.ser_client.competitor_metrics",
            return_value=[
                {"domain": "www.webfx.com", "visibility": 57.01},
                {"domain": "straightnorth.com", "visibility": 16.26},
            ],
        ),
        patch("app.ingestion.seranking.fetch.ser_client.site_summary", return_value={}),
    ):
        fetch_seranking_search(db, job)

    rows = db.query(StagingSerCompetitor).filter(StagingSerCompetitor.job_id == job.id).all()
    by_id = {row.competitor_id: row for row in rows}
    assert by_id["101"].visibility == Decimal("57.01")
    assert by_id["102"].visibility == Decimal("16.26")
    get_settings.cache_clear()


def test_historical_backfill_does_not_backdate_current_site_summary(db, client_a, monkeypatch):
    from contextlib import ExitStack
    from app.ingestion.seranking.fetch import fetch_seranking_search
    from app.models.seranking import StagingSerSiteSummary
    monkeypatch.setenv("SE_RANKING_API_KEY", "test-key")
    get_settings.cache_clear()
    _connect_ser(db, client_a)
    job = SyncJob(id=uuid4(), client_id=client_a.id, source="se_ranking_search",
        start_date=date(2026, 1, 1), end_date=date(2026, 1, 31), status=SyncJobStatus.QUEUED)
    db.add(job)
    db.commit()
    with ExitStack() as stack:
        for method in ("list_search_engines", "list_keyword_groups", "list_keywords", "list_positions", "list_competitors"):
            stack.enter_context(patch(f"app.ingestion.seranking.fetch.ser_client.{method}", return_value=[]))
        stack.enter_context(patch("app.ingestion.seranking.fetch.ser_client.site_summary", return_value={"visibility_percent": 12}))
        fetch_seranking_search(db, job)
    row = db.query(StagingSerSiteSummary).filter_by(job_id=job.id).one()
    assert row.metric_date == date.today()
    assert row.metric_date != job.end_date
    get_settings.cache_clear()


def test_ranking_urls_use_only_landing_page_evidence_available_at_the_check_date():
    from app.ingestion.seranking.fetch import _flatten_positions
    rows=_flatten_positions([{'site_engine_id':'e','keywords':[{'id':'k','name':'service',
        'landing_pages':[{'url':'https://example.com/old','date':'2026-08-17'},{'url':'https://example.com/new','date':'2026-10-01'}],
        'positions':[{'date':'2026-08-01','pos':2},{'date':'2026-09-30','pos':3},{'date':'2026-10-02','pos':1},{'date':'2026-10-03','pos':0}]}]}],'e')
    assert [r['ranking_url'] for r in rows]==[None,'https://example.com/old','https://example.com/new',None]


def test_catalog_refresh_retires_terms_without_deleting_history(db, client_a, client_b):
    start, end = _window(2)
    job = SyncJob(client_id=client_a.id, source="se_ranking_search", start_date=start,
                  end_date=end, status=SyncJobStatus.QUEUED)
    db.add(job)
    db.flush()
    for owner, engine, term in [(client_a, "one", "keep"), (client_a, "one", "retire"),
                                (client_a, "two", "other engine"), (client_b, "one", "other client")]:
        db.add(FactSerKeyword(client_id=owner.id, site_engine_id=engine, keyword_id=term,
                              keyword=term, is_tracked=True))
    db.add(FactSerRanking(client_id=client_a.id, site_engine_id="one", keyword_id="retire",
                          keyword="retire", date=end, position=7))
    db.add(StagingSerKeyword(job_id=job.id, client_id=client_a.id, raw={},
                             site_engine_id="one", keyword_id="keep", keyword="keep"))
    db.flush()
    publish_seranking_search(db, job)
    db.expire_all()
    tracked = {(str(row.client_id), row.keyword): row.is_tracked for row in db.query(FactSerKeyword)}
    assert tracked[(str(client_a.id), "keep")] is True
    assert tracked[(str(client_a.id), "retire")] is False
    assert tracked[(str(client_a.id), "other engine")] is True
    assert tracked[(str(client_b.id), "other client")] is True
    assert db.query(FactSerRanking).filter_by(client_id=client_a.id, keyword="retire").count() == 1
    # No catalog is not evidence that the tracker removed everything.
    db.query(StagingSerKeyword).filter_by(job_id=job.id).delete()
    publish_seranking_search(db, job)
    db.expire_all()
    assert db.query(FactSerKeyword).filter_by(client_id=client_a.id, keyword="keep").one().is_tracked is True
