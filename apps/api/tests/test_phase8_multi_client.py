"""Phase 8 — multi-client isolation, mappings, and independent sync jobs."""

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from app.models.gsc import FactGscDaily
from app.models.integration import ConnectionStatus, IntegrationProvider
from app.models.job import DataWatermark, SyncJob, SyncJobStatus, ValidationStatus
from app.services.data_health import load_client_data_health
from tests.conftest import auth_header, client_header, date_window


def _watermark(db, client_id, source: str, fact_through: date) -> None:
    db.add(
        DataWatermark(
            id=uuid4(),
            client_id=client_id,
            source=source,
            fact_through_date=fact_through,
            validation_status=ValidationStatus.PASSED,
        )
    )


def test_two_clients_can_enqueue_same_source(db, client, admin_user, client_a, client_b):
    start, end = date_window(14)
    payload = {
        "source": "gsc_pages",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
    }
    res_a = client.post("/jobs", headers=client_header(client_a.id, admin_user.email), json=payload)
    res_b = client.post("/jobs", headers=client_header(client_b.id, admin_user.email), json=payload)
    assert res_a.status_code == 201
    assert res_b.status_code == 201
    assert res_a.json()["client_id"] == str(client_a.id)
    assert res_b.json()["client_id"] == str(client_b.id)


def test_gsc_daily_facts_are_client_isolated(db, client_a, client_b):
    day = date(2026, 8, 1)
    db.add_all(
        [
            FactGscDaily(
                id=uuid4(),
                client_id=client_a.id,
                date=day,
                impressions=Decimal("100"),
                clicks=Decimal("5"),
                ctr=Decimal("0.05"),
                average_position=Decimal("10"),
            ),
            FactGscDaily(
                id=uuid4(),
                client_id=client_b.id,
                date=day,
                impressions=Decimal("200"),
                clicks=Decimal("20"),
                ctr=Decimal("0.1"),
                average_position=Decimal("8"),
            ),
        ]
    )
    db.commit()

    a_rows = db.query(FactGscDaily).filter(FactGscDaily.client_id == client_a.id).all()
    b_rows = db.query(FactGscDaily).filter(FactGscDaily.client_id == client_b.id).all()
    assert len(a_rows) == 1
    assert len(b_rows) == 1
    assert a_rows[0].clicks == Decimal("5")
    assert b_rows[0].clicks == Decimal("20")


def test_watermarks_and_data_health_are_client_scoped(db, client_a, client_b):
    end = date(2026, 8, 29)
    beacon_end = end - timedelta(days=5)
    _watermark(db, client_a.id, "gsc_pages", end)
    _watermark(db, client_b.id, "gsc_pages", beacon_end)
    db.commit()

    health_a = {row["source"]: row for row in load_client_data_health(db, client_a.id)}
    health_b = {row["source"]: row for row in load_client_data_health(db, client_b.id)}
    assert health_a["gsc_pages"]["fact_through"] == end.isoformat()
    assert health_b["gsc_pages"]["fact_through"] == beacon_end.isoformat()


def test_integration_mappings_are_independent(db, client, admin_user, client_a, client_b):
    from app.models.integration import Integration

    gsc_a = (
        db.query(Integration)
        .filter(Integration.client_id == client_a.id, Integration.provider == IntegrationProvider.GSC)
        .one()
    )
    gsc_b = (
        db.query(Integration)
        .filter(Integration.client_id == client_b.id, Integration.provider == IntegrationProvider.GSC)
        .one()
    )
    gsc_a.connection_status = ConnectionStatus.CONNECTED
    gsc_a.external_property_id = "sc-domain:client-a.example"
    gsc_b.connection_status = ConnectionStatus.CONNECTED
    gsc_b.external_property_id = "sc-domain:client-b.example"
    db.commit()

    res_a = client.get("/integrations", headers=client_header(client_a.id, admin_user.email))
    res_b = client.get("/integrations", headers=client_header(client_b.id, admin_user.email))
    by_provider_a = {row["provider"]: row for row in res_a.json()}
    by_provider_b = {row["provider"]: row for row in res_b.json()}
    assert by_provider_a["gsc"]["external_property_id"] == "sc-domain:client-a.example"
    assert by_provider_b["gsc"]["external_property_id"] == "sc-domain:client-b.example"


def test_team_user_only_sees_assigned_client_jobs(db, client, team_user, client_a, client_b, admin_user):
    start, end = date_window(7)
    client.post(
        "/jobs",
        headers=client_header(client_b.id, admin_user.email),
        json={"source": "ga4", "start_date": start.isoformat(), "end_date": end.isoformat()},
    )
    db.commit()

    team_jobs = client.get("/jobs", headers=client_header(client_a.id, team_user.email))
    assert team_jobs.status_code == 200
    assert all(row["client_id"] == str(client_a.id) for row in team_jobs.json())

    blocked = client.get("/jobs", headers=client_header(client_b.id, team_user.email))
    assert blocked.status_code == 403


def test_completed_jobs_remain_client_scoped(db, client_a, client_b):
    start, end = date_window(7)
    db.add_all(
        [
            SyncJob(
                id=uuid4(),
                client_id=client_a.id,
                source="gsc_pages",
                start_date=start,
                end_date=end,
                status=SyncJobStatus.SUCCESSFUL,
            ),
            SyncJob(
                id=uuid4(),
                client_id=client_b.id,
                source="gsc_pages",
                start_date=start,
                end_date=end,
                status=SyncJobStatus.SUCCESSFUL,
            ),
        ]
    )
    db.commit()

    a_count = db.query(SyncJob).filter(SyncJob.client_id == client_a.id).count()
    b_count = db.query(SyncJob).filter(SyncJob.client_id == client_b.id).count()
    assert a_count == 1
    assert b_count == 1


def test_admin_lists_both_seed_clients(db, client, admin_user, client_a, client_b):
    res = client.get("/clients", headers=auth_header(admin_user.email))
    assert res.status_code == 200
    names = {row["client_name"] for row in res.json()}
    assert "Client A" in names
    assert "Client B" in names
