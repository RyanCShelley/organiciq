"""Pull data: what is fetched and how far back, progress per source, and the time left."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.models.integration import Integration
from app.models.job import SyncJob, SyncJobStatus
from tests.conftest import auth_header, client_header


def connect(db, client):
    for row in db.query(Integration).filter(Integration.client_id == client.id):
        row.external_property_id = f"id-{row.provider.value}"
    client.domain = "example.com"
    db.commit()


def test_a_team_member_cannot_pull(client, db, client_a, team_user):
    h = auth_header(team_user.email)
    assert client.get(f"/v2/admin/clients/{client_a.id}/pull", headers=h).status_code == 403
    assert client.post(f"/v2/admin/clients/{client_a.id}/pull", headers=h).status_code == 403


def test_nothing_connected_says_to_connect_first(client, db, client_a, admin_user):
    client_a.domain = ""
    db.query(Integration).filter(Integration.client_id == client_a.id).delete()
    db.commit()
    res = client.post(f"/v2/admin/clients/{client_a.id}/pull", headers=auth_header(admin_user.email))
    assert res.status_code == 400 and "Connect a data source" in res.json()["detail"]


def test_the_plan_says_how_far_back_each_source_goes(client, db, client_a, admin_user):
    connect(db, client_a)
    out = client.get(f"/v2/admin/clients/{client_a.id}/pull", headers=auth_header(admin_user.email)).json()
    by = {s["source"]: s for s in out["sources"]}
    assert by["ga4"]["reach"] == "26 months of daily data" and by["gsc_queries"]["reach"] == "13 months of daily data"
    assert by["site_crawl"]["state"] == "not_started" and out["running"] is False


def test_starting_queues_every_source_and_a_second_press_adds_nothing(client, db, client_a, admin_user):
    connect(db, client_a)
    h = auth_header(admin_user.email)
    first = client.post(f"/v2/admin/clients/{client_a.id}/pull", headers=h).json()
    assert "ga4" in first["queued"] and first["running"] is True and first["jobs_total"] == len(first["sources"])
    assert {s["state"] for s in first["sources"]} == {"queued"}
    assert client.post(f"/v2/admin/clients/{client_a.id}/pull", headers=h).json()["queued"] == []


def test_progress_counts_finished_sources_and_reports_failures(client, db, client_a, admin_user):
    connect(db, client_a)
    h = auth_header(admin_user.email)
    client.post(f"/v2/admin/clients/{client_a.id}/pull", headers=h)
    jobs = {j.source: j for j in db.query(SyncJob).filter(SyncJob.client_id == client_a.id)}
    jobs["ga4"].status = SyncJobStatus.SUCCESSFUL
    jobs["site_crawl"].status, jobs["site_crawl"].error_message = SyncJobStatus.FAILED, "Site blocked the crawler"
    jobs["gsc_pages"].status = SyncJobStatus.FETCHING
    db.commit()
    out = client.get(f"/v2/admin/clients/{client_a.id}/pull", headers=h).json()
    by = {s["source"]: s for s in out["sources"]}
    assert by["ga4"]["state"] == "done" and by["gsc_pages"]["state"] == "running" and by["site_crawl"]["state"] == "failed"
    assert by["site_crawl"]["error"] == "Site blocked the crawler" and out["failed"] == ["Site crawl"]
    assert out["jobs_done"] == 1 and out["finished"] is False


def test_jobs_queued_for_other_clients_ahead_of_ours_are_counted(client, db, client_a, client_b, admin_user):
    connect(db, client_a)
    db.add(SyncJob(client_id=client_b.id, source="ga4", start_date=datetime.now().date(), end_date=datetime.now().date(), status=SyncJobStatus.QUEUED,
                   created_at=datetime.now(timezone.utc) - timedelta(hours=1)))
    db.commit()
    out = client.post(f"/v2/admin/clients/{client_a.id}/pull", headers=auth_header(admin_user.email)).json()
    assert out["jobs_ahead"] == 1


def test_a_running_source_says_how_long_it_has_been_going_and_no_time_left_is_promised(client, db, client_a, admin_user):
    connect(db, client_a)
    h = auth_header(admin_user.email)
    client.post(f"/v2/admin/clients/{client_a.id}/pull", headers=h)
    job = db.query(SyncJob).filter(SyncJob.client_id == client_a.id, SyncJob.source == "ga4").one()
    job.status, job.started_at = SyncJobStatus.FETCHING, datetime.now(timezone.utc) - timedelta(minutes=5)
    db.commit()
    out = client.get(f"/v2/admin/clients/{client_a.id}/pull", headers=h).json()
    ga4 = next(s for s in out["sources"] if s["source"] == "ga4")
    assert 295 <= ga4["running_seconds"] <= 310 and "seconds_left" not in ga4 and "seconds_left" not in out


def test_a_job_orphaned_by_a_restart_shows_as_interrupted_and_pulling_again_replaces_it(client, db, client_a, client_b, admin_user):
    connect(db, client_a)
    h = auth_header(admin_user.email)
    now = datetime.now(timezone.utc)
    client.post(f"/v2/admin/clients/{client_a.id}/pull", headers=h)
    dead = db.query(SyncJob).filter(SyncJob.client_id == client_a.id, SyncJob.source == "ga4").one()
    dead.status, dead.started_at = SyncJobStatus.NORMALIZING, now - timedelta(minutes=30)
    # The worker has since started a later job, so the first cannot still be running.
    db.add(SyncJob(client_id=client_b.id, source="ga4", start_date=now.date(), end_date=now.date(), status=SyncJobStatus.SUCCESSFUL, started_at=now - timedelta(minutes=20), completed_at=now - timedelta(minutes=19)))
    db.commit()
    db.execute(__import__("sqlalchemy").text("update sync_jobs set updated_at = :t where id = :i"), {"t": now - timedelta(minutes=25), "i": dead.id})
    db.commit()

    shown = {s["source"]: s for s in client.get(f"/v2/admin/clients/{client_a.id}/pull", headers=h).json()["sources"]}
    assert shown["ga4"]["state"] == "failed" and "restart" in shown["ga4"]["error"]
    again = client.post(f"/v2/admin/clients/{client_a.id}/pull", headers=h).json()
    assert again["queued"] == ["ga4"]
    db.refresh(dead)
    assert dead.status == SyncJobStatus.FAILED


def test_a_running_job_is_not_called_interrupted_when_nothing_started_after_it(client, db, client_a, admin_user):
    connect(db, client_a)
    h = auth_header(admin_user.email)
    client.post(f"/v2/admin/clients/{client_a.id}/pull", headers=h)
    job = db.query(SyncJob).filter(SyncJob.client_id == client_a.id, SyncJob.source == "ga4").one()
    job.status, job.started_at = SyncJobStatus.NORMALIZING, datetime.now(timezone.utc) - timedelta(minutes=30)
    db.commit()
    shown = {s["source"]: s for s in client.get(f"/v2/admin/clients/{client_a.id}/pull", headers=h).json()["sources"]}
    assert shown["ga4"]["state"] == "running"


def finish(db, client, source, start_days_back, hours_ago=1, status=SyncJobStatus.SUCCESSFUL):
    now = datetime.now(timezone.utc)
    db.add(SyncJob(client_id=client.id, source=source, start_date=(now - timedelta(days=start_days_back)).date(), end_date=now.date(), status=status,
                   started_at=now - timedelta(hours=hours_ago, minutes=5), completed_at=now - timedelta(hours=hours_ago)))
    db.commit()


def test_pulling_queues_only_what_is_missing(client, db, client_a, admin_user):
    connect(db, client_a)
    h = auth_header(admin_user.email)
    plan = {s["source"] for s in client.get(f"/v2/admin/clients/{client_a.id}/pull", headers=h).json()["sources"]}
    for source in plan - {"ga4", "site_crawl"}:
        finish(db, client_a, source, start_days_back=800)
    finish(db, client_a, "site_crawl", start_days_back=0, status=SyncJobStatus.FAILED)
    queued = client.post(f"/v2/admin/clients/{client_a.id}/pull", headers=h).json()["queued"]
    assert sorted(queued) == ["ga4", "site_crawl"]


def test_a_source_pulled_over_a_day_ago_or_over_a_shorter_window_is_pulled_again(client, db, client_a, admin_user):
    connect(db, client_a)
    h = auth_header(admin_user.email)
    plan = {s["source"] for s in client.get(f"/v2/admin/clients/{client_a.id}/pull", headers=h).json()["sources"]}
    for source in plan:
        finish(db, client_a, source, start_days_back=800)
    finish(db, client_a, "ga4", start_days_back=800, hours_ago=30)       # stale
    finish(db, client_a, "gsc_pages", start_days_back=30, hours_ago=1)   # newest job only went back a month
    assert sorted(client.post(f"/v2/admin/clients/{client_a.id}/pull", headers=h).json()["queued"]) == ["ga4", "gsc_pages"]


def test_everything_current_queues_nothing_and_force_pulls_everything(client, db, client_a, admin_user):
    connect(db, client_a)
    h = auth_header(admin_user.email)
    plan = {s["source"] for s in client.get(f"/v2/admin/clients/{client_a.id}/pull", headers=h).json()["sources"]}
    for source in plan:
        finish(db, client_a, source, start_days_back=800)
    out = client.post(f"/v2/admin/clients/{client_a.id}/pull", headers=h).json()
    assert out["queued"] == [] and out["up_to_date"] is True and out["running"] is False
    forced = client.post(f"/v2/admin/clients/{client_a.id}/pull?force=true", headers=h).json()
    assert sorted(forced["queued"]) == sorted(plan)


def test_connecting_another_source_makes_only_that_source_missing(client, db, client_a, admin_user):
    from app.models.client_bing_site import ClientBingSite

    connect(db, client_a)
    h = auth_header(admin_user.email)
    for source in {s["source"] for s in client.get(f"/v2/admin/clients/{client_a.id}/pull", headers=h).json()["sources"]}:
        finish(db, client_a, source, start_days_back=800)
    assert client.get(f"/v2/admin/clients/{client_a.id}/pull", headers=h).json()["up_to_date"] is True

    db.add(ClientBingSite(client_id=client_a.id, site_url="https://example.com/", status="unchecked"))
    db.commit()
    status = client.get(f"/v2/admin/clients/{client_a.id}/pull", headers=h).json()
    assert status["up_to_date"] is False
    assert [s["source"] for s in status["sources"] if not s["current"]] == ["bing_query_stats"]
    assert client.post(f"/v2/admin/clients/{client_a.id}/pull", headers=h).json()["queued"] == ["bing_query_stats"]


def test_connecting_a_source_pulls_only_what_it_feeds_even_if_pulled_today(client, db, client_a, admin_user):
    connect(db, client_a)
    h = client_header(client_a.id, admin_user.email)
    for source in {s["source"] for s in client.get(f"/v2/admin/clients/{client_a.id}/pull", headers=auth_header(admin_user.email)).json()["sources"]}:
        finish(db, client_a, source, start_days_back=800)
    out = client.post("/v2/connections/pull", json={"sources": ["ga4", "not_a_source"]}, headers=h).json()
    assert out["queued"] == ["ga4"]
    assert client.post("/v2/connections/pull", json={"sources": ["not_a_source"]}, headers=h).json()["queued"] == []


def test_a_long_pull_is_not_called_interrupted_just_because_a_job_in_another_lane_started_after_it(client, db, client_a, admin_user):
    connect(db, client_a)
    h = auth_header(admin_user.email)
    now = datetime.now(timezone.utc)
    client.post(f"/v2/admin/clients/{client_a.id}/pull", headers=h)
    long_pull = db.query(SyncJob).filter(SyncJob.client_id == client_a.id, SyncJob.source == "gsc_queries").one()
    long_pull.status, long_pull.started_at = SyncJobStatus.FETCHING, now - timedelta(minutes=40)
    crawl = db.query(SyncJob).filter(SyncJob.client_id == client_a.id, SyncJob.source == "site_crawl").one()
    crawl.status, crawl.started_at = SyncJobStatus.FETCHING, now - timedelta(minutes=5)
    db.commit()
    db.execute(__import__("sqlalchemy").text("update sync_jobs set updated_at = :t where id = :i"), {"t": now - timedelta(minutes=35), "i": long_pull.id})
    db.commit()
    shown = {s["source"]: s for s in client.get(f"/v2/admin/clients/{client_a.id}/pull", headers=h).json()["sources"]}
    assert shown["gsc_queries"]["state"] == "running" and shown["site_crawl"]["state"] == "running"


def test_stopping_cancels_what_is_waiting_and_asks_what_is_running_to_stop(client, db, client_a, admin_user):
    connect(db, client_a)
    h = auth_header(admin_user.email)
    client.post(f"/v2/admin/clients/{client_a.id}/pull", headers=h)
    running = db.query(SyncJob).filter(SyncJob.client_id == client_a.id, SyncJob.source == "gsc_queries").one()
    running.status, running.started_at = SyncJobStatus.FETCHING, datetime.now(timezone.utc)
    db.commit()

    out = client.post(f"/v2/admin/clients/{client_a.id}/pull/stop", headers=h).json()
    by = {s["source"]: s for s in out["sources"]}
    assert by["gsc_queries"]["state"] == "stopping" and out["stopping"] is True and out["running"] is True
    waiting = [s for s in out["sources"] if s["source"] != "gsc_queries"]
    assert waiting and all(s["state"] == "stopped" and "Stopped by" in s["error"] for s in waiting)
    assert out["failed"] == []  # a stop is not a failure

    # Once the worker honours the request the job ends as stopped, and pulling again queues everything that did not finish.
    db.refresh(running)
    running.status, running.error_message, running.completed_at = SyncJobStatus.FAILED, "Stopped by admin", datetime.now(timezone.utc)
    db.commit()
    again = client.post(f"/v2/admin/clients/{client_a.id}/pull", headers=h).json()
    assert len(again["queued"]) == len(out["sources"])


def test_a_job_checks_for_a_stop_request_and_raises_when_there_is_one(db, client_a):
    import pytest

    from app.services import jobs

    job = SyncJob(client_id=client_a.id, source="gsc_queries", start_date=datetime.now().date(), end_date=datetime.now().date(),
                  status=SyncJobStatus.FETCHING, params_json={})
    db.add(job)
    db.commit()
    jobs.check_stop()  # no job running on this thread: nothing happens
    jobs._running.job_id, jobs._running.checked_at = job.id, 0.0
    try:
        jobs.check_stop()  # no request yet
        job.params_json = {"stop_requested_by": "ryan@example.com"}
        db.commit()
        jobs._running.checked_at = 0.0
        with pytest.raises(jobs.JobStopped, match="Stopped by ryan@example.com"):
            jobs.check_stop()
    finally:
        jobs._running.job_id = None


# ---- the lean Search Console pull ------------------------------------------------------------------------

def test_lean_windows_are_daily_for_120_days_and_monthly_before():
    from app.ingestion.gsc.fetch import lean_windows

    daily, months = lean_windows(date(2025, 10, 3), date(2026, 10, 30))
    assert daily == (date(2026, 7, 3), date(2026, 10, 30))  # the last 120 days
    assert months[0] == (date(2025, 10, 3), date(2025, 10, 31))  # the first month may start mid-month
    assert months[1] == (date(2025, 11, 1), date(2025, 11, 30))
    assert months[-1] == (date(2026, 7, 1), date(2026, 7, 2))  # the last stops where the daily stretch begins
    assert len(months) == 10
    spans = [w for w in months] + [daily]
    assert all(a_end < b_start for (_, a_end), (b_start, _) in zip(spans, spans[1:]))  # no day twice, none missing
    assert all((b_start - a_end).days == 1 for (_, a_end), (b_start, _) in zip(spans, spans[1:]))
    short_daily, short_months = lean_windows(date(2026, 10, 27), date(2026, 10, 30))  # the daily top-up window
    assert short_daily == (date(2026, 10, 27), date(2026, 10, 30)) and short_months == []


def test_a_lean_client_pulls_searches_daily_then_monthly_without_country_or_device(db, client_a):
    from unittest.mock import patch
    from uuid import uuid4

    from app.ingestion.gsc.fetch import fetch_gsc_queries
    from app.models.gsc import StagingGscQueryPage
    from app.models.integration import ConnectionStatus, Integration, IntegrationProvider

    row = db.query(Integration).filter(Integration.client_id == client_a.id, Integration.provider == IntegrationProvider.GSC).one()
    row.external_property_id, row.connection_status = "sc-domain:example.com", ConnectionStatus.CONNECTED
    client_a.gsc_lean_pull = True
    job = SyncJob(id=uuid4(), client_id=client_a.id, source="gsc_queries", start_date=date(2026, 3, 1), end_date=date(2026, 10, 30), status=SyncJobStatus.FETCHING)
    db.add(job)
    db.commit()

    seen = []

    def fake(*, dimensions, start_date, end_date, **_):
        seen.append((dimensions, start_date, end_date))
        return [{"keys": ["2026-10-02", "natural sunscreen", "https://example.com/spf"] if dimensions[0] == "date" else ["natural sunscreen", "https://example.com/spf"],
                 "impressions": 10, "clicks": 1, "ctr": 0.1, "position": 8.0}]

    with patch("app.ingestion.gsc.fetch.access_token_for_client", return_value="t"), patch("app.ingestion.gsc.fetch.client_has_google_credentials", return_value=True), patch("app.ingestion.gsc.fetch.query_search_analytics", side_effect=fake):
        fetch_gsc_queries(db, job)

    assert seen[0][0] == ["date", "query", "page"] and all(d == ["query", "page"] for d, _, _ in seen[1:])
    rows = db.query(StagingGscQueryPage).filter(StagingGscQueryPage.job_id == job.id).order_by(StagingGscQueryPage.date).all()
    assert len(rows) == len(seen) and all(r.country == "" and r.device == "" and r.query == "natural sunscreen" for r in rows)
    assert rows[0].date == date(2026, 3, 1) and rows[-1].date == date(2026, 10, 2)  # a month's row carries the first day of its window


def test_a_client_not_switched_keeps_the_full_pull(db, client_a):
    client_a.gsc_lean_pull = False
    db.commit()
    from unittest.mock import patch
    from uuid import uuid4

    from app.ingestion.gsc.fetch import fetch_gsc_queries
    from app.models.integration import ConnectionStatus, Integration, IntegrationProvider

    row = db.query(Integration).filter(Integration.client_id == client_a.id, Integration.provider == IntegrationProvider.GSC).one()
    row.external_property_id, row.connection_status = "sc-domain:example.com", ConnectionStatus.CONNECTED
    job = SyncJob(id=uuid4(), client_id=client_a.id, source="gsc_queries", start_date=date(2026, 3, 1), end_date=date(2026, 10, 30), status=SyncJobStatus.FETCHING)
    db.add(job)
    db.commit()
    with patch("app.ingestion.gsc.fetch.access_token_for_client", return_value="t"), patch("app.ingestion.gsc.fetch.client_has_google_credentials", return_value=True), patch("app.ingestion.gsc.fetch.query_search_analytics", return_value=[]) as q:
        fetch_gsc_queries(db, job)
    assert q.call_count == 1 and q.call_args.kwargs["dimensions"] == ["date", "query", "page", "country", "device"]
    assert q.call_args.kwargs["start_date"] == date(2026, 3, 1)


def test_switching_a_client_to_lean_is_instant_and_the_pull_replaces_its_rows_when_it_lands(client, db, client_a, admin_user):
    from app.models.gsc import FactGscQueryPage

    connect(db, client_a)
    client_a.gsc_lean_pull = False
    db.add(FactGscQueryPage(client_id=client_a.id, date=date(2026, 9, 1), query="q", raw_url="https://x.example/", normalized_url="https://x.example/",
                            country="usa", device="DESKTOP", impressions=5, clicks=1, ctr=0, average_position=4))
    db.commit()
    h = auth_header(admin_user.email)
    out = client.post(f"/v2/admin/clients/{client_a.id}/gsc-lean", json={"enabled": True}, headers=h).json()
    assert out["gsc_lean"] is True and sorted(out["queued"]) == ["gsc_pages", "gsc_queries"]
    # Nothing is cleared by the click: the queued pull replaces the window itself, once the new rows have arrived.
    assert db.query(FactGscQueryPage).count() == 1
    jobs = db.query(SyncJob).filter(SyncJob.client_id == client_a.id, SyncJob.source.in_(["gsc_pages", "gsc_queries"])).all()
    assert jobs and all((j.params_json or {}).get("replace_gsc_window") is True for j in jobs)
    again = client.post(f"/v2/admin/clients/{client_a.id}/gsc-lean", json={"enabled": True}, headers=h).json()
    assert again["queued"] == []  # already lean: nothing cleared, nothing queued
    assert any(c["gsc_lean"] for c in client.get("/v2/admin/clients", headers=h).json())


def test_a_lean_pull_with_the_replace_flag_removes_the_old_full_rows_and_keeps_the_new(db, client_a):
    from uuid import uuid4

    from app.ingestion.gsc.publish import publish_gsc_queries
    from app.models.gsc import FactGscQueryPage, StagingGscQueryPage

    old = dict(client_id=client_a.id, raw_url="https://example.com/spf", normalized_url="https://example.com/spf", impressions=5, clicks=1, ctr=0, average_position=4)
    db.add(FactGscQueryPage(date=date(2026, 9, 1), query="natural sunscreen", country="usa", device="DESKTOP", gsc_site_url="sc-domain:example.com", **old))
    db.add(FactGscQueryPage(date=date(2026, 9, 1), query="natural sunscreen", country="usa", device="MOBILE", gsc_site_url="sc-domain:example.com", **old))
    db.commit()
    job = SyncJob(id=uuid4(), client_id=client_a.id, source="gsc_queries", start_date=date(2026, 8, 1), end_date=date(2026, 10, 30),
                  status=SyncJobStatus.NORMALIZING, params_json={"replace_gsc_window": True})
    db.add(job)
    db.commit()
    db.add(StagingGscQueryPage(job_id=job.id, client_id=client_a.id, raw={}, date=date(2026, 9, 1), query="natural sunscreen", page="https://example.com/spf",
                               country="", device="", gsc_site_url="sc-domain:example.com", impressions=9, clicks=2, ctr=0.2, average_position=4.1))
    db.commit()
    publish_gsc_queries(db, job)
    rows = db.query(FactGscQueryPage).filter(FactGscQueryPage.client_id == client_a.id).all()
    assert [(r.country, r.device, int(r.impressions)) for r in rows] == [("", "", 9)]  # the two full-grain rows are gone: no double counting
