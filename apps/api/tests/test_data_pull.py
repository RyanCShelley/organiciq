"""Pull data: what is fetched and how far back, progress per source, and the time left."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.integration import Integration
from app.models.job import SyncJob, SyncJobStatus
from tests.conftest import auth_header


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
