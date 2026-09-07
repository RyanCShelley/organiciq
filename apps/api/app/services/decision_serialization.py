from __future__ import annotations

from app.schemas import DiagnoseResponse, FindingOut, LeverSummaryOut, SearchOpportunityOut
from app.services.lever_engine import LEVER_LABELS, SEARCH_OPPORTUNITY_LABEL


def _label_for_lever(lever: str) -> str:
    if lever == "search_opportunity":
        return SEARCH_OPPORTUNITY_LABEL
    return LEVER_LABELS.get(lever, lever)


def _serialize_finding(row) -> FindingOut:
    return FindingOut(
        rule_key=row.rule_key,
        lever=row.lever,
        label=_label_for_lever(row.lever),
        stage=row.stage.value,
        diagnosis=row.diagnosis,
        recommended_action=row.recommended_action,
        success_metric=row.success_metric,
        priority_score=row.priority_score,
        impact=row.impact,
        confidence=row.confidence,
        urgency=row.urgency,
        effort=row.effort,
        severity=row.severity,
        page_url=row.page_url,
        query=row.query,
        evidence_json=row.evidence_json,
        is_recommended_action=row.is_recommended_action,
        promotion_blocked_reason=row.promotion_blocked_reason,
        priority_band=row.priority_band,
        priority_band_reason=row.priority_band_reason,
        finding_group_key=row.finding_group_key,
    )


def _serialize_search_opportunity(row) -> SearchOpportunityOut:
    evidence = row.evidence_json
    topic = evidence.get("priority_topic")
    return SearchOpportunityOut(
        rule_key=row.rule_key,
        page_url=row.page_url,
        query=row.query,
        topic=str(topic) if topic else None,
        impressions=int(evidence["impressions"]) if evidence.get("impressions") is not None else None,
        clicks=int(evidence["clicks"]) if evidence.get("clicks") is not None else None,
        ctr_percent=(
            float(evidence["ctr_percent"]) if evidence.get("ctr_percent") is not None else None
        ),
        average_position=(
            float(evidence["average_position"])
            if evidence.get("average_position") is not None
            else None
        ),
        page_type=str(evidence["page_type"]) if evidence.get("page_type") else None,
        opportunity_type=str(
            evidence.get("opportunity_type") or "Striking-Distance Opportunity"
        ),
        diagnosis=row.diagnosis,
    )


def serialize_diagnose(result) -> DiagnoseResponse:
    findings = [_serialize_finding(row) for row in result.findings]
    recommended_actions = [_serialize_finding(row) for row in result.recommended_actions]
    search_opportunities = [
        _serialize_search_opportunity(row) for row in result.search_opportunities
    ]
    return DiagnoseResponse(
        ready=result.ready,
        message=result.message,
        readiness=result.readiness,
        formula=result.formula,
        requested_from=result.requested_from,
        requested_to=result.requested_to,
        analysis_from=result.analysis_from,
        analysis_to=result.analysis_to,
        partial_message=result.partial_message,
        findings_count=result.findings_count,
        recommended_actions_count=result.recommended_actions_count,
        levers=[
            LeverSummaryOut(
                lever=row.lever,
                label=row.label,
                findings_count=row.findings_count,
                recommended_actions_count=row.recommended_actions_count,
                status=row.status,
            )
            for row in result.levers
        ],
        findings=findings,
        recommended_actions=recommended_actions,
        search_opportunities=search_opportunities,
        recommendations=recommended_actions,
    )
