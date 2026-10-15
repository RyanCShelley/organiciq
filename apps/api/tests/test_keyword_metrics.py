"""Market data for keywords the client does not rank for.

Every "nothing ranks for this" finding estimates what winning the term
would be worth, and had no idea how hard it was. The rank tracker carries
no difficulty, and the domain-keywords endpoint only covers terms already
ranking — by definition not these.
"""

from __future__ import annotations

from datetime import date, timedelta
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
    # Old enough to be worth buying again. A reading from today is not.
    db.query(FactSerKeywordMetric).update(
        {"fetched_at": TODAY - timedelta(days=pipeline.KEYWORD_METRICS_INTERVAL_DAYS + 1)}
    )
    db.commit()

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




# ── Only what is missing or stale is bought ──


def _priced(db, client_id, keyword, *, days_ago=0, data_found=True):
    db.add(
        FactSerKeywordMetric(
            id=uuid4(), client_id=client_id, keyword=keyword, source="us",
            volume=100, difficulty=20, data_found=data_found,
            fetched_at=TODAY - timedelta(days=days_ago),
        )
    )
    db.commit()


def test_a_term_already_priced_is_not_bought_again(db, client_a, monkeypatch):
    _tracked(db, client_a.id, "seo services")
    _priced(db, client_a.id, "seo services")
    called: list[list[str]] = []
    _stub(monkeypatch, spy=called)

    job = pipeline.run_seranking_keyword_metrics_job(db, _job(db, client_a.id))

    assert called == []  # nothing missing, nothing billed
    assert job.status is SyncJobStatus.SUCCESSFUL


def test_adding_one_keyword_buys_only_that_keyword(db, client_a, monkeypatch):
    """It used to re-price the whole list."""
    _tracked(db, client_a.id, "seo services", "seo agency", "link building")
    _priced(db, client_a.id, "seo services")
    _priced(db, client_a.id, "seo agency")
    called: list[list[str]] = []
    _stub(monkeypatch, spy=called)

    pipeline.run_seranking_keyword_metrics_job(db, _job(db, client_a.id))

    assert [sorted(batch) for batch in called] == [["link building"]]


def test_a_stale_reading_is_bought_again_and_a_fresh_one_is_not(db, client_a):
    _tracked(db, client_a.id, "old term", "new term")
    _priced(db, client_a.id, "old term", days_ago=pipeline.KEYWORD_METRICS_INTERVAL_DAYS + 5)
    _priced(db, client_a.id, "new term", days_ago=3)

    assert pipeline.keywords_to_price(db, client_a.id, today=TODAY) == ["old term"]


def test_case_and_whitespace_do_not_make_a_priced_term_look_unpriced(db, client_a):
    """The due check compared raw strings, so this could keep a client due forever."""
    _tracked(db, client_a.id, "  SEO Services ")
    _priced(db, client_a.id, "seo services")

    assert pipeline.keywords_to_price(db, client_a.id, today=TODAY) == []


def test_a_term_with_no_data_counts_as_priced(db, client_a):
    """'SE Ranking has nothing on this' was an answer. Asking again buys the same one."""
    _tracked(db, client_a.id, "zxqv nonsense")
    _priced(db, client_a.id, "zxqv nonsense", data_found=False)

    assert pipeline.keywords_to_price(db, client_a.id, today=TODAY) == []


def test_refresh_all_is_the_deliberate_way_to_pay_for_everything(db, client_a, monkeypatch):
    _tracked(db, client_a.id, "seo services")
    _priced(db, client_a.id, "seo services")
    called: list[list[str]] = []
    _stub(monkeypatch, spy=called)
    job = _job(db, client_a.id)
    job.params_json = {"refresh_all": True}
    db.commit()

    pipeline.run_seranking_keyword_metrics_job(db, job)

    assert [sorted(batch) for batch in called] == [["seo services"]]
