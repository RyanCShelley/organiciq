"""Service contribution from one GA4 page/channel breakdown.

Whole-site headline measurements and their baselines keep their original
scope. Service rows use one disjoint channel classification per observation;
combining enabled services never adds the whole-site headline a second time.
"""
from sqlalchemy import func
from app.models.config import ConversionDefinition, OrganicChannel as Channel
from app.models.ga4 import Ga4NativeChannelObservation as Observation
from app.models.job import SyncJob, SyncJobStatus

ORGANICIQ_CHANNELS = frozenset((Channel.ORGANIC_SEARCH, Channel.AI_REFERRAL,
                              Channel.DIRECT_UNATTRIBUTED, Channel.REFERRAL))
PAID_CHANNELS = frozenset((Channel.PAID_SEARCH, Channel.PAID_SOCIAL, Channel.DISPLAY,
                          Channel.CROSS_NETWORK, Channel.OTHER_PAID))
SERVICE_CHANNELS = {"organiciq": ORGANICIQ_CHANNELS, "ad_accelerator": PAID_CHANNELS}
LABELS = {"organiciq": "OrganicIQ", "ad_accelerator": "Ad Accelerator"}


def has_native_coverage(db, client_id, period):
    if period is None:
        return False
    start, end = period
    covered = db.query(SyncJob.id).filter(SyncJob.client_id == client_id, SyncJob.source == "ga4",
        SyncJob.start_date <= start, SyncJob.end_date >= end, SyncJob.fact_watermark >= end,
        SyncJob.status.in_((SyncJobStatus.SUCCESSFUL, SyncJobStatus.PARTIAL)),
        SyncJob.params_json["ga4_extract"]["native_complete"].astext == "true").first()
    return covered is not None


def _window(db, client, period, names):
    if period is None:
        return {"status": "not_available", "sessions": {}, "lead_events": {}}
    start, end = period
    if not has_native_coverage(db, client.id, period):
        return {"status": "needs_refresh", "sessions": {}, "lead_events": {}}
    rows = db.query(Observation.channel, func.sum(Observation.sessions)).filter(
        Observation.client_id == client.id, Observation.date >= start,
        Observation.date <= end, Observation.event_name == "").group_by(Observation.channel).all()
    events = db.query(Observation.channel, func.sum(Observation.event_count)).filter(
        Observation.client_id == client.id, Observation.date >= start,
        Observation.date <= end, Observation.event_name.in_(names)).group_by(Observation.channel).all() if names else []
    return {"status": "measured", "sessions": {channel: float(count or 0) for channel,count in rows},
            "lead_events": {channel: float(count or 0) for channel,count in events} if names else None}


def _ai_sources(db, client, period, names):
    if not period:
        return []
    start, end = period
    filters = (Observation.client_id == client.id, Observation.date >= start,
               Observation.date <= end, Observation.channel == Channel.AI_REFERRAL)
    rows = db.query(Observation.session_source, func.sum(Observation.sessions),
        func.array_agg(func.distinct(Observation.session_default_channel_group))).filter(
        *filters, Observation.event_name == "").group_by(Observation.session_source).all()
    events = dict(db.query(Observation.session_source, func.sum(Observation.event_count)).filter(
        *filters, Observation.event_name.in_(names)).group_by(Observation.session_source).all()) if names else {}
    return sorted([{"source": source, "sessions": float(count or 0),
        "lead_events": float(events.get(source) or 0) if names else None,
        "google_channels": sorted(group for group in groups if group)} for source,count,groups in rows],
        key=lambda row: (-row["sessions"], row["source"]))


def _metric(current, previous):
    return {"current": current, "previous": previous,
            "change_pct": (current - previous) / previous * 100 if current is not None and previous else None}


def build_service_reporting(db, client, current_period, previous_period):
    settings = client.service_reporting
    if settings is None:
        return {"status": "not_configured", "rows": [], "headline_scope": "whole_site"}
    names = [r[0] for r in db.query(ConversionDefinition.event_name).filter_by(
        client_id=client.id, active=True, conversion_type="lead")]
    current, previous = (_window(db, client, period, names) for period in (current_period, previous_period))
    enabled = [key for key in SERVICE_CHANNELS if settings.get(key) is True]

    def values(window, channels, metric):
        if window["status"] != "measured" or window[metric] is None:
            return None
        return sum(value for channel, value in window[metric].items() if channel in channels)

    def row(key, label, channels):
        return {"key": key, "label": label, "channels": sorted(c.value for c in channels),
            **{metric: _metric(values(current, channels, metric), values(previous, channels, metric))
               for metric in ("sessions", "lead_events")}}

    combined = frozenset().union(*(SERVICE_CHANNELS[key] for key in enabled))
    return {"status": current["status"], "previous_status": previous["status"],
        "headline_scope": "whole_site", "settings": settings,
        "current_period": [str(d) for d in current_period] if current_period else None,
        "previous_period": [str(d) for d in previous_period] if previous_period else None,
        "basis": "ga4_page_channel_breakdown", "mapping_version": "ga4-native-v1",
        "rows": [row(key, LABELS[key], SERVICE_CHANNELS[key]) for key in enabled],
        "combined": row("combined", "Combined agency services", combined),
        "ai_referrals": row("ai_referrals", "AI referrals included in OrganicIQ", frozenset((Channel.AI_REFERRAL,))),
        "ai_sources": _ai_sources(db, client, current_period, names) if current["status"] == "measured" else [],
        "outside_services": row("outside_services", "Outside enabled services", frozenset(Channel)-combined),
        "detail_sessions": _metric(sum(current["sessions"].values()) if current["status"]=="measured" else None,
                                   sum(previous["sessions"].values()) if previous["status"]=="measured" else None),
        "note": "Service visits use the GA4 page/channel breakdown and may sum differently from exact-period whole-site visits. Lead events include repeats. Direct/referral inclusion does not establish agency causation. Existing baselines and targets remain whole-site."}
