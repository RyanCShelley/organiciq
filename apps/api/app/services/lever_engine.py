"""Deterministic Decision Engine — diagnose() over validated facts only."""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta
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
from app.models.crawl import (
    CRAWL_SOURCE_FIRST_PARTY,
    CRAWL_SOURCE_SE_RANKING,
    FactCrawlInternalLink,
    FactCrawlPageIssue,
    FactCrawlPageSchema,
    FactCrawlPageSnapshot,
)
from app.models.decision import (
    Decision,
    DecisionStatus,
    DecisionThreshold,
    DiagnosticLayer,
    GrowthAction,
)
from app.models.ga4 import FactGa4Event, FactGa4Traffic
from app.models.gsc import FactGscPage, FactGscQueryPage
from app.models.job import DataWatermark, ValidationStatus
from app.core.settings import get_settings
from app.core.urls import normalize_url
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
    business_impact_reference_leads,
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

#: How many times a team can override the same kind of suggestion before the
#: rule, not the team, is the thing that is wrong. From the product spec.
OVERRIDE_RETIREMENT_COUNT = 3


def rule_family(lever: str, evidence: dict[str, Any]) -> str:
    """The kind of suggestion, as distinct from the page it landed on.

    `rule_key` is hashed per page, so counting overrides by it would ask "has
    anyone dismissed this exact finding three times", which is a question about
    one page. The useful question is whether the same *kind* of suggestion
    keeps being rejected across different pages — that is a rule that does not
    fit how this client is run.
    """
    signal = evidence.get("audit_signal") or evidence.get("gate")
    return f"{lever}:{signal}" if signal else lever


def _overridden_rule_families(db: Session, client_id: UUID) -> dict[str, int]:
    """Rule families this client's team keeps dismissing, and how often.

    Counted across distinct pages. Dismissing the same page three times is one
    disagreement repeated, not three — usually someone working through a stale
    queue — and retiring a rule on that would be the engine misreading its own
    history.
    """
    rows = (
        db.query(Decision.evidence_json, Decision.growth_action, Decision.rule_key)
        .filter(
            Decision.client_id == client_id,
            Decision.status == DecisionStatus.DISMISSED,
        )
        .all()
    )
    seen: dict[str, set[str]] = {}
    for evidence, growth_action, key in rows:
        lever = growth_action.value if growth_action is not None else ""
        if not lever:
            continue
        family = rule_family(lever, evidence or {})
        seen.setdefault(family, set()).add(key)
    return {family: len(keys) for family, keys in seen.items()}


#: Conversions at zero this long, while traffic keeps arriving, is the product
#: spec's first Urgent condition. Shorter and a quiet fortnight at a small
#: client reads as a broken tag.
TRACKING_SILENCE_DAYS = 14
#: Zero conversions only means something if conversions were likely. Measured
#: against the client's own historical rate: fire when the fortnight should
#: have produced at least this many and produced none. A flat session floor
#: cried wolf on small clients, where fifty sessions at a one percent rate
#: expects half a lead and zero is an ordinary fortnight.
TRACKING_EXPECTED_LEADS = 3.0
#: With no history there is no rate to expect against, so a plain volume floor
#: is all that is left — set high, because this is the weaker signal.
TRACKING_NO_HISTORY_SESSIONS = 500.0

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


def active_crawl_source() -> str:
    """
    The crawl the engine reads. Both keep writing.

    Settable so a bad crawl can be backed out by flipping one variable rather
    than deploying, and so the two can be compared on the same data.
    """
    configured = (get_settings().crawl_facts_source or "").strip()
    return configured if configured in {CRAWL_SOURCE_FIRST_PARTY, CRAWL_SOURCE_SE_RANKING} else CRAWL_SOURCE_FIRST_PARTY


def _load_crawl_by_url(db: Session, client_id: UUID) -> dict[str, FactCrawlPageSnapshot]:
    """
    Crawl snapshots from the source the engine trusts.

    The table holds both crawls. Reading it unscoped would mix them and make the
    row for a page depend on insert order.
    """
    rows = (
        db.query(FactCrawlPageSnapshot)
        .filter(
            FactCrawlPageSnapshot.client_id == client_id,
            FactCrawlPageSnapshot.source == active_crawl_source(),
        )
        .all()
    )
    return {row.normalized_url: row for row in rows}


def _load_page_schema(
    db: Session, client_id: UUID
) -> tuple[dict[str, PageSchema], frozenset[str]]:
    """
    Structured data per page, plus the URLs the first-party crawl covered.

    The two are returned together on purpose. A page with no rows in the schema
    table has either no structured data or was never crawled, and only the
    covered set tells them apart.
    """
    covered = frozenset(
        row[0]
        for row in db.query(FactCrawlPageSnapshot.normalized_url).filter(
            FactCrawlPageSnapshot.client_id == client_id,
            FactCrawlPageSnapshot.source == CRAWL_SOURCE_FIRST_PARTY,
        )
    )
    if not covered:
        return {}, frozenset()

    blocks: dict[str, list[FactCrawlPageSchema]] = {}
    for row in db.query(FactCrawlPageSchema).filter(FactCrawlPageSchema.client_id == client_id):
        blocks.setdefault(row.normalized_url, []).append(row)

    by_url = {
        url: PageSchema(
            blocks=len(rows),
            invalid=sum(1 for r in rows if r.parse_error),
            types=frozenset(r.schema_type for r in rows if r.schema_type),
        )
        for url, rows in blocks.items()
    }
    return by_url, covered


def _load_audit_issues(
    db: Session, client_id: UUID
) -> tuple[dict[str, set[str]], set[str]]:
    """Return (page_url -> issue codes, site-level issue codes)."""
    rows = (
        db.query(FactCrawlPageIssue)
        .filter(
            FactCrawlPageIssue.client_id == client_id,
            FactCrawlPageIssue.source == active_crawl_source(),
        )
        .all()
    )
    by_url: dict[str, set[str]] = {}
    site_codes: set[str] = set()
    for row in rows:
        if row.normalized_url:
            by_url.setdefault(row.normalized_url, set()).add(row.issue_code)
        else:
            site_codes.add(row.issue_code)
    return by_url, site_codes


#: Technical signals that remove a page from search. These stay in the Growth
#: Action queue and preempt, because nothing else matters on a page Google
#: cannot index.
INDEXATION_BLOCKING_SIGNALS = frozenset(
    {"status_error", "non_indexable", "canonical_elsewhere", "broken_redirect", "robots_blocking"}
)

#: Everything else Technical SEO detects is upkeep the plan already covers
#: every month — "titles, metas, internal links, schema" is Core Work in the
#: product spec, not one of the one-to-five flexible actions a client buys. It
#: is still reported; it just stops competing for capacity it was never meant
#: to spend. Before this, a Launch client with one action a month could be
#: handed twenty-five findings, most of them work already paid for.
def is_core_work_signal(audit_signal: str | None) -> bool:
    return bool(audit_signal) and audit_signal not in INDEXATION_BLOCKING_SIGNALS


