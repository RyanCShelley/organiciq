"""Read-only GA4 source reconciliation; never publishes facts or changes setup.

Run in the API environment with its existing database and Google connection::

    python -m app.ga4_reconcile --client aquaman-leak-detection --from 2026-09-01 --to 2026-09-30

Use --all-clients explicitly for the active/onboarding roster. Output contains
aggregate differences, not access tokens, visitor identifiers or raw page rows.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import text

from app.core.db import SessionLocal
from app.core.urls import normalize_landing_page, normalize_path_prefix, url_in_scope
from app.ingestion.ga4.client import run_report
from app.ingestion.ga4.fetch import _dim, _metric, _parse_ga4_date
from app.ingestion.ga4.lead_sessions import fetch_lead_session_measurement
from app.ingestion.google_credentials import access_token_for_client
from app.models.client import Client, WORKED_STATUSES
from app.models.config import ConversionDefinition
from app.models.ga4 import FactGa4Event, FactGa4Traffic
from app.models.integration import Integration, IntegrationProvider

TRAFFIC_METRICS = ["sessions", "screenPageViews", "engagedSessions"]


def _source_observations(rows, client, start, end, *, events=False):
    observations = defaultdict(lambda: [Decimal(0)] * (1 if events else 3))
    scope = normalize_path_prefix(client.path_prefix)
    for row in rows:
        if len(row.get("dimensionValues") or []) != (5 if events else 4):
            raise ValueError("Provider dimensions do not match the requested report")
        day = _parse_ga4_date(_dim(row, 0))
        if not start <= day <= end:
            raise ValueError("Provider returned a date outside the requested period")
        url = normalize_landing_page(_dim(row, 1), client.domain)
        if not url_in_scope(url, scope):
            continue
        key = (day, url, _dim(row, 2), _dim(row, 3))
        if events:
            key += (_dim(row, 4),)
        for i in range(1 if events else 3):
            observations[key][i] += _metric(row, i)
    return observations


def _compare(source, stored, metrics):
    expected = defaultdict(lambda: [Decimal(0)] * len(metrics))
    counts = defaultdict(int)
    for key, measures in stored:
        counts[key] += 1
        for i, value in enumerate(measures):
            expected[key][i] += Decimal(value or 0)
    all_keys = set(source) | set(expected)
    return {
        "source_observations": len(source),
        "stored_observations": len(expected),
        "duplicate_channel_keys": sum(count > 1 for count in counts.values()),
        "missing_stored_keys": len(set(source) - set(expected)),
        "stored_keys_absent_from_source": len(set(expected) - set(source)),
        "different_value_keys": sum(
            source.get(key, [Decimal(0)] * len(metrics)) != expected.get(key, [Decimal(0)] * len(metrics))
            for key in all_keys
        ),
        "metrics": {
            metric: {
                "source_extract": float(sum((values[i] for values in source.values()), Decimal(0))),
                "stored": float(sum((values[i] for values in expected.values()), Decimal(0))),
                "stored_minus_source": float(
                    sum((values[i] for values in expected.values()), Decimal(0))
                    - sum((values[i] for values in source.values()), Decimal(0))
                ),
            }
            for i, metric in enumerate(metrics)
        },
    }


def reconcile_client(db, client, start, end, *, include_lead_sessions=False):
    integration = db.query(Integration).filter_by(
        client_id=client.id, provider=IntegrationProvider.GA4
    ).one_or_none()
    if integration is None or not integration.external_property_id:
        return {"client": client.slug, "status": "not_configured"}
    token = access_token_for_client(db, client.id)
    reports = {}
    for name, dimensions, metrics in [
        ("property", [], TRAFFIC_METRICS),
        ("events", ["eventName"], ["eventCount"]),
        ("traffic_extract", ["date", "landingPage", "sessionSource", "sessionMedium"], TRAFFIC_METRICS),
        ("event_extract", ["date", "landingPage", "sessionSource", "sessionMedium", "eventName"], ["eventCount"]),
    ]:
        reports[name] = run_report(access_token=token, property_id=integration.external_property_id,
            start_date=start, end_date=end, dimensions=dimensions, metrics=metrics)
        if not getattr(reports[name], "complete", False):
            raise ValueError("Source report completeness was not verified")
    traffic = _source_observations(reports["traffic_extract"], client, start, end)
    events = _source_observations(reports["event_extract"], client, start, end, events=True)
    lead_names = sorted({row[0] for row in db.query(ConversionDefinition.event_name).filter_by(
        client_id=client.id, active=True, conversion_type="lead").all()})
    stored_traffic = db.query(FactGa4Traffic).filter(FactGa4Traffic.client_id == client.id,
        FactGa4Traffic.date >= start, FactGa4Traffic.date <= end).all()
    stored_events = db.query(FactGa4Event).filter(FactGa4Event.client_id == client.id,
        FactGa4Event.date >= start, FactGa4Event.date <= end).all()
    key = lambda row: (row.date, row.normalized_url, row.session_source, row.session_medium)
    traffic_result = _compare(traffic, [(key(row), [row.sessions, row.views, row.engaged_sessions]) for row in stored_traffic],
        ["sessions", "views", "engaged_sessions"])
    event_result = _compare(events, [(key(row) + (row.event_name,), [row.event_count]) for row in stored_events], ["events"])
    lead_result = _compare({k: v for k, v in events.items() if k[-1] in lead_names},
        [(key(row) + (row.event_name,), [row.event_count]) for row in stored_events if row.event_name in lead_names], ["lead_events"])
    result = {
        "client": client.slug,
        "status": "matches_extract" if all(result["different_value_keys"] == 0 and result["duplicate_channel_keys"] == 0
            and result["missing_stored_keys"] == 0 and result["stored_keys_absent_from_source"] == 0
            for result in [traffic_result, event_result]) else "differences_found",
        "property": integration.external_property_id,
        "period": [start.isoformat(), end.isoformat()], "path_scope": client.path_prefix,
        "client_timezone": client.timezone, "lead_events": lead_names,
        "property_totals_not_folder_scoped": {metric: float(sum((_metric(row, i) for row in reports["property"]), Decimal(0)))
            for i, metric in enumerate(TRAFFIC_METRICS)},
        "property_lead_events_not_folder_scoped": {name: float(sum((_metric(row, 0) for row in reports["events"] if _dim(row, 0) == name), Decimal(0)))
            for name in lead_names},
        "traffic": traffic_result, "events": event_result, "leads": lead_result,
        "unknown_engagement_stored_rows": sum(row.engaged_sessions is None for row in stored_traffic),
        "source_metadata": {name: rows.pages for name, rows in reports.items()},
        "interpretation": "Compare stored facts with the matching extract first. Property-level session estimates can differ from sums of detailed rows. Folder-scoped clients cannot use whole-property totals. Event counts are not converting visits.",
    }

    if include_lead_sessions:
        result["session_lead_measurement"] = fetch_lead_session_measurement(
            access_token=token, property_id=integration.external_property_id,
            start_date=start, end_date=end, lead_events=lead_names, path_prefix=client.path_prefix,
        )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--client")
    selection.add_argument("--all-clients", action="store_true")
    parser.add_argument("--from", dest="start", type=date.fromisoformat, required=True)
    parser.add_argument("--to", dest="end", type=date.fromisoformat, required=True)
    parser.add_argument("--lead-session-check", action="store_true", help="Also measure the union of visits with configured lead events")
    args = parser.parse_args()
    if args.end < args.start:
        parser.error("end date must be on or after start date")
    results = []
    with SessionLocal() as db:
        # Enforced by Postgres, not just by convention. The token helper refreshes
        # in memory and does not persist credentials or enqueue ingestion.
        db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        query = db.query(Client)
        query = query.filter(Client.slug == args.client) if args.client else query.filter(Client.status.in_(WORKED_STATUSES))
        clients = query.order_by(Client.slug).all()
        if not clients:
            parser.error("no matching clients")
        for client in clients:
            try:
                results.append(reconcile_client(db, client, args.start, args.end, include_lead_sessions=args.lead_session_check))
            except Exception as exc:
                # Do not serialize raw provider errors, URLs or authorization data.
                results.append({"client": client.slug, "status": "source_check_failed", "error_type": type(exc).__name__})
        db.rollback()
    print(json.dumps({"checked_at": datetime.now(timezone.utc).isoformat(), "read_only": True, "results": results}, indent=2))
    return 0 if all(row["status"] == "matches_extract" for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
