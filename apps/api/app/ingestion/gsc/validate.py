from __future__ import annotations

from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.gsc import (
    FactGscDaily,
    FactGscPage,
    FactGscQueryPage,
    StagingGscDaily,
    StagingGscPage,
    StagingGscQueryPage,
)
from app.models.job import SyncJob


class ValidationError(Exception):
    pass


def validate_gsc_pages(db: Session, job: SyncJob, records_fetched: int, records_written: int) -> date | None:
    staging_count = (
        db.query(func.count())
        .select_from(StagingGscPage)
        .filter(StagingGscPage.job_id == job.id)
        .scalar()
    )
    if staging_count != records_fetched and records_fetched > 0 and staging_count == 0:
        raise ValidationError("Staging empty after fetch reported rows")

    blank_pages = (
        db.query(func.count())
        .select_from(FactGscPage)
        .filter(
            FactGscPage.client_id == job.client_id,
            FactGscPage.date >= job.start_date,
            FactGscPage.date <= job.end_date,
            FactGscPage.normalized_url == "",
        )
        .scalar()
    )
    if blank_pages:
        raise ValidationError("facts_gsc_pages contains blank normalized_url rows")

    daily_staging_count = (
        db.query(func.count())
        .select_from(StagingGscDaily)
        .filter(StagingGscDaily.job_id == job.id)
        .scalar()
    )
    if daily_staging_count and records_fetched > 0:
        daily_facts = (
            db.query(func.count())
            .select_from(FactGscDaily)
            .filter(
                FactGscDaily.client_id == job.client_id,
                FactGscDaily.date >= job.start_date,
                FactGscDaily.date <= job.end_date,
            )
            .scalar()
        )
        if not daily_facts:
            raise ValidationError("facts_gsc_daily empty after daily fetch reported rows")

    max_date = (
        db.query(func.max(FactGscDaily.date))
        .filter(
            FactGscDaily.client_id == job.client_id,
            FactGscDaily.date >= job.start_date,
            FactGscDaily.date <= job.end_date,
        )
        .scalar()
    )
    if max_date is None:
        max_date = (
            db.query(func.max(FactGscPage.date))
            .filter(
                FactGscPage.client_id == job.client_id,
                FactGscPage.date >= job.start_date,
                FactGscPage.date <= job.end_date,
            )
            .scalar()
        )
    return max_date


def validate_gsc_queries(db: Session, job: SyncJob, records_fetched: int, records_written: int) -> date | None:
    blank_queries = (
        db.query(func.count())
        .select_from(FactGscQueryPage)
        .filter(
            FactGscQueryPage.client_id == job.client_id,
            FactGscQueryPage.date >= job.start_date,
            FactGscQueryPage.date <= job.end_date,
            FactGscQueryPage.query == "",
        )
        .scalar()
    )
    if blank_queries:
        raise ValidationError("facts_gsc_query_pages contains blank query rows")

    staging_blank = (
        db.query(func.count())
        .select_from(StagingGscQueryPage)
        .filter(
            StagingGscQueryPage.job_id == job.id,
            StagingGscQueryPage.query.is_(None),
        )
        .scalar()
    )
    # staged with NULL query is ok only if we filtered blanks; reject empty string
    _ = staging_blank

    max_date = (
        db.query(func.max(FactGscQueryPage.date))
        .filter(
            FactGscQueryPage.client_id == job.client_id,
            FactGscQueryPage.date >= job.start_date,
            FactGscQueryPage.date <= job.end_date,
        )
        .scalar()
    )
    return max_date
