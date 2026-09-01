from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy.orm import Session

from app.decisions.engine import DecisionDraft, evaluate_decision_drafts
from app.decisions.thresholds import DEFAULT_DECISION_THRESHOLDS, merge_thresholds
from app.models.client import Client
from app.models.decision import Decision, DecisionStatus, DecisionThreshold


def get_thresholds(db: Session, client_id: UUID) -> dict[str, float | int]:
    row = db.query(DecisionThreshold).filter(DecisionThreshold.client_id == client_id).one_or_none()
    if row is None:
        return merge_thresholds(None)
    return merge_thresholds(row.thresholds)


def upsert_thresholds(db: Session, client_id: UUID, overrides: dict) -> dict[str, float | int]:
    row = db.query(DecisionThreshold).filter(DecisionThreshold.client_id == client_id).one_or_none()
    existing = row.thresholds if row is not None else None
    merged = merge_thresholds({**(existing or {}), **overrides})
    if row is None:
        row = DecisionThreshold(client_id=client_id, thresholds=merged)
        db.add(row)
    else:
        row.thresholds = merged
    db.commit()
    return merged


def list_decisions(
    db: Session,
    client_id: UUID,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    status: DecisionStatus | None = None,
    limit: int = 100,
) -> list[Decision]:
    query = db.query(Decision).filter(Decision.client_id == client_id)
    if from_date is not None:
        query = query.filter(Decision.date_range_start >= from_date)
    if to_date is not None:
        query = query.filter(Decision.date_range_end <= to_date)
    if status is not None:
        query = query.filter(Decision.status == status)
    return (
        query.order_by(
            Decision.priority.desc(),
            Decision.created_at.desc(),
        )
        .limit(limit)
        .all()
    )


def _draft_to_model(client_id: UUID, draft: DecisionDraft, from_date: date, to_date: date) -> Decision:
    return Decision(
        client_id=client_id,
        rule_key=draft.rule_key,
        decision_type=draft.decision_type,
        growth_action=draft.growth_action,
        diagnostic_layer=draft.diagnostic_layer,
        priority=draft.priority,
        status=DecisionStatus.NEW,
        page_url=draft.page_url,
        query=draft.query,
        keyword=draft.keyword,
        prompt=draft.prompt,
        diagnosis=draft.diagnosis,
        recommended_action=draft.recommended_action,
        evidence_json=draft.evidence_json,
        baseline_metrics_json=draft.baseline_metrics_json,
        success_metric=draft.success_metric,
        date_range_start=from_date,
        date_range_end=to_date,
    )


def evaluate_and_store(
    db: Session,
    client: Client,
    *,
    from_date: date,
    to_date: date,
) -> tuple[list[Decision], int]:
    thresholds = get_thresholds(db, client.id)
    drafts = evaluate_decision_drafts(
        db,
        client_id=client.id,
        from_date=from_date,
        to_date=to_date,
        threshold_overrides=thresholds,
    )

    created: list[Decision] = []
    skipped = 0
    for draft in drafts:
        existing = (
            db.query(Decision)
            .filter(
                Decision.client_id == client.id,
                Decision.rule_key == draft.rule_key,
                Decision.date_range_start == from_date,
                Decision.date_range_end == to_date,
            )
            .one_or_none()
        )
        if existing is not None:
            skipped += 1
            continue
        decision = _draft_to_model(client.id, draft, from_date, to_date)
        db.add(decision)
        created.append(decision)

    db.commit()
    for decision in created:
        db.refresh(decision)
    return created, skipped


def update_decision_status(
    db: Session,
    *,
    client_id: UUID,
    decision_id: UUID,
    status: DecisionStatus,
    dismissal_reason: str | None = None,
) -> Decision | None:
    decision = (
        db.query(Decision)
        .filter(Decision.id == decision_id, Decision.client_id == client_id)
        .one_or_none()
    )
    if decision is None:
        return None
    decision.status = status
    if status == DecisionStatus.DISMISSED:
        decision.dismissal_reason = dismissal_reason
    db.commit()
    db.refresh(decision)
    return decision


def default_threshold_catalog() -> dict[str, float | int]:
    return dict(DEFAULT_DECISION_THRESHOLDS)
