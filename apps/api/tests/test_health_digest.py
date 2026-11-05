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
    assert [(p.source, p.state, p.what) for p in digest.problems] == [("Google Analytics", "failing", "Google Analytics failed: boom")]


def test_a_failure_a_later_success_superseded_is_not(db, client_a):
    _job(db, client_a, "ga4", SyncJobStatus.FAILED, age_hours=30)
    _job(db, client_a, "ga4", SyncJobStatus.SUCCESSFUL, age_hours=2)
    assert build_digest(db, now=NOW).healthy


def test_a_mapped_source_with_no_recent_success_is_stale(db, client_a):
    _map(db, client_a, IntegrationProvider.GSC)
    _job(db, client_a, "gsc_pages", SyncJobStatus.SUCCESSFUL, age_hours=24 * 6)
    digest = build_digest(db, now=NOW)
    assert len(digest.problems) == 1 and digest.problems[0].state == "stalled"
    assert digest.problems[0].source == "Search Console" and "Last success" in digest.problems[0].history


def test_an_unmapped_source_is_a_setup_task_not_a_fault(db, client_a):
    assert build_digest(db, now=NOW).healthy


def test_a_job_working_for_hours_is_stuck(db, client_a):
    _job(db, client_a, "site_crawl", SyncJobStatus.FETCHING, age_hours=5)
    problems = build_digest(db, now=NOW).problems
    assert len(problems) == 1 and problems[0].state == "stuck"


def test_render_names_the_client_and_the_cause(db, client_a):
    _job(db, client_a, "ga4", SyncJobStatus.FAILED, error="boom")
    subject, body = render(build_digest(db, now=NOW), today=date(2026, 10, 15))
    assert "1 to look at" in subject
    assert client_a.client_name in body and "boom" in body and "Google Analytics" in body


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


FORBIDDEN = ("Client error '403 Forbidden' for url 'https://www.googleapis.com/webmasters/v3/sites/https%3A%2F%2Fboyselectrical.com%2F/searchAnalytics/query'\n"
             "For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/403")


def test_two_search_console_jobs_and_a_stale_check_are_one_problem(db, client_a):
    _map(db, client_a, IntegrationProvider.GSC)
    _job(db, client_a, "gsc_pages", SyncJobStatus.FAILED, error=FORBIDDEN)
    _job(db, client_a, "gsc_queries", SyncJobStatus.FAILED, error=FORBIDDEN)
    digest = build_digest(db, now=NOW)
    assert len(digest.problems) == 1
    p = digest.problems[0]
    assert p.what == "Search Console has no access to boyselectrical.com."
    assert p.history == "Never synced successfully." and "Add the connected Google account" in p.fix


def test_a_403_reads_as_an_instruction_not_a_url(db, client_a):
    _job(db, client_a, "gsc_pages", SyncJobStatus.FAILED, error=FORBIDDEN)
    _, body = render(build_digest(db, now=NOW), today=date(2026, 10, 15))
    assert "googleapis" not in body and "mozilla" not in body
    assert "To fix:" in body


def test_a_source_never_set_up_is_not_reported(db, client_a):
    _job(db, client_a, "se_ranking_ai", SyncJobStatus.FAILED, error="No SE Ranking AI engines configured for this project")
    assert build_digest(db, now=NOW).healthy


def test_a_client_with_two_problems_is_listed_once(db, client_a):
    _job(db, client_a, "ga4", SyncJobStatus.FAILED, error="boom")
    _job(db, client_a, "site_crawl", SyncJobStatus.FETCHING, age_hours=5)
    _, body = render(build_digest(db, now=NOW), today=date(2026, 10, 15))
    assert body.count(client_a.client_name) == 1 and "2 things need a look" in body
