"""Deterministic Decision Engine — diagnose() over validated facts only."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.decisions.ctr_curve import expected_ctr_percent
from app.models.client import Client
from app.models.crawl import FactCrawlPageSnapshot
from app.models.decision import DiagnosticLayer, GrowthAction
from app.models.ga4 import FactGa4Event, FactGa4Traffic
from app.models.gsc import FactGscPage
from app.services.dashboard import (
    _effective_range,
    _lead_event_names,
    _load_watermarks,
    _resolve_search_visibility,
    build_dashboard,
    previous_period,
)

SCORE_FORMULA = "0.4·impact + 0.3·confidence + 0.2·urgency + 0.1·(100−effort)"
DEFAULT_TOP_N = 14
MIN_PAGE_IMPRESSIONS = 30

LEVER_LABELS: dict[str, str] = {
    GrowthAction.TECHNICAL_SEO.value: "Technical SEO & Indexation",
    GrowthAction.INTERNAL_LINKING.value: "Internal Linking & Architecture",
    GrowthAction.SERP_CTR.value: "SERP / CTR Optimization",
    GrowthAction.STRUCTURED_DATA_AI.value: "Structured Data & Entities",
    GrowthAction.CONVERSION_PATH.value: "Conversion Path Optimization",
    "content_expansion": "Content Expansion / Optimization",
}


@dataclass(frozen=True)
class LeverInputs:
    confidence: float
    urgency: float
    effort: float
    stage: DiagnosticLayer
    recommended_action: str
    success_metric: str


LEVER_INPUTS: dict[str, LeverInputs] = {
    GrowthAction.TECHNICAL_SEO.value: LeverInputs(
        confidence=85,
        urgency=80,
        effort=45,
        stage=DiagnosticLayer.VISIBILITY,
        recommended_action="Resolve indexation, status, or canonical issues on affected URLs.",
        success_metric="Page becomes indexable with a healthy status code and self-canonical URL.",
    ),
    GrowthAction.INTERNAL_LINKING.value: LeverInputs(
        confidence=75,
        urgency=55,
        effort=30,
        stage=DiagnosticLayer.VISIBILITY,
        recommended_action="Add internal links from mapped authoritative pages.",
        success_metric="Inbound internal links meet the word-count floor while rankings hold or improve.",
    ),
    GrowthAction.SERP_CTR.value: LeverInputs(
        confidence=80,
        urgency=50,
        effort=20,
        stage=DiagnosticLayer.TRAFFIC,
        recommended_action="Improve title/meta alignment and SERP snippet appeal for this page.",
        success_metric="CTR reaches at least half the expected rate for its average position.",
    ),
    GrowthAction.STRUCTURED_DATA_AI.value: LeverInputs(
        confidence=65,
        urgency=45,
        effort=55,
        stage=DiagnosticLayer.VISIBILITY,
        recommended_action="Strengthen entity clarity, structured data, and citation-ready content.",
        success_metric="AI visibility improves toward parity with search visibility.",
    ),
    GrowthAction.CONVERSION_PATH.value: LeverInputs(
        confidence=70,
        urgency=65,
        effort=40,
        stage=DiagnosticLayer.CONVERSION,
        recommended_action="Audit the CTA/form/phone path on affected landing pages.",
        success_metric="Managed lead rate recovers while sessions remain stable.",
    ),
    "content_expansion": LeverInputs(
        confidence=60,
        urgency=40,
        effort=50,
        stage=DiagnosticLayer.VISIBILITY,
        recommended_action="Evaluate topic coverage during monthly content planning.",
        success_metric="Priority topic demand is covered by a suitable page.",
    ),
}


@dataclass
class LeverFinding:
    rule_key: str
    lever: str
    stage: DiagnosticLayer
    diagnosis: str
    recommended_action: str
    success_metric: str
    evidence_json: dict[str, Any]
    baseline_metrics_json: dict[str, Any]
    impact: float
    confidence: float
    urgency: float
    effort: float
    priority_score: float
    page_url: str | None = None
    query: str | None = None


@dataclass
class LeverSummary:
    lever: str
    label: str
    findings_count: int
    status: str


@dataclass
class DiagnoseResult:
    ready: bool
    message: str | None
    readiness: dict[str, bool]
    formula: str
    levers: list[LeverSummary] = field(default_factory=list)
    recommendations: list[LeverFinding] = field(default_factory=list)


def score_finding(*, impact: float, confidence: float, urgency: float, effort: float) -> float:
    return round(0.40 * impact + 0.30 * confidence + 0.20 * urgency + 0.10 * (100 - effort), 1)


def impact_from_impressions(impressions: float) -> float:
    return min(100.0, round(impressions / 40.0, 1))


def _rule_key(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]


def _link_floor(word_count: int) -> int:
    if word_count < 1000:
        return 2
    if word_count < 2000:
        return 5
    return 10


def _normalize_canonical(url: str | None) -> str | None:
    if not url:
        return None
    return url.strip().rstrip("/").lower()


@dataclass
class PageDemand:
    normalized_url: str
    impressions: float
    clicks: float
    average_position: float
    ctr_percent: float


def _load_page_demand(
    db: Session,
    *,
    client_id: UUID,
    period: tuple[date, date] | None,
) -> list[PageDemand]:
    if period is None:
        return []
    start, end = period
    rows = (
        db.query(
            FactGscPage.normalized_url,
            func.coalesce(func.sum(FactGscPage.impressions), 0),
            func.coalesce(func.sum(FactGscPage.clicks), 0),
            func.coalesce(
                func.sum(FactGscPage.average_position * FactGscPage.impressions),
                0,
            ),
        )
        .filter(
            FactGscPage.client_id == client_id,
            FactGscPage.date >= start,
            FactGscPage.date <= end,
        )
        .group_by(FactGscPage.normalized_url)
        .all()
    )
    pages: list[PageDemand] = []
    for url, impressions, clicks, weighted_position in rows:
        impressions_f = float(impressions or 0)
        if impressions_f < MIN_PAGE_IMPRESSIONS:
            continue
        clicks_f = float(clicks or 0)
        avg_position = float(weighted_position or 0) / impressions_f if impressions_f else 0.0
        ctr_percent = (clicks_f / impressions_f) * 100 if impressions_f else 0.0
        pages.append(
            PageDemand(
                normalized_url=str(url),
                impressions=impressions_f,
                clicks=clicks_f,
                average_position=avg_position,
                ctr_percent=ctr_percent,
            )
        )
    return pages


def _load_crawl_by_url(db: Session, client_id: UUID) -> dict[str, FactCrawlPageSnapshot]:
    rows = db.query(FactCrawlPageSnapshot).filter(FactCrawlPageSnapshot.client_id == client_id).all()
    return {row.normalized_url: row for row in rows}


def _make_finding(
    *,
    lever: str,
    rule_key: str,
    diagnosis: str,
    evidence_json: dict[str, Any],
    baseline_metrics_json: dict[str, Any],
    impact: float,
    page_url: str | None = None,
    query: str | None = None,
) -> LeverFinding:
    inputs = LEVER_INPUTS[lever]
    priority_score = score_finding(
        impact=impact,
        confidence=inputs.confidence,
        urgency=inputs.urgency,
        effort=inputs.effort,
    )
    return LeverFinding(
        rule_key=rule_key,
        lever=lever,
        stage=inputs.stage,
        diagnosis=diagnosis,
        recommended_action=inputs.recommended_action,
        success_metric=inputs.success_metric,
        evidence_json=evidence_json,
        baseline_metrics_json=baseline_metrics_json,
        impact=impact,
        confidence=inputs.confidence,
        urgency=inputs.urgency,
        effort=inputs.effort,
        priority_score=priority_score,
        page_url=page_url,
        query=query,
    )


def _technical_finding(page: PageDemand, crawl: FactCrawlPageSnapshot) -> LeverFinding | None:
    canonical = _normalize_canonical(crawl.canonical_url)
    page_norm = _normalize_canonical(page.normalized_url)
    canonicalized_elsewhere = canonical is not None and page_norm is not None and canonical != page_norm
    status_bad = crawl.status_code is not None and crawl.status_code >= 400
    if crawl.indexable and not status_bad and not canonicalized_elsewhere:
        return None
    impact = impact_from_impressions(page.impressions)
    diagnosis = f"Technical issue on {page.normalized_url}"
    if not crawl.indexable:
        diagnosis = f"Non-indexable page with demand: {page.normalized_url}"
    elif status_bad:
        diagnosis = f"HTTP {crawl.status_code} on page with demand: {page.normalized_url}"
    elif canonicalized_elsewhere:
        diagnosis = f"Canonicalized elsewhere: {page.normalized_url}"
    return _make_finding(
        lever=GrowthAction.TECHNICAL_SEO.value,
        rule_key=_rule_key("technical", page.normalized_url),
        diagnosis=diagnosis,
        evidence_json={
            "impressions": int(page.impressions),
            "indexable": crawl.indexable,
            "status_code": crawl.status_code,
            "canonical_url": crawl.canonical_url,
        },
        baseline_metrics_json={
            "impressions": page.impressions,
            "average_position": round(page.average_position, 1),
        },
        impact=impact,
        page_url=page.normalized_url,
    )


def _internal_linking_finding(page: PageDemand, crawl: FactCrawlPageSnapshot) -> LeverFinding | None:
    if page.average_position < 4 or page.average_position > 20:
        return None
    floor = _link_floor(crawl.word_count)
    if crawl.inbound_internal_links >= floor:
        return None
    impact = impact_from_impressions(page.impressions)
    diagnosis = (
        f"Under-linked page ranking {page.average_position:.0f}: {page.normalized_url}"
    )
    return _make_finding(
        lever=GrowthAction.INTERNAL_LINKING.value,
        rule_key=_rule_key("internal_linking", page.normalized_url),
        diagnosis=diagnosis,
        evidence_json={
            "position": round(page.average_position, 1),
            "inbound_internal_links": crawl.inbound_internal_links,
            "link_floor": floor,
            "word_count": crawl.word_count,
            "impressions": int(page.impressions),
        },
        baseline_metrics_json={
            "impressions": page.impressions,
            "average_position": round(page.average_position, 1),
        },
        impact=impact,
        page_url=page.normalized_url,
    )


def _serp_ctr_finding(page: PageDemand) -> LeverFinding | None:
    if page.impressions < 1000:
        return None
    if page.average_position < 2 or page.average_position > 10:
        return None
    expected = expected_ctr_percent(page.average_position)
    if page.ctr_percent >= expected * 0.5:
        return None
    impact = impact_from_impressions(page.impressions)
    diagnosis = (
        f"High-impression page underperforming CTR: {page.normalized_url} "
        f"(position {page.average_position:.1f}, CTR {page.ctr_percent:.2f}% vs expected {expected:.2f}%)"
    )
    return _make_finding(
        lever=GrowthAction.SERP_CTR.value,
        rule_key=_rule_key("serp_ctr", page.normalized_url),
        diagnosis=diagnosis,
        evidence_json={
            "impressions": int(page.impressions),
            "clicks": int(page.clicks),
            "ctr_percent": round(page.ctr_percent, 2),
            "expected_ctr_percent": expected,
            "average_position": round(page.average_position, 1),
        },
        baseline_metrics_json={
            "impressions": page.impressions,
            "ctr_percent": round(page.ctr_percent, 2),
        },
        impact=impact,
        page_url=page.normalized_url,
    )


def _per_page_cascade(
    pages: list[PageDemand],
    crawl_by_url: dict[str, FactCrawlPageSnapshot],
    *,
    crawl_ready: bool,
) -> list[LeverFinding]:
    findings: list[LeverFinding] = []
    for page in pages:
        crawl = crawl_by_url.get(page.normalized_url)
        finding: LeverFinding | None = None
        if crawl_ready and crawl is not None:
            finding = _technical_finding(page, crawl)
            if finding is None:
                finding = _internal_linking_finding(page, crawl)
        if finding is None:
            finding = _serp_ctr_finding(page)
        if finding is not None:
            findings.append(finding)
    return findings


def _structured_data_portfolio(
    db: Session,
    client_id: UUID,
    period: tuple[date, date] | None,
    ai_mention: float | None,
) -> LeverFinding | None:
    if period is None or ai_mention is None:
        return None
    search_visibility, _ = _resolve_search_visibility(db, client_id, period)
    if search_visibility is None or search_visibility < 0.10:
        return None
    if ai_mention >= search_visibility / 2:
        return None
    impact = min(100.0, round(search_visibility * 100, 1))
    return _make_finding(
        lever=GrowthAction.STRUCTURED_DATA_AI.value,
        rule_key=_rule_key("structured_data_gap", str(client_id)),
        diagnosis="Search visibility is healthy but AI visibility lags search visibility.",
        evidence_json={
            "search_visibility": search_visibility,
            "ai_mention_presence_pct": ai_mention,
        },
        baseline_metrics_json={
            "search_visibility": search_visibility,
            "ai_mention_presence_pct": ai_mention,
        },
        impact=impact,
    )


def _managed_lead_rate(
    db: Session,
    client_id: UUID,
    lead_events: list[str],
    period: tuple[date, date] | None,
) -> float | None:
    if period is None or not lead_events:
        return None
    start, end = period
    leads = (
        db.query(func.coalesce(func.sum(FactGa4Event.event_count), 0))
        .filter(
            FactGa4Event.client_id == client_id,
            FactGa4Event.date >= start,
            FactGa4Event.date <= end,
            FactGa4Event.event_name.in_(lead_events),
        )
        .scalar()
    )
    sessions = (
        db.query(func.coalesce(func.sum(FactGa4Traffic.sessions), 0))
        .filter(
            FactGa4Traffic.client_id == client_id,
            FactGa4Traffic.date >= start,
            FactGa4Traffic.date <= end,
        )
        .scalar()
    )
    sessions_f = float(sessions or 0)
    if sessions_f <= 0:
        return None
    return (float(leads or 0) / sessions_f) * 100


def _conversion_portfolio(
    db: Session,
    client: Client,
    *,
    from_date: date,
    to_date: date,
    dashboard: dict[str, Any],
) -> LeverFinding | None:
    lead_events = _lead_event_names(db, client.id)
    if not lead_events:
        return None
    current_period = (from_date, to_date)
    prev_from, prev_to = previous_period(from_date, to_date)
    previous_period_range = (prev_from, prev_to)

    current_rate = _managed_lead_rate(db, client.id, lead_events, current_period)
    previous_rate = _managed_lead_rate(db, client.id, lead_events, previous_period_range)
    sessions_current = dashboard.get("traffic", {}).get("ga4_sessions", {}).get("current")
    sessions_previous = dashboard.get("traffic", {}).get("ga4_sessions", {}).get("previous")
    if current_rate is None or previous_rate is None:
        return None
    if sessions_current is None or sessions_previous is None or sessions_previous <= 0:
        return None

    sessions_change_pct = ((float(sessions_current) - float(sessions_previous)) / float(sessions_previous)) * 100
    if sessions_change_pct < -5:
        return None
    if previous_rate <= 0:
        lead_rate_change_pct = -100.0 if current_rate <= 0 else 100.0
    else:
        lead_rate_change_pct = ((current_rate - previous_rate) / previous_rate) * 100
    if lead_rate_change_pct > -10:
        return None

    impact = min(100.0, round(abs(lead_rate_change_pct), 1))
    return _make_finding(
        lever=GrowthAction.CONVERSION_PATH.value,
        rule_key=_rule_key("conversion_path", str(client.id), from_date.isoformat(), to_date.isoformat()),
        diagnosis="Managed traffic holding but lead rate falling",
        evidence_json={
            "lead_rate_change_pct": round(lead_rate_change_pct, 1),
            "sessions_change_pct": round(sessions_change_pct, 1),
            "tracking_validated": True,
        },
        baseline_metrics_json={
            "lead_rate_current": round(current_rate, 2),
            "lead_rate_previous": round(previous_rate, 2),
            "sessions_current": float(sessions_current),
            "sessions_previous": float(sessions_previous),
        },
        impact=impact,
    )


def _lever_summaries(findings: list[LeverFinding]) -> list[LeverSummary]:
    counts: dict[str, int] = {key: 0 for key in LEVER_LABELS}
    for finding in findings:
        counts[finding.lever] = counts.get(finding.lever, 0) + 1
    summaries: list[LeverSummary] = []
    for lever, label in LEVER_LABELS.items():
        count = counts.get(lever, 0)
        summaries.append(
            LeverSummary(
                lever=lever,
                label=label,
                findings_count=count,
                status="findings" if count else "clear",
            )
        )
    return summaries


def diagnose(
    db: Session,
    client: Client,
    *,
    from_date: date,
    to_date: date,
    top_n: int = DEFAULT_TOP_N,
) -> DiagnoseResult:
    watermarks = _load_watermarks(db, client.id)
    gsc_period = _effective_range(from_date, to_date, watermarks.get("gsc_pages"))
    ga4_period = _effective_range(from_date, to_date, watermarks.get("ga4"))
    ser_period = _effective_range(from_date, to_date, watermarks.get("se_ranking_search"))
    ai_period = _effective_range(from_date, to_date, watermarks.get("se_ranking_ai"))

    gsc_rows = 0
    if gsc_period is not None:
        start, end = gsc_period
        gsc_rows = (
            db.query(func.count())
            .select_from(FactGscPage)
            .filter(
                FactGscPage.client_id == client.id,
                FactGscPage.date >= start,
                FactGscPage.date <= end,
            )
            .scalar()
            or 0
        )
    crawl_ready = (
        db.query(func.count())
        .select_from(FactCrawlPageSnapshot)
        .filter(FactCrawlPageSnapshot.client_id == client.id)
        .scalar()
        or 0
    ) > 0

    readiness = {
        "search_console": gsc_rows > 0,
        "crawl_audit": crawl_ready,
    }
    if gsc_rows == 0:
        return DiagnoseResult(
            ready=False,
            message="Search Console page facts are required before the Decision Engine can run.",
            readiness=readiness,
            formula=SCORE_FORMULA,
            levers=_lever_summaries([]),
        )

    dashboard = build_dashboard(db, client, from_date, to_date)
    pages = _load_page_demand(db, client_id=client.id, period=gsc_period)
    crawl_by_url = _load_crawl_by_url(db, client.id)

    findings: list[LeverFinding] = []
    findings.extend(_per_page_cascade(pages, crawl_by_url, crawl_ready=crawl_ready))

    ai_mention = dashboard.get("visibility", {}).get("ai", {}).get("mention_presence", {}).get("current")
    structured = _structured_data_portfolio(db, client.id, ser_period, ai_mention)
    if structured is not None:
        findings.append(structured)

    conversion = _conversion_portfolio(
        db,
        client,
        from_date=from_date,
        to_date=to_date,
        dashboard=dashboard,
    )
    if conversion is not None:
        findings.append(conversion)

    findings.sort(key=lambda row: row.priority_score, reverse=True)
    top_findings = findings[:top_n]

    return DiagnoseResult(
        ready=True,
        message=None,
        readiness=readiness,
        formula=SCORE_FORMULA,
        levers=_lever_summaries(findings),
        recommendations=top_findings,
    )
