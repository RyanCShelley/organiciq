"""Drop staging rows once they have been published to facts.

Staging tables hold the raw API payload for one job. Each fetch clears rows for
its *own* job id, but job ids are unique, so nothing ever removed a previous
run's rows — every staging table grew without bound while only ever being read
once, immediately after the fetch that wrote it.

`staging_gsc_query_pages` dominates: its grain is date x query x page x country
x device and every row also carries the full JSON response in `raw`.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.crawl import StagingSerAuditIssue, StagingSerAuditPage
from app.models.ga4 import StagingGa4Event, StagingGa4Traffic
from app.models.gsc import StagingGscDaily, StagingGscPage, StagingGscQueryPage
from app.models.seranking import (
    StagingSerAiCheck,
    StagingSerAiPresence,
    StagingSerAiPrompt,
    StagingSerAiTrackerStats,
    StagingSerCompetitor,
    StagingSerKeyword,
    StagingSerPosition,
    StagingSerSiteSummary,
)

logger = logging.getLogger("organiciq.staging")

# Every staging model, keyed by the job source that writes it. A job only ever
# populates its own tables, so a wrong entry costs nothing but a no-op delete.
_STAGING_BY_SOURCE: dict[str, tuple[type, ...]] = {
    "gsc_pages": (StagingGscPage, StagingGscDaily),
    "gsc_queries": (StagingGscQueryPage,),
    "ga4": (StagingGa4Traffic, StagingGa4Event),
    "se_ranking_search": (
        StagingSerKeyword,
        StagingSerPosition,
        StagingSerCompetitor,
        StagingSerSiteSummary,
    ),
    "se_ranking_ai": (
        StagingSerAiPrompt,
        StagingSerAiCheck,
        StagingSerAiPresence,
        StagingSerAiTrackerStats,
    ),
    "se_ranking_audit": (StagingSerAuditPage, StagingSerAuditIssue),
}


def purge_staging_for_job(db: Session, *, job_id: UUID, source: str) -> int:
    """
    Delete this job's staging rows. Returns rows removed.

    Called after a successful publish. Never raises: losing the cleanup is a
    storage problem, but failing the job here would discard a good sync.
    """
    models = _STAGING_BY_SOURCE.get(source)
    if not models:
        return 0

    removed = 0
    try:
        for model in models:
            removed += (
                db.query(model)
                .filter(model.job_id == job_id)
                .delete(synchronize_session=False)
            )
        db.commit()
    except Exception:  # noqa: BLE001 — cleanup must not fail a successful job
        db.rollback()
        logger.exception("Staging purge failed for job=%s source=%s", job_id, source)
        return 0
    return removed
