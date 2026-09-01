from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.ingestion.ga4.client import run_report
from app.ingestion.google_credentials import access_token_for_client
from app.models.ga4 import StagingGa4Event, StagingGa4Traffic
from app.models.integration import Integration, IntegrationProvider
from app.models.job import SyncJob


def _load_ga4_integration(db: Session, client_id: UUID) -> Integration:
    integration = (
        db.query(Integration)
        .filter(
            Integration.client_id == client_id,
            Integration.provider == IntegrationProvider.GA4,
        )
        .one_or_none()
    )
    if integration is None:
        raise RuntimeError("GA4 integration row missing")
    if not integration.credentials:
        raise RuntimeError("GA4 is not connected (missing credentials)")
    if not integration.external_property_id:
        raise RuntimeError("GA4 property is not selected")
    return integration


def _parse_ga4_date(value: str) -> date:
    if len(value) == 8 and value.isdigit():
        return datetime.strptime(value, "%Y%m%d").date()
    return date.fromisoformat(value)


def _dim(row: dict, index: int) -> str:
    values = row.get("dimensionValues") or []
    if index >= len(values):
        return ""
    return str((values[index] or {}).get("value") or "")


def _metric(row: dict, index: int) -> Decimal:
    values = row.get("metricValues") or []
    if index >= len(values):
        return Decimal(0)
    return Decimal(str((values[index] or {}).get("value") or 0))


def fetch_ga4(db: Session, job: SyncJob) -> tuple[int, int]:
    integration = _load_ga4_integration(db, job.client_id)
    token = access_token_for_client(db, job.client_id)
    property_id = integration.external_property_id or ""

    traffic_rows = run_report(
        access_token=token,
        property_id=property_id,
        start_date=job.start_date,
        end_date=job.end_date,
        dimensions=["date", "landingPage", "sessionSource", "sessionMedium"],
        metrics=["sessions", "activeUsers", "screenPageViews"],
    )
    event_rows = run_report(
        access_token=token,
        property_id=property_id,
        start_date=job.start_date,
        end_date=job.end_date,
        dimensions=["date", "landingPage", "sessionSource", "sessionMedium", "eventName"],
        metrics=["eventCount"],
    )

    db.query(StagingGa4Traffic).filter(StagingGa4Traffic.job_id == job.id).delete()
    db.query(StagingGa4Event).filter(StagingGa4Event.job_id == job.id).delete()

    for row in traffic_rows:
        raw_date = _dim(row, 0)
        if not raw_date:
            continue
        db.add(
            StagingGa4Traffic(
                job_id=job.id,
                client_id=job.client_id,
                raw=row,
                date=_parse_ga4_date(raw_date),
                landing_page=_dim(row, 1),
                session_source=_dim(row, 2),
                session_medium=_dim(row, 3),
                sessions=_metric(row, 0),
                active_users=_metric(row, 1),
                views=_metric(row, 2),
            )
        )

    for row in event_rows:
        raw_date = _dim(row, 0)
        event_name = _dim(row, 4)
        if not raw_date or not event_name:
            continue
        db.add(
            StagingGa4Event(
                job_id=job.id,
                client_id=job.client_id,
                raw=row,
                date=_parse_ga4_date(raw_date),
                landing_page=_dim(row, 1),
                session_source=_dim(row, 2),
                session_medium=_dim(row, 3),
                event_name=event_name,
                event_count=int(_metric(row, 0)),
            )
        )
    db.commit()
    return len(traffic_rows), len(event_rows)
