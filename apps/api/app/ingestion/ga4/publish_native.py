"""Publish the independently queried native-channel report transactionally."""
from decimal import Decimal
import hashlib
import json
from sqlalchemy.dialects.postgresql import insert
from app.core.urls import normalize_landing_page, normalize_path_prefix, url_in_scope
from app.ingestion.channels import classify_channel
from app.models.ga4 import Ga4NativeChannelObservation, StagingGa4Traffic, StagingGa4Event

GRAIN = ("client_id", "date", "normalized_url", "session_source", "session_medium", "session_default_channel_group", "event_name")


def publish_native_channels(db, job, client, rules):
    manifest = (job.params_json or {}).get("ga4_extract") or {}
    if not manifest.get("native_complete"):
        return 0, 0
    traffic = db.query(StagingGa4Traffic).filter_by(job_id=job.id, client_id=job.client_id, report_basis="native").all()
    events = db.query(StagingGa4Event).filter_by(job_id=job.id, client_id=job.client_id, report_basis="native").all()
    if (not manifest.get("complete") or manifest.get("start") != str(job.start_date)
            or manifest.get("end") != str(job.end_date) or manifest.get("native_traffic_rows") != len(traffic)
            or manifest.get("native_event_rows") != len(events)):
        raise ValueError("Native GA4 report manifest does not match staged rows")
    rule_definition = [{"channel": r.channel.value, "source": r.match_source, "medium": r.match_medium,
        "host": r.match_host_contains, "priority": r.priority, "active": r.active} for r in sorted(rules, key=lambda r: (r.priority, str(r.id)))]
    rule_key = hashlib.sha256(json.dumps(rule_definition, sort_keys=True).encode()).hexdigest()[:12]
    mapping_version = "ga4-native-v1:" + rule_key
    job.params_json = {**(job.params_json or {}), "ga4_extract": {**manifest,
        "native_mapping_version": mapping_version, "native_channel_rules": rule_definition}}
    payloads = []
    scope = normalize_path_prefix(client.path_prefix)
    for is_event, rows in ((False, traffic), (True, events)):
        for row in rows:
            if row.date is None or not job.start_date <= row.date <= job.end_date:
                raise ValueError("Native GA4 row is outside the requested window")
            url = normalize_landing_page(row.landing_page or "", client.domain)
            if not url_in_scope(url, scope):
                continue
            payloads.append(dict(client_id=client.id, date=row.date, raw_url=row.landing_page or "",
                normalized_url=url, session_source=row.session_source or "", session_medium=row.session_medium or "",
                session_default_channel_group=row.session_default_channel_group or "",
                channel=classify_channel(row.session_source, row.session_medium, rules, row.session_default_channel_group),
                channel_rule_version=mapping_version, event_name=row.event_name if is_event else "",
                sessions=None if is_event else row.sessions or Decimal(0), active_users=None if is_event else row.active_users,
                views=None if is_event else row.views, engaged_sessions=None if is_event else row.engaged_sessions,
                event_count=row.event_count if is_event else None))
    from app.ingestion.ga4.publish import _merge_on_grain, _chunked
    payloads = _merge_on_grain(payloads, GRAIN, ("sessions", "active_users", "views", "engaged_sessions", "event_count"))
    db.query(Ga4NativeChannelObservation).filter(Ga4NativeChannelObservation.client_id == client.id,
        Ga4NativeChannelObservation.date >= job.start_date, Ga4NativeChannelObservation.date <= job.end_date).delete(synchronize_session=False)
    for batch in _chunked(payloads, 1000):
        statement = insert(Ga4NativeChannelObservation).values(batch)
        db.execute(statement.on_conflict_do_update(constraint="uq_ga4_native_channel_grain",
            set_={name: getattr(statement.excluded, name) for name in ("channel", "raw_url", "channel_rule_version", "sessions", "active_users", "views", "engaged_sessions", "event_count")}))
    return sum(not row["event_name"] for row in payloads), sum(bool(row["event_name"]) for row in payloads)
