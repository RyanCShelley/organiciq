"""Shared, exact-period session conversion measurement for dashboard and engine."""
import hashlib
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy.dialects.postgresql import insert
from app.models.config import ConversionDefinition
from app.models.ga4 import Ga4LeadMeasurement
from app.models.integration import Integration, IntegrationProvider
from app.ingestion.google_credentials import access_token_for_client, client_has_google_credentials
from app.ingestion.ga4.lead_sessions import fetch_lead_session_measurement


def session_lead_measurement(db, client, start, end):
    names = sorted({r[0] for r in db.query(ConversionDefinition.event_name).filter_by(
        client_id=client.id, active=True, conversion_type="lead").all()})
    empty = {"basis": "sessions_with_selected_lead_event", "period": [start.isoformat(), end.isoformat()],
        "lead_events": names, "sessions": None, "lead_sessions": None, "conversion_rate_pct": None,
        "channel_scope": "all_channels", "path_scope": client.path_prefix}
    if not names:
        return {**empty, "status": "not_configured"}
    integration = db.query(Integration).filter_by(client_id=client.id, provider=IntegrationProvider.GA4).one_or_none()
    if not integration or not integration.external_property_id:
        return {**empty, "status": "unavailable", "reason": "No GA4 property selected"}
    definition = {"version": 1, "property": integration.external_property_id, "lead_events": names,
        "path_scope": client.path_prefix, "channel_scope": "all_channels", "timezone": client.timezone, "domain": client.domain}
    key = hashlib.sha256(json.dumps(definition, sort_keys=True).encode()).hexdigest()
    snapshot = db.query(Ga4LeadMeasurement).filter_by(client_id=client.id, start_date=start, end_date=end, definition_key=key).one_or_none()
    now = datetime.now(timezone.utc)
    if snapshot and now - snapshot.measured_at < timedelta(hours=24) and (
        not integration.last_successful_sync or snapshot.measured_at >= integration.last_successful_sync
    ):
        return {**snapshot.measurement, "measured_at": snapshot.measured_at.isoformat()}
    if not client_has_google_credentials(db, client.id):
        return {**empty, "status": "unavailable", "reason": "GA4 session conversion measurement is not available"}
    try:
        measurement = fetch_lead_session_measurement(access_token=access_token_for_client(db, client.id),
            property_id=integration.external_property_id, start_date=start, end_date=end,
            lead_events=names, path_prefix=client.path_prefix)
    except Exception:
        # Failed refreshes never become a measured zero or reuse an expired rate.
        return {**empty, "status": "unavailable", "reason": "GA4 session conversion measurement could not be verified; retry after checking the connection"}
    measurement = {**measurement, "property": integration.external_property_id, "definition_key": key}
    db.execute(insert(Ga4LeadMeasurement).values(client_id=client.id, start_date=start, end_date=end,
        definition_key=key, measurement=measurement, measured_at=now).on_conflict_do_update(
            constraint="uq_ga4_lead_measurement_scope", set_={"measurement": measurement, "measured_at": now}))
    db.flush()
    if snapshot is not None:
        db.expire(snapshot)
    return {**measurement, "measured_at": now.isoformat()}
