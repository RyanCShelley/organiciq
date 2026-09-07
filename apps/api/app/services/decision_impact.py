"""Business-impact scoring for Decision Engine prioritization.

Diagnosis (which lever applies) is handled separately in lever_engine.py.
This module translates upstream opportunities into downstream lead opportunity
where reliable data exists, and falls back to stage-specific signals otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.decisions.ctr_curve import expected_ctr_percent
from app.models.client import Client
from app.models.ga4 import FactGa4Event, FactGa4Traffic
from app.services.dashboard import period_lead_goal
from app.services.page_eligibility import PageClassification, PageType

LEAD_IMPACT_REFERENCE_FRACTION = 0.25
UPSTREAM_FALLBACK_IMPACT_CAP = 35.0
FALLBACK_VISIBILITY_IMPACT_CAP = 35.0
DATA_CONFIDENCE_MULTIPLIERS: dict[str, float] = {
    "high": 1.0,
    "medium": 0.85,
    "low": 0.55,
}
MIN_PAGE_SESSIONS_FOR_PAGE_RATE = 10
STRATEGIC_SESSIONS_ABSOLUTE = 50.0
STRATEGIC_CLICKS = 10
MIN_INDEXATION_DEMAND_IMPRESSIONS = 30


@dataclass(frozen=True)
class TechnicalAssessment:
    impact: float
    severity: float
    critical_override: bool
    critical_override_reason: str | None
    evidence: dict[str, Any]


@dataclass(frozen=True)
class SiteBusinessContext:
    site_lead_rate_pct: float | None
    period_sessions: float
    period_leads: int
    period_lead_goal: int | None
    p90_page_sessions: float


@dataclass(frozen=True)
class LeadRateContext:
    page_type: PageType | None = None
    page_type_rates: dict[str, float] = field(default_factory=dict)
    topic: str | None = None
    topic_rates: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class PageBusinessContext:
    normalized_url: str
    ga4_sessions: float
    ga4_leads: int

    @property
    def page_lead_rate_pct(self) -> float | None:
        if self.ga4_sessions <= 0:
            return None
        return (self.ga4_leads / self.ga4_sessions) * 100


def business_impact_reference_leads(site: SiteBusinessContext) -> float:
    if site.period_lead_goal is not None and site.period_lead_goal > 0:
        return max(2.0, float(site.period_lead_goal) * LEAD_IMPACT_REFERENCE_FRACTION)
    if site.period_leads > 0:
        return max(2.0, float(site.period_leads) * LEAD_IMPACT_REFERENCE_FRACTION)
    return 5.0


def _confidence_multiplier(data_confidence: str) -> float:
    return DATA_CONFIDENCE_MULTIPLIERS.get(data_confidence, DATA_CONFIDENCE_MULTIPLIERS["low"])


def normalize_business_impact(
    *,
    site: SiteBusinessContext,
    estimated_incremental_leads: float | None = None,
    leads_at_risk: float | None = None,
    page_leads: int = 0,
    recoverable_clicks: float = 0,
    sessions: float = 0,
    strategic_priority: int = 3,
    data_confidence: str = "high",
) -> tuple[float, dict[str, Any]]:
    reference_leads = business_impact_reference_leads(site)
    confidence = _confidence_multiplier(data_confidence)

    if estimated_incremental_leads is not None and estimated_incremental_leads > 0:
        raw = (estimated_incremental_leads / reference_leads) * 100.0
        impact = min(100.0, round(raw * confidence, 1))
        return impact, {
            "impact_normalization_basis": "incremental_leads",
            "impact_reference_leads": round(reference_leads, 2),
            "data_confidence": data_confidence,
            "estimated_incremental_leads": round(estimated_incremental_leads, 2),
        }

    if leads_at_risk is not None and leads_at_risk > 0:
        raw = (leads_at_risk / reference_leads) * 100.0
        impact = min(100.0, round(raw * confidence, 1))
        return impact, {
            "impact_normalization_basis": "leads_at_risk",
            "impact_reference_leads": round(reference_leads, 2),
            "data_confidence": data_confidence,
            "estimated_leads_at_risk": round(leads_at_risk, 2),
        }

    if page_leads > 0:
        raw = (float(page_leads) / reference_leads) * 100.0
        impact = min(100.0, round(raw * confidence * 0.75, 1))
        return impact, {
            "impact_normalization_basis": "existing_page_leads",
            "impact_reference_leads": round(reference_leads, 2),
            "data_confidence": data_confidence,
            "page_leads": page_leads,
        }

    click_component = min(15.0, recoverable_clicks * 0.6)
    session_component = min(10.0, sessions * 0.04)
    strategic_component = max(0.0, float(strategic_priority - 3) * 4.0)
    fallback_raw = click_component + session_component + strategic_component
    impact = min(
        UPSTREAM_FALLBACK_IMPACT_CAP,
        round(fallback_raw * _confidence_multiplier("low"), 1),
    )
    return impact, {
        "impact_normalization_basis": "upstream_fallback",
        "impact_reference_leads": round(reference_leads, 2),
        "data_confidence": "low",
        "upstream_fallback_score": impact,
    }


def impact_from_lead_opportunity(estimated_leads: float, site: SiteBusinessContext) -> float:
    impact, _ = normalize_business_impact(
        site=site,
        estimated_incremental_leads=estimated_leads,
        data_confidence="high",
    )
    return impact


def compute_page_type_lead_rates(
    page_contexts: dict[str, PageBusinessContext],
    classifications: dict[str, PageClassification],
) -> dict[str, float]:
    totals: dict[str, tuple[float, int]] = {}
    for url, ctx in page_contexts.items():
        if ctx.ga4_sessions < MIN_PAGE_SESSIONS_FOR_PAGE_RATE:
            continue
        classification = classifications.get(url)
        if classification is None:
            continue
        page_type = classification.page_type.value
        sessions, leads = totals.get(page_type, (0.0, 0))
        totals[page_type] = (sessions + ctx.ga4_sessions, leads + ctx.ga4_leads)
    rates: dict[str, float] = {}
    for page_type, (sessions, leads) in totals.items():
        if sessions > 0 and leads > 0:
            rates[page_type] = (leads / sessions) * 100
    return rates


def compute_topic_lead_rates(
    page_contexts: dict[str, PageBusinessContext],
    classifications: dict[str, PageClassification],
) -> dict[str, float]:
    totals: dict[str, tuple[float, int]] = {}
    for url, ctx in page_contexts.items():
        if ctx.ga4_sessions < MIN_PAGE_SESSIONS_FOR_PAGE_RATE:
            continue
        classification = classifications.get(url)
        if classification is None or not classification.priority_topic:
            continue
        topic = classification.priority_topic
        sessions, leads = totals.get(topic, (0.0, 0))
        totals[topic] = (sessions + ctx.ga4_sessions, leads + ctx.ga4_leads)
    return {
        topic: (leads / sessions) * 100
        for topic, (sessions, leads) in totals.items()
        if sessions > 0 and leads > 0
    }


def resolve_lead_rate_pct(
    *,
    page_ctx: PageBusinessContext | None,
    site: SiteBusinessContext,
    page_type: PageType | None,
    page_type_rates: dict[str, float],
    topic: str | None,
    topic_rates: dict[str, float],
) -> tuple[float | None, str]:
    if (
        page_ctx is not None
        and page_ctx.ga4_sessions >= MIN_PAGE_SESSIONS_FOR_PAGE_RATE
        and page_ctx.page_lead_rate_pct is not None
        and page_ctx.page_lead_rate_pct > 0
    ):
        return page_ctx.page_lead_rate_pct, "page_historical"
    if page_type is not None:
        page_type_rate = page_type_rates.get(page_type.value)
        if page_type_rate is not None and page_type_rate > 0:
            return page_type_rate, "page_type"
    if topic:
        topic_rate = topic_rates.get(topic)
        if topic_rate is not None and topic_rate > 0:
            return topic_rate, "topic_intent"
    if site.site_lead_rate_pct is not None and site.site_lead_rate_pct > 0:
        return site.site_lead_rate_pct, "client_wide"
    return None, "none"


def effective_lead_rate_pct(
    page_ctx: PageBusinessContext | None,
    site: SiteBusinessContext,
    *,
    page_type: PageType | None = None,
    page_type_rates: dict[str, float] | None = None,
    topic: str | None = None,
    topic_rates: dict[str, float] | None = None,
) -> float | None:
    rate, _ = resolve_lead_rate_pct(
        page_ctx=page_ctx,
        site=site,
        page_type=page_type,
        page_type_rates=page_type_rates or {},
        topic=topic,
        topic_rates=topic_rates or {},
    )
    return rate


def build_impact_explanation(
    evidence: dict[str, Any],
    *,
    classification: PageClassification | None = None,
    page_ctx: PageBusinessContext | None = None,
) -> list[str]:
    lines: list[str] = []
    basis = evidence.get("impact_basis")
    if evidence.get("critical_override"):
        lines.append("Critical technical override applied")
        override_reason = evidence.get("critical_override_reason")
        if override_reason:
            lines.append(f"Override reason: {str(override_reason).replace('_', ' ')}")
    if evidence.get("severity") is not None:
        lines.append(f"Technical severity: {evidence['severity']}")
    if basis == "downstream":
        lines.append("Impact driven by available business opportunity evidence")
    elif basis == "fallback":
        lines.append("Impact uses upstream fallback signals (downstream data unavailable)")

    normalization_basis = evidence.get("impact_normalization_basis")
    if normalization_basis:
        lines.append(f"Impact normalization: {str(normalization_basis).replace('_', ' ')}")
    reference = evidence.get("impact_reference_leads")
    if reference is not None:
        lines.append(f"Impact reference (period leads scale): {reference}")

    if evidence.get("indexable") is False:
        lines.append("Non-indexable URL blocks organic visibility")
    if evidence.get("status_code") and int(evidence["status_code"]) >= 400:
        lines.append(f"HTTP {evidence['status_code']} prevents page delivery")

    if classification is not None:
        if classification.page_type == PageType.COMMERCIAL:
            lines.append("Primary commercial page")
        elif classification.page_type == PageType.CONVERSION:
            lines.append("Primary conversion page")
        if classification.commercial_priority >= 4:
            lines.append(f"Commercial priority {classification.commercial_priority}/5")
        if classification.strategic_priority >= 4:
            lines.append(f"Strategic priority {classification.strategic_priority}/5")
        if not classification.eligible_for_growth_action and classification.excluded_reason:
            lines.append(f"Page excluded from growth actions: {classification.excluded_reason}")

    if page_ctx is not None and page_ctx.ga4_leads > 0:
        lines.append(f"Page generated {page_ctx.ga4_leads} lead(s) in period")
    if page_ctx is not None and page_ctx.ga4_sessions > 0:
        lines.append(f"{int(page_ctx.ga4_sessions)} GA4 sessions in period")

    lead_rate_source = evidence.get("lead_rate_source")
    if lead_rate_source:
        lines.append(f"Lead rate source: {str(lead_rate_source).replace('_', ' ')}")

    for key, label in (
        ("estimated_lead_opportunity", "Estimated lead opportunity"),
        ("leads_at_risk", "Leads at risk"),
        ("recoverable_clicks", "Recoverable clicks"),
        ("unlock_clicks", "Visibility unlock clicks"),
    ):
        value = evidence.get(key)
        if value is not None:
            lines.append(f"{label}: {value}")

    return lines


def downstream_lead_opportunity(
    recoverable_clicks: float,
    lead_rate_pct: float | None,
) -> float | None:
    if lead_rate_pct is None or lead_rate_pct <= 0 or recoverable_clicks <= 0:
        return None
    expected_sessions = recoverable_clicks
    return expected_sessions * (lead_rate_pct / 100.0)


def estimate_visibility_recoverable_clicks(*, impressions: float, clicks: float, average_position: float) -> float:
    expected = expected_ctr_percent(average_position)
    target_clicks = impressions * (expected / 100.0) * 0.5
    return max(0.0, target_clicks - clicks)


def estimate_indexation_unlock_clicks(*, impressions: float, clicks: float, average_position: float) -> float:
    """Full addressable search traffic if a blocked page becomes visible at its current rank."""
    expected = expected_ctr_percent(average_position)
    full_expected_clicks = impressions * (expected / 100.0)
    return max(full_expected_clicks, clicks)


def assess_technical_severity(
    *,
    indexable: bool,
    status_code: int | None,
    canonicalized_elsewhere: bool,
    classification: PageClassification | None,
) -> tuple[float, bool, str | None]:
    base = 40.0
    reason: str | None = None

    if not indexable:
        base = 80.0
        reason = "unexpected_noindex"
    elif status_code is not None and status_code >= 500:
        base = 90.0
        reason = "server_error_on_demand_page"
    elif status_code is not None and status_code >= 400:
        base = 75.0
        reason = "client_error_on_demand_page"
    elif canonicalized_elsewhere:
        base = 60.0
        reason = "incorrect_canonical"

    boost = 0.0
    if classification is not None:
        boost += max(0.0, (classification.strategic_priority - 3) * 8.0)
        boost += max(0.0, (classification.commercial_priority - 3) * 8.0)

    severity = min(100.0, round(base + boost, 1))

    critical_override = False
    critical_reason: str | None = None

    if (
        not indexable
        and classification is not None
        and classification.commercial_priority >= 5
    ):
        severity = 100.0
        critical_override = True
        critical_reason = "unexpected_noindex_on_priority_commercial_page"
    elif (
        not indexable
        and classification is not None
        and classification.page_type in {PageType.COMMERCIAL, PageType.CONVERSION}
    ):
        severity = max(severity, 90.0)
        critical_override = True
        critical_reason = reason
    elif (
        status_code is not None
        and status_code >= 400
        and classification is not None
        and classification.commercial_priority >= 4
    ):
        critical_override = True
        critical_reason = reason
    elif severity >= 85.0:
        critical_override = True
        critical_reason = reason

    return severity, critical_override, critical_reason


def fallback_visibility_impact(*, clicks: float, average_position: float, impressions: float = 0) -> float:
    position_score = max(0.0, 25.0 - average_position)
    demand_score = min(30.0, clicks * 2.0)
    impression_demand = min(20.0, impressions / 100.0)
    return min(FALLBACK_VISIBILITY_IMPACT_CAP, round(position_score + demand_score + impression_demand, 1))


def is_strategic_page(
    *,
    clicks: float,
    page_ctx: PageBusinessContext | None,
    site: SiteBusinessContext,
) -> bool:
    if page_ctx is not None:
        if page_ctx.ga4_leads > 0:
            return True
        if page_ctx.ga4_sessions >= max(STRATEGIC_SESSIONS_ABSOLUTE, site.p90_page_sessions * 0.5):
            return True
    return clicks >= STRATEGIC_CLICKS


def portfolio_urgency_adjustment(base_urgency: float, site: SiteBusinessContext) -> float:
    if site.period_lead_goal is None or site.period_leads <= 0:
        return base_urgency
    goal = site.period_lead_goal
    if site.period_leads < goal * 0.8:
        return min(100.0, base_urgency + 10.0)
    return base_urgency


def load_site_business_context(
    db: Session,
    client: Client,
    *,
    period: tuple[date, date],
    lead_events: list[str],
    dashboard: dict[str, Any],
) -> SiteBusinessContext:
    start, end = period
    period_goal, _ = period_lead_goal(client.monthly_lead_goal, start, end)

    sessions = (
        db.query(func.coalesce(func.sum(FactGa4Traffic.sessions), 0))
        .filter(
            FactGa4Traffic.client_id == client.id,
            FactGa4Traffic.date >= start,
            FactGa4Traffic.date <= end,
        )
        .scalar()
    )
    period_sessions = float(sessions or 0)

    period_leads = 0
    site_lead_rate_pct: float | None = None
    if lead_events:
        leads = (
            db.query(func.coalesce(func.sum(FactGa4Event.event_count), 0))
            .filter(
                FactGa4Event.client_id == client.id,
                FactGa4Event.date >= start,
                FactGa4Event.date <= end,
                FactGa4Event.event_name.in_(lead_events),
            )
            .scalar()
        )
        period_leads = int(leads or 0)
        if period_sessions > 0:
            site_lead_rate_pct = (period_leads / period_sessions) * 100

    if period_goal is None:
        period_goal = dashboard.get("conversions", {}).get("period_lead_goal")

    return SiteBusinessContext(
        site_lead_rate_pct=site_lead_rate_pct,
        period_sessions=period_sessions,
        period_leads=period_leads,
        period_lead_goal=period_goal,
        p90_page_sessions=0.0,
    )


def load_page_business_contexts(
    db: Session,
    *,
    client_id: UUID,
    period: tuple[date, date],
    lead_events: list[str],
    normalized_urls: list[str],
) -> dict[str, PageBusinessContext]:
    if not normalized_urls:
        return {}

    start, end = period
    session_rows = (
        db.query(
            FactGa4Traffic.normalized_url,
            func.coalesce(func.sum(FactGa4Traffic.sessions), 0),
        )
        .filter(
            FactGa4Traffic.client_id == client_id,
            FactGa4Traffic.date >= start,
            FactGa4Traffic.date <= end,
            FactGa4Traffic.normalized_url.in_(normalized_urls),
        )
        .group_by(FactGa4Traffic.normalized_url)
        .all()
    )
    sessions_by_url = {url: float(total or 0) for url, total in session_rows}

    leads_by_url: dict[str, int] = {url: 0 for url in normalized_urls}
    if lead_events:
        lead_rows = (
            db.query(
                FactGa4Event.normalized_url,
                func.coalesce(func.sum(FactGa4Event.event_count), 0),
            )
            .filter(
                FactGa4Event.client_id == client_id,
                FactGa4Event.date >= start,
                FactGa4Event.date <= end,
                FactGa4Event.event_name.in_(lead_events),
                FactGa4Event.normalized_url.in_(normalized_urls),
            )
            .group_by(FactGa4Event.normalized_url)
            .all()
        )
        leads_by_url.update({url: int(total or 0) for url, total in lead_rows})

    return {
        url: PageBusinessContext(
            normalized_url=url,
            ga4_sessions=sessions_by_url.get(url, 0.0),
            ga4_leads=leads_by_url.get(url, 0),
        )
        for url in normalized_urls
    }


def with_p90_sessions(
    site: SiteBusinessContext,
    page_contexts: dict[str, PageBusinessContext],
) -> SiteBusinessContext:
    session_values = sorted(ctx.ga4_sessions for ctx in page_contexts.values() if ctx.ga4_sessions > 0)
    if not session_values:
        return site
    index = max(0, int(len(session_values) * 0.9) - 1)
    p90 = session_values[index]
    return SiteBusinessContext(
        site_lead_rate_pct=site.site_lead_rate_pct,
        period_sessions=site.period_sessions,
        period_leads=site.period_leads,
        period_lead_goal=site.period_lead_goal,
        p90_page_sessions=p90,
    )


def _downstream_or_fallback(
    *,
    recoverable_clicks: float,
    page_ctx: PageBusinessContext | None,
    site: SiteBusinessContext,
    clicks: float,
    average_position: float,
    impressions: float = 0,
    lead_rate_ctx: LeadRateContext | None = None,
    strategic_priority: int = 3,
) -> tuple[float, dict[str, Any]]:
    if lead_rate_ctx is not None:
        lead_rate, lead_rate_source = resolve_lead_rate_pct(
            page_ctx=page_ctx,
            site=site,
            page_type=lead_rate_ctx.page_type,
            page_type_rates=lead_rate_ctx.page_type_rates,
            topic=lead_rate_ctx.topic,
            topic_rates=lead_rate_ctx.topic_rates,
        )
    else:
        lead_rate = effective_lead_rate_pct(page_ctx, site)
        lead_rate_source = "client_wide" if lead_rate else "none"

    lead_opp = downstream_lead_opportunity(recoverable_clicks, lead_rate)
    if lead_opp is not None:
        confidence = "high" if lead_rate_source == "page_historical" else "medium"
        impact, norm_meta = normalize_business_impact(
            site=site,
            estimated_incremental_leads=lead_opp,
            data_confidence=confidence,
        )
        if impact > 0:
            return impact, {
                "impact_basis": "downstream",
                "recoverable_clicks": round(recoverable_clicks, 1),
                "expected_sessions": round(recoverable_clicks, 1),
                "estimated_lead_opportunity": round(lead_opp, 2),
                "estimated_incremental_leads": round(lead_opp, 2),
                "lead_rate_source": lead_rate_source,
                "site_lead_rate_pct": round(lead_rate, 2) if lead_rate is not None else None,
                "page_lead_rate_pct": (
                    round(page_ctx.page_lead_rate_pct, 2)
                    if page_ctx and page_ctx.page_lead_rate_pct is not None
                    else None
                ),
                "page_ga4_sessions": page_ctx.ga4_sessions if page_ctx else None,
                "page_ga4_leads": page_ctx.ga4_leads if page_ctx else None,
                **norm_meta,
            }

    page_lead_count = page_ctx.ga4_leads if page_ctx else 0
    page_sessions = page_ctx.ga4_sessions if page_ctx else 0
    impact, norm_meta = normalize_business_impact(
        site=site,
        page_leads=page_lead_count,
        recoverable_clicks=recoverable_clicks,
        sessions=page_sessions,
        strategic_priority=strategic_priority,
        data_confidence="medium" if page_lead_count > 0 else "low",
    )
    return impact, {
        "impact_basis": "fallback",
        "recoverable_clicks": round(recoverable_clicks, 1),
        "page_ga4_sessions": page_ctx.ga4_sessions if page_ctx else None,
        "page_ga4_leads": page_ctx.ga4_leads if page_ctx else None,
        **norm_meta,
    }


def score_technical_impact(
    *,
    impressions: float,
    clicks: float,
    average_position: float,
    indexable: bool,
    status_code: int | None,
    canonicalized_elsewhere: bool,
    page_ctx: PageBusinessContext | None,
    site: SiteBusinessContext,
    classification: PageClassification | None = None,
    lead_rate_ctx: LeadRateContext | None = None,
) -> TechnicalAssessment:
    status_error = status_code is not None and status_code >= 400
    blocked = not indexable or status_error
    strategic_priority = classification.strategic_priority if classification else 3

    if blocked:
        recoverable_clicks = estimate_indexation_unlock_clicks(
            impressions=impressions,
            clicks=clicks,
            average_position=average_position,
        )
    else:
        recoverable_clicks = estimate_visibility_recoverable_clicks(
            impressions=impressions,
            clicks=clicks,
            average_position=average_position,
        )

    impact, evidence = _downstream_or_fallback(
        recoverable_clicks=recoverable_clicks,
        page_ctx=page_ctx,
        site=site,
        clicks=clicks,
        average_position=average_position,
        impressions=impressions,
        lead_rate_ctx=lead_rate_ctx,
        strategic_priority=strategic_priority,
    )
    if blocked:
        evidence = {
            **evidence,
            "unlock_clicks": round(recoverable_clicks, 1),
        }

    severity, critical_override, critical_reason = assess_technical_severity(
        indexable=indexable,
        status_code=status_code,
        canonicalized_elsewhere=canonicalized_elsewhere,
        classification=classification,
    )

    return TechnicalAssessment(
        impact=impact,
        severity=severity,
        critical_override=critical_override,
        critical_override_reason=critical_reason,
        evidence={
            **evidence,
            "severity": severity,
            "critical_override": critical_override,
            "critical_override_reason": critical_reason,
        },
    )


def score_internal_linking_impact(
    *,
    impressions: float,
    clicks: float,
    average_position: float,
    page_ctx: PageBusinessContext | None,
    site: SiteBusinessContext,
    lead_rate_ctx: LeadRateContext | None = None,
    strategic_priority: int = 3,
) -> tuple[float, dict[str, Any]]:
    recoverable = estimate_visibility_recoverable_clicks(
        impressions=impressions,
        clicks=clicks,
        average_position=average_position,
    )
    return _downstream_or_fallback(
        recoverable_clicks=recoverable,
        page_ctx=page_ctx,
        site=site,
        clicks=clicks,
        average_position=average_position,
        impressions=impressions,
        lead_rate_ctx=lead_rate_ctx,
        strategic_priority=strategic_priority,
    )


def score_serp_ctr_impact(
    *,
    recoverable_clicks: float,
    page_ctx: PageBusinessContext | None,
    site: SiteBusinessContext,
    clicks: float,
    average_position: float,
    lead_rate_ctx: LeadRateContext | None = None,
    strategic_priority: int = 3,
) -> tuple[float, dict[str, Any]]:
    if lead_rate_ctx is not None:
        lead_rate, lead_rate_source = resolve_lead_rate_pct(
            page_ctx=page_ctx,
            site=site,
            page_type=lead_rate_ctx.page_type,
            page_type_rates=lead_rate_ctx.page_type_rates,
            topic=lead_rate_ctx.topic,
            topic_rates=lead_rate_ctx.topic_rates,
        )
    else:
        lead_rate = effective_lead_rate_pct(page_ctx, site)
        lead_rate_source = "client_wide" if lead_rate else "none"
    lead_opp = downstream_lead_opportunity(recoverable_clicks, lead_rate)
    if lead_opp is not None:
        confidence = "high" if lead_rate_source == "page_historical" else "medium"
        impact, norm_meta = normalize_business_impact(
            site=site,
            estimated_incremental_leads=lead_opp,
            data_confidence=confidence,
        )
        return impact, {
            "impact_basis": "downstream",
            "recoverable_clicks": round(recoverable_clicks, 1),
            "expected_sessions": round(recoverable_clicks, 1),
            "estimated_lead_opportunity": round(lead_opp, 2),
            "estimated_incremental_leads": round(lead_opp, 2),
            "lead_rate_source": lead_rate_source,
            "site_lead_rate_pct": round(lead_rate, 2) if lead_rate is not None else None,
            "page_lead_rate_pct": (
                round(page_ctx.page_lead_rate_pct, 2)
                if page_ctx and page_ctx.page_lead_rate_pct is not None
                else None
            ),
            "page_ga4_sessions": page_ctx.ga4_sessions if page_ctx else None,
            "page_ga4_leads": page_ctx.ga4_leads if page_ctx else None,
            **norm_meta,
        }

    page_lead_count = page_ctx.ga4_leads if page_ctx else 0
    page_sessions = page_ctx.ga4_sessions if page_ctx else 0
    impact, norm_meta = normalize_business_impact(
        site=site,
        page_leads=page_lead_count,
        recoverable_clicks=recoverable_clicks,
        sessions=page_sessions,
        strategic_priority=strategic_priority,
        data_confidence="low",
    )
    return impact, {
        "impact_basis": "fallback",
        "recoverable_clicks": round(recoverable_clicks, 1),
        **norm_meta,
    }


def score_structured_data_impact(
    *,
    search_visibility: float,
    ai_mention: float,
    site: SiteBusinessContext,
) -> tuple[float, dict[str, Any]]:
    gap = max(0.0, search_visibility - ai_mention)
    if site.site_lead_rate_pct is not None and site.period_leads > 0:
        estimated = site.period_leads * gap * 0.25
        impact, norm_meta = normalize_business_impact(
            site=site,
            estimated_incremental_leads=estimated,
            data_confidence="medium",
        )
        return impact, {
            "impact_basis": "downstream",
            "estimated_lead_opportunity": round(estimated, 2),
            "estimated_incremental_leads": round(estimated, 2),
            "visibility_gap": round(gap, 3),
            "site_lead_rate_pct": round(site.site_lead_rate_pct, 2),
            **norm_meta,
        }

    impact, norm_meta = normalize_business_impact(
        site=site,
        recoverable_clicks=gap * 1000,
        strategic_priority=3,
        data_confidence="low",
    )
    return impact, {
        "impact_basis": "fallback",
        "visibility_gap": round(gap, 3),
        **norm_meta,
    }


def score_conversion_impact(
    *,
    sessions_current: float,
    current_rate: float,
    previous_rate: float,
    site: SiteBusinessContext,
) -> tuple[float, dict[str, Any]]:
    rate_drop = max(0.0, previous_rate - current_rate)
    leads_at_risk = sessions_current * (rate_drop / 100.0)
    impact, norm_meta = normalize_business_impact(
        site=site,
        leads_at_risk=leads_at_risk if leads_at_risk > 0 else None,
        sessions=sessions_current,
        recoverable_clicks=0,
        data_confidence="high" if leads_at_risk > 0 else "low",
    )

    return impact, {
        "impact_basis": "downstream" if leads_at_risk > 0 else "fallback",
        "leads_at_risk": round(leads_at_risk, 2),
        "estimated_leads_at_risk": round(leads_at_risk, 2),
        "lead_rate_drop_pct_points": round(rate_drop, 2),
        "site_lead_rate_pct": round(site.site_lead_rate_pct, 2) if site.site_lead_rate_pct else None,
        "period_sessions": site.period_sessions,
        "period_leads": site.period_leads,
        **norm_meta,
    }
