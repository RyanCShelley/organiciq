from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from app.core.crypto import encrypt_json
from app.ingestion.channels import classify_channel
from app.ingestion.ga4.pipeline import run_ga4_job
from app.ingestion.ga4.publish import publish_ga4
from app.models.config import ChannelRule, OrganicChannel
from app.models.ga4 import FactGa4Event, FactGa4Traffic, StagingGa4Event, StagingGa4Traffic
from app.models.integration import ConnectionStatus, Integration, IntegrationProvider
from app.models.job import DataWatermark, SyncJob, SyncJobStatus, ValidationStatus


def _window(days: int = 14):
    end = date.today()
    start = end - timedelta(days=days - 1)
    return start, end


def _connect_ga4(db, client):
    integration = (
        db.query(Integration)
        .filter(Integration.client_id == client.id, Integration.provider == IntegrationProvider.GA4)
        .one()
    )
    integration.connection_status = ConnectionStatus.CONNECTED
    integration.external_property_id = "properties/123456"
    integration.credentials = encrypt_json({"refresh_token": "rt-test", "token": "at-test"})
    db.commit()
    return integration


def _seed_channel_rules(db):
    db.add_all(
        [
            ChannelRule(
                match_host_contains="chatgpt",
                channel=OrganicChannel.AI_REFERRAL,
                priority=10,
                active=True,
            ),
            ChannelRule(
                match_source="google",
                match_medium="organic",
                channel=OrganicChannel.ORGANIC_SEARCH,
                priority=20,
                active=True,
            ),
            ChannelRule(
                match_source="google",
                match_medium="cpc",
                channel=OrganicChannel.PAID_SEARCH,
                priority=40,
                active=True,
            ),
        ]
    )
    db.commit()


def _ga4_row(dims: list[str], metrics: list[str]) -> dict:
    return {
        "dimensionValues": [{"value": v} for v in dims],
        "metricValues": [{"value": v} for v in metrics],
    }


def test_direct_is_never_classified_as_organic():
    rules = [
        ChannelRule(
            match_source="(direct)",
            match_medium="(none)",
            channel=OrganicChannel.ORGANIC_SEARCH,
            priority=1,
            active=True,
        )
    ]
    assert classify_channel("(direct)", "(none)", rules) == OrganicChannel.DIRECT_UNATTRIBUTED
    assert classify_channel("direct", "none", rules) == OrganicChannel.DIRECT_UNATTRIBUTED


def test_classify_google_organic_and_ai_host():
    rules = [
        ChannelRule(
            match_host_contains="chatgpt",
            channel=OrganicChannel.AI_REFERRAL,
            priority=10,
            active=True,
        ),
        ChannelRule(
            match_source="google",
            match_medium="organic",
            channel=OrganicChannel.ORGANIC_SEARCH,
            priority=20,
            active=True,
        ),
    ]
    assert classify_channel("google", "organic", rules) == OrganicChannel.ORGANIC_SEARCH
    assert classify_channel("chatgpt.com", "referral", rules) == OrganicChannel.AI_REFERRAL
    assert classify_channel("newsletter", "email", rules) == OrganicChannel.OTHER


def test_ga4_traffic_upsert_idempotent(db, client_a):
    _seed_channel_rules(db)
    start, end = _window(2)
    job = SyncJob(
        id=uuid4(),
        client_id=client_a.id,
        source="ga4",
        start_date=start,
        end_date=end,
        status=SyncJobStatus.QUEUED,
    )
    db.add(job)
    db.flush()
    db.add(
        StagingGa4Traffic(
            job_id=job.id,
            client_id=client_a.id,
            raw={},
            date=start,
            landing_page="/Home/",
            session_source="google",
            session_medium="organic",
            sessions=Decimal("10"),
            active_users=Decimal("8"),
            views=Decimal("20"),
        )
    )
    db.commit()

    assert publish_ga4(db, job) == (1, 0)
    assert publish_ga4(db, job) == (1, 0)
    facts = db.query(FactGa4Traffic).filter(FactGa4Traffic.client_id == client_a.id).all()
    assert len(facts) == 1
    assert facts[0].normalized_url == f"https://{client_a.domain}/home"
    assert facts[0].channel == OrganicChannel.ORGANIC_SEARCH
    assert facts[0].sessions == Decimal("10")


