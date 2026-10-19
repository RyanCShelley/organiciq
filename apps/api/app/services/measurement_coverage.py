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
