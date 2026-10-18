from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.ingestion.ga4.client import run_report
from app.ingestion.google_credentials import access_token_for_client, client_has_google_credentials
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
    if not client_has_google_credentials(db, client_id):
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


def _validate_report_rows(rows: list[dict], *, dimensions: int, metrics: int) -> None:
    for row in rows:
        if len(row.get("dimensionValues") or []) != dimensions or not _dim(row, 0):
            raise ValueError("GA4 report dimensions are incomplete")
        values = row.get("metricValues") or []
        if len(values) != metrics or any(value.get("value") in (None, "") for value in values):
            raise ValueError("GA4 report metrics are incomplete")
        for i in range(metrics):
            value = _metric(row, i)
            if not value.is_finite() or value < 0 or value != value.to_integral_value():
                raise ValueError("GA4 report count metric is invalid")


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
        metrics=["sessions", "activeUsers", "screenPageViews", "engagedSessions"],
    )
    event_rows = run_report(
        access_token=token,
        property_id=property_id,
        start_date=job.start_date,
        end_date=job.end_date,
        dimensions=["date", "landingPage", "sessionSource", "sessionMedium", "eventName"],
        metrics=["eventCount"],
    )

    # Service reporting is opt-in per client. Existing whole-site report grain
    # stays unchanged, so native dimensions cannot restate baseline inputs.
    from app.models.client import Client
    client = db.get(Client, job.client_id)
    native_traffic, native_events = [], []
    native_enabled = client.service_reporting is not None
    if native_enabled:
        native_traffic = run_report(access_token=token, property_id=property_id,
            start_date=job.start_date, end_date=job.end_date,
            dimensions=["date", "landingPage", "sessionSource", "sessionMedium", "sessionDefaultChannelGroup"],
            metrics=["sessions", "activeUsers", "screenPageViews", "engagedSessions"])
        native_events = run_report(access_token=token, property_id=property_id,
            start_date=job.start_date, end_date=job.end_date,
            dimensions=["date", "landingPage", "sessionSource", "sessionMedium", "eventName", "sessionDefaultChannelGroup"],
            metrics=["eventCount"])
        if not (getattr(native_traffic, "complete", False) and getattr(native_events, "complete", False)):
            raise ValueError("Native GA4 channel reports were not verified complete")
        _validate_report_rows(native_traffic, dimensions=5, metrics=4)
        _validate_report_rows(native_events, dimensions=6, metrics=1)
        if any(not _dim(row, 4) for row in native_events):
            raise ValueError("Native GA4 event name is missing")

    complete = bool(getattr(traffic_rows, "complete", False) and getattr(event_rows, "complete", False))
    if complete:
        _validate_report_rows(traffic_rows, dimensions=4, metrics=4)
        _validate_report_rows(event_rows, dimensions=5, metrics=1)
        if any(not _dim(row, 4) for row in event_rows):
            raise ValueError("GA4 event name is missing")

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
                engaged_sessions=_metric(row, 3),
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
    for row in native_traffic:
        db.add(StagingGa4Traffic(job_id=job.id, client_id=job.client_id, raw=row,
            date=_parse_ga4_date(_dim(row, 0)), landing_page=_dim(row, 1),
            session_source=_dim(row, 2), session_medium=_dim(row, 3),
            session_default_channel_group=_dim(row, 4), report_basis="native",
            sessions=_metric(row, 0), active_users=_metric(row, 1), views=_metric(row, 2), engaged_sessions=_metric(row, 3)))
    for row in native_events:
        db.add(StagingGa4Event(job_id=job.id, client_id=job.client_id, raw=row,
            date=_parse_ga4_date(_dim(row, 0)), landing_page=_dim(row, 1),
            session_source=_dim(row, 2), session_medium=_dim(row, 3),
            event_name=_dim(row, 4), session_default_channel_group=_dim(row, 5),
            report_basis="native", event_count=int(_metric(row, 0))))
    job.params_json = {**(job.params_json or {}), "ga4_extract": {
        "complete": complete, "start": job.start_date.isoformat(), "end": job.end_date.isoformat(),
        "property": property_id, "native_complete": native_enabled, "native_traffic_rows": len(native_traffic),
        "native_event_rows": len(native_events), "native_traffic_pages": getattr(native_traffic, "pages", []),
        "native_event_pages": getattr(native_events, "pages", []), "traffic_rows": len(traffic_rows), "event_rows": len(event_rows),
        "traffic_pages": getattr(traffic_rows, "pages", []), "event_pages": getattr(event_rows, "pages", []),
    }}
    db.commit()
    return len(traffic_rows) + len(native_traffic), len(event_rows) + len(native_events)