#: What to actually do, per signal.
#:
#: The lever-level action said "resolve the flagged technical issue (status,
#: redirect, indexation, canonical, or core meta)", which is the finding read
#: back with the word "resolve" in front. A strategist opening the queue needs
#: the next move, not a restatement — and where the work is cheap, saying so
#: is what lets someone judge whether it is worth an action.
TECHNICAL_ACTIONS: dict[str, str] = {
    "status_error": (
        "Restore the page, or 301 it to the closest live equivalent. It has demand, "
        "so leaving the error throws that away."
    ),
    "broken_redirect": (
        "Repoint this redirect at a live URL. It currently lands on an error, so the "
        "visitor and the link equity both stop here."
    ),
    "redirect_chain": (
        "Collapse the chain to one hop, straight from the original URL to the final "
        "destination."
    ),
    "non_indexable": (
        "Remove the noindex or robots rule if this page should rank. If it genuinely "
        "should not, the demand it is attracting belongs on a page that can."
    ),
    "canonical_elsewhere": (
        "Point the canonical at this URL, or confirm the target is the page you want "
        "ranking. Right now this page tells Google to ignore it, and it has demand."
    ),
    "missing_meta": "Write a title and meta description for this page.",
    "duplicate_meta": (
        "Give this page its own title and description — it currently shares them with "
        "another page, so neither reads as the better answer."
    ),
    "invalid_schema": (
        "Fix the malformed structured data. It is present but cannot be parsed, so it "
        "earns nothing while looking like it should."
    ),
    "missing_schema": "Add structured data describing what this page is.",
    "sitemap_missing": "Publish an XML sitemap and declare it in robots.txt.",
    "robots_blocking": (
        "Remove the robots.txt rule blocking crawl. Nothing on the blocked paths can "
        "rank while it stands."
    ),
    "robots_advisory": (
        "Correct the robots.txt syntax errors. A malformed rule is read more "
        "broadly than intended often enough to be worth ten minutes."
    ),
}

TRACKING_ACTION = (
    "Fire a test conversion and confirm it reaches GA4. Until it does, every "
    "other number in this report is built on a zero that may not be real."
)


ROBOTS_BLOCKING_CODES = frozenset({"robots_disallow_crawling"})
ROBOTS_ADVISORY_CODES = frozenset(
    {"no_robots", "robots_not_accessible", "robots_has_errors"}
)


#: Types an SEO plugin emits on every page regardless of content. Their presence
#: says a plugin is installed, not that the page is described. `Person` is here
#: too: author markup describes the author, not the page.
BOILERPLATE_SCHEMA_TYPES: frozenset[str] = frozenset(
    {
        "WebPage",
        "WebSite",
        "Organization",
        "Corporation",
        "BreadcrumbList",
        "ListItem",
        "ImageObject",
        "SiteNavigationElement",
        "WPHeader",
        "WPFooter",
        "WPSideBar",
        "CollectionPage",
        "SearchAction",
        "ReadAction",
        "Person",
    }
)


