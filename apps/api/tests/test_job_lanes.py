"""Lanes: an AI run and a site crawl do not wait behind a long data pull, and each lane still runs one job at a time in order."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.models.job import SyncJob, SyncJobStatus
from app.services import jobs


def queue(db, client, source, minutes_ago):
    db.add(SyncJob(client_id=client.id, source=source, start_date=date.today(), end_date=date.today(), status=SyncJobStatus.QUEUED,
                   created_at=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)))
    db.commit()


def test_each_lane_claims_only_its_own_jobs_oldest_first(db, client_a):
    queue(db, client_a, "gsc_queries", 30)
    queue(db, client_a, "llm_visibility", 20)
    queue(db, client_a, "site_crawl", 10)
    queue(db, client_a, "ga4", 5)

    assert jobs.claim_next_job(db, "llm").source == "llm_visibility"
    assert jobs.claim_next_job(db, "llm") is None
    assert jobs.claim_next_job(db, "crawl").source == "site_crawl"
    assert jobs.claim_next_job(db, "main").source == "gsc_queries"
    assert jobs.claim_next_job(db, "main").source == "ga4"
    assert jobs.claim_next_job(db, "main") is None


def test_the_main_lane_never_takes_a_lane_job_even_when_it_is_the_oldest(db, client_a):
    queue(db, client_a, "llm_visibility", 90)
    queue(db, client_a, "bing_query_stats", 1)
    assert jobs.claim_next_job(db, "main").source == "bing_query_stats"
    assert jobs.claim_next_job(db, "main") is None


def test_lane_of_names_the_lane(db):
    assert [jobs.lane_of(s) for s in ("llm_visibility", "site_crawl", "gsc_pages", "ga4", "bing_query_stats")] == ["llm", "crawl", "main", "main", "main"]


def test_a_stop_request_ends_a_search_console_fetch_at_the_next_page(monkeypatch):
    import pytest

    from app.ingestion.gsc import client as gsc_client

    pages = []

    class Response:
        def json(self):
            return {"rows": [{"keys": ["2026-10-01"]}] * 25000}

    def post(*args, **kwargs):
        pages.append(1)
        return Response()

    calls = {"n": 0}

    def stop_after_first_page():
        calls["n"] += 1
        if calls["n"] > 1:
            raise jobs.JobStopped("Stopped by ryan@example.com")

    monkeypatch.setattr(gsc_client, "post_json", post)
    monkeypatch.setattr(gsc_client, "check_stop", stop_after_first_page)
    rows = gsc_client.query_search_analytics(access_token="t", site_url="sc-domain:x.com", start_date=date(2026, 10, 1), end_date=date(2026, 10, 2), dimensions=["date"])
    with pytest.raises(jobs.JobStopped):
        list(rows)
    assert len(pages) == 1  # asked for the first page only
