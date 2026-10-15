from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from app.models.integration import Integration, IntegrationProvider
from app.models.job import SyncJob, SyncJobStatus
from app.services import health_digest
from app.services.health_digest import build_digest, render

NOW = datetime(2026, 10, 15, 13, 0, tzinfo=timezone.utc)


def _job(db, client, source, status, *, age_hours=1.0, error=None):
    created = NOW - timedelta(hours=age_hours)
    db.add(
        SyncJob(
            id=uuid4(),
            client_id=client.id,
            source=source,
            start_date=NOW.date(),
            end_date=NOW.date(),
            status=status,
            error_message=error,
            created_at=created,
            completed_at=created,
        )
    )
    db.commit()


def _map(db, client, provider):
    row = (
        db.query(Integration)
        .filter(Integration.client_id == client.id, Integration.provider == provider)
        .one()
    )
    row.external_property_id = "x"
    db.commit()


def test_a_failure_still_standing_is_reported(db, client_a):
    _job(db, client_a, "ga4", SyncJobStatus.FAILED, error="boom")
    digest = build_digest(db, now=NOW)
    assert [(p.what, p.detail) for p in digest.failures] == [("ga4 failed", "boom")]


def test_a_failure_a_later_success_superseded_is_not(db, client_a):
    _job(db, client_a, "ga4", SyncJobStatus.FAILED, age_hours=30)
    _job(db, client_a, "ga4", SyncJobStatus.SUCCESSFUL, age_hours=2)
    assert build_digest(db, now=NOW).healthy


def test_a_mapped_source_with_no_recent_success_is_stale(db, client_a):
    _map(db, client_a, IntegrationProvider.GSC)
    _job(db, client_a, "gsc_pages", SyncJobStatus.SUCCESSFUL, age_hours=24 * 6)
    digest = build_digest(db, now=NOW)
    assert len(digest.stale) == 1 and "gsc_pages" in digest.stale[0].what


def test_an_unmapped_source_is_a_setup_task_not_a_fault(db, client_a):
    assert build_digest(db, now=NOW).healthy


def test_a_job_working_for_hours_is_stuck(db, client_a):
    _job(db, client_a, "site_crawl", SyncJobStatus.FETCHING, age_hours=5)
    assert len(build_digest(db, now=NOW).stuck) == 1


def test_render_names_the_client_and_the_cause(db, client_a):
    _job(db, client_a, "ga4", SyncJobStatus.FAILED, error="boom")
    subject, body = render(build_digest(db, now=NOW), today=date(2026, 10, 15))
    assert "1 to look at" in subject
    assert client_a.client_name in body and "boom" in body


def test_quiet_days_are_not_emailed_but_mondays_are(db, client_a, monkeypatch):
    sent = []
    monkeypatch.setattr(health_digest, "send_email", lambda s, b: sent.append(s) or True)
    settings = health_digest.get_settings()
    monkeypatch.setattr(settings, "health_digest_hour_utc", 0)

    class _At(datetime):
        current = NOW  # a Thursday

        @classmethod
        def now(cls, tz=None):
            return cls.current

    monkeypatch.setattr(health_digest, "datetime", _At)
    assert health_digest.maybe_send_health_digest(db) is True
    assert sent == []

    from app.models.scheduler import SchedulerCheckpoint

    db.query(SchedulerCheckpoint).delete()
    db.commit()
    _At.current = datetime(2026, 10, 19, 13, 0, tzinfo=timezone.utc)  # a Monday
    assert health_digest.maybe_send_health_digest(db) is True
    assert len(sent) == 1 and "all clear" in sent[0]
