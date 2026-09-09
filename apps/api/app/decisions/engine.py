from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.decisions.thresholds import merge_thresholds
from app.models.decision import (
    DecisionPriority,
    DecisionType,
    DiagnosticLayer,
    GrowthAction,
)
from app.models.client import Client
from app.models.gsc import FactGscQueryPage
from app.services.dashboard import _effective_range, _load_watermarks, build_dashboard


@dataclass(frozen=True)
class DecisionDraft:
    rule_key: str
    decision_type: DecisionType
    growth_action: GrowthAction | None
    diagnostic_layer: DiagnosticLayer
    priority: DecisionPriority
    diagnosis: str
    recommended_action: str
    success_metric: str
    evidence_json: dict[str, Any]
    baseline_metrics_json: dict[str, Any]
    page_url: str | None = None
    query: str | None = None
    keyword: str | None = None
    prompt: str | None = None


def _rule_key(*parts: str) -> str:
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _metric(dashboard: dict[str, Any], *path: str) -> float | None:
    node: Any = dashboard
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    if node is None:
        return None
    if isinstance(node, (int, float)):
        return float(node)
    return None


def _conversion_rules(
    dashboard: dict[str, Any],
    *,
    client_id: UUID,
    start: date,
    end: date,
    thresholds: dict[str, float | int],
) -> list[DecisionDraft]:
    sessions_current = _metric(dashboard, "traffic", "ga4_sessions", "current")
    sessions_previous = _metric(dashboard, "traffic", "ga4_sessions", "previous")
    leads_current = _metric(dashboard, "conversions", "leads", "current")
    leads_previous = _metric(dashboard, "conversions", "leads", "previous")
    lead_rate_current = _metric(dashboard, "conversions", "lead_rate", "current")
    lead_rate_previous = _metric(dashboard, "conversions", "lead_rate", "previous")

    if sessions_current is None or sessions_previous is None:
        return []

    drafts: list[DecisionDraft] = []
    sessions_growth = thresholds["conversion_sessions_growth_min_pct"]
    if sessions_previous > 0:
        sessions_change_pct = ((sessions_current - sessions_previous) / sessions_previous) * 100
    else:
        sessions_change_pct = 100.0 if sessions_current > 0 else 0.0

    lead_rate_decline = thresholds["conversion_lead_rate_decline_min_pct"]
    lead_rate_drop_pct: float | None = None
    if lead_rate_current is not None and lead_rate_previous is not None and lead_rate_previous > 0:
        lead_rate_drop_pct = ((lead_rate_previous - lead_rate_current) / lead_rate_previous) * 100

    traffic_up = sessions_change_pct >= float(sessions_growth)
    leads_flat = (
        leads_current is not None
        and leads_previous is not None
        and leads_current <= leads_previous
    )
    lead_rate_down = lead_rate_drop_pct is not None and lead_rate_drop_pct >= float(lead_rate_decline)

    if traffic_up and (leads_flat or lead_rate_down):
        drafts.append(
            DecisionDraft(
                rule_key=_rule_key("conversion_path", str(client_id), start.isoformat(), end.isoformat()),
                decision_type=DecisionType.BOTTLENECK,
                growth_action=GrowthAction.CONVERSION_PATH,
                diagnostic_layer=DiagnosticLayer.CONVERSION,
                priority=DecisionPriority.HIGH,
                diagnosis=(
                    "Traffic increased while lead volume or lead rate did not keep pace, "
                    "suggesting a conversion-path constraint."
                ),
                recommended_action=(
                    "Review high-traffic landing pages, CTAs, forms, and commercial paths "
                    "for friction or intent mismatch."
                ),
                success_metric="Lead rate improves while sessions remain stable or grow",
                evidence_json={
                    "sessions_change_pct": round(sessions_change_pct, 2),
                    "leads_current": leads_current,
                    "leads_previous": leads_previous,
                    "lead_rate_current": lead_rate_current,
                    "lead_rate_previous": lead_rate_previous,
                },
                baseline_metrics_json={
                    "ga4_sessions_current": sessions_current,
                    "ga4_sessions_previous": sessions_previous,
                    "leads_current": leads_current,
                    "leads_previous": leads_previous,
                    "lead_rate_current": lead_rate_current,
                    "lead_rate_previous": lead_rate_previous,
                },
            )
        )
    return drafts


