"""Market data for keywords the client does not rank for.

Every "nothing ranks for this" finding estimates what winning the term
would be worth, and had no idea how hard it was. The rank tracker carries
no difficulty, and the domain-keywords endpoint only covers terms already
ranking — by definition not these.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

from app.ingestion.seranking import pipeline_keyword_metrics as pipeline
from app.models.job import SyncJob, SyncJobStatus, ValidationStatus
from app.models.seranking import FactSerKeyword, FactSerKeywordMetric

TODAY = date(2026, 10, 3)

API_ROWS = [
    {
        "is_data_found": True,
        "keyword": "seo services",
        "volume": 74000,
        "cpc": 11.45,
        "difficulty": 72,
        "competition": 0.07,
        "intents": ["L", "C"],
    },
    {
        "is_data_found": False,
        "keyword": "a term nobody searches",
        "volume": 0,
        "difficulty": None,
    },
]


def _job(db, client_id) -> SyncJob:
    job = SyncJob(
        id=uuid4(),
        client_id=client_id,
        source="se_ranking_keyword_metrics",
        start_date=TODAY,
        end_date=TODAY,
        status=SyncJobStatus.QUEUED,
    )
    db.add(job)
    db.commit()
    return job


def _tracked(db, client_id, *keywords):
    for keyword in keywords:
        db.add(
            FactSerKeyword(
                id=uuid4(),
                client_id=client_id,
                site_engine_id="1",
                keyword_id=str(uuid4())[:8],
                keyword=keyword,
                volume=None,
            )
        )
    db.commit()


def _stub(monkeypatch, rows=API_ROWS, spy=None):
    monkeypatch.setattr(
        pipeline, "get_settings", lambda: SimpleNamespace(se_ranking_api_key="k")
    )

    def _fetch(api_key, keywords, *, source="us"):
        if spy is not None:
            spy.append(list(keywords))
        return rows

    monkeypatch.setattr(pipeline, "fetch_keyword_metrics", _fetch)


def test_it_stores_difficulty_for_a_term_the_client_does_not_rank_for(
    db, client_a, monkeypatch
):
    _tracked(db, client_a.id, "seo services")
    _stub(monkeypatch)

    job = pipeline.run_seranking_keyword_metrics_job(db, _job(db, client_a.id))

    assert job.status is SyncJobStatus.SUCCESSFUL
    assert job.records_written == 2
    assert job.error_message is None

    row = (
        db.query(FactSerKeywordMetric)
        .filter(FactSerKeywordMetric.keyword == "seo services")
        .one()
    )
    assert float(row.difficulty) == 72.0
    assert float(row.volume) == 74000.0
    assert row.data_found is True


def test_a_term_with_no_data_is_recorded_as_such():
    """"No data" is an answer: a keyword nobody searches is not an
    opportunity, and storing nothing would mean asking again every run."""
    assert API_ROWS[1]["is_data_found"] is False


def test_only_tracked_keywords_are_looked_up(db, client_a, monkeypatch):
    """The call is billed per keyword, so it asks about the watchlist and
    nothing else."""
    _tracked(db, client_a.id, "seo services", "seo agency")
    asked: list[list[str]] = []
    _stub(monkeypatch, spy=asked)

    pipeline.run_seranking_keyword_metrics_job(db, _job(db, client_a.id))

    assert len(asked) == 1
    assert sorted(asked[0]) == ["seo agency", "seo services"]


def test_a_client_with_no_watchlist_is_skipped_not_billed(db, client_a, monkeypatch):
    called: list[list[str]] = []
    _stub(monkeypatch, spy=called)

    job = pipeline.run_seranking_keyword_metrics_job(db, _job(db, client_a.id))

    assert called == []
    assert job.status is SyncJobStatus.SUCCESSFUL
    assert job.validation_status is ValidationStatus.SKIPPED
    assert job.records_written == 0


def test_a_rerun_updates_rather_than_duplicating(db, client_a, monkeypatch):
    _tracked(db, client_a.id, "seo services")
    _stub(monkeypatch)
    pipeline.run_seranking_keyword_metrics_job(db, _job(db, client_a.id))

    moved = [dict(API_ROWS[0], difficulty=80), API_ROWS[1]]
    _stub(monkeypatch, rows=moved)
    pipeline.run_seranking_keyword_metrics_job(db, _job(db, client_a.id))

    rows = (
        db.query(FactSerKeywordMetric)
        .filter(FactSerKeywordMetric.keyword == "seo services")
        .all()
    )
    assert len(rows) == 1
    assert float(rows[0].difficulty) == 80.0


def test_a_failure_records_why(db, client_a, monkeypatch):
    _tracked(db, client_a.id, "seo services")
    monkeypatch.setattr(
        pipeline, "get_settings", lambda: SimpleNamespace(se_ranking_api_key="k")
    )

    def _boom(*args, **kwargs):
        raise RuntimeError("keyword database said no")

    monkeypatch.setattr(pipeline, "fetch_keyword_metrics", _boom)

    job = pipeline.run_seranking_keyword_metrics_job(db, _job(db, client_a.id))

    assert job.status is SyncJobStatus.FAILED
    assert "keyword database said no" in job.error_message


def test_the_engine_prefers_measured_difficulty_over_what_only_ranks(db, client_a):
    """The domain endpoint cannot price a term the client does not rank for,
    so the keyword database wins where the two disagree."""
    from app.models.seranking import FactSerDomainKeyword
    from app.services.lever_engine import _keyword_market_data

    db.add(
        FactSerDomainKeyword(
            id=uuid4(),
            client_id=client_a.id,
            keyword="seo services",
            difficulty=None,
            serp_features=["ai_overview"],
            fetched_at=TODAY,
        )
    )
    db.add(
        FactSerKeywordMetric(
            id=uuid4(),
            client_id=client_a.id,
            keyword="seo services",
            source="us",
            difficulty=72,
            data_found=True,
            fetched_at=TODAY,
        )
    )
    db.commit()

    market = _keyword_market_data(db, client_a.id)
    difficulty, ai_overview = market["seo services"]
    assert difficulty == 72.0
    # The AI Overview seen by the domain endpoint survives the merge.
    assert ai_overview is True