@dataclass(frozen=True)
class PageSchema:
    """Structured data found on a page by the first-party crawl."""

    blocks: int
    invalid: int
    types: frozenset[str] = frozenset()

    @property
    def descriptive_types(self) -> frozenset[str]:
        """Types that say something about this page rather than the site."""
        return self.types - BOILERPLATE_SCHEMA_TYPES


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
    schema_by_url: dict[str, PageSchema] | None = None,
    schema_crawled_urls: frozenset[str] | None = None,
) -> DetectedTechnicalSignal | None:
    """
    Priority-ordered Technical SEO detector for a single page.

    Structured data is checked last: it is an enhancement, and a page that is
    also returning 404 has a bigger problem than its markup.
    """
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
    # A working redirect is not a content defect. Broken ones and chains are
    # already reported above, and a 301 is non-indexable by definition — without
    # this, the `/page` that redirects to `/page/` reports itself as a
    # "non-indexable page with demand" for doing the correct thing.
    if not crawl.indexable and not is_redirect:
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

    # Only pages the first-party crawl actually reached can be said to lack
    # schema. Without that evidence, "no structured data" would really mean
    # "not crawled", which is a different statement and a false one.
    if schema_crawled_urls is not None and page_url in schema_crawled_urls:
        found = (schema_by_url or {}).get(page_url, PageSchema(blocks=0, invalid=0))
        if found.invalid:
            return DetectedTechnicalSignal(
                audit_signal="invalid_schema",
                issue_code=None,
                diagnosis=f"Structured data present but unparseable: {page_url}",
            )
        if found.blocks == 0:
            return DetectedTechnicalSignal(
                audit_signal="missing_schema",
                issue_code=None,
                diagnosis=f"No structured data on page with demand: {page_url}",
            )
        if not found.descriptive_types:
            # Markup is present, but all of it is the wrapper a plugin emits on
            # every page. Nothing here says what this page is — which is the
            # part an answer engine needs. Asking instead whether the type is
            # "right" would need a template classifier we do not have, and a
            # schema.org subtype map to avoid calling BlogPosting a missing
            # Article.
            present = ", ".join(sorted(found.types)) or "no recognisable types"
            return DetectedTechnicalSignal(
                audit_signal="missing_schema",
                issue_code="boilerplate_schema_only",
                diagnosis=(
                    f"Only site-wide boilerplate structured data ({present}) on page "
                    f"with demand: {page_url}"
                ),
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
    schema_by_url: dict[str, PageSchema] | None = None,
    schema_crawled_urls: frozenset[str] | None = None,
) -> LeverFinding | None:
    detected = detect_technical_signal(
        page.normalized_url,
        crawl,
        page_issue_codes=page_issue_codes,
        crawl_by_url=crawl_by_url,
        schema_by_url=schema_by_url,
        schema_crawled_urls=schema_crawled_urls,
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
    finding = _make_finding(
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
            "schema_types": sorted(
                (schema_by_url or {}).get(page.normalized_url, PageSchema(0, 0)).types
            ),
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
        action_override=TECHNICAL_ACTIONS.get(detected.audit_signal),
    )
    finding.core_work = is_core_work_signal(detected.audit_signal)
    return finding


def _site_technical_findings(
    site_codes: set[str],
    *,
    site: SiteBusinessContext,
    client_id: UUID,
) -> list[LeverFinding]:
    def tagged(finding: LeverFinding, audit_signal: str) -> LeverFinding:
        finding.core_work = is_core_work_signal(audit_signal)
        return finding

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
            tagged(
            _make_finding(
                lever=GrowthAction.TECHNICAL_SEO.value,
                rule_key=_rule_key("technical_sitemap", str(client_id)),
                diagnosis="Website Audit reports the XML sitemap is missing.",
                action_override=TECHNICAL_ACTIONS["sitemap_missing"],
                evidence_json={
                    "audit_signal": "sitemap_missing",
                    "issue_code": "sitemap_missing",
                    "promotion_class": "advisory",
                    **assessment.evidence,
                },
                baseline_metrics_json={},
                impact=assessment.impact,
                severity=assessment.severity,
            ),
            "sitemap_missing",
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
            tagged(
            _make_finding(
                lever=GrowthAction.TECHNICAL_SEO.value,
                rule_key=_rule_key("technical_robots", str(client_id)),
                diagnosis=(
                    "Website Audit reports robots.txt is blocking crawl."
                    if audit_signal == "robots_blocking"
                    else "Website Audit reports robots.txt problems."
                ),
                action_override=TECHNICAL_ACTIONS.get(audit_signal),
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
            ),
            audit_signal,
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
    action_override: str | None = None,
) -> LeverFinding:
    inputs = LEVER_INPUTS[lever]
    # Recorded rather than derived later: the finding knows its own kind, and
    # a dismissal has to be countable against it long after the finding is gone.
    evidence_json = {**evidence_json, "rule_family": rule_family(lever, evidence_json)}
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
        recommended_action=action_override or inputs.recommended_action,
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


#: Queries worth considering as a bridge between two pages. Below this the
#: overlap is usually incidental rather than a shared subject.
LINK_GAP_MIN_IMPRESSIONS = 50.0
#: A source has to be meaningfully stronger than the target, or the link is
#: being asked for in the wrong direction.
LINK_GAP_SOURCE_CLICK_RATIO = 2.0
#: How many shared queries to name. One is the reason; a list is a report.
LINK_GAP_MAX_QUERIES = 2


@dataclass(frozen=True)
class LinkGap:
    """A link that should exist and does not."""

    source_url: str
    shared_query: str
    source_clicks: float


def _link_gaps(
    db: Session,
    client_id: UUID,
    *,
    period: tuple[date, date] | None,
    targets: set[str],
) -> dict[str, LinkGap]:
    """For each under-linked page, the best page that should link to it.

    "This page has fewer than five inbound links" is a symptom. It tells a
    strategist that something is wrong and leaves them to work out what to do,
    which on a four-hundred-page site is most of the job.

    Two pages ranking for the same query are, by definition, about the same
    thing — and the one already earning clicks for it has the authority the
    other needs. If no editorial link runs between them, that is a specific
    link from a named page, which is ten minutes of work rather than an
    afternoon of judgement.

    Direction matters: the link has to come from the stronger page. Pointing it
    the other way asks the page with nothing to give to give it.
    """
    if period is None or not targets:
        return {}

    start, end = period
    rows = (
        db.query(
            FactGscQueryPage.query,
            FactGscQueryPage.normalized_url,
            func.sum(FactGscQueryPage.impressions).label("impressions"),
            func.sum(FactGscQueryPage.clicks).label("clicks"),
        )
        .filter(
            FactGscQueryPage.client_id == client_id,
            FactGscQueryPage.date >= start,
            FactGscQueryPage.date <= end,
        )
        .group_by(FactGscQueryPage.query, FactGscQueryPage.normalized_url)
        .having(func.sum(FactGscQueryPage.impressions) >= LINK_GAP_MIN_IMPRESSIONS)
        .all()
    )

    by_query: dict[str, list[tuple[str, float]]] = {}
    for query, url, _impressions, clicks in rows:
        by_query.setdefault(query, []).append((url, float(clicks or 0)))

    # Editorial edges only. A target already in the navigation still needs a
    # reference from a page about the same subject — that is the whole reason
    # the floor counts editorial links and not every link.
    existing = {
        (row.from_url, row.to_url)
        for row in db.query(FactCrawlInternalLink)
        .filter(
            FactCrawlInternalLink.client_id == client_id,
            FactCrawlInternalLink.source == active_crawl_source(),
            FactCrawlInternalLink.is_template.is_(False),
            FactCrawlInternalLink.to_url.in_(targets),
        )
        .all()
    }

    best: dict[str, LinkGap] = {}
    for query, entries in by_query.items():
        if len(entries) < 2:
            continue
        for target_url, target_clicks in entries:
            if target_url not in targets:
                continue
            for source_url, source_clicks in entries:
                if source_url == target_url:
                    continue
                if source_clicks < max(target_clicks * LINK_GAP_SOURCE_CLICK_RATIO, 1.0):
                    continue
                if (source_url, target_url) in existing:
                    continue
                current = best.get(target_url)
                if current is None or source_clicks > current.source_clicks:
                    best[target_url] = LinkGap(
                        source_url=source_url,
                        shared_query=query,
                        source_clicks=source_clicks,
                    )
    return best


def _internal_linking_finding(
    page: PageDemand,
    crawl: FactCrawlPageSnapshot,
    *,
    page_ctx: PageBusinessContext | None,
    site: SiteBusinessContext,
    lead_rate_ctx: LeadRateContext | None = None,
    classification: PageClassification | None = None,
    link_gap: LinkGap | None = None,
) -> LeverFinding | None:
    if page.average_position < 4 or page.average_position > 20:
        return None
    floor = _link_floor(crawl.word_count)
    # Editorial links only. Counting navigation put every page that sits in a
    # menu above the floor regardless of whether anything references it — on
    # smamarketing.com only 12% of inbound links are editorial, so the lever was
    # quietest on exactly the sites that needed it. The audit has no such figure,
    # so fall back to the total when reading that source.
    inbound = (
        crawl.inbound_editorial_links
        if crawl.source == CRAWL_SOURCE_FIRST_PARTY
        else crawl.inbound_internal_links
    )
    if inbound >= floor:
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
    # Naming the source turns the finding into the work. Without one the
    # generic lever text still applies — there is simply no page that both
    # shares a subject and has the authority to lend.
    action = None
    if link_gap is not None:
        action = (
            f"Add a link to this page from {link_gap.source_url}. Both rank for "
            f"\u201c{link_gap.shared_query}\u201d and that page earns "
            f"{int(link_gap.source_clicks):,} clicks for it, so it has the authority "
            "this one is missing."
        )
    return _make_finding(
        lever=GrowthAction.INTERNAL_LINKING.value,
        rule_key=_rule_key("internal_linking", page.normalized_url),
        diagnosis=diagnosis,
        action_override=action,
        evidence_json={
            "position": round(page.average_position, 1),
            "link_from": link_gap.source_url if link_gap else None,
            "link_shared_query": link_gap.shared_query if link_gap else None,
            "inbound_internal_links": crawl.inbound_internal_links,
            "inbound_editorial_links": crawl.inbound_editorial_links,
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
    schema_by_url: dict[str, PageSchema] | None = None,
    #: URLs the first-party crawl covered. None means it has never run, and no
    #: schema claim can be made about any page.
    schema_crawled_urls: frozenset[str] | None = None,
    link_gaps: dict[str, LinkGap] | None = None,
) -> list[LeverFinding]:
    findings: list[LeverFinding] = []
    issue_map = issues_by_url or {}
    gaps = link_gaps or {}
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
            # Schema is withheld from this pass on purpose. It is advisory, and
            # a page whose only issue is thin markup should still be allowed to
            # surface an internal-linking or CTR opportunity, which are things
            # someone can act on for a return.
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
                    link_gap=gaps.get(page.normalized_url),
                )
        if finding is None:
            finding = _serp_ctr_finding(
                page,
                page_ctx=page_ctx,
                site=site,
                lead_rate_ctx=lead_rate_ctx,
                classification=classification,
            )
        if finding is None and crawl_ready and crawl is not None:
            # Last resort: nothing else to say about this page, so report the
            # structured data if it is thin.
            finding = _technical_finding(
                page,
                crawl,
                page_ctx=page_ctx,
                site=site,
                lead_rate_ctx=lead_rate_ctx,
                classification=classification,
                page_issue_codes=issue_map.get(page.normalized_url),
                crawl_by_url=crawl_by_url,
                schema_by_url=schema_by_url,
                schema_crawled_urls=schema_crawled_urls,
            )
        if finding is not None:
            _enrich_finding(finding, classification=classification, page_ctx=page_ctx)
            findings.append(finding)
    return findings


# Opportunity types, derived rather than a single constant.
#
# Every row used to carry "Striking-Distance Opportunity", which made the label
# decorative. These split the same band into the three shapes that call for
# different work: a page that already ranks well but is under-clicked, a page
# on the cusp of page one, and the broad middle.
CTR_GAP_RATIO = 0.5
NEAR_WIN_MAX_POSITION = 5.0


def _classify_opportunity(*, average_position: float, ctr_percent: float) -> str:
    expected = expected_ctr_percent(average_position)
    if expected > 0 and ctr_percent < expected * CTR_GAP_RATIO:
        # Ranking is fine; the listing is not earning the clicks it should.
        return "CTR gap"
    if average_position <= NEAR_WIN_MAX_POSITION:
        return "Near win"
    return "Striking distance"


def _tracked_keywords_by_url(db: Session, client_id: UUID) -> dict[str, int]:
    """
    Tracked SE Ranking keywords per ranking URL.

    Content opportunities are page-level — they carry no query — so a
    query-to-keyword text match is not possible. Joining on the ranking URL is
    exact instead of fuzzy, and answers the more useful question: does this page
    already rank for keywords we track?
    """
    rows = (
        db.query(FactSerKeyword.ranking_url, func.count())
        .filter(
            FactSerKeyword.client_id == client_id,
            FactSerKeyword.ranking_url.isnot(None),
        )
        .group_by(FactSerKeyword.ranking_url)
        .all()
    )
    counts: dict[str, int] = {}
    for raw_url, count in rows:
        if not raw_url:
            continue
        key = normalize_url(raw_url)
        counts[key] = counts.get(key, 0) + int(count)
    return counts


def _search_opportunities(
    pages: list[PageDemand],
    *,
    actioned_urls: set[str],
    classifications: dict[str, PageClassification],
    thresholds: dict[str, float | int],
    tracked_by_url: dict[str, int] | None = None,
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
                "opportunity_type": _classify_opportunity(
                    average_position=page.average_position,
                    ctr_percent=page.ctr_percent,
                ),
                "impressions": int(page.impressions),
                "average_position": round(page.average_position, 1),
                "clicks": int(page.clicks),
                "ctr_percent": round(page.ctr_percent, 2),
                "page_type": classification.page_type.value,
                "priority_topic": classification.priority_topic,
                "tracked_keywords": (tracked_by_url or {}).get(page.normalized_url, 0),
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


#: A page converts "below the site" only when the gap is worth someone's
#: afternoon. Measured in leads rather than percentage points: a page five
#: points under the site rate is noise at forty sessions and a serious problem
#: at four thousand, and only the lead count tells the two apart.
CONVERSION_PAGE_MIN_SHORTFALL = 3.0
#: Half the site's own rate. A page merely under the average is not a finding —
#: half of every site's pages are, by definition.
CONVERSION_PAGE_RATE_RATIO = 0.5


def _conversion_page_findings(
    pages: list[PageDemand],
    *,
    page_contexts: dict[str, PageBusinessContext],
    classifications: dict[str, PageClassification],
    site: SiteBusinessContext,
) -> list[LeverFinding]:
    """Gate 3: pages earning traffic and not turning it into anything.

    The engine spent its attention on whether pages could be *found*. This asks
    the question the client is actually paying for — the traffic arrived, so
    what happened next?

    The comparison is against the site's own lead rate, not an industry figure:
    a 2% site and a 0.4% site both have pages letting them down, and only the
    site itself says what normal looks like here.

    Like the tracking gate, this fires on expected leads rather than a rate
    gap, because a rate gap means nothing without volume behind it. A page
    converting at zero against a site rate of 1% needs three hundred sessions
    before "zero" is even surprising.
    """
    site_rate = site.site_lead_rate_pct
    if not site_rate or site_rate <= 0:
        # Without a site rate there is nothing to be below. A client with no
        # conversions at all is Gate 0's problem, not this one.
        return []

    findings: list[LeverFinding] = []
    for page in pages:
        ctx = page_contexts.get(page.normalized_url)
        if ctx is None or ctx.ga4_sessions <= 0:
            continue
        classification = classifications.get(page.normalized_url)
        if classification is not None and not classification.eligible_for_growth_action:
            continue

        expected = ctx.ga4_sessions * (site_rate / 100.0)
        shortfall = expected - ctx.ga4_leads
        if shortfall < CONVERSION_PAGE_MIN_SHORTFALL:
            continue
        page_rate = ctx.page_lead_rate_pct or 0.0
        if page_rate >= site_rate * CONVERSION_PAGE_RATE_RATIO:
            continue

        none_at_all = ctx.ga4_leads == 0
        diagnosis = (
            f"{int(ctx.ga4_sessions):,} sessions and no conversions: {page.normalized_url}"
            if none_at_all
            else (
                f"Converting at {page_rate:.2f}% against a site rate of {site_rate:.2f}%: "
                f"{page.normalized_url}"
            )
        )
        action = (
            "Work the conversion path on this page — CTA placement, form length, and "
            "whether the offer matches what the visitor searched for. "
            f"At the site's own rate it would be producing about {shortfall:.0f} more "
            "leads per period."
        )

        # Impact is the shortfall measured against what a lead is worth to this
        # site, so a page losing ten leads outranks one losing three.
        reference = business_impact_reference_leads(site)
        impact = min(100.0, (shortfall / reference) * 100.0) if reference > 0 else 50.0

        findings.append(
            _make_finding(
                lever=GrowthAction.CONVERSION_PATH.value,
                rule_key=_rule_key("conversion_page", page.normalized_url),
                diagnosis=diagnosis,
                evidence_json={
                    "gate": "conversion_page",
                    "sessions": int(ctx.ga4_sessions),
                    "leads": int(ctx.ga4_leads),
                    "page_lead_rate_pct": round(page_rate, 2),
                    "site_lead_rate_pct": round(site_rate, 2),
                    "expected_leads": round(expected, 1),
                    "shortfall_leads": round(shortfall, 1),
                    "no_conversions_at_all": none_at_all,
                    "promotion_class": "actionable",
                },
                baseline_metrics_json={
                    "impressions": page.impressions,
                    "sessions": ctx.ga4_sessions,
                },
                impact=impact,
                severity=impact,
                page_url=page.normalized_url,
                action_override=action,
            )
        )
    return findings


#: Page one. Below this a thin impression count is just the ranking.
VISIBILITY_MAX_POSITION = 10.0
#: Terms smaller than this can legitimately draw almost nothing, so silence
#: tells you nothing about whether the ranking is working.
VISIBILITY_MIN_VOLUME = 100.0
#: Ranking on page one should put the site in front of most people searching
#: the term. Seeing under a tenth of them means the ranking is not reaching
#: the demand the term was picked for.
VISIBILITY_IMPRESSION_RATIO = 0.1
DAYS_PER_MONTH_VISIBILITY = 365 / 12


def _visibility_without_traffic_findings(
    db: Session,
    client: Client,
    pages: list[PageDemand],
    *,
    period: tuple[date, date] | None,
) -> list[LeverFinding]:
    """Gate 2: core terms that rank and bring nothing.

    Visibility earns traffic and traffic earns leads, so a ranking that
    produces no demand breaks the chain at the top — and it was invisible to
    every rule here. The keyword rules watch for a term *falling*; a term
    sitting at position three and delivering nothing never moves, so nothing
    fired, and the watchlist looked healthy.

    Measured against the term's own search volume rather than a flat
    impression floor. Ranking on page one should put the site in front of most
    people searching it; seeing a tenth of them means the ranking is not
    reaching the demand, and that is usually the term rather than the page —
    volume overstated, a market Search Console does not report, or a phrase
    buyers do not actually use.
    """
    if period is None or not pages:
        # With no Search Console data every ranking would look like it earns
        # nothing, which says more about the gap in the data than the site.
        return []

    start, end = period
    period_days = (end - start).days + 1
    impressions_by_url = {page.normalized_url: page.impressions for page in pages}

    rows = (
        db.query(FactSerKeyword)
        .filter(
            FactSerKeyword.client_id == client.id,
            FactSerKeyword.ranking_url.isnot(None),
            FactSerKeyword.current_position.isnot(None),
        )
        .all()
    )

    findings: list[LeverFinding] = []
    for row in rows:
        position = float(row.current_position or 0)
        volume = float(row.volume or 0)
        if position <= 0 or position > VISIBILITY_MAX_POSITION:
            continue
        if volume < VISIBILITY_MIN_VOLUME:
            continue

        url = normalize_url(row.ranking_url or "")
        if not url:
            continue
        impressions = float(impressions_by_url.get(url, 0.0))
        expected = volume * (period_days / DAYS_PER_MONTH_VISIBILITY)
        if expected <= 0 or impressions >= expected * VISIBILITY_IMPRESSION_RATIO:
            continue

        share = (impressions / expected) * 100 if expected else 0.0
        findings.append(
            _make_finding(
                lever=GrowthAction.AI_VISIBILITY.value,
                rule_key=_rule_key("visibility_no_traffic", str(row.keyword_id), url),
                diagnosis=(
                    f"Ranking {position:.0f} for \u201c{row.keyword}\u201d but the page drew "
                    f"{int(impressions):,} impressions against {int(expected):,} searches"
                ),
                action_override=(
                    "Check the term before the page: confirm the volume is real in this "
                    "market, and that this is the phrasing buyers use. If it is, the "
                    "ranking is in a market Search Console does not report and the term "
                    "belongs off the watchlist."
                ),
                evidence_json={
                    "gate": "visibility_no_traffic",
                    "keyword": row.keyword,
                    "current_position": round(position, 1),
                    "search_volume": round(volume),
                    "expected_impressions": round(expected),
                    "actual_impressions": int(impressions),
                    "impression_share_pct": round(share, 1),
                    "promotion_class": "actionable",
                },
                baseline_metrics_json={"search_volume": volume, "position": position},
                # What the term is worth, capped: a 5,000/month phrase earning
                # nothing matters more than a 150/month one.
                impact=min(100.0, (volume / 1000.0) * 100.0),
                page_url=url,
                query=row.keyword,
            )
        )
    return findings


#: Words that join queries together without saying what they are about.
CLUSTER_STOPWORDS: frozenset[str] = frozenset(
    """a an and are as at be best by can cheap cost do does for from get good how
    i in is it me my near of on or our price pricing should that the to top
    vs what when where which who why will with you your""".split()
)
#: A token has to recur across this many distinct queries before it describes a
#: subject rather than a coincidence.
CLUSTER_MIN_QUERIES = 3
#: Demand worth writing for.
CLUSTER_MIN_IMPRESSIONS = 300.0
#: Page one. Anything better than this and the subject already has an owner.
CLUSTER_OWNED_POSITION = 10.0
#: Clusters overlap by construction, so only the strongest few are reported.
CLUSTER_MAX_FINDINGS = 5


def _cluster_tokens(query: str, brand: frozenset[str]) -> list[str]:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", (query or "").lower())
    return [
        token
        for token in cleaned.split()
        if len(token) > 2 and token not in CLUSTER_STOPWORDS and token not in brand
    ]


def _brand_tokens(client: Client) -> frozenset[str]:
    """The client's own name, which otherwise forms the biggest cluster on every site.

    Brand queries are demand the site already owns by existing; they are not a
    subject anyone needs to go and write about.
    """
    parts = re.split(r"[^a-z0-9]+", (client.client_name or "").lower())
    host = (client.domain or "").lower().split(".")[0]
    return frozenset(part for part in [*parts, host] if len(part) > 2)


def _content_cluster_findings(
    db: Session,
    client: Client,
    *,
    period: tuple[date, date] | None,
) -> list[LeverFinding]:
    """Subjects the site draws demand for and has no page ranking on.

    The link-gap rule asks which existing page should point at another. This
    asks the question underneath it: is there a subject here with no page at
    all? Same query data, read the other way.

    The grouping is a heuristic and worth naming as one: queries are clustered
    by a shared word, after stripping the words that join queries without
    describing them and the client's own brand. It will not find a subject
    whose queries share no vocabulary, and it will occasionally group two
    subjects that happen to share a word. It is reported with its own example
    queries so a strategist can see in a second whether the grouping is real —
    which is the honest way to ship a heuristic.
    """
    if period is None:
        return []
    start, end = period
    rows = (
        db.query(
            FactGscQueryPage.query,
            func.sum(FactGscQueryPage.impressions).label("impressions"),
            func.min(FactGscQueryPage.average_position).label("best_position"),
        )
        .filter(
            FactGscQueryPage.client_id == client.id,
            FactGscQueryPage.date >= start,
            FactGscQueryPage.date <= end,
        )
        .group_by(FactGscQueryPage.query)
        .all()
    )
    if not rows:
        return []

    brand = _brand_tokens(client)
    clusters: dict[str, list[tuple[str, float, float]]] = {}
    for query, impressions, best_position in rows:
        entry = (query, float(impressions or 0), float(best_position or 100))
        for token in set(_cluster_tokens(query, brand)):
            clusters.setdefault(token, []).append(entry)

    # A cluster is named by every word its queries share, not by the one word
    # that seeded it. Three queries all containing "metal" and "roofing" are
    # about metal roofing; calling that cluster "metal" tells a strategist
    # nothing, and it also means two seed words over one set of queries —
    # "schema" and "markup" — collapse to a single finding instead of two
    # saying the same thing.
    by_label: dict[str, list[tuple[str, float, float]]] = {}
    for entries in clusters.values():
        if len(entries) < CLUSTER_MIN_QUERIES:
            continue
        shared: set[str] | None = None
        for query, _impressions, _position in entries:
            tokens = set(_cluster_tokens(query, brand))
            shared = tokens if shared is None else (shared & tokens)
        if not shared:
            continue
        # Read the words off the busiest query so they come out in the order a
        # person would say them, not alphabetically.
        busiest = max(entries, key=lambda row: row[1])[0]
        order = {word: index for index, word in enumerate(_cluster_tokens(busiest, brand))}
        label = " ".join(sorted(shared, key=lambda word: order.get(word, 99)))
        by_label.setdefault(label, entries)

    candidates: list[tuple[float, str, list[tuple[str, float, float]]]] = []
    for label, entries in by_label.items():
        total = sum(row[1] for row in entries)
        if total < CLUSTER_MIN_IMPRESSIONS:
            continue
        best = min(row[2] for row in entries)
        if best <= CLUSTER_OWNED_POSITION:
            # Something already ranks for this subject. That is a page to
            # strengthen, not a cluster to start, and the page-level rules
            # already have it.
            continue
        candidates.append((total, label, entries))

    candidates.sort(key=lambda row: (-row[0], row[1]))
    findings: list[LeverFinding] = []
    for total, token, entries in candidates[:CLUSTER_MAX_FINDINGS]:
        examples = [row[0] for row in sorted(entries, key=lambda row: -row[1])[:3]]
        best = min(row[2] for row in entries)
        findings.append(
            _make_finding(
                lever=GrowthAction.AI_VISIBILITY.value,
                rule_key=_rule_key("content_cluster", str(client.id), token),
                diagnosis=(
                    f"No page ranking for \u201c{token}\u201d: {len(entries)} queries, "
                    f"{int(total):,} impressions, best position {best:.0f}"
                ),
                action_override=(
                    f"Write or rework a page that answers \u201c{token}\u201d properly — "
                    f"the demand is already there ({int(total):,} impressions across "
                    f"{len(entries)} queries) and nothing on the site ranks for it. "
                    f"Start from: {', '.join(examples)}."
                ),
                evidence_json={
                    "gate": "content_cluster",
                    "cluster_token": token,
                    "query_count": len(entries),
                    "impressions": int(total),
                    "best_position": round(best, 1),
                    "example_queries": examples,
                    "promotion_class": "actionable",
                },
                baseline_metrics_json={"impressions": total, "best_position": best},
                impact=min(100.0, (total / 2000.0) * 100.0),
                query=token,
            )
        )
    return findings


#: A page has to have been worth something before it can have decayed.
DECAY_MIN_PRIOR_CLICKS = 20.0
#: How far clicks must have fallen before it is decay rather than a wobble.
DECAY_MIN_DROP_PCT = 40.0
#: And how far it must have fallen *beyond the site*. In a seasonal trough
#: every page is down; a page is only decaying if it is losing ground its
#: neighbours are not.
DECAY_EXCESS_OVER_SITE_PCT = 25.0
#: A year back reads through seasonality. Anything shorter is compared to the
#: nearest window that is at least this far from the current one, so a decline
#: has had room to happen.
DECAY_MIN_GAP_DAYS = 90
DECAY_MAX_FINDINGS = 10


def _page_totals(
    db: Session, client_id: UUID, window: tuple[date, date]
) -> dict[str, tuple[float, float]]:
    """clicks and impressions per URL across a window."""
    start, end = window
    rows = (
        db.query(
            FactGscPage.normalized_url,
            func.sum(FactGscPage.clicks),
            func.sum(FactGscPage.impressions),
        )
        .filter(
            FactGscPage.client_id == client_id,
            FactGscPage.date >= start,
            FactGscPage.date <= end,
        )
        .group_by(FactGscPage.normalized_url)
        .all()
    )
    return {url: (float(clicks or 0), float(impressions or 0)) for url, clicks, impressions in rows}


def _decay_comparison_window(
    current: tuple[date, date], fact_min: date | None
) -> tuple[date, date] | None:
    """The window to measure decay against.

    A year back where the history allows, because that reads through
    seasonality — a pool company in November should be compared with last
    November, not with August. Where it does not, fall back to the nearest
    window far enough back that a decline has had room to happen; a page
    compared with last month is being asked about noise.
    """
    if fact_min is None:
        return None
    start, end = current
    span = (end - start).days

    year_start = start - timedelta(days=365)
    if year_start >= fact_min:
        return (year_start, year_start + timedelta(days=span))

    earlier_end = start - timedelta(days=DECAY_MIN_GAP_DAYS)
    earlier_start = earlier_end - timedelta(days=span)
    if earlier_start >= fact_min:
        return (earlier_start, earlier_end)
    return None


def _decaying_page_findings(
    db: Session,
    client: Client,
    *,
    period: tuple[date, date] | None,
    fact_min: date | None,
) -> list[LeverFinding]:
    """Pages that used to perform and no longer do.

    Every other rule here reads a snapshot: what is wrong with this page now.
    Decay is only visible across time, so a page that quietly lost three
    quarters of its traffic over a year looked perfectly healthy to all of
    them — correct status, fine meta, decent links, still ranking somewhere.

    The site's own decline is subtracted before judging. Without that, a
    seasonal trough or a sitewide algorithm hit flags every page at once, which
    is both useless and the loudest possible false alarm.
    """
    if period is None:
        return []
    earlier = _decay_comparison_window(period, fact_min)
    if earlier is None:
        # Not enough history to say anything about a trend. Saying it anyway
        # would mean reporting the shape of the backfill as the shape of the
        # site.
        return []

    now = _page_totals(db, client.id, period)
    before = _page_totals(db, client.id, earlier)
    if not before:
        return []

    site_now = sum(clicks for clicks, _ in now.values())
    site_before = sum(clicks for clicks, _ in before.values())
    site_drop_pct = ((site_before - site_now) / site_before * 100) if site_before > 0 else 0.0

    yoy = (period[0] - earlier[0]).days >= 300
    candidates: list[tuple[float, LeverFinding]] = []
    for url, (prior_clicks, prior_impressions) in before.items():
        if prior_clicks < DECAY_MIN_PRIOR_CLICKS:
            continue
        current_clicks, current_impressions = now.get(url, (0.0, 0.0))
        drop_pct = (prior_clicks - current_clicks) / prior_clicks * 100
        if drop_pct < DECAY_MIN_DROP_PCT:
            continue
        if drop_pct - site_drop_pct < DECAY_EXCESS_OVER_SITE_PCT:
            continue
        # Impressions have to be down too. Clicks falling while impressions
        # hold is a listing problem, and the CTR rule owns that one.
        if prior_impressions > 0 and current_impressions >= prior_impressions:
            continue

        lost = prior_clicks - current_clicks
        against = "the same period last year" if yoy else "earlier in the history"
        finding = _make_finding(
            lever=GrowthAction.AI_VISIBILITY.value,
            rule_key=_rule_key("decaying_page", url),
            diagnosis=(
                f"Down {drop_pct:.0f}% on {against}: {url} "
                f"({int(prior_clicks):,} clicks to {int(current_clicks):,})"
            ),
            action_override=(
                f"Deep refresh this page. It earned {int(prior_clicks):,} clicks "
                f"{against} and now earns {int(current_clicks):,}, while the site as a "
                f"whole moved {-site_drop_pct:+.0f}% — so this is the page losing ground, "
                "not the market. Rework the content against what currently ranks."
            ),
            evidence_json={
                "gate": "decaying_page",
                "prior_clicks": int(prior_clicks),
                "current_clicks": int(current_clicks),
                "prior_impressions": int(prior_impressions),
                "current_impressions": int(current_impressions),
                "drop_pct": round(drop_pct, 1),
                "site_drop_pct": round(site_drop_pct, 1),
                "compared_with": [earlier[0].isoformat(), earlier[1].isoformat()],
                "year_over_year": yoy,
                "promotion_class": "actionable",
            },
            baseline_metrics_json={"clicks": prior_clicks, "impressions": prior_impressions},
            impact=min(100.0, (lost / 200.0) * 100.0),
            page_url=url,
        )
        candidates.append((lost, finding))

    candidates.sort(key=lambda row: -row[0])
    return [finding for _, finding in candidates[:DECAY_MAX_FINDINGS]]


def _tracking_failure_finding(
    db: Session,
    client: Client,
    *,
    period: tuple[date, date] | None,
) -> LeverFinding | None:
    """Gate 0: are conversions being recorded at all?

    Every impact score in this engine is computed from leads. If the tag has
    stopped firing, everything below is scored against a zero that is not real,
    and the engine would confidently rank work nobody can judge. So this does
    not merely outrank the other findings — when it fires they are suppressed.

    Three things must be true together, because each alone is ordinary:
    conversions are configured, traffic is still arriving, and nothing has been
    recorded for a fortnight. A client with no conversions configured has not
    broken anything, and a quiet week is a quiet week.
    """
    if period is None:
        return None
    lead_events = _lead_event_names(db, client.id)
    if not lead_events:
        # Nothing expected, so nothing missing. No conversions configured is a
        # Setup gap, not a tracking failure, and saying otherwise would put
        # every unconfigured client at the top of its own queue.
        return None

    _, end = period
    window_start = end - timedelta(days=TRACKING_SILENCE_DAYS - 1)

    sessions = float(
        db.query(func.coalesce(func.sum(FactGa4Traffic.sessions), 0))
        .filter(
            FactGa4Traffic.client_id == client.id,
            FactGa4Traffic.date >= window_start,
            FactGa4Traffic.date <= end,
        )
        .scalar()
        or 0
    )
    leads = float(
        db.query(func.coalesce(func.sum(FactGa4Event.event_count), 0))
        .filter(
            FactGa4Event.client_id == client.id,
            FactGa4Event.date >= window_start,
            FactGa4Event.date <= end,
            FactGa4Event.event_name.in_(lead_events),
        )
        .scalar()
        or 0
    )
    if leads > 0:
        return None

    # What the fortnight should have produced, from the client's own history.
    # Whether anything was ever recorded also separates a tag that broke from
    # one never wired up: both need fixing, but they are different jobs.
    prior_leads = float(
        db.query(func.coalesce(func.sum(FactGa4Event.event_count), 0))
        .filter(
            FactGa4Event.client_id == client.id,
            FactGa4Event.date < window_start,
            FactGa4Event.event_name.in_(lead_events),
        )
        .scalar()
        or 0
    )
    prior_sessions = float(
        db.query(func.coalesce(func.sum(FactGa4Traffic.sessions), 0))
        .filter(
            FactGa4Traffic.client_id == client.id,
            FactGa4Traffic.date < window_start,
        )
        .scalar()
        or 0
    )
    ever_recorded = prior_leads > 0

    if ever_recorded and prior_sessions > 0:
        expected = sessions * (prior_leads / prior_sessions)
        if expected < TRACKING_EXPECTED_LEADS:
            return None
    elif sessions < TRACKING_NO_HISTORY_SESSIONS:
        return None
    else:
        expected = 0.0

    return _make_finding(
        lever=GrowthAction.CONVERSION_PATH.value,
        rule_key=_rule_key("tracking_silent", str(client.id)),
        diagnosis=(
            f"No conversions recorded in {TRACKING_SILENCE_DAYS} days while "
            f"{int(sessions):,} sessions arrived"
            + (
                " — tracking was working before this"
                if ever_recorded
                else " — tracking may never have fired"
            )
        ),
        evidence_json={
            "sessions": int(sessions),
            "leads": 0,
            "window_days": TRACKING_SILENCE_DAYS,
            "window_start": window_start.isoformat(),
            "window_end": end.isoformat(),
            "lead_events": lead_events,
            "previously_recorded": ever_recorded,
            "expected_leads": round(expected, 1),
            # Rule keys are hashed, so this is how anything downstream — the
            # UI, a report, a test — recognises the gate that suppressed the
            # rest rather than matching on diagnosis text.
            "gate": "tracking",
            "promotion_class": "actionable",
        },
        baseline_metrics_json={},
        impact=100.0,
        severity=100.0,
        urgency_override=100.0,
    )


#: Behind the plan by less than this is a normal month, not a finding.
CONVERSION_PLAN_SHORTFALL_RATIO = 0.8
#: Below where the client started by more than this is going backwards.
CONVERSION_BASELINE_RATIO = 0.9


def _conversion_portfolio(
    db: Session,
    client: Client,
    *,
    from_date: date,
    to_date: date,
    dashboard: dict[str, Any],
    site: SiteBusinessContext,
) -> LeverFinding | None:
    """Gate 1: is the site converting at the level the plan requires?

    The rule here used to ask one question — did the rate fall while traffic
    held — which only catches a site that got worse recently. A site that has
    converted badly since the day it was onboarded never tripped it, and that
    is the client most in need of the finding.

    Three references, because they answer different questions. Against last
    period: did something just break? Against the baseline: have we gone
    backwards from where we started? Against this month's checkpoint goal: are
    we going to make the number we promised?

    One finding either way. Three findings saying the same thing in different
    units is the noise this engine is being pulled out of, so the most urgent
    reading leads and the rest ride along as evidence.
    """
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
    if previous_rate <= 0:
        lead_rate_change_pct = -100.0 if current_rate <= 0 else 100.0
    else:
        lead_rate_change_pct = ((current_rate - previous_rate) / previous_rate) * 100

    conversions = dashboard.get("conversions", {}) or {}
    period_goal = conversions.get("period_lead_goal")
    period_leads = conversions.get("leads", {}).get("current")
    raw_baseline = client.baseline_lead_rate_pct
    baseline_rate = float(raw_baseline) if raw_baseline is not None else None

    # ── Trigger 1: something broke recently ──
    # Traffic has to be holding, or this is a traffic problem wearing a
    # conversion problem's clothes.
    falling = sessions_change_pct >= -5 and lead_rate_change_pct <= -10

    # ── Trigger 2: we have gone backwards from where we started ──
    below_baseline = (
        baseline_rate is not None
        and baseline_rate > 0
        and current_rate < baseline_rate * CONVERSION_BASELINE_RATIO
    )

    # ── Trigger 3: we are not going to make the number we promised ──
    behind_plan = (
        period_goal is not None
        and period_goal > 0
        and period_leads is not None
        and float(period_leads) < float(period_goal) * CONVERSION_PLAN_SHORTFALL_RATIO
    )

    if not (falling or below_baseline or behind_plan):
        return None

    # Most urgent reading leads: a fall says act now, backwards says the work
    # is not landing, behind plan is the ongoing story.
    if falling:
        diagnosis = "Managed traffic holding but lead rate falling"
        action = (
            "Find what changed on the conversion path in the last period — form, "
            "CTA, page template, or a tracking change that moved the goalposts."
        )
    elif below_baseline:
        diagnosis = (
            f"Lead rate {current_rate:.2f}% is below the {baseline_rate:.2f}% baseline "
            "the engagement started from"
        )
        action = (
            "Review the conversion path against what the site was doing at baseline. "
            "Converting worse than the starting point means the work is not landing "
            "where it matters."
        )
    else:
        short = float(period_goal) - float(period_leads)
        diagnosis = (
            f"{int(float(period_leads))} leads against a goal of {int(float(period_goal))} "
            f"for this period"
        )
        action = (
            f"Close a {short:.0f}-lead gap: take the pages with the most traffic and the "
            "worst conversion first, since that is where the shortfall is cheapest to buy back."
        )

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
        diagnosis=diagnosis,
        action_override=action,
        evidence_json={
            "gate": "site_conversion",
            "lead_rate_change_pct": round(lead_rate_change_pct, 1),
            "sessions_change_pct": round(sessions_change_pct, 1),
            "tracking_validated": True,
            # Every trigger is recorded, not just the one that led, so the
            # reader can see whether this is one problem or three.
            "triggers": [
                name
                for name, hit in (
                    ("falling", falling),
                    ("below_baseline", below_baseline),
                    ("behind_plan", behind_plan),
                )
                if hit
            ],
            "baseline_lead_rate_pct": round(baseline_rate, 2) if baseline_rate else None,
            "period_lead_goal": float(period_goal) if period_goal else None,
            "period_leads": float(period_leads) if period_leads is not None else None,
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


logger = logging.getLogger("organiciq.decision_engine")


# Every source the Decision Engine requires, in the order it reports them.
REQUIRED_SOURCE_LABELS: dict[str, str] = {
    "search_console": "Search Console",
    "analytics": "GA4 analytics",
    "crawl_audit": "site crawl (SE Ranking website audit)",
    "ai_visibility": "AI visibility (SE Ranking AI tracker)",
}


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
    # Scoped to the active source: a client with only the other crawl's rows
    # would otherwise read as ready while the engine finds nothing to work with.
    crawl_ready = (
        db.query(func.count())
        .select_from(FactCrawlPageSnapshot)
        .filter(
            FactCrawlPageSnapshot.client_id == client.id,
            FactCrawlPageSnapshot.source == active_crawl_source(),
        )
        .scalar()
        or 0
    ) > 0

    # GA4 drives the Conversion Path lever, which needs no Search Console data.
    ga4_period = _effective_range(from_date, to_date, watermarks.get("ga4"))
    ga4_rows = 0
    if ga4_period is not None:
        ga4_start, ga4_end = ga4_period
        ga4_rows = (
            db.query(func.count())
            .select_from(FactGa4Traffic)
            .filter(
                FactGa4Traffic.client_id == client.id,
                FactGa4Traffic.date >= ga4_start,
                FactGa4Traffic.date <= ga4_end,
            )
            .scalar()
            or 0
        )

    readiness = {
        "search_console": gsc_rows > 0,
        "analytics": ga4_rows > 0,
        "crawl_audit": crawl_ready,
        "ai_visibility": ai_period is not None,
    }
    base_result = {
        "requested_from": from_date,
        "requested_to": to_date,
        "analysis_from": gsc_period[0] if gsc_period else None,
        "analysis_to": gsc_period[1] if gsc_period else None,
        "partial_message": partial_message,
    }
    # All four sources are required, and a missing one stops the run.
    #
    # An earlier version ran on whatever happened to be present, so a client
    # with no site crawl still got a scored, confident-looking plan built from
    # three sources — the Technical SEO lever silently contributed nothing and
    # nothing on screen said so. Scores computed from a partial source set are
    # not comparable to scores computed from a full one, which makes the
    # ranking between levers wrong rather than merely incomplete. Refusing to
    # run, and naming exactly what is missing, is the honest failure.
    missing = [name for name, ok in readiness.items() if not ok]
    if missing:
        missing_labels = ", ".join(REQUIRED_SOURCE_LABELS[name] for name in missing)
        logger.warning(
            "Decision Engine blocked for client %s (%s): missing %s",
            client.id,
            client.domain,
            ", ".join(missing),
        )
        return DiagnoseResult(
            ready=False,
            message=(
                f"Decision Engine needs all four data sources. Missing: {missing_labels}. "
                "Fix the sync for those sources, then re-run."
                + (f" {block_message}" if block_message else "")
            ),
            readiness=readiness,
            formula=SCORE_FORMULA,
            levers=_lever_summaries([], []),
            **base_result,
        )

    dashboard = build_dashboard(db, client, from_date, to_date)
    pages = _load_page_demand(db, client_id=client.id, period=gsc_period)
    crawl_by_url = _load_crawl_by_url(db, client.id)
    issues_by_url, site_issue_codes = _load_audit_issues(db, client.id)
    schema_by_url, schema_crawled_urls = _load_page_schema(db, client.id)

    lead_events = _lead_event_names(db, client.id)
    site_period = ga4_period or gsc_period
    site = load_site_business_context(
        db,
        client,
        period=site_period,
        lead_events=lead_events,
        dashboard=dashboard,
    )
    page_urls = [page.normalized_url for page in pages]
    # gsc_period can be None now that GSC is no longer a hard prerequisite;
    # with no GSC there are no page URLs to build contexts for either.
    page_contexts = (
        load_page_business_contexts(
            db,
            client_id=client.id,
            period=gsc_period,
            lead_events=lead_events,
            normalized_urls=page_urls,
        )
        if gsc_period is not None and page_urls
        else {}
    )
    site = with_p90_sessions(site, page_contexts)
    thresholds = _load_thresholds(db, client.id)
    classifications = classify_pages(page_urls)
    page_type_rates = compute_page_type_lead_rates(page_contexts, classifications)
    topic_rates = compute_topic_lead_rates(page_contexts, classifications)

    # Which pages are short of links, so the gap search only runs for those
    # rather than every page on the site.
    under_linked = {
        page.normalized_url
        for page in pages
        if (crawl := crawl_by_url.get(page.normalized_url)) is not None
        and (
            crawl.inbound_editorial_links
            if crawl.source == CRAWL_SOURCE_FIRST_PARTY
            else crawl.inbound_internal_links
        )
        < _link_floor(crawl.word_count)
    }
    link_gaps = _link_gaps(db, client.id, period=gsc_period, targets=under_linked)

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
            schema_by_url=schema_by_url,
            schema_crawled_urls=schema_crawled_urls,
            link_gaps=link_gaps,
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

    # ── Pages that used to perform ──
    findings.extend(
        _decaying_page_findings(db, client, period=gsc_period, fact_min=fact_min)
    )
    for finding in findings:
        if finding.evidence_json.get("gate") == "decaying_page":
            _enrich_finding(
                finding,
                classification=classifications.get(finding.page_url or ""),
                page_ctx=page_contexts.get(finding.page_url or ""),
            )

    # ── Subjects with demand and no page at all ──
    findings.extend(_content_cluster_findings(db, client, period=gsc_period))
    for finding in findings:
        if finding.evidence_json.get("gate") == "content_cluster":
            _enrich_finding(finding, classification=None, page_ctx=None)

    # ── Gate 2: rankings that bring nothing ──
    findings.extend(
        _visibility_without_traffic_findings(db, client, pages, period=gsc_period)
    )
    for finding in findings:
        if finding.evidence_json.get("gate") == "visibility_no_traffic":
            _enrich_finding(finding, classification=None, page_ctx=None)

    # ── Gate 3: traffic that is not turning into anything ──
    # The layer closest to leads, which is the order the product works in:
    # visibility earns traffic, traffic earns leads, and a page that takes the
    # traffic and stops is the most expensive thing on the site.
    findings.extend(
        _conversion_page_findings(
            pages,
            page_contexts=page_contexts,
            classifications=classifications,
            site=site,
        )
    )
    for finding in findings:
        if finding.evidence_json.get("gate") == "conversion_page":
            _enrich_finding(
                finding,
                classification=classifications.get(finding.page_url or ""),
                page_ctx=page_contexts.get(finding.page_url or ""),
            )

    # ── The 3x override rule ──
    # A team that has thrown the same kind of suggestion away three times is
    # telling us the rule does not fit how this client is run. Keeping it in
    # the queue spends capacity on an argument already had three times, so it
    # is marked and stops being promoted — but it keeps appearing, because a
    # rule that vanishes silently can never be rewritten or deliberately
    # removed, which is what the spec asks for.
    overridden = _overridden_rule_families(db, client.id)
    for finding in findings:
        count = overridden.get(finding.evidence_json.get("rule_family", ""), 0)
        if count >= OVERRIDE_RETIREMENT_COUNT:
            finding.override_count = count

    # ── Gate 0 ──
    # A silent conversion tag makes every impact score below it a fiction, so
    # the others are marked suppressed rather than ranked beneath it. They stay
    # in the payload — hiding them entirely would make the queue look empty
    # when it is only untrustworthy — but nothing is promoted to a Growth
    # Action until the tag is fixed.
    tracking = _tracking_failure_finding(db, client, period=ga4_period)
    if tracking is not None:
        _enrich_finding(tracking, classification=None, page_ctx=None)
        for finding in findings:
            finding.suppressed_by = tracking.rule_key
        findings.append(tracking)

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
        tracked_by_url=_tracked_keywords_by_url(db, client.id),
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