def _visibility_rules(
    dashboard: dict[str, Any],
    *,
    client_id: UUID,
    start: date,
    end: date,
    thresholds: dict[str, float | int],
) -> list[DecisionDraft]:
    drafts: list[DecisionDraft] = []
    gsc_impressions = _metric(dashboard, "visibility", "search", "gsc_impressions", "current")
    gsc_ctr = _metric(dashboard, "visibility", "search", "gsc_ctr", "current")
    search_visibility = _metric(dashboard, "visibility", "search", "search_visibility", "current")
    ai_mention = _metric(dashboard, "visibility", "ai", "mention_presence", "current")

    min_impressions = float(thresholds["property_low_ctr_min_impressions"])
    max_ctr = float(thresholds["property_low_ctr_max_pct"])
    if (
        gsc_impressions is not None
        and gsc_impressions >= min_impressions
        and gsc_ctr is not None
        and gsc_ctr <= max_ctr
    ):
        drafts.append(
            DecisionDraft(
                rule_key=_rule_key("property_low_ctr", str(client_id), start.isoformat(), end.isoformat()),
                decision_type=DecisionType.BOTTLENECK,
                growth_action=GrowthAction.SERP_CTR,
                diagnostic_layer=DiagnosticLayer.TRAFFIC,
                priority=DecisionPriority.HIGH,
                diagnosis=(
                    "Search visibility is generating material impressions but property CTR is "
                    "below the configured threshold."
                ),
                recommended_action=(
                    "Prioritize title tags, meta descriptions, and SERP intent alignment on "
                    "high-impression pages and queries."
                ),
                success_metric="GSC CTR improves without losing average position",
                evidence_json={
                    "gsc_impressions": gsc_impressions,
                    "gsc_ctr_pct": gsc_ctr,
                },
                baseline_metrics_json={
                    "gsc_impressions": gsc_impressions,
                    "gsc_ctr_pct": gsc_ctr,
                },
            )
        )

    search_min = float(thresholds["ai_visibility_gap_search_min"])
    mention_max = float(thresholds["ai_visibility_gap_mention_max_pct"])
    if (
        search_visibility is not None
        and search_visibility >= search_min
        and ai_mention is not None
        and ai_mention <= mention_max
    ):
        drafts.append(
            DecisionDraft(
                rule_key=_rule_key("ai_visibility_gap", str(client_id), start.isoformat(), end.isoformat()),
                decision_type=DecisionType.OPPORTUNITY,
                growth_action=GrowthAction.AI_VISIBILITY,
                diagnostic_layer=DiagnosticLayer.VISIBILITY,
                priority=DecisionPriority.MEDIUM,
                diagnosis=(
                    "Search visibility is present but AI mention presence is low relative to "
                    "the configured threshold."
                ),
                recommended_action=(
                    "Review entity clarity, structured data, and citation-ready content for "
                    "priority topics and commercial pages."
                ),
                success_metric="AI mention presence improves while search visibility is maintained",
                evidence_json={
                    "search_visibility": search_visibility,
                    "ai_mention_presence_pct": ai_mention,
                },
                baseline_metrics_json={
                    "search_visibility": search_visibility,
                    "ai_mention_presence_pct": ai_mention,
                },
            )
        )
    return drafts


