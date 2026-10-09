"""Run the engine for a month and save the record.

The page reads the saved record and never recomputes. That is the whole point
of saving it: a run is a thing that happened on a date, with the data it had,
and a reader comparing this month to last is comparing two decisions rather
than two recalculations.

The record is built to `monthly-record.schema.json`, which the client page
renders field for field.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.decisions.triage import (
    WITHHELD,
    Branch,
    Status,
    Triage,
    assess_leads,
    assess_traffic,
    assess_visibility,
    select_constraint,
    summarise_branch,
)
from app.decisions.thresholds import merge_thresholds
from app.models.annotation import Annotation
from app.models.client import Client
from app.decisions.overrides import Exclusion
from app.models.decision import ConstraintOverride, ExcludedPage, MonthlyRecord
from app.models.gsc import FactGscPage
from app.models.ga4 import FactGa4Traffic
from app.services.plan_allowances import resolve_plan_allowances
from app.services.triage_signals import lead_signals, traffic_signals, visibility_signals

logger = logging.getLogger("organiciq.monthly_run")

#: A source older than this and the run is withheld rather than served. Acting
#: on numbers that stopped updating is worse than acting on none.
STALE_DAYS = 7

#: A relaunch, migration or domain change inside this window forces Visibility.
RELAUNCH_WINDOW_DAYS = 180

#: Words in an annotation that mean the site changed underneath its rankings.
RELAUNCH_WORDS = ("relaunch", "migration", "migrated", "redesign", "domain change")


def month_key(when: date) -> str:
    return f"{when.year:04d}-{when.month:02d}"


def _previous_month(key: str) -> str:
    year, month = (int(part) for part in key.split("-"))
    return f"{year - 1:04d}-12" if month == 1 else f"{year:04d}-{month - 1:02d}"


def _last_fact(db: Session, model, column, client_id: UUID) -> date | None:
    return (
        db.query(func.max(column)).filter(model.client_id == client_id).scalar()
    )


def _stale_reason(db: Session, client: Client, today: date) -> str | None:
    """Which source stopped reporting, if any.

    Read from the facts rather than the watermarks. A watermark is a claim
    about what was fetched, and a watermark that advanced past data that was
    never there is what hid a broken Search Console sync for fifteen days.
    """
    for label, model, column in (
        ("Search Console", FactGscPage, FactGscPage.date),
        ("GA4", FactGa4Traffic, FactGa4Traffic.date),
    ):
        newest = _last_fact(db, model, column, client.id)
        if newest is None:
            return f"No {label} data at all for this client."
        age = (today - newest).days
        if age > STALE_DAYS:
            return (
                f"{label} data is {age} days stale — newest day on record is "
                f"{newest.isoformat()}. Nothing is served off numbers that "
                "stopped updating."
            )
    return None


def _relaunched_recently(db: Session, client: Client, today: date) -> bool:
    since = today - timedelta(days=RELAUNCH_WINDOW_DAYS)
    rows = (
        db.query(Annotation)
        .filter(Annotation.client_id == client.id, Annotation.date >= since)
        .all()
    )
    for row in rows:
        text = (row.description or "").lower()
        if any(word in text for word in RELAUNCH_WORDS):
            return True
    return False


def _confidence(triage: Triage, *, blocked_inputs: list[str]) -> tuple[str, list[dict]]:
    """High, medium or low, and what to check before assigning.

    A blocked test is a missing input, and a run with missing inputs is not a
    run anyone should act on without being told which.
    """
    reasons = [
        {"code": "missing_input", "text": text} for text in sorted(set(blocked_inputs))
    ]
    if triage.constraint == WITHHELD:
        return "low", reasons
    if len(reasons) >= 3:
        return "low", reasons
    if reasons:
        return "medium", reasons
    return "high", reasons


def _held_since(db: Session, client: Client, month: str, constraint: str) -> str:
    """The month this constraint was first named.

    Without it the two-month hold cannot exist, and the page cannot say "month
    two" — which is the difference between a client being worked on and a
    client being rediscovered every month.
    """
    previous = (
        db.query(MonthlyRecord)
        .filter(
            MonthlyRecord.client_id == client.id,
            MonthlyRecord.month == _previous_month(month),
        )
        .one_or_none()
    )
    if previous is not None and previous.constraint_name == constraint:
        return previous.held_since
    return month


def load_exclusions(db: Session, client: Client) -> list[Exclusion]:
    return [
        Exclusion(url_pattern=row.url_pattern, reason=row.reason)
        for row in db.query(ExcludedPage).filter(ExcludedPage.client_id == client.id)
    ]


def load_override(db: Session, client: Client, month: str) -> ConstraintOverride | None:
    return (
        db.query(ConstraintOverride)
        .filter(
            ConstraintOverride.client_id == client.id,
            ConstraintOverride.month == month,
        )
        .one_or_none()
    )


def build_record(
    db: Session, client: Client, *, today: date | None = None
) -> dict:
    """Run Decision 1 and return the record, without saving it."""
    today = today or date.today()
    month = month_key(today)
    thresholds = merge_thresholds(getattr(client, "decision_thresholds", None))

    gsc_newest = _last_fact(db, FactGscPage, FactGscPage.date, client.id)
    gsc_period = (today - timedelta(days=29), gsc_newest) if gsc_newest else None
    ai_period = (today - timedelta(days=29), today)

    branches = [
        summarise_branch(
            Branch.VISIBILITY,
            assess_visibility(
                visibility_signals(db, client, today=today, ai_period=ai_period),
                thresholds=thresholds,
            ),
        ),
        summarise_branch(
            Branch.TRAFFIC,
            assess_traffic(
                traffic_signals(db, client, today=today, gsc_period=gsc_period),
                thresholds=thresholds,
            ),
        ),
        summarise_branch(
            Branch.LEADS,
            assess_leads(lead_signals(db, client, today=today), thresholds=thresholds),
        ),
    ]

    triage = select_constraint(
        branches,
        relaunch_within_180d=_relaunched_recently(db, client, today),
        withheld_reason=_stale_reason(db, client, today),
    )

    # Somebody overruled it. The branches keep the statuses the tests
    # produced — the override changes which one gets the slots, not what the
    # numbers said, because a record that rewrote the evidence to match the
    # decision would be unreadable a month later.
    override = load_override(db, client, month)
    engine_said = triage.constraint
    if override is not None and triage.constraint != WITHHELD:
        triage = Triage(
            constraint=override.constraint_name,
            reason_text=override.reason,
            branches=triage.branches,
            override="manual",
        )

    blocked_inputs = [
        test.missing
        for branch in branches
        for test in branch.tests
        if test.status is Status.BLOCKED and test.missing
    ]
    confidence, confidence_reasons = _confidence(triage, blocked_inputs=blocked_inputs)

    exclusions = load_exclusions(db, client)
    allowances = resolve_plan_allowances(client, getattr(client, "tier", None))
    slots = 0 if triage.constraint == WITHHELD else allowances.growth_action_allowance

    return {
        "client": client.slug,
        "client_name": client.client_name,
        "domain": client.domain,
        "month": month,
        "run_saved_at": datetime.now(timezone.utc).isoformat(),
        "data_through": gsc_newest.isoformat() if gsc_newest else None,
        "plan": (allowances.tier_name or "launch").lower(),
        "action_slots": slots,
        "constraint": triage.constraint,
        "reason_text": triage.reason_text,
        "override": triage.override,
        # What the tests produced, kept beside what a person chose. A record
        # that showed only the override could not be read back as a
        # disagreement, and the disagreement is the interesting part.
        **(
            {
                "engine_constraint": engine_said,
                "override_reason": override.reason,
            }
            if override is not None and triage.override == "manual"
            else {}
        ),
        "held_since": _held_since(db, client, month, triage.constraint),
        "confidence": confidence,
        "confidence_reasons": confidence_reasons,
        "branches": [
            {
                "branch": branch.branch.value,
                "status": branch.status.value,
                "headline_test": branch.headline_test,
                "display": branch.display,
                "missing": list(branch.missing),
                "tests": [
                    {
                        "id": test.id,
                        "name": test.name,
                        "metric_label": test.metric_label,
                        "value": test.value,
                        "pass_line": test.pass_line,
                        "direction": test.direction,
                        "unit": test.unit,
                        "status": test.status.value,
                        **({"display": test.display} if test.display else {}),
                        **({"missing": test.missing} if test.missing else {}),
                    }
                    for test in branch.tests
                ],
            }
            for branch in triage.branches
        ],
        # Decisions 2 and 3 fill these. The keys are present from the start so
        # the page binds against one shape rather than two.
        "actions": [],
        "empty_slots": [],
        "incidents": [],
        "not_this_month": [],
        "data_gaps": [
            {"input": text, "status": "missing"} for text in sorted(set(blocked_inputs))
        ],
        "previous_results": [],
        "excluded_pages": [
            {"url_pattern": x.url_pattern, "reason": x.reason} for x in exclusions
        ],
    }


def save_record(db: Session, client: Client, *, today: date | None = None) -> MonthlyRecord:
    """Run the engine and store the month's record, replacing any earlier one.

    One plan a month: re-running corrects this month's answer rather than
    adding a second one. Workflow state lives in `engine_actions`, keyed by a
    uid that survives the replacement, so an assignment made before a re-run
    is not lost by it.
    """
    today = today or date.today()
    record = build_record(db, client, today=today)
    month = record["month"]

    existing = (
        db.query(MonthlyRecord)
        .filter(MonthlyRecord.client_id == client.id, MonthlyRecord.month == month)
        .one_or_none()
    )
    if existing is None:
        existing = MonthlyRecord(id=uuid4(), client_id=client.id, month=month)
        db.add(existing)

    existing.run_saved_at = datetime.now(timezone.utc)
    existing.data_through = (
        date.fromisoformat(record["data_through"]) if record["data_through"] else None
    )
    existing.constraint_name = record["constraint"]
    existing.held_since = record["held_since"]
    existing.confidence = record["confidence"]
    existing.record = record
    db.commit()
    db.refresh(existing)
    logger.info(
        "%s %s: %s (%s confidence)",
        client.slug, month, record["constraint"], record["confidence"],
    )
    return existing


def latest_record(db: Session, client: Client) -> MonthlyRecord | None:
    return (
        db.query(MonthlyRecord)
        .filter(MonthlyRecord.client_id == client.id)
        .order_by(MonthlyRecord.month.desc())
        .first()
    )
