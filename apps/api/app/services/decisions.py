from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.decisions.thresholds import DEFAULT_DECISION_THRESHOLDS, merge_thresholds
from app.models.client import Client
from app.models.decision import (
    Decision,
    DecisionPriority,
    DecisionStatus,
    DecisionThreshold,
    DecisionType,
    GrowthAction,
)
from app.services.lever_engine import DiagnoseResult, LeverFinding, diagnose


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


def run_diagnose(
    db: Session,
    client: Client,
    *,
    from_date: date,
    to_date: date,
) -> DiagnoseResult:
    settings = get_settings()
    if not settings.decision_engine_enabled:
        return DiagnoseResult(
            ready=False,
            message="Decision Engine is disabled.",
            readiness={"search_console": False, "crawl_audit": False},
            formula="",
        )
    return diagnose(db, client, from_date=from_date, to_date=to_date)


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
            Decision.priority_score.desc().nullslast(),
            Decision.created_at.desc(),
        )
        .limit(limit)
        .all()
    )


def _priority_band(score: float) -> DecisionPriority:
    if score >= 70:
        return DecisionPriority.HIGH
    if score >= 50:
        return DecisionPriority.MEDIUM
    return DecisionPriority.LOW


def _decision_type_for_lever(lever: str) -> DecisionType:
    if lever == "content_expansion":
        return DecisionType.CONTENT_PLANNING_SIGNAL
    if lever == GrowthAction.CONVERSION_PATH.value:
        return DecisionType.BOTTLENECK
    if lever in {GrowthAction.TECHNICAL_SEO.value, GrowthAction.SERP_CTR.value}:
        return DecisionType.BOTTLENECK if lever == GrowthAction.TECHNICAL_SEO.value else DecisionType.OPPORTUNITY
    return DecisionType.OPPORTUNITY


def _growth_action_for_lever(lever: str) -> GrowthAction | None:
    if lever == "content_expansion":
        return None
    return GrowthAction(lever)


def _finding_to_model(client_id: UUID, finding: LeverFinding, from_date: date, to_date: date) -> Decision:
    growth_action = _growth_action_for_lever(finding.lever)
    return Decision(
        client_id=client_id,
        rule_key=finding.rule_key,
        decision_type=_decision_type_for_lever(finding.lever),
        growth_action=growth_action,
        diagnostic_layer=finding.stage,
        priority=_priority_band(finding.priority_score),
        status=DecisionStatus.NEW,
        page_url=finding.page_url,
        query=finding.query,
        diagnosis=finding.diagnosis,
        recommended_action=finding.recommended_action,
        evidence_json=finding.evidence_json,
        baseline_metrics_json=finding.baseline_metrics_json,
        success_metric=finding.success_metric,
        date_range_start=from_date,
        date_range_end=to_date,
        priority_score=Decimal(str(finding.priority_score)),
        impact=Decimal(str(finding.impact)),
        confidence=Decimal(str(finding.confidence)),
        urgency=Decimal(str(finding.urgency)),
        effort=Decimal(str(finding.effort)),
    )


def evaluate_and_store(
    db: Session,
    client: Client,
    *,
    from_date: date,
    to_date: date,
) -> tuple[list[Decision], int, DiagnoseResult]:
    result = run_diagnose(db, client, from_date=from_date, to_date=to_date)
    if not result.ready:
        return [], 0, result

    created: list[Decision] = []
    skipped = 0
    for finding in result.recommendations:
        existing = (
            db.query(Decision)
            .filter(
                Decision.client_id == client.id,
                Decision.rule_key == finding.rule_key,
                Decision.date_range_start == from_date,
                Decision.date_range_end == to_date,
            )
            .one_or_none()
        )
        if existing is not None:
            skipped += 1
            continue
        decision = _finding_to_model(client.id, finding, from_date, to_date)
        db.add(decision)
        created.append(decision)

    db.commit()
    for decision in created:
        db.refresh(decision)
    return created, skipped, result


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