def _gsc_query_rules(
    db: Session,
    *,
    client_id: UUID,
    period: tuple[date, date] | None,
    thresholds: dict[str, float | int],
) -> list[DecisionDraft]:
    if period is None:
        return []

    start, end = period
    rows = (
        db.query(
            FactGscQueryPage.query,
            FactGscQueryPage.normalized_url,
            func.coalesce(func.sum(FactGscQueryPage.impressions), 0),
            func.coalesce(func.sum(FactGscQueryPage.clicks), 0),
            func.coalesce(
                func.sum(FactGscQueryPage.average_position * FactGscQueryPage.impressions),
                0,
            ),
        )
        .filter(
            FactGscQueryPage.client_id == client_id,
            FactGscQueryPage.date >= start,
            FactGscQueryPage.date <= end,
        )
        .group_by(FactGscQueryPage.query, FactGscQueryPage.normalized_url)
        .all()
    )

    drafts: list[DecisionDraft] = []
    high_impression_min = float(thresholds["gsc_high_impression_min"])
    low_ctr_max = float(thresholds["gsc_low_ctr_max_pct"])
    strike_min_pos = float(thresholds["gsc_striking_distance_min_pos"])
    strike_max_pos = float(thresholds["gsc_striking_distance_max_pos"])
    strike_min_impressions = float(thresholds["gsc_striking_distance_min_impressions"])

    for query, page_url, impressions, clicks, weighted_position in rows:
        impressions_f = float(impressions or 0)
        clicks_f = float(clicks or 0)
        if impressions_f <= 0:
            continue
        avg_position = float(weighted_position or 0) / impressions_f
        ctr_pct = (clicks_f / impressions_f) * 100

        if impressions_f >= high_impression_min and avg_position <= 10 and ctr_pct <= low_ctr_max:
            drafts.append(
                DecisionDraft(
                    rule_key=_rule_key("high_impression_low_ctr", query, page_url),
                    decision_type=DecisionType.OPPORTUNITY,
                    growth_action=GrowthAction.SERP_CTR,
                    diagnostic_layer=DiagnosticLayer.TRAFFIC,
                    priority=DecisionPriority.MEDIUM,
                    diagnosis=(
                        f"Query '{query}' on {page_url} has strong visibility "
                        f"({int(impressions_f)} impressions, position {avg_position:.1f}) "
                        f"but CTR is only {ctr_pct:.2f}%."
                    ),
                    recommended_action=(
                        "Improve title/meta alignment and SERP snippet appeal for this query/page pairing."
                    ),
                    success_metric="CTR improves for this query/page while impressions remain stable",
                    evidence_json={
                        "impressions": impressions_f,
                        "clicks": clicks_f,
                        "ctr_pct": round(ctr_pct, 4),
                        "average_position": round(avg_position, 2),
                    },
                    baseline_metrics_json={
                        "impressions": impressions_f,
                        "clicks": clicks_f,
                        "ctr_pct": round(ctr_pct, 4),
                        "average_position": round(avg_position, 2),
                    },
                    query=query,
                    page_url=page_url,
                )
            )

        if (
            strike_min_pos <= avg_position <= strike_max_pos
            and impressions_f >= strike_min_impressions
        ):
            drafts.append(
                DecisionDraft(
                    rule_key=_rule_key("striking_distance", query, page_url),
                    decision_type=DecisionType.CONTENT_PLANNING_SIGNAL,
                    growth_action=None,
                    diagnostic_layer=DiagnosticLayer.VISIBILITY,
                    priority=DecisionPriority.LOW,
                    diagnosis=(
                        f"Query '{query}' on {page_url} is in striking distance "
                        f"(position {avg_position:.1f}) with {int(impressions_f)} impressions."
                    ),
                    recommended_action=(
                        "Evaluate whether supporting content, internal links, or on-page "
                        "optimization could move this topic into stronger positions."
                    ),
                    success_metric="Average position improves into page 1 for this query/page",
                    evidence_json={
                        "impressions": impressions_f,
                        "clicks": clicks_f,
                        "average_position": round(avg_position, 2),
                    },
                    baseline_metrics_json={
                        "impressions": impressions_f,
                        "clicks": clicks_f,
                        "average_position": round(avg_position, 2),
                    },
                    query=query,
                    page_url=page_url,
                )
            )

    return drafts


def evaluate_decision_drafts(
    db: Session,
    *,
    client_id: UUID,
    from_date: date,
    to_date: date,
    threshold_overrides: dict[str, Any] | None = None,
) -> list[DecisionDraft]:
    client = db.get(Client, client_id)
    if client is None:
        return []

    thresholds = merge_thresholds(threshold_overrides)
    dashboard = build_dashboard(db, client, from_date, to_date)
    watermarks = _load_watermarks(db, client_id)
    gsc_period = _effective_range(from_date, to_date, watermarks.get("gsc_queries"))

    drafts: list[DecisionDraft] = []
    drafts.extend(
        _conversion_rules(
            dashboard,
            client_id=client_id,
            start=from_date,
            end=to_date,
            thresholds=thresholds,
        )
    )
    drafts.extend(
        _visibility_rules(
            dashboard,
            client_id=client_id,
            start=from_date,
            end=to_date,
            thresholds=thresholds,
        )
    )

    query_drafts = _gsc_query_rules(
        db,
        client_id=client_id,
        period=gsc_period,
        thresholds=thresholds,
    )
    query_drafts.sort(
        key=lambda draft: float(draft.evidence_json.get("impressions", 0)),
        reverse=True,
    )
    drafts.extend(query_drafts[:25])
    return drafts
