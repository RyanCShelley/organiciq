"""Verified source windows for automatic before/after verdicts."""
from datetime import timedelta
from app.models.job import SyncJob, SyncJobStatus


def covers(db, client_id, source, start, end):
    cursor = start
    rows = db.query(SyncJob.start_date, SyncJob.end_date, SyncJob.fact_watermark).filter(
        SyncJob.client_id == client_id, SyncJob.source == source,
        SyncJob.start_date <= end, SyncJob.end_date >= start,
        SyncJob.fact_watermark >= start,
        SyncJob.status.in_((SyncJobStatus.SUCCESSFUL, SyncJobStatus.PARTIAL)),
    ).order_by(SyncJob.start_date).all()
    for first, requested_end, through in rows:
        last = min(requested_end, through, end)
        if last < cursor:
            continue
        if first > cursor:
            return False
        cursor = last + timedelta(days=1)
        if cursor > end:
            return True
    return False


def metric_ready(db, client_id, metric_key, as_of):
    from app.models.integration import Integration, IntegrationProvider
    sources = {'page_clicks': ('gsc_pages', IntegrationProvider.GSC),
               'page_impressions': ('gsc_pages', IntegrationProvider.GSC),
               'page_position': ('gsc_pages', IntegrationProvider.GSC),
               'engagement_rate': ('ga4', IntegrationProvider.GA4),
               'page_lead_rate': ('ga4', IntegrationProvider.GA4)}
    if metric_key not in sources:
        return True
    source, provider = sources[metric_key]
    integration = db.query(Integration).filter_by(client_id=client_id, provider=provider).one_or_none()
    # Manually imported readings have no configured provider extraction.
    if not integration or not integration.external_property_id:
        return True
    return covers(db, client_id, source, as_of - timedelta(days=27), as_of)
