"""Multi-GSC primary + secondary properties."""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from app.core.crypto import encrypt_json
from app.ingestion.gsc.fetch import fetch_gsc_pages
from app.ingestion.gsc.publish import publish_gsc_daily, publish_gsc_pages
from app.models.gsc import FactGscDaily, FactGscPage, StagingGscDaily, StagingGscPage
from app.models.integration import ConnectionStatus, Integration, IntegrationProvider
from app.models.job import SyncJob, SyncJobStatus
from tests.conftest import client_header


def _window(days: int = 14):
    end = date.today()
    start = end - timedelta(days=days - 1)
    return start, end


def _connect_gsc(db, client, *, primary: str, secondaries: list[str] | None = None):
    integration = (
        db.query(Integration)
        .filter(Integration.client_id == client.id, Integration.provider == IntegrationProvider.GSC)
        .one()
    )
    integration.connection_status = ConnectionStatus.CONNECTED
    integration.external_property_id = primary
    integration.gsc_secondary_site_urls = list(secondaries or [])
    integration.credentials = encrypt_json({"refresh_token": "rt-test", "token": "at-test"})
    db.commit()
    return integration


def test_save_secondary_gsc_property_via_api(db, client, admin_user, client_a):
    _connect_gsc(db, client_a, primary="sc-domain:new.example")
    headers = client_header(client_a.id, admin_user.email)

    res = client.post(
        "/integrations/gsc/property",
        headers=headers,
        json={"site_url": "sc-domain:old.example", "role": "secondary"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["external_property_id"] == "sc-domain:new.example"
    assert body["gsc_secondary_site_urls"] == ["sc-domain:old.example"]

    dup = client.post(
        "/integrations/gsc/property",
        headers=headers,
        json={"site_url": "sc-domain:new.example", "role": "secondary"},
    )
    assert dup.status_code == 400

    deleted = client.request(
        "DELETE",
        "/integrations/gsc/property",
        headers=headers,
        json={"site_url": "sc-domain:old.example"},
    )
    assert deleted.status_code == 200
    assert deleted.json()["gsc_secondary_site_urls"] == []


def test_publish_primary_wins_daily_and_rewrites_secondary_pages(db, client_a):
    primary = "sc-domain:clienta.example"
    secondary = "sc-domain:legacy.example"
    _connect_gsc(db, client_a, primary=primary, secondaries=[secondary])
    # client_a.domain is clienta.example from fixture naming
    start, end = _window(2)
    job = SyncJob(
        id=uuid4(),
        client_id=client_a.id,
        source="gsc_pages",
        start_date=start,
        end_date=end,
        status=SyncJobStatus.QUEUED,
    )
    db.add(job)
    db.flush()
    db.add_all(
        [
            StagingGscDaily(
                job_id=job.id,
                client_id=client_a.id,
                raw={},
                date=start,
                gsc_site_url=primary,
                impressions=Decimal("100"),
                clicks=Decimal("10"),
                ctr=Decimal("0.1"),
                average_position=Decimal("5"),
            ),
            StagingGscDaily(
                job_id=job.id,
                client_id=client_a.id,
                raw={},
                date=start,
                gsc_site_url=secondary,
                impressions=Decimal("999"),
                clicks=Decimal("99"),
                ctr=Decimal("0.1"),
                average_position=Decimal("20"),
            ),
            StagingGscPage(
                job_id=job.id,
                client_id=client_a.id,
                raw={},
                date=start,
                page="https://legacy.example/services",
                country="usa",
                device="DESKTOP",
                gsc_site_url=secondary,
                impressions=Decimal("50"),
                clicks=Decimal("5"),
                ctr=Decimal("0.1"),
                average_position=Decimal("8"),
            ),
            StagingGscPage(
                job_id=job.id,
                client_id=client_a.id,
                raw={},
                date=start,
                page="https://clienta.example/services",
                country="usa",
                device="DESKTOP",
                gsc_site_url=primary,
                impressions=Decimal("20"),
                clicks=Decimal("2"),
                ctr=Decimal("0.1"),
                average_position=Decimal("4"),
            ),
        ]
    )
    db.commit()

    assert publish_gsc_daily(db, job) == 1
    daily = db.query(FactGscDaily).one()
    assert daily.impressions == Decimal("100")
    assert daily.clicks == Decimal("10")

    assert publish_gsc_pages(db, job) == 1
    page = db.query(FactGscPage).one()
    assert page.normalized_url == "https://clienta.example/services"
    assert page.impressions == Decimal("20")
    assert page.clicks == Decimal("2")


def test_fetch_gsc_pages_queries_primary_and_secondary(db, client_a):
    primary = "https://clienta.example/"
    secondary = "https://legacy.example/"
    _connect_gsc(db, client_a, primary=primary, secondaries=[secondary])
    start, end = _window(1)
    job = SyncJob(
        id=uuid4(),
        client_id=client_a.id,
        source="gsc_pages",
        start_date=start,
        end_date=end,
        status=SyncJobStatus.QUEUED,
    )
    db.add(job)
    db.commit()

    calls: list[str] = []

    def _mock_query(*, site_url, **_kwargs):
        calls.append(site_url)
        return [
            {
                "keys": [start.isoformat(), f"{site_url.rstrip('/')}/page", "usa", "DESKTOP"],
                "clicks": 1,
                "impressions": 10,
                "ctr": 0.1,
                "position": 3,
            }
        ]

    with (
        patch("app.ingestion.gsc.fetch.access_token_for_client", return_value="token"),
        patch("app.ingestion.gsc.fetch.query_search_analytics", side_effect=_mock_query),
    ):
        written = fetch_gsc_pages(db, job)

    assert written == 2
    assert calls == [primary, secondary]
    staged = db.query(StagingGscPage).filter(StagingGscPage.job_id == job.id).all()
    assert {row.gsc_site_url for row in staged} == {primary, secondary}