def test_ga4_direct_traffic_is_not_organic(db, client_a):
    _seed_channel_rules(db)
    start, end = _window(2)
    job = SyncJob(
        id=uuid4(),
        client_id=client_a.id,
        source="ga4",
        start_date=start,
        end_date=end,
        status=SyncJobStatus.QUEUED,
    )
    db.add(job)
    db.flush()
    db.add(
        StagingGa4Traffic(
            job_id=job.id,
            client_id=client_a.id,
            raw={},
            date=start,
            landing_page="/",
            session_source="(direct)",
            session_medium="(none)",
            sessions=Decimal("4"),
            active_users=Decimal("4"),
            views=Decimal("4"),
        )
    )
    db.commit()
    publish_ga4(db, job)
    fact = db.query(FactGa4Traffic).one()
    assert fact.channel == OrganicChannel.DIRECT_UNATTRIBUTED


def test_ga4_pipeline_with_mocked_api(db, client_a):
    _connect_ga4(db, client_a)
    _seed_channel_rules(db)
    start, end = _window(3)
    job = SyncJob(
        id=uuid4(),
        client_id=client_a.id,
        source="ga4",
        start_date=start,
        end_date=end,
        status=SyncJobStatus.QUEUED,
    )
    db.add(job)
    db.commit()

    start_key = start.strftime("%Y%m%d")
    end_key = end.strftime("%Y%m%d")
    traffic_rows = [
        _ga4_row([start_key, "/home", "google", "organic"], ["10", "8", "20", "7"]),
        _ga4_row([end_key, "/", "(direct)", "(none)"], ["3", "3", "3", "1"]),
        _ga4_row([start_key, "/ai", "chatgpt.com", "referral"], ["2", "2", "5", "2"]),
    ]
    event_rows = [
        _ga4_row([start_key, "/home", "google", "organic", "generate_lead"], ["2"]),
        _ga4_row([start_key, "/home", "google", "organic", ""], ["9"]),
    ]

    def fake_run_report(*, dimensions, **_kwargs):
        if "eventName" in dimensions:
            return event_rows
        return traffic_rows

    with (
        patch("app.ingestion.ga4.fetch.access_token_for_client", return_value="token"),
        patch("app.ingestion.ga4.fetch.run_report", side_effect=fake_run_report),
    ):
        result = run_ga4_job(db, job)

    assert result.status in {SyncJobStatus.SUCCESSFUL, SyncJobStatus.PARTIAL}
    assert result.validation_status == ValidationStatus.PASSED
    assert result.records_fetched == 5
    traffic = db.query(FactGa4Traffic).filter(FactGa4Traffic.client_id == client_a.id).all()
    assert len(traffic) == 3
    channels = {row.channel for row in traffic}
    assert OrganicChannel.ORGANIC_SEARCH in channels
    assert OrganicChannel.DIRECT_UNATTRIBUTED in channels
    assert OrganicChannel.AI_REFERRAL in channels
    organic = next(row for row in traffic if row.channel == OrganicChannel.ORGANIC_SEARCH)
    assert organic.engaged_sessions == Decimal("7")
    events = db.query(FactGa4Event).filter(FactGa4Event.client_id == client_a.id).all()
    assert len(events) == 1
    assert events[0].event_name == "generate_lead"
    assert events[0].event_count == 2
    wm = (
        db.query(DataWatermark)
        .filter(DataWatermark.client_id == client_a.id, DataWatermark.source == "ga4")
        .one()
    )
    assert wm.fact_through_date is not None
    assert wm.validation_status == ValidationStatus.PASSED
