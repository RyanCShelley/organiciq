"""Regression tests for the pre-launch hardening pass.

Each test pins a defect found in the production readiness review; see
docs/production-readiness-review.md.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.settings import INSECURE_AUTH_SECRET, INSECURE_TOKEN_KEY, Settings
from app.models.job import SyncJob, SyncJobStatus
from app.models.user import UserRole
from app.services.auth import upsert_user
from app.services.jobs import fail_stale_active_jobs
from app.schemas import AuthUpsertRequest

STRONG = "x" * 48


def _prod_settings(**overrides) -> Settings:
    base = dict(
        app_env="production",
        auth_secret=STRONG,
        integration_token_key=STRONG,
        internal_api_secret=STRONG,
        allowed_origins="https://app.example.com",
    )
    base.update(overrides)
    return Settings(**base)


# --- Finding 1: default secrets must not boot in production -----------------


def test_production_rejects_default_auth_secret():
    with pytest.raises(RuntimeError, match="AUTH_SECRET"):
        _prod_settings(auth_secret=INSECURE_AUTH_SECRET)


def test_production_rejects_default_integration_token_key():
    with pytest.raises(RuntimeError, match="INTEGRATION_TOKEN_KEY"):
        _prod_settings(integration_token_key=INSECURE_TOKEN_KEY)


def test_production_rejects_short_secret():
    with pytest.raises(RuntimeError, match="at least"):
        _prod_settings(auth_secret="tooshort")


def test_production_requires_internal_api_secret():
    with pytest.raises(RuntimeError, match="INTERNAL_API_SECRET"):
        _prod_settings(internal_api_secret="")


def test_production_rejects_wildcard_cors():
    with pytest.raises(RuntimeError, match="ALLOWED_ORIGINS"):
        _prod_settings(allowed_origins="*")


def test_production_accepts_strong_configuration():
    settings = _prod_settings()
    assert settings.is_production is True


def test_development_tolerates_defaults():
    settings = Settings(app_env="development", auth_secret=INSECURE_AUTH_SECRET)
    assert settings.is_production is False


# --- Finding 2: /auth/upsert requires the internal secret -------------------


def test_upsert_guard_rejects_missing_secret(monkeypatch):
    from fastapi import HTTPException

    from app.api.routers import auth as auth_router

    monkeypatch.setattr(auth_router, "get_settings", _prod_settings)

    with pytest.raises(HTTPException) as exc:
        auth_router.require_internal_caller(None)
    assert exc.value.status_code == 401


def test_upsert_guard_rejects_wrong_secret(monkeypatch):
    from fastapi import HTTPException

    from app.api.routers import auth as auth_router

    monkeypatch.setattr(auth_router, "get_settings", _prod_settings)

    with pytest.raises(HTTPException) as exc:
        auth_router.require_internal_caller("not-the-secret")
    assert exc.value.status_code == 401


def test_upsert_guard_accepts_correct_secret(monkeypatch):
    from app.api.routers import auth as auth_router

    monkeypatch.setattr(auth_router, "get_settings", _prod_settings)

    assert auth_router.require_internal_caller(STRONG) is None


def test_upsert_guard_is_skipped_in_development(monkeypatch):
    """Local dev has no secret configured; the endpoint must stay usable."""
    from app.api.routers import auth as auth_router

    monkeypatch.setattr(
        auth_router,
        "get_settings",
        lambda: Settings(app_env="development", internal_api_secret=""),
    )

    assert auth_router.require_internal_caller(None) is None


# --- Finding 3: domain login must not confer admin --------------------------


def test_upsert_assigns_team_not_admin_by_default(db):
    user = upsert_user(
        db,
        AuthUpsertRequest(email="Staffer@smamarketing.net", name="Staffer", google_sub="g-1"),
    )
    assert user.role == UserRole.SMA_TEAM


def test_unknown_workspace_login_is_not_auto_admin(db):
    """
    get_current_user provisions unknown SMA addresses at SMA_TEAM. Admin comes
    only from SMA_ADMIN_EMAILS, so one compromised staff login cannot read
    every client.
    """
    import inspect

    from app.core import security

    source = inspect.getsource(security.get_current_user)
    assert "role=UserRole.SMA_ADMIN," not in source, (
        "get_current_user must not unconditionally provision admins"
    )
    assert "admin_email_set" in source


# --- Finding 4: queued jobs must survive a long daily backlog ---------------


def _job(client_id, *, status, source, age_minutes, started=False) -> SyncJob:
    created = datetime.now(timezone.utc) - timedelta(minutes=age_minutes)
    return SyncJob(
        client_id=client_id,
        source=source,
        start_date=created.date(),
        end_date=created.date(),
        status=status,
        created_at=created,
        updated_at=created,
        started_at=created if started else None,
    )


def test_queued_jobs_survive_a_long_backlog(db, client_a):
    """
    A 35-client cycle enqueues ~210 jobs and takes hours to drain. Queued jobs
    were previously failed 45 minutes after enqueue, without ever running.
    """
    job = _job(client_a.id, status=SyncJobStatus.QUEUED, source="ga4", age_minutes=180)
    db.add(job)
    db.commit()

    fail_stale_active_jobs(db)
    db.refresh(job)

    assert job.status == SyncJobStatus.QUEUED
    assert job.error_message is None


def test_running_jobs_still_time_out(db, client_a):
    job = _job(
        client_a.id,
        status=SyncJobStatus.FETCHING,
        source="gsc_pages",
        age_minutes=90,
        started=True,
    )
    db.add(job)
    db.commit()

    stale = fail_stale_active_jobs(db)
    db.refresh(job)

    assert job.status == SyncJobStatus.FAILED
    assert job in stale


def test_queued_jobs_fail_after_the_long_ceiling(db, client_a):
    job = _job(
        client_a.id,
        status=SyncJobStatus.QUEUED,
        source="se_ranking_ai",
        age_minutes=60 * 30,
    )
    db.add(job)
    db.commit()

    fail_stale_active_jobs(db)
    db.refresh(job)

    assert job.status == SyncJobStatus.FAILED
    assert "Never started" in (job.error_message or "")


# --- Finding 5: no hot reload in production ---------------------------------


def test_worker_skips_hot_reload_in_production():
    import inspect

    from app import worker

    source = inspect.getsource(worker._jobs_module)
    assert "is_production" in source, "worker must not reload modules in production"


# --- Finding 6: Google access tokens are cached -----------------------------


def test_access_token_is_cached_across_calls(db, client_a, monkeypatch):
    """
    Four fetch calls per client per cycle previously meant four token requests
    and ~70 encrypted writes each. One mint should now serve them all.
    """
    from datetime import datetime, timedelta, timezone

    from app.ingestion import google_credentials as gc

    gc.reset_access_token_cache()
    monkeypatch.setattr(gc, "load_google_refresh_token", lambda db, cid: "rt-shared")
    monkeypatch.setattr(
        gc,
        "get_settings",
        lambda: Settings(
            google_data_oauth_client_id="cid", google_data_oauth_client_secret="secret"
        ),
    )

    mints: list[int] = []

    def fake_mint(refresh_token: str):
        mints.append(1)
        return "tok-1", datetime.now(timezone.utc) + timedelta(hours=1)

    monkeypatch.setattr(gc, "_mint_access_token", fake_mint)

    tokens = [gc.access_token_for_client(db, client_a.id) for _ in range(4)]

    assert tokens == ["tok-1"] * 4
    assert len(mints) == 1, "token should be minted once, not per call"
    gc.reset_access_token_cache()


def test_expired_cached_token_is_reminted(db, client_a, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from app.ingestion import google_credentials as gc

    gc.reset_access_token_cache()
    monkeypatch.setattr(gc, "load_google_refresh_token", lambda db, cid: "rt-shared")
    monkeypatch.setattr(
        gc,
        "get_settings",
        lambda: Settings(
            google_data_oauth_client_id="cid", google_data_oauth_client_secret="secret"
        ),
    )

    calls: list[str] = []

    def fake_mint(refresh_token: str):
        calls.append(refresh_token)
        # Already inside the refresh skew, so it must not be reused.
        return f"tok-{len(calls)}", datetime.now(timezone.utc) + timedelta(minutes=1)

    monkeypatch.setattr(gc, "_mint_access_token", fake_mint)

    first = gc.access_token_for_client(db, client_a.id)
    second = gc.access_token_for_client(db, client_a.id)

    assert first == "tok-1"
    assert second == "tok-2"
    gc.reset_access_token_cache()


def test_credential_refresh_no_longer_rewrites_every_client():
    """The O(N^2) write amplification path must stay deleted."""
    from app.ingestion import google_credentials as gc

    assert not hasattr(gc, "persist_google_tokens")


# --- Finding 7: staging rows are purged after publish -----------------------


def test_purge_removes_staging_rows_for_the_job(db, client_a):
    from app.ingestion.staging_cleanup import purge_staging_for_job
    from app.models.gsc import StagingGscPage

    job = _job(client_a.id, status=SyncJobStatus.SUCCESSFUL, source="gsc_pages", age_minutes=1)
    db.add(job)
    db.commit()

    from datetime import date as date_cls

    for i in range(3):
        db.add(
            StagingGscPage(
                job_id=job.id,
                client_id=client_a.id,
                raw={"keys": [str(i)]},
                date=date_cls.today(),
                page=f"https://example.com/{i}",
                country="usa",
                device="DESKTOP",
                gsc_site_url="https://example.com",
                impressions=1,
                clicks=1,
                ctr=1,
                average_position=1,
            )
        )
    db.commit()
    assert db.query(StagingGscPage).filter_by(job_id=job.id).count() == 3

    removed = purge_staging_for_job(db, job_id=job.id, source="gsc_pages")

    assert removed == 3
    assert db.query(StagingGscPage).filter_by(job_id=job.id).count() == 0


def test_purge_is_a_noop_for_unknown_source(db, client_a):
    from app.ingestion.staging_cleanup import purge_staging_for_job

    assert purge_staging_for_job(db, job_id=client_a.id, source="not_a_source") == 0


def test_every_job_source_has_a_purge_mapping():
    from app.ingestion.staging_cleanup import _STAGING_BY_SOURCE
    from app.services.jobs import _job_handlers

    assert set(_job_handlers()) <= set(_STAGING_BY_SOURCE), (
        "a job source with no staging mapping would leak staging rows forever"
    )


# --- Finding 8: Google calls retry throttling and transient errors ----------


def _response(status: int, *, headers: dict[str, str] | None = None):
    import httpx

    return httpx.Response(
        status, headers=headers or {}, request=httpx.Request("GET", "https://example.test")
    )


def test_retry_recovers_from_429():
    from app.ingestion.google_http import request_with_retry

    attempts = {"n": 0}

    def send():
        attempts["n"] += 1
        return _response(429) if attempts["n"] == 1 else _response(200)

    res = request_with_retry(send, description="test", sleep=lambda _: None)

    assert res.status_code == 200
    assert attempts["n"] == 2


def test_retry_honours_retry_after():
    from app.ingestion.google_http import request_with_retry

    slept: list[float] = []
    attempts = {"n": 0}

    def send():
        attempts["n"] += 1
        return _response(429, headers={"Retry-After": "7"}) if attempts["n"] == 1 else _response(200)

    request_with_retry(send, description="test", sleep=slept.append)

    assert slept == [7.0]


def test_permanent_4xx_is_not_retried():
    import httpx

    from app.ingestion.google_http import request_with_retry

    attempts = {"n": 0}

    def send():
        attempts["n"] += 1
        return _response(403)

    with pytest.raises(httpx.HTTPStatusError):
        request_with_retry(send, description="test", sleep=lambda _: None)
    assert attempts["n"] == 1, "403 is permanent — retrying it just burns quota"


def test_retry_gives_up_and_raises():
    import httpx

    from app.ingestion.google_http import request_with_retry

    attempts = {"n": 0}

    def send():
        attempts["n"] += 1
        return _response(503)

    with pytest.raises(httpx.HTTPStatusError):
        request_with_retry(send, description="test", max_attempts=3, sleep=lambda _: None)
    assert attempts["n"] == 3


def test_google_clients_no_longer_call_raise_for_status_directly():
    import inspect

    from app.ingestion.ga4 import client as ga4_client
    from app.ingestion.gsc import client as gsc_client

    for module in (ga4_client, gsc_client):
        assert "raise_for_status" not in inspect.getsource(module), (
            f"{module.__name__} must route through google_http retry"
        )


# --- Baseline hero copy: the snapshot's own window, not the viewed period ---


def test_baseline_payload_exposes_its_measured_window(db, client_a):
    """
    The hero says what the snapshot is frozen between. That has to come from
    the baseline's own window — `current_window` is the period being viewed.
    """
    from datetime import date as date_cls

    from app.services.dashboard import _baseline_comparison

    client_a.baseline_as_of = date_cls(2026, 9, 9)
    client_a.baseline_period_start = date_cls(2026, 8, 11)
    client_a.baseline_period_end = date_cls(2026, 9, 9)
    client_a.baseline_monthly_sessions = 2863
    client_a.baseline_monthly_leads = 19
    db.commit()

    payload = _baseline_comparison(
        client_a,
        current_sessions=1000,
        current_leads=10,
        current_lead_rate=1.0,
        current_window=(date_cls(2026, 6, 12), date_cls(2026, 9, 9)),
    )

    assert payload["period_start"] == "2026-08-11"
    assert payload["period_end"] == "2026-09-09"
    # The viewed period stays separate and must not leak into the frozen line.
    assert payload["current_window"]["from"] == "2026-06-12"


def test_baseline_period_end_falls_back_to_as_of(db, client_a):
    """Manual snapshots record no window; the hero still reports a true date."""
    from datetime import date as date_cls

    from app.services.dashboard import _baseline_comparison

    client_a.baseline_as_of = date_cls(2026, 9, 9)
    client_a.baseline_period_start = None
    client_a.baseline_period_end = None
    client_a.baseline_monthly_sessions = 2863
    db.commit()

    payload = _baseline_comparison(
        client_a,
        current_sessions=None,
        current_leads=None,
        current_lead_rate=None,
        current_window=None,
    )

    assert payload["period_start"] is None
    assert payload["period_end"] == "2026-09-09"
