from fastapi.testclient import TestClient

from tests.conftest import auth_header, client_header, date_window


def test_health(client: TestClient):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_admin_lists_all_clients(client, admin_user, client_a, client_b):
    res = client.get("/clients", headers=auth_header(admin_user.email))
    assert res.status_code == 200
    ids = {row["id"] for row in res.json()}
    assert str(client_a.id) in ids
    assert str(client_b.id) in ids


def test_team_lists_only_assigned_clients(client, team_user, client_a, client_b):
    res = client.get("/clients", headers=auth_header(team_user.email))
    assert res.status_code == 200
    ids = {row["id"] for row in res.json()}
    assert str(client_a.id) in ids
    assert str(client_b.id) not in ids


def test_team_cannot_access_other_client_integrations(client, team_user, client_b):
    res = client.get(
        "/integrations",
        headers=client_header(client_b.id, team_user.email),
    )
    assert res.status_code == 403


def test_admin_can_access_any_client_integrations(client, admin_user, client_b):
    res = client.get(
        "/integrations",
        headers=client_header(client_b.id, admin_user.email),
    )
    assert res.status_code == 200
    assert len(res.json()) == 3


def test_team_cannot_get_other_client_by_id(client, team_user, client_b):
    res = client.get(f"/clients/{client_b.id}", headers=auth_header(team_user.email))
    assert res.status_code == 403


def test_overlapping_jobs_rejected(client, admin_user, client_a):
    start, end = date_window(14)
    payload = {
        "source": "gsc_pages",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
    }
    headers = client_header(client_a.id, admin_user.email)

    first = client.post("/jobs", headers=headers, json=payload)
    assert first.status_code == 201
    assert first.json()["status"] == "queued"

    second = client.post("/jobs", headers=headers, json=payload)
    assert second.status_code == 409


def test_cancel_active_jobs_clears_overlap(client, admin_user, client_a):
    start, end = date_window(14)
    payload = {
        "source": "se_ranking_audit",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
    }
    headers = client_header(client_a.id, admin_user.email)

    first = client.post("/jobs", headers=headers, json=payload)
    assert first.status_code == 201

    cancelled = client.post("/jobs/cancel-active", headers=headers)
    assert cancelled.status_code == 200
    body = cancelled.json()
    assert len(body) == 1
    assert body[0]["status"] == "failed"
    assert "stuck sync" in (body[0]["error_message"] or "").lower()

    second = client.post("/jobs", headers=headers, json=payload)
    assert second.status_code == 201


def test_fail_stale_active_jobs(db, client_a):
    from datetime import datetime, timedelta, timezone
    from uuid import uuid4

    from app.models.job import SyncJob, SyncJobStatus
    from app.services.jobs import fail_stale_active_jobs

    start, end = date_window(14)
    old = datetime.now(timezone.utc) - timedelta(hours=2)
    job = SyncJob(
        id=uuid4(),
        client_id=client_a.id,
        source="se_ranking_audit",
        start_date=start,
        end_date=end,
        status=SyncJobStatus.FETCHING,
        started_at=old,
        created_at=old,
    )
    db.add(job)
    db.commit()

    stale = fail_stale_active_jobs(db, max_age_minutes=45)
    assert len(stale) == 1
    db.refresh(job)
    assert job.status == SyncJobStatus.FAILED
    assert "timed out" in (job.error_message or "").lower()


def test_job_for_different_source_allowed(client, admin_user, client_a):
    start, end = date_window(14)
    headers = client_header(client_a.id, admin_user.email)

    a = client.post(
        "/jobs",
        headers=headers,
        json={"source": "gsc_pages", "start_date": start.isoformat(), "end_date": end.isoformat()},
    )
    b = client.post(
        "/jobs",
        headers=headers,
        json={"source": "ga4", "start_date": start.isoformat(), "end_date": end.isoformat()},
    )
    assert a.status_code == 201
    assert b.status_code == 201


def test_worker_marks_seranking_ai_failed_without_project(db, client_a):
    from app.models.job import SyncJob, SyncJobStatus
    from app.services.jobs import claim_next_job, process_job

    start, end = date_window(7)
    job = SyncJob(
        client_id=client_a.id,
        source="se_ranking_ai",
        start_date=start,
        end_date=end,
        status=SyncJobStatus.QUEUED,
    )
    db.add(job)
    db.commit()

    claimed = claim_next_job(db)
    assert claimed is not None
    assert claimed.status == SyncJobStatus.FETCHING

    processed = process_job(db, claimed)
    assert processed.status == SyncJobStatus.FAILED
    assert "se ranking project is not selected" in (processed.error_message or "").lower()


def test_worker_routes_seranking_search(db, client_a):
    from app.models.job import SyncJob, SyncJobStatus
    from app.services.jobs import claim_next_job, process_job

    start, end = date_window(7)
    job = SyncJob(
        client_id=client_a.id,
        source="se_ranking_search",
        start_date=start,
        end_date=end,
        status=SyncJobStatus.QUEUED,
    )
    db.add(job)
    db.commit()

    claimed = claim_next_job(db)
    processed = process_job(db, claimed)
    assert processed.status == SyncJobStatus.FAILED
    assert "se ranking project is not selected" in (processed.error_message or "").lower()


def test_worker_marks_unknown_source_failed(db, client_a):
    from app.models.job import SyncJob, SyncJobStatus
    from app.services.jobs import claim_next_job, process_job

    start, end = date_window(7)
    job = SyncJob(
        client_id=client_a.id,
        source="made_up_source",
        start_date=start,
        end_date=end,
        status=SyncJobStatus.QUEUED,
    )
    db.add(job)
    db.commit()

    claimed = claim_next_job(db)
    processed = process_job(db, claimed)
    assert processed.status == SyncJobStatus.FAILED
    assert "Unknown source" in (processed.error_message or "")


def test_auth_upsert_promotes_admin_email(client):
    res = client.post(
        "/auth/upsert",
        json={
            "email": "admin@smamarketing.net",
            "name": "Admin",
            "google_sub": "g-admin",
        },
    )
    assert res.status_code == 200
    assert res.json()["role"] == "sma_admin"


def test_jobs_are_client_scoped(client, admin_user, client_a, client_b):
    start, end = date_window(7)
    client.post(
        "/jobs",
        headers=client_header(client_a.id, admin_user.email),
        json={"source": "gsc_pages", "start_date": start.isoformat(), "end_date": end.isoformat()},
    )
    res_a = client.get("/jobs", headers=client_header(client_a.id, admin_user.email))
    res_b = client.get("/jobs", headers=client_header(client_b.id, admin_user.email))
    assert len(res_a.json()) == 1
    assert len(res_b.json()) == 0
