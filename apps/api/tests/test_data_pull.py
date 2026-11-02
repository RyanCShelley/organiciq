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


def done_job(db, client, source, seconds, days=400):
    now = datetime.now(timezone.utc)
    db.add(SyncJob(client_id=client.id, source=source, start_date=(now - timedelta(days=days)).date(), end_date=now.date(),
                   status=SyncJobStatus.SUCCESSFUL, started_at=now - timedelta(seconds=seconds + 5), completed_at=now - timedelta(seconds=5), created_at=now - timedelta(days=3)))
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


def test_time_left_comes_from_past_runs_and_is_unknown_without_any(client, db, client_a, admin_user):
    connect(db, client_a)
    h = auth_header(admin_user.email)
    unknown = client.post(f"/v2/admin/clients/{client_a.id}/pull", headers=h).json()
    assert unknown["seconds_left"] is None

    for source in [s["source"] for s in unknown["sources"]]:
        done_job(db, client_a, source, seconds=120)
    known = client.get(f"/v2/admin/clients/{client_a.id}/pull", headers=h).json()
    assert known["seconds_left"] == 120 * len(known["sources"])


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
