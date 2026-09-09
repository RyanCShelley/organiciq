"""Deterministic Decision Engine — diagnose() over validated facts only."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.decisions.ctr_curve import (
    benchmark_source_label,
    expected_ctr_percent,
    is_ctr_underperforming,
    recoverable_clicks_at_threshold,
)
from app.decisions.thresholds import merge_thresholds
from app.models.client import Client
from app.models.crawl import FactCrawlPageIssue, FactCrawlPageSnapshot
from app.models.decision import DecisionThreshold, DiagnosticLayer, GrowthAction
from app.models.ga4 import FactGa4Event, FactGa4Traffic
from app.models.gsc import FactGscPage
from app.models.job import DataWatermark, ValidationStatus
from app.models.seranking import FactSerAiCheck, FactSerAiPrompt, FactSerKeyword
from app.services.action_promotion import promote_findings
from app.services.dashboard import (
    _effective_range,
    _lead_event_names,
    _load_watermarks,
    build_dashboard,
    previous_period,
)
from app.services.decision_impact import (
    ADVISORY_AUDIT_SIGNALS,
    LeadRateContext,
    PageBusinessContext,
    SiteBusinessContext,
    build_impact_explanation,
    compute_page_type_lead_rates,
    compute_topic_lead_rates,
    load_page_business_contexts,
    load_site_business_context,
    portfolio_urgency_adjustment,
    score_ai_visibility_impact,
    score_conversion_impact,
    score_internal_linking_impact,
    score_serp_ctr_impact,
    score_technical_impact,
    with_p90_sessions,
)
from app.services.decision_types import DiagnoseResult, LeverFinding, LeverSummary
from app.services.page_eligibility import PageClassification, PageType, classify_pages

SCORE_FORMULA = (
    "0.6·impact + (0.15·confidence + 0.15·urgency + 0.1·(100−effort)) × min(1, impact÷20)"
)
PRIORITY_IMPACT_WEIGHT = 0.60
PRIORITY_CONFIDENCE_WEIGHT = 0.15
PRIORITY_URGENCY_WEIGHT = 0.15
PRIORITY_EFFORT_WEIGHT = 0.10
PRIORITY_IMPACT_RELEVANCE_SCALE = 20.0
DEFAULT_TOP_N = 25
MIN_PAGE_IMPRESSIONS = 30

LEVER_LABELS: dict[str, str] = {
    GrowthAction.TECHNICAL_SEO.value: "Technical SEO & Indexation",
    GrowthAction.INTERNAL_LINKING.value: "Internal Linking & Site Architecture",
    GrowthAction.SERP_CTR.value: "SERP & CTR Optimization",
    GrowthAction.AI_VISIBILITY.value: "Search & AI Visibility",
    GrowthAction.CONVERSION_PATH.value: "Conversion Path Optimization",
}

SEARCH_OPPORTUNITY_LEVER = "search_opportunity"
SEARCH_OPPORTUNITY_LABEL = "Search Opportunity"


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
        recommended_action=(
            "Resolve the flagged technical issue (status, redirect, indexation, "
            "canonical, or core meta) on the affected URL or site."
        ),
        success_metric=(
            "Issue clears in the next Website Audit and the page remains indexable "
            "with healthy status and meta."
        ),
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
    GrowthAction.AI_VISIBILITY.value: LeverInputs(
        confidence=75,
        urgency=60,
        effort=40,
        stage=DiagnosticLayer.VISIBILITY,
        recommended_action=(
            "Recover search rankings for tracked keywords and improve AI citation "
            "presence for tracked prompts."
        ),
        success_metric=(
            "Keywords return to the target rank band and prompts earn consistent "
            "AI citations/mentions."
        ),
    ),
    GrowthAction.CONVERSION_PATH.value: LeverInputs(
        confidence=70,
        urgency=65,
        effort=40,
        stage=DiagnosticLayer.CONVERSION,
        recommended_action="Audit the CTA/form/phone path on affected landing pages.",
        success_metric="Managed lead rate recovers while sessions remain stable.",
    ),
}


def score_finding(
    *,
    impact: float,
    confidence: float,
    urgency: float,
    effort: float,
) -> float:
    """Impact-led priority: secondary inputs only contribute when impact is meaningful."""
    impact_relevance = min(1.0, max(0.0, impact / PRIORITY_IMPACT_RELEVANCE_SCALE))
    secondary = (
        PRIORITY_CONFIDENCE_WEIGHT * confidence
        + PRIORITY_URGENCY_WEIGHT * urgency
        + PRIORITY_EFFORT_WEIGHT * (100.0 - effort)
    )
    score = PRIORITY_IMPACT_WEIGHT * impact + secondary * impact_relevance
    return round(min(100.0, score), 1)


def _rule_key(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]


def _link_floor(word_count: int) -> int:
    if word_count < 500:
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


def _gsc_fact_bounds(db: Session, client_id: UUID) -> tuple[date | None, date | None]:
    min_date = (
        db.query(func.min(FactGscPage.date))
        .filter(FactGscPage.client_id == client_id)
        .scalar()
    )
    max_date = (
        db.query(func.max(FactGscPage.date))
        .filter(FactGscPage.client_id == client_id)
        .scalar()
    )
    return min_date, max_date


def _resolve_gsc_analysis_period(
    *,
    from_date: date,
    to_date: date,
    watermark: DataWatermark | None,
    fact_min: date | None,
    fact_max: date | None,
) -> tuple[tuple[date, date] | None, str | None, str | None]:
    """Return (analysis period, blocking message, partial coverage note)."""
    if watermark is None or watermark.fact_through_date is None:
        return None, "Search Console has not been synced for this client yet.", None
    if watermark.validation_status != ValidationStatus.PASSED:
        return None, "Search Console data has not passed validation yet.", None
    if fact_min is None or fact_max is None:
        return (
            None,
            "Search Console page facts are required before the Decision Engine can run.",
            None,
        )

    sync_through = watermark.fact_through_date
    analysis_from = max(from_date, fact_min)
    analysis_to = min(to_date, sync_through, fact_max)
    if analysis_from > analysis_to:
        return (
            None,
            (
                f"No Search Console page facts overlap {from_date.isoformat()} to {to_date.isoformat()}. "
                f"Available facts: {fact_min.isoformat()} to {sync_through.isoformat()}."
            ),
            None,
        )

    # Apply coverage gaps (including normal GSC lag) to analysis_from/to silently.
    return (analysis_from, analysis_to), None, None


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


def _load_audit_issues(
    db: Session, client_id: UUID
) -> tuple[dict[str, set[str]], set[str]]:
    """Return (page_url -> issue codes, site-level issue codes)."""
    rows = db.query(FactCrawlPageIssue).filter(FactCrawlPageIssue.client_id == client_id).all()
    by_url: dict[str, set[str]] = {}
    site_codes: set[str] = set()
    for row in rows:
        if row.normalized_url:
            by_url.setdefault(row.normalized_url, set()).add(row.issue_code)
        else:
            site_codes.add(row.issue_code)
    return by_url, site_codes


ROBOTS_BLOCKING_CODES = frozenset({"robots_disallow_crawling"})
ROBOTS_ADVISORY_CODES = frozenset(
    {"no_robots", "robots_not_accessible", "robots_has_errors"}
)


@dataclass(frozen=True)
class DetectedTechnicalSignal:
    audit_signal: str
    issue_code: str | None
    diagnosis: str


def detect_technical_signal(
    page_url: str,
    crawl: FactCrawlPageSnapshot,
    *,
    page_issue_codes: set[str] | None = None,
    crawl_by_url: dict[str, FactCrawlPageSnapshot] | None = None,
) -> DetectedTechnicalSignal | None:
    """Priority-ordered Technical SEO detector for a single page."""
    codes = page_issue_codes or set()
    canonical = _normalize_canonical(crawl.canonical_url)
    page_norm = _normalize_canonical(page_url)
    canonicalized_elsewhere = canonical is not None and page_norm is not None and canonical != page_norm
    status = crawl.status_code
    status_bad = status is not None and status >= 400
    is_redirect = status is not None and 300 <= status < 400

    redirect_target_bad = False
    if crawl.redirect_url and crawl_by_url:
        target = crawl_by_url.get(crawl.redirect_url)
        if target is not None and target.status_code is not None and target.status_code >= 400:
            redirect_target_bad = True

    if status_bad:
        return DetectedTechnicalSignal(
            audit_signal="status_error",
            issue_code=None,
            diagnosis=f"HTTP {status} on page with demand: {page_url}",
        )
    if "redirect45xx" in codes or (is_redirect and redirect_target_bad):
        return DetectedTechnicalSignal(
            audit_signal="broken_redirect",
            issue_code="redirect45xx" if "redirect45xx" in codes else None,
            diagnosis=f"Broken redirect on page with demand: {page_url}",
        )
    if "redirect_chain" in codes or crawl.redirect_count >= 3:
        return DetectedTechnicalSignal(
            audit_signal="redirect_chain",
            issue_code="redirect_chain" if "redirect_chain" in codes else None,
            diagnosis=f"Redirect chain on page with demand: {page_url}",
        )
    if not crawl.indexable:
        return DetectedTechnicalSignal(
            audit_signal="non_indexable",
            issue_code=None,
            diagnosis=f"Non-indexable page with demand: {page_url}",
        )
    if canonicalized_elsewhere:
        return DetectedTechnicalSignal(
            audit_signal="canonical_elsewhere",
            issue_code=None,
            diagnosis=f"Canonicalized elsewhere: {page_url}",
        )
    missing_title = crawl.title == "" or "title_missing" in codes
    missing_description = crawl.description == "" or "description_missing" in codes
    if missing_title or missing_description:
        issue_code = "title_missing" if missing_title else "description_missing"
        return DetectedTechnicalSignal(
            audit_signal="missing_meta",
            issue_code=issue_code,
            diagnosis=f"Missing core meta on page with demand: {page_url}",
        )
    duplicate = (
        crawl.title_duplicate
        or crawl.description_duplicate
        or "title_duplicate" in codes
        or "description_duplicate" in codes
    )
    if duplicate:
        issue_code = (
            "title_duplicate"
            if crawl.title_duplicate or "title_duplicate" in codes
            else "description_duplicate"
        )
        return DetectedTechnicalSignal(
            audit_signal="duplicate_meta",
            issue_code=issue_code,
            diagnosis=f"Duplicate meta on page with demand: {page_url}",
        )
    return None


def _technical_finding(
    page: PageDemand,
    crawl: FactCrawlPageSnapshot,
    *,
    page_ctx: PageBusinessContext | None,
    site: SiteBusinessContext,
    lead_rate_ctx: LeadRateContext | None = None,
    classification: PageClassification | None = None,
    page_issue_codes: set[str] | None = None,
    crawl_by_url: dict[str, FactCrawlPageSnapshot] | None = None,
) -> LeverFinding | None:
    detected = detect_technical_signal(
        page.normalized_url,
        crawl,
        page_issue_codes=page_issue_codes,
        crawl_by_url=crawl_by_url,
    )
    if detected is None:
        return None

    assessment = score_technical_impact(
        impressions=page.impressions,
        clicks=page.clicks,
        average_position=page.average_position,
        indexable=crawl.indexable,
        status_code=crawl.status_code,
        canonicalized_elsewhere=detected.audit_signal == "canonical_elsewhere",
        page_ctx=page_ctx,
        site=site,
        classification=classification,
        lead_rate_ctx=lead_rate_ctx,
        audit_signal=detected.audit_signal,
    )
    urgency_override = None
    if assessment.critical_override:
        urgency_override = max(LEVER_INPUTS[GrowthAction.TECHNICAL_SEO.value].urgency, 90.0)
    return _make_finding(
        lever=GrowthAction.TECHNICAL_SEO.value,
        rule_key=_rule_key("technical", page.normalized_url),
        diagnosis=detected.diagnosis,
        evidence_json={
            "impressions": int(page.impressions),
            "indexable": crawl.indexable,
            "status_code": crawl.status_code,
            "canonical_url": crawl.canonical_url,
            "title": crawl.title,
            "description": crawl.description,
            "title_duplicate": crawl.title_duplicate,
            "description_duplicate": crawl.description_duplicate,
            "redirect_url": crawl.redirect_url,
            "redirect_count": crawl.redirect_count,
            "audit_signal": detected.audit_signal,
            "issue_code": detected.issue_code,
            "promotion_class": (
                "advisory" if detected.audit_signal in ADVISORY_AUDIT_SIGNALS else "actionable"
            ),
            **assessment.evidence,
        },
        baseline_metrics_json={
            "impressions": page.impressions,
            "average_position": round(page.average_position, 1),
        },
        impact=assessment.impact,
        severity=assessment.severity,
        urgency_override=urgency_override,
        page_url=page.normalized_url,
    )


def _site_technical_findings(
    site_codes: set[str],
    *,
    site: SiteBusinessContext,
    client_id: UUID,
) -> list[LeverFinding]:
    findings: list[LeverFinding] = []
    if "sitemap_missing" in site_codes:
        assessment = score_technical_impact(
            impressions=0,
            clicks=0,
            average_position=10,
            indexable=True,
            status_code=200,
            canonicalized_elsewhere=False,
            page_ctx=None,
            site=site,
            audit_signal="sitemap_missing",
        )
        findings.append(
            _make_finding(
                lever=GrowthAction.TECHNICAL_SEO.value,
                rule_key=_rule_key("technical_sitemap", str(client_id)),
                diagnosis="Website Audit reports the XML sitemap is missing.",
                evidence_json={
                    "audit_signal": "sitemap_missing",
                    "issue_code": "sitemap_missing",
                    "promotion_class": "advisory",
                    **assessment.evidence,
                },
                baseline_metrics_json={},
                impact=assessment.impact,
                severity=assessment.severity,
            )
        )

    robots_codes = site_codes & (ROBOTS_BLOCKING_CODES | ROBOTS_ADVISORY_CODES)
    if robots_codes:
        blocking = sorted(robots_codes & ROBOTS_BLOCKING_CODES)
        audit_signal = "robots_blocking" if blocking else "robots_advisory"
        primary_code = blocking[0] if blocking else sorted(robots_codes)[0]
        assessment = score_technical_impact(
            impressions=0,
            clicks=0,
            average_position=10,
            indexable=True,
            status_code=200,
            canonicalized_elsewhere=False,
            page_ctx=None,
            site=site,
            audit_signal=audit_signal,
        )
        urgency_override = None
        if assessment.critical_override:
            urgency_override = max(LEVER_INPUTS[GrowthAction.TECHNICAL_SEO.value].urgency, 90.0)
        findings.append(
            _make_finding(
                lever=GrowthAction.TECHNICAL_SEO.value,
                rule_key=_rule_key("technical_robots", str(client_id)),
                diagnosis=(
                    "Website Audit reports robots.txt is blocking crawl."
                    if audit_signal == "robots_blocking"
                    else "Website Audit reports robots.txt problems."
                ),
                evidence_json={
                    "audit_signal": audit_signal,
                    "issue_code": primary_code,
                    "issue_codes": sorted(robots_codes),
                    "promotion_class": (
                        "advisory" if audit_signal in ADVISORY_AUDIT_SIGNALS else "actionable"
                    ),
                    **assessment.evidence,
                },
                baseline_metrics_json={},
                impact=assessment.impact,
                severity=assessment.severity,
                urgency_override=urgency_override,
            )
        )
    return findings


def _load_thresholds(db: Session, client_id: UUID) -> dict[str, float | int]:
    row = db.query(DecisionThreshold).filter(DecisionThreshold.client_id == client_id).one_or_none()
    if row is None:
        return merge_thresholds(None)
    return merge_thresholds(row.thresholds)


def _lead_rate_context_for_url(
    url: str,
    classifications: dict[str, PageClassification],
    page_type_rates: dict[str, float],
    topic_rates: dict[str, float],
) -> LeadRateContext:
    classification = classifications.get(url)
    return LeadRateContext(
        page_type=classification.page_type if classification else None,
        page_type_rates=page_type_rates,
        topic=classification.priority_topic if classification else None,
        topic_rates=topic_rates,
    )


def _enrich_finding(
    finding: LeverFinding,
    *,
    classification: PageClassification | None,
    page_ctx: PageBusinessContext | None,
) -> None:
    if classification is not None:
        finding.evidence_json.update(classification.as_evidence())
    finding.evidence_json["impact_explanation"] = build_impact_explanation(
        finding.evidence_json,
        classification=classification,
        page_ctx=page_ctx,
    )
    if classification is not None and classification.priority_topic:
        finding.finding_group_key = f"topic:{classification.priority_topic}:{finding.lever}"
    else:
        finding.finding_group_key = finding.rule_key


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
    urgency_override: float | None = None,
    severity: float | None = None,
) -> LeverFinding:
    inputs = LEVER_INPUTS[lever]
    urgency = urgency_override if urgency_override is not None else inputs.urgency
    priority_score = score_finding(
        impact=impact,
        confidence=inputs.confidence,
        urgency=urgency,
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
        urgency=urgency,
        effort=inputs.effort,
        priority_score=priority_score,
        page_url=page_url,
        query=query,
        severity=severity,
    )


def _internal_linking_finding(
    page: PageDemand,
    crawl: FactCrawlPageSnapshot,
    *,
    page_ctx: PageBusinessContext | None,
    site: SiteBusinessContext,
    lead_rate_ctx: LeadRateContext | None = None,
    classification: PageClassification | None = None,
) -> LeverFinding | None:
    if page.average_position < 4 or page.average_position > 20:
        return None
    floor = _link_floor(crawl.word_count)
    if crawl.inbound_internal_links >= floor:
        return None
    impact, impact_evidence = score_internal_linking_impact(
        impressions=page.impressions,
        clicks=page.clicks,
        average_position=page.average_position,
        page_ctx=page_ctx,
        site=site,
        lead_rate_ctx=lead_rate_ctx,
        strategic_priority=classification.strategic_priority if classification else 3,
    )
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
            "inlink_source": "se_ranking_audit",
            "link_floor": floor,
            "word_count": crawl.word_count,
            "impressions": int(page.impressions),
            **impact_evidence,
        },
        baseline_metrics_json={
            "impressions": page.impressions,
            "average_position": round(page.average_position, 1),
        },
        impact=impact,
        page_url=page.normalized_url,
    )


def _serp_ctr_finding(
    page: PageDemand,
    *,
    page_ctx: PageBusinessContext | None,
    site: SiteBusinessContext,
    lead_rate_ctx: LeadRateContext | None = None,
    classification: PageClassification | None = None,
) -> LeverFinding | None:
    if page.impressions < 1000:
        return None
    if page.average_position < 2 or page.average_position > 10:
        return None
    expected = expected_ctr_percent(page.average_position)
    if not is_ctr_underperforming(
        ctr_percent=page.ctr_percent,
        expected_ctr=expected,
        impressions=page.impressions,
    ):
        return None
    recoverable = float(recoverable_clicks_at_threshold(
        impressions=page.impressions,
        ctr_percent=page.ctr_percent,
        expected_ctr=expected,
    ))
    recoverable_int = int(round(recoverable))
    impact, impact_evidence = score_serp_ctr_impact(
        recoverable_clicks=recoverable,
        page_ctx=page_ctx,
        site=site,
        clicks=page.clicks,
        average_position=page.average_position,
        lead_rate_ctx=lead_rate_ctx,
        strategic_priority=classification.strategic_priority if classification else 3,
    )
    diagnosis = (
        f"Low CTR at position {page.average_position:.0f}: {page.normalized_url} "
        f"(CTR {page.ctr_percent:.2f}% vs expected {expected:.1f}% at pos {page.average_position:.1f}; "
        f"~{recoverable_int} clicks recoverable)"
    )
    return _make_finding(
        lever=GrowthAction.SERP_CTR.value,
        rule_key=_rule_key("serp_ctr", page.normalized_url),
        diagnosis=diagnosis,
        evidence_json={
            "impressions": int(page.impressions),
            "clicks": int(page.clicks),
            "ctr_percent": round(page.ctr_percent, 2),
            "expected_ctr_percent": round(expected, 2),
            "ctr_benchmark_source": benchmark_source_label(),
            "recoverable_clicks": recoverable_int,
            "average_position": round(page.average_position, 1),
            **impact_evidence,
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
    page_contexts: dict[str, PageBusinessContext],
    site: SiteBusinessContext,
    classifications: dict[str, PageClassification],
    page_type_rates: dict[str, float],
    topic_rates: dict[str, float],
    issues_by_url: dict[str, set[str]] | None = None,
) -> list[LeverFinding]:
    findings: list[LeverFinding] = []
    issue_map = issues_by_url or {}
    for page in pages:
        page_ctx = page_contexts.get(page.normalized_url)
        classification = classifications.get(page.normalized_url)
        lead_rate_ctx = _lead_rate_context_for_url(
            page.normalized_url,
            classifications,
            page_type_rates,
            topic_rates,
        )
        crawl = crawl_by_url.get(page.normalized_url)
        finding: LeverFinding | None = None
        if crawl_ready and crawl is not None:
            finding = _technical_finding(
                page,
                crawl,
                page_ctx=page_ctx,
                site=site,
                lead_rate_ctx=lead_rate_ctx,
                classification=classification,
                page_issue_codes=issue_map.get(page.normalized_url),
                crawl_by_url=crawl_by_url,
            )
            if finding is None:
                finding = _internal_linking_finding(
                    page,
                    crawl,
                    page_ctx=page_ctx,
                    site=site,
                    lead_rate_ctx=lead_rate_ctx,
                    classification=classification,
                )
        if finding is None:
            finding = _serp_ctr_finding(
                page,
                page_ctx=page_ctx,
                site=site,
                lead_rate_ctx=lead_rate_ctx,
                classification=classification,
            )
        if finding is not None:
            _enrich_finding(finding, classification=classification, page_ctx=page_ctx)
            findings.append(finding)
    return findings


def _search_opportunities(
    pages: list[PageDemand],
    *,
    actioned_urls: set[str],
    classifications: dict[str, PageClassification],
    thresholds: dict[str, float | int],
) -> list[LeverFinding]:
    # GEO Grader / structured-data enrichment for Content Opportunities is deferred.
    min_pos = int(thresholds["gsc_striking_distance_min_pos"])
    max_pos = int(thresholds["gsc_striking_distance_max_pos"])
    min_impressions = max(
        int(thresholds["gsc_striking_distance_min_impressions"]),
        int(thresholds.get("content_planning_min_impressions", 200)),
    )
    top_n = int(thresholds.get("content_planning_top_n", 50))
    candidates: list[tuple[float, LeverFinding]] = []

    for page in pages:
        if page.normalized_url in actioned_urls:
            continue
        if page.average_position < min_pos or page.average_position > max_pos:
            continue
        if page.impressions < min_impressions:
            continue

        classification = classifications.get(page.normalized_url)
        if classification is None or not classification.eligible_for_growth_action:
            continue
        if classification.page_type in {PageType.COMMERCIAL, PageType.CONVERSION, PageType.UTILITY}:
            continue
        if classification.page_type not in {PageType.INFORMATIONAL, PageType.CONSIDERATION}:
            continue
        if not classification.priority_topic and page.impressions < 500:
            continue

        finding = LeverFinding(
            rule_key=_rule_key("search_opportunity", page.normalized_url),
            lever=SEARCH_OPPORTUNITY_LEVER,
            stage=DiagnosticLayer.VISIBILITY,
            diagnosis=f"Striking-distance ranking opportunity: {page.normalized_url}",
            recommended_action="",
            success_metric="",
            evidence_json={
                "opportunity_type": "Striking-Distance Opportunity",
                "impressions": int(page.impressions),
                "average_position": round(page.average_position, 1),
                "clicks": int(page.clicks),
                "ctr_percent": round(page.ctr_percent, 2),
                "page_type": classification.page_type.value,
                "priority_topic": classification.priority_topic,
            },
            baseline_metrics_json={
                "impressions": page.impressions,
                "average_position": round(page.average_position, 1),
            },
            impact=0.0,
            confidence=0.0,
            urgency=0.0,
            effort=0.0,
            priority_score=0.0,
            page_url=page.normalized_url,
        )
        candidates.append((page.impressions, finding))

    candidates.sort(key=lambda row: row[0], reverse=True)
    return [finding for _, finding in candidates[:top_n]]


def _rank_position(value: Any) -> float | None:
    if value is None:
        return None
    try:
        position = float(value)
    except (TypeError, ValueError):
        return None
    if position <= 0:
        return None
    return position


def _keyword_volume(row: FactSerKeyword) -> float:
    try:
        return float(row.volume or 0)
    except (TypeError, ValueError):
        return 0.0


def detect_keyword_rank_signal(
    *,
    current_position: Any,
    previous_position: Any,
) -> str | None:
    """Return keyword_fell_top5 / keyword_fell_top10 / keyword_not_ranking or None."""
    prev = _rank_position(previous_position)
    curr = _rank_position(current_position)
    if prev is not None and prev <= 5 and (curr is None or curr > 5):
        return "keyword_fell_top5"
    if prev is not None and prev <= 10 and (curr is None or curr > 10):
        return "keyword_fell_top10"
    if curr is None:
        return "keyword_not_ranking"
    return None


def _ai_visibility_keyword_findings(
    db: Session,
    client_id: UUID,
    *,
    site: SiteBusinessContext,
    thresholds: dict[str, float | int],
) -> list[LeverFinding]:
    min_volume = float(thresholds.get("ai_visibility_min_keyword_volume", 50))
    top_n = int(thresholds.get("ai_visibility_keyword_top_n", 25))
    rows = db.query(FactSerKeyword).filter(FactSerKeyword.client_id == client_id).all()
    candidates: list[tuple[float, LeverFinding]] = []
    for row in rows:
        volume = _keyword_volume(row)
        if volume < min_volume:
            continue
        signal = detect_keyword_rank_signal(
            current_position=row.current_position,
            previous_position=row.previous_position,
        )
        if signal is None:
            continue
        impact, impact_evidence = score_ai_visibility_impact(
            signal=signal,
            volume=volume,
            site=site,
        )
        prev = _rank_position(row.previous_position)
        curr = _rank_position(row.current_position)
        curr_label = f"{curr:.0f}" if curr is not None else "not ranking"
        if signal == "keyword_fell_top5":
            diagnosis = (
                f"Keyword fell out of the top 5: “{row.keyword}” "
                f"(was {prev:.0f}, now {curr_label})"
            )
        elif signal == "keyword_fell_top10":
            diagnosis = (
                f"Keyword fell out of the top 10: “{row.keyword}” "
                f"(was {prev:.0f}, now {curr_label})"
            )
        else:
            diagnosis = f"Tracked keyword is not ranking: “{row.keyword}”"
        finding = _make_finding(
            lever=GrowthAction.AI_VISIBILITY.value,
            rule_key=_rule_key("ai_vis_kw", f"{row.site_engine_id}:{row.keyword_id}"),
            diagnosis=diagnosis,
            evidence_json={
                "audit_signal": signal,
                "keyword": row.keyword,
                "keyword_id": row.keyword_id,
                "site_engine_id": row.site_engine_id,
                "current_position": curr,
                "previous_position": prev,
                "ranking_url": row.ranking_url,
                "volume": volume,
                **impact_evidence,
            },
            baseline_metrics_json={
                "current_position": curr,
                "previous_position": prev,
                "volume": volume,
            },
            impact=impact,
            query=row.keyword,
            page_url=row.ranking_url,
        )
        # Prefer fallouts over not-ranking when sorting; volume is secondary.
        rank_boost = {"keyword_fell_top5": 1e9, "keyword_fell_top10": 1e8}.get(signal, 0.0)
        candidates.append((rank_boost + volume, finding))

    candidates.sort(key=lambda row: row[0], reverse=True)
    return [finding for _, finding in candidates[:top_n]]


def _ai_visibility_prompt_findings(
    db: Session,
    client_id: UUID,
    period: tuple[date, date] | None,
    *,
    site: SiteBusinessContext,
    thresholds: dict[str, float | int],
) -> list[LeverFinding]:
    if period is None:
        return []
    start, end = period
    min_checks = int(thresholds.get("ai_visibility_prompt_min_checks", 2))
    top_n = int(thresholds.get("ai_visibility_prompt_top_n", 25))

    checks = (
        db.query(FactSerAiCheck)
        .filter(
            FactSerAiCheck.client_id == client_id,
            FactSerAiCheck.date >= start,
            FactSerAiCheck.date <= end,
        )
        .all()
    )
    if not checks:
        return []

    by_prompt: dict[tuple[str, str], list[FactSerAiCheck]] = {}
    for check in checks:
        by_prompt.setdefault((check.llm_id, check.prompt_id), []).append(check)

    prompt_meta = {
        (row.llm_id, row.prompt_id): row
        for row in db.query(FactSerAiPrompt).filter(FactSerAiPrompt.client_id == client_id).all()
    }

    candidates: list[tuple[float, LeverFinding]] = []
    for key, rows in by_prompt.items():
        if len(rows) < min_checks:
            continue
        cited_any = False
        for row in rows:
            url_pos = _rank_position(row.url_position)
            if url_pos is not None or row.brand_cited is True:
                cited_any = True
                break
        if cited_any:
            continue

        meta = prompt_meta.get(key)
        prompt_text = (meta.prompt if meta else rows[0].prompt) or "AI prompt"
        try:
            volume = float(meta.search_volume or 0) if meta else 0.0
        except (TypeError, ValueError):
            volume = 0.0
        impact, impact_evidence = score_ai_visibility_impact(
            signal="prompt_not_cited",
            volume=max(volume, 50.0),
            site=site,
        )
        engine = meta.engine if meta else None
        diagnosis = (
            f"Tracked prompt is not earning AI citations across {len(rows)} checks: "
            f"“{prompt_text[:120]}”"
        )
        finding = _make_finding(
            lever=GrowthAction.AI_VISIBILITY.value,
            rule_key=_rule_key("ai_vis_prompt", f"{key[0]}:{key[1]}"),
            diagnosis=diagnosis,
            evidence_json={
                "audit_signal": "prompt_not_cited",
                "prompt": prompt_text,
                "prompt_id": key[1],
                "llm_id": key[0],
                "engine": engine,
                "checks_in_period": len(rows),
                "min_checks_required": min_checks,
                "brand_cited": False,
                "search_volume": volume,
                **impact_evidence,
            },
            baseline_metrics_json={
                "checks_in_period": len(rows),
                "search_volume": volume,
            },
            impact=impact,
            query=prompt_text[:200],
        )
        candidates.append((volume + len(rows), finding))

    candidates.sort(key=lambda row: row[0], reverse=True)
    return [finding for _, finding in candidates[:top_n]]


def _ai_visibility_findings(
    db: Session,
    client_id: UUID,
    period: tuple[date, date] | None,
    *,
    site: SiteBusinessContext,
    thresholds: dict[str, float | int],
) -> list[LeverFinding]:
    """Ranking + AI citation findings.

    Structured data / GEO Grader schema signals are deferred to Content Opportunities.
    """
    findings = _ai_visibility_keyword_findings(
        db, client_id, site=site, thresholds=thresholds
    )
    findings.extend(
        _ai_visibility_prompt_findings(
            db, client_id, period, site=site, thresholds=thresholds
        )
    )
    return findings


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
    site: SiteBusinessContext,
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

    impact, impact_evidence = score_conversion_impact(
        sessions_current=float(sessions_current),
        current_rate=current_rate,
        previous_rate=previous_rate,
        site=site,
    )
    urgency = portfolio_urgency_adjustment(LEVER_INPUTS[GrowthAction.CONVERSION_PATH.value].urgency, site)
    return _make_finding(
        lever=GrowthAction.CONVERSION_PATH.value,
        rule_key=_rule_key("conversion_path", str(client.id), from_date.isoformat(), to_date.isoformat()),
        diagnosis="Managed traffic holding but lead rate falling",
        evidence_json={
            "lead_rate_change_pct": round(lead_rate_change_pct, 1),
            "sessions_change_pct": round(sessions_change_pct, 1),
            "tracking_validated": True,
            **impact_evidence,
        },
        baseline_metrics_json={
            "lead_rate_current": round(current_rate, 2),
            "lead_rate_previous": round(previous_rate, 2),
            "sessions_current": float(sessions_current),
            "sessions_previous": float(sessions_previous),
        },
        impact=impact,
        urgency_override=urgency,
    )


def _lever_summaries(
    findings: list[LeverFinding],
    recommended_actions: list[LeverFinding],
) -> list[LeverSummary]:
    finding_counts: dict[str, int] = {key: 0 for key in LEVER_LABELS}
    action_counts: dict[str, int] = {key: 0 for key in LEVER_LABELS}
    for finding in findings:
        if finding.lever in finding_counts:
            finding_counts[finding.lever] += 1
    for action in recommended_actions:
        if action.lever in action_counts:
            action_counts[action.lever] += 1
    summaries: list[LeverSummary] = []
    for lever, label in LEVER_LABELS.items():
        count = finding_counts.get(lever, 0)
        action_count = action_counts.get(lever, 0)
        summaries.append(
            LeverSummary(
                lever=lever,
                label=label,
                findings_count=count,
                recommended_actions_count=action_count,
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
    gsc_watermark = watermarks.get("gsc_pages")
    fact_min, fact_max = _gsc_fact_bounds(db, client.id)
    gsc_period, block_message, partial_message = _resolve_gsc_analysis_period(
        from_date=from_date,
        to_date=to_date,
        watermark=gsc_watermark,
        fact_min=fact_min,
        fact_max=fact_max,
    )
    ser_period = _effective_range(from_date, to_date, watermarks.get("se_ranking_search"))
    ai_period = _effective_range(from_date, to_date, watermarks.get("se_ranking_ai")) or ser_period

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
    base_result = {
        "requested_from": from_date,
        "requested_to": to_date,
        "analysis_from": gsc_period[0] if gsc_period else None,
        "analysis_to": gsc_period[1] if gsc_period else None,
        "partial_message": partial_message,
    }
    if gsc_rows == 0:
        return DiagnoseResult(
            ready=False,
            message=block_message
            or "Search Console page facts are required before the Decision Engine can run.",
            readiness=readiness,
            formula=SCORE_FORMULA,
            levers=_lever_summaries([], []),
            **base_result,
        )

    dashboard = build_dashboard(db, client, from_date, to_date)
    pages = _load_page_demand(db, client_id=client.id, period=gsc_period)
    crawl_by_url = _load_crawl_by_url(db, client.id)
    issues_by_url, site_issue_codes = _load_audit_issues(db, client.id)

    lead_events = _lead_event_names(db, client.id)
    ga4_period = _effective_range(from_date, to_date, watermarks.get("ga4"))
    site_period = ga4_period or gsc_period
    site = load_site_business_context(
        db,
        client,
        period=site_period,
        lead_events=lead_events,
        dashboard=dashboard,
    )
    page_urls = [page.normalized_url for page in pages]
    page_contexts = load_page_business_contexts(
        db,
        client_id=client.id,
        period=gsc_period,
        lead_events=lead_events,
        normalized_urls=page_urls,
    )
    site = with_p90_sessions(site, page_contexts)
    thresholds = _load_thresholds(db, client.id)
    classifications = classify_pages(page_urls)
    page_type_rates = compute_page_type_lead_rates(page_contexts, classifications)
    topic_rates = compute_topic_lead_rates(page_contexts, classifications)

    findings: list[LeverFinding] = []
    findings.extend(
        _per_page_cascade(
            pages,
            crawl_by_url,
            crawl_ready=crawl_ready,
            page_contexts=page_contexts,
            site=site,
            classifications=classifications,
            page_type_rates=page_type_rates,
            topic_rates=topic_rates,
            issues_by_url=issues_by_url,
        )
    )
    for site_finding in _site_technical_findings(
        site_issue_codes, site=site, client_id=client.id
    ):
        _enrich_finding(site_finding, classification=None, page_ctx=None)
        findings.append(site_finding)

    for ai_finding in _ai_visibility_findings(
        db,
        client.id,
        ai_period,
        site=site,
        thresholds=thresholds,
    ):
        _enrich_finding(ai_finding, classification=None, page_ctx=None)
        findings.append(ai_finding)

    conversion = _conversion_portfolio(
        db,
        client,
        from_date=from_date,
        to_date=to_date,
        dashboard=dashboard,
        site=site,
    )
    if conversion is not None:
        _enrich_finding(conversion, classification=None, page_ctx=None)
        findings.append(conversion)

    findings.sort(key=lambda row: row.priority_score, reverse=True)
    all_findings, recommended_actions = promote_findings(
        findings,
        classifications=classifications,
        page_contexts=page_contexts,
        thresholds=thresholds,
    )
    actioned_urls = {finding.page_url for finding in all_findings if finding.page_url}
    search_opportunities = _search_opportunities(
        pages,
        actioned_urls=actioned_urls,
        classifications=classifications,
        thresholds=thresholds,
    )

    return DiagnoseResult(
        ready=True,
        message=None,
        readiness=readiness,
        formula=SCORE_FORMULA,
        levers=_lever_summaries(all_findings, recommended_actions),
        findings=all_findings,
        recommended_actions=recommended_actions,
        search_opportunities=search_opportunities,
        **base_result,
    )
