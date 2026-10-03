"""Deterministic Decision Engine — diagnose() over validated facts only."""

from __future__ import annotations

import hashlib
from contextvars import ContextVar
import logging
import re
from urllib.parse import urlsplit
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Mapping
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.decisions.confidence import data_confidence
from app.decisions.prompt_cause import PromptSignals, classify_prompt_gap
from app.decisions.ctr_cause import CtrSignals, classify_ctr_gap
from app.decisions.link_cause import Donor, LinkSignals, classify_link_gap
from app.decisions.rank_push_cause import (
    RankPushDonor,
    RankPushSignals,
    classify_rank_push,
)
from app.decisions.site_conversion_cause import (
    SiteConversionSignals,
    classify_site_conversion,
)
from app.decisions.keyword_cause import (
    MIN_IMPRESSIONS_FOR_PAGE_MATCH as KEYWORD_PAGE_MATCH_MIN_IMPRESSIONS,
    KeywordSignals,
    classify_keyword_gap,
)
from app.decisions.page_drop_cause import PageDropSignals, classify_page_drop
from app.decisions.prescription import Prescription, Step
from app.decisions.tracking_cause import TrackingSignals, classify_tracking_break
from app.decisions.effort import effort_class, ranking_score
from app.decisions.ctr_curve import has_ai_overview
from app.decisions.client_ctr_curve import build_client_ctr_curve, ctr_at
from app.decisions.ctr_curve import (
    MIN_RECOVERABLE_CLICKS,
    benchmark_source_label,
    expected_ctr_percent,
    is_ctr_underperforming,
    recoverable_clicks_at_threshold,
)
from app.decisions.thresholds import merge_thresholds
from app.models.client import Client
from app.models.config import OrganicChannel
from app.models.crawl import (
    CRAWL_SOURCE_FIRST_PARTY,
    CRAWL_SOURCE_SE_RANKING,
    FactCrawlInternalLink,
    FactCrawlPageIssue,
    FactCrawlPageSchema,
    FactCrawlPageSnapshot,
)
from app.models.decision import (
    KeywordPageMap,
    Decision,
    DecisionStatus,
    DecisionThreshold,
    DiagnosticLayer,
    DismissalReason,
    GrowthAction,
)
from app.models.ga4 import FactGa4Event, FactGa4Traffic
from app.models.gsc import FactGscPage, FactGscQueryPage
from app.models.job import DataWatermark, ValidationStatus
from app.core.settings import get_settings
from app.core.urls import normalize_url
from app.models.seranking import (
    FactSerAiCheck,
    FactSerDomainKeyword,
    FactSerKeywordMetric,
    FactSerAiPrompt,
    FactSerAiTrackerStats,
    FactSerBacklinkPage,
    FactSerKeyword,
)
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
    page_type_rate_support,
    compute_topic_lead_rates,
    load_page_business_contexts,
    downstream_lead_opportunity,
    load_site_business_context,
    normalize_business_impact,
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

#: The client's scoring weights for the run in progress.
#:
#: `_make_finding` is called from forty places and none of them care about
#: the formula, so threading the weights through every signature would be
#: noise. A context variable is the smaller lie: set once per `diagnose`,
#: read where the score is computed.
_SCORE_WEIGHTS: ContextVar[dict[str, Any]] = ContextVar("score_weights", default={})

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

#: What each gate does when it fires. B5.
#:
#: Only Gate 0 suppresses, and it suppresses because every impact score below
#: it is computed from a lead count it says is wrong. Gates 1-3 compete on
#: impact like any other finding: nothing downstream depends on them being
#: true, so silencing anything would hide work rather than clarify it.
GATE_BEHAVIOUR: dict[str, dict[str, str]] = {
    "tracking": {
        "layer": "Gate 0",
        "bucket": "Conversion Path",
        "suppresses": (
            "everything except blocking technical findings on pages that had "
            "traffic in the previous period — a 5xx on a page with demand is "
            "true whatever the conversion tag is doing"
        ),
    },
    "tracking_partial": {
        "layer": "Gate 0",
        "bucket": "Conversion Path",
        "suppresses": (
            "nothing — one form going quiet makes some scores wrong, not all "
            "of them, so the honest response is to say which"
        ),
    },
    "tracking_spike": {
        "layer": "Gate 0",
        "bucket": "Conversion Path",
        "suppresses": "nothing",
    },
    "site_conversion": {"layer": "Gate 1", "bucket": "Conversion Path", "suppresses": "nothing"},
    "visibility_no_traffic": {
        "layer": "Gate 2",
        "bucket": "Search & AI Visibility",
        "suppresses": "nothing",
    },
    "conversion_page": {"layer": "Gate 3", "bucket": "Conversion Path", "suppresses": "nothing"},
}


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


def _contested_window_start(
    db: Session, client_id: UUID, *, reset_days: int, today: date | None = None
) -> date:
    """How far back a dismissal still counts against a rule. T8.

    Two things give a rule another chance. Time, because a judgement made
    against last quarter's site is not a judgement about this one. And a
    change to the client's thresholds, because the rule that was dismissed is
    not the rule running now — holding the old verdict against it would mean
    a tuned rule could never come back.
    """
    cutoff = (today or date.today()) - timedelta(days=reset_days)
    row = (
        db.query(DecisionThreshold.updated_at)
        .filter(DecisionThreshold.client_id == client_id)
        .one_or_none()
    )
    if row and row[0]:
        changed = row[0].date() if hasattr(row[0], "date") else row[0]
        cutoff = max(cutoff, changed)
    return cutoff


def _overridden_rule_families(
    db: Session, client_id: UUID, *, reset_days: int = 90
) -> dict[str, int]:
    """Rule families this client's team keeps dismissing, and how often.

    Counted across distinct pages. Dismissing the same page three times is one
    disagreement repeated, not three — usually someone working through a stale
    queue — and retiring a rule on that would be the engine misreading its own
    history.
    """
    since = _contested_window_start(db, client_id, reset_days=reset_days)
    rows = (
        db.query(
            Decision.evidence_json,
            Decision.growth_action,
            Decision.rule_key,
            Decision.dismissal_reason,
        )
        .filter(
            Decision.client_id == client_id,
            Decision.status == DecisionStatus.DISMISSED,
            Decision.date_range_end >= since,
        )
        .all()
    )
    seen: dict[str, set[str]] = {}
    for evidence, growth_action, key, reason in rows:
        # "Wrong data" is a bug report and "already done" is a scheduling
        # note. Neither says the rule is a bad fit, and counting them would
        # retire rules for being right at an inconvenient moment. T8.
        if reason in {DismissalReason.WRONG_DATA.value, DismissalReason.ALREADY_DONE.value}:
            continue
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


def score_breakdown(
    *,
    impact: float,
    confidence: float,
    urgency: float,
    effort: float,
    thresholds: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Every term of the priority score, with its weight and contribution.

    The score was a number with a formula printed somewhere else, which is
    not the same as being able to see why one finding outranks another.
    This returns the arithmetic so the card can show it and so the weights
    can be argued with.
    """
    limits = thresholds or {}

    def weight(key: str, fallback: float) -> float:
        value = limits.get(key)
        return float(value) if isinstance(value, (int, float)) else fallback

    w_impact = weight("score_weight_impact", PRIORITY_IMPACT_WEIGHT)
    w_confidence = weight("score_weight_confidence", PRIORITY_CONFIDENCE_WEIGHT)
    w_urgency = weight("score_weight_urgency", PRIORITY_URGENCY_WEIGHT)
    w_effort = weight("score_weight_effort", PRIORITY_EFFORT_WEIGHT)
    scale = weight("score_impact_relevance_scale", PRIORITY_IMPACT_RELEVANCE_SCALE) or 1.0

    # Secondary inputs are scaled by how real the impact is, so a tidy,
    # confident, urgent finding worth nothing cannot climb on those alone.
    relevance = min(1.0, max(0.0, impact / scale))
    terms = [
        {
            "name": "Impact",
            "value": round(impact, 1),
            "weight": w_impact,
            "contribution": round(w_impact * impact, 2),
            "scaled_by_impact": False,
        },
        {
            "name": "Confidence",
            "value": round(confidence, 1),
            "weight": w_confidence,
            "contribution": round(w_confidence * confidence * relevance, 2),
            "scaled_by_impact": True,
        },
        {
            "name": "Urgency",
            "value": round(urgency, 1),
            "weight": w_urgency,
            "contribution": round(w_urgency * urgency * relevance, 2),
            "scaled_by_impact": True,
        },
        {
            "name": "Ease",
            "value": round(100.0 - effort, 1),
            "weight": w_effort,
            "contribution": round(w_effort * (100.0 - effort) * relevance, 2),
            "scaled_by_impact": True,
        },
    ]
    total = min(100.0, sum(term["contribution"] for term in terms))
    return {
        "terms": terms,
        "impact_relevance": round(relevance, 3),
        "impact_relevance_scale": scale,
        "capped_at_100": sum(term["contribution"] for term in terms) > 100.0,
        "total": round(total, 1),
    }


def score_finding(
    *,
    impact: float,
    confidence: float,
    urgency: float,
    effort: float,
    thresholds: Mapping[str, Any] | None = None,
) -> float:
    """Impact-led priority: secondary inputs only contribute when impact is meaningful."""
    return score_breakdown(
        impact=impact,
        confidence=confidence,
        urgency=urgency,
        effort=effort,
        thresholds=thresholds,
    )["total"]


def _rule_key(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]


def _link_floor(
    word_count: int,
    classification: PageClassification | None = None,
    thresholds: dict[str, float | int] | None = None,
) -> int:
    """How many editorial links a page should have, by what it is for. T4.

    Length was the wrong yardstick. A three-thousand-word blog post was held
    to the same bar as the services page the business runs on, and a short
    high-intent page was let off with two. What a page is for decides how much
    of the site should be pointing at it.
    """
    limits = thresholds or {}
    if classification is not None:
        if classification.page_type in {PageType.CONVERSION, PageType.COMMERCIAL}:
            return int(limits.get("link_floor_money", 10))
        if classification.page_type is PageType.CONSIDERATION:
            return int(limits.get("link_floor_industry", 6))
        if classification.page_type is PageType.INFORMATIONAL:
            return int(limits.get("link_floor_blog", 3))
    # No classification: fall back to length, which is better than nothing.
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


def _site_issue_payloads(db: Session, client_id: UUID) -> dict[str, dict[str, Any]]:
    """The `raw` payload of each site-level crawl issue, by code.

    Most codes carry nothing, but a few say which thing they are about —
    which AI crawlers robots.txt turns away, for instance — and the set of
    codes alone cannot answer that.
    """
    rows = (
        db.query(FactCrawlPageIssue.issue_code, FactCrawlPageIssue.raw)
        .filter(
            FactCrawlPageIssue.client_id == client_id,
            FactCrawlPageIssue.source == active_crawl_source(),
            FactCrawlPageIssue.normalized_url.is_(None),
        )
        .all()
    )
    return {code: (raw or {}) for code, raw in rows}


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
    {
        "status_error",
        "non_indexable",
        "canonical_elsewhere",
        "broken_redirect",
        "robots_blocking",
        # A page nothing links to is unreachable by crawl and by visitor alike.
        # It is blocking in the same sense a noindex is: the page exists and
        # cannot be arrived at. Phase 3.
        "orphan_page",
        # A 200 that says 404 is dropped by Google exactly as a real 404 is,
        # and a page whose stylesheet robots.txt forbids is rendered without
        # it. Both are blocking, and neither shows in a status code.
        "soft_404",
        "blocked_resources",
    }
)

#: Which growth action a technical signal belongs to.
#:
#: A title is the listing, not the plumbing. It earns the click, so a page
#: missing one is SERP & CTR work that can be promoted — the same sentence
#: cannot be said of a meta description, which Google rewrites at will and
#: which stays monthly upkeep. They used to be one signal, "missing_meta",
#: and lumping them meant the half that moves clicks could never compete for
#: an action. Phase 3.
SIGNAL_LEVERS: dict[str, str] = {
    "title_missing": GrowthAction.SERP_CTR.value,
    "title_duplicate": GrowthAction.SERP_CTR.value,
    # Nothing to convert through is not a technical defect; it is the whole
    # conversion path missing from a page people are already reaching.
    "no_conversion_element": GrowthAction.CONVERSION_PATH.value,
}


def signal_lever(audit_signal: str | None) -> str:
    return SIGNAL_LEVERS.get(audit_signal or "", GrowthAction.TECHNICAL_SEO.value)

#: Everything else Technical SEO detects is upkeep the plan already covers
#: every month — "titles, metas, internal links, schema" is Core Work in the
#: product spec, not one of the one-to-five flexible actions a client buys. It
#: is still reported; it just stops competing for capacity it was never meant
#: to spend. Before this, a Launch client with one action a month could be
#: handed twenty-five findings, most of them work already paid for.
def is_core_work_signal(audit_signal: str | None) -> bool:
    if not audit_signal:
        return False
    if audit_signal in INDEXATION_BLOCKING_SIGNALS:
        return False
    # A signal that belongs to another lever is that lever's work, and the
    # Technical SEO core-work carve-out has nothing to say about it.
    return audit_signal not in SIGNAL_LEVERS


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
    "soft_404": (
        "Return a real 404 for this URL, or restore the page. It currently "
        "answers 200 with an error, so Google keeps it in the index and keeps "
        "sending people to nothing."
    ),
    "blocked_resources": (
        "Allow these files in robots.txt. Google renders the page without them "
        "and ranks what is left, which is not the page a visitor sees."
    ),
    "no_conversion_element": (
        "Add a way to convert — a form, a phone number, or a link to the one "
        "that matters. People are reaching this page and it asks them for "
        "nothing."
    ),
    "orphan_page": (
        "Link to this page from the section it belongs to. It is earning impressions "
        "with nothing pointing at it, so neither a crawler following links nor a "
        "visitor browsing the site can reach it."
    ),
    "title_missing": (
        "Write a title tag. This page has demand and no headline in the results, so "
        "Google is inventing one from the content."
    ),
    "title_duplicate": (
        "Give this page its own title — it currently shares one with another page, so "
        "neither reads as the better answer to the query."
    ),
    "description_missing": "Write a meta description for this page.",
    "description_duplicate": (
        "Give this page its own meta description; it currently shares one with "
        "another page."
    ),
    # Kept: findings stored before titles and descriptions were separated still
    # carry these signals, and a stored finding with no action reads as a bug.
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

#: What to do about a watchlist term, per shape of the problem. A term that
#: slipped has a page to recover; a term that never ranked has no page at all,
#: and telling someone to "recover rankings" for it is telling them nothing.
def keyword_action(
    signal: str,
    keyword: str,
    ranking_url: str | None,
    existing: ExistingPageForQuery | None = None,
) -> str:
    """What to do about a keyword, given whether a page for it already exists.

    This used to tell every client with an unranked term to "build a page
    that targets it properly, or drop it from the watchlist — a term tracked
    for months with no page behind it". On smamarketing.com that went out for
    "seo services", "seo agency" and "seo company", all three of which are
    answered by /capabilities/seo. The advice was to build a page they have.

    Not ranking in the top hundred and having no page are different problems
    with opposite fixes, and Search Console already knows which one it is:
    it reports the page Google shows for the query.
    """
    where = f" on {ranking_url}" if ranking_url else ""
    if signal in {"keyword_fell_top5", "keyword_fell_top10"}:
        return (
            f"Recover \u201c{keyword}\u201d{where}: compare the page against what now "
            "outranks it for coverage and freshness, and check nothing changed on it "
            "when the slip began."
        )
    if existing is not None:
        position = (
            f" at position {existing.average_position:.0f}"
            if existing.average_position
            else ""
        )
        return (
            f"A page for \u201c{keyword}\u201d already exists: {existing.page_url}. "
            f"It draws {int(existing.impressions):,} impressions{position} and is not "
            "competing. Strengthen that page rather than building another — a second "
            "page on the same term splits what the first one has earned."
        )
    return (
        f"Nothing on the site answers \u201c{keyword}\u201d — no page draws an "
        "impression for it. Build one that targets it properly, or drop it from the "
        "watchlist, because a term tracked for months with nothing behind it is "
        "measuring an intention rather than the work."
    )


@dataclass(frozen=True)
class ExistingPageForQuery:
    page_url: str
    impressions: float
    average_position: float | None


def _pages_for_queries(
    db: Session,
    client_id: UUID,
    *,
    period: tuple[date, date] | None,
) -> dict[str, ExistingPageForQuery]:
    """The page Search Console already shows for each query.

    Keyed on the lowercased query, because a watchlist entry and a Search
    Console query differ in case far more often than in substance.
    """
    if period is None:
        return {}
    start, end = period
    rows = (
        db.query(
            FactGscQueryPage.query,
            FactGscQueryPage.normalized_url,
            func.sum(FactGscQueryPage.impressions).label("impressions"),
            func.avg(FactGscQueryPage.average_position).label("position"),
        )
        .filter(
            FactGscQueryPage.client_id == client_id,
            FactGscQueryPage.date >= start,
            FactGscQueryPage.date <= end,
        )
        .group_by(FactGscQueryPage.query, FactGscQueryPage.normalized_url)
        .all()
    )
    best: dict[str, ExistingPageForQuery] = {}
    for query, url, impressions, position in rows:
        key = (query or "").strip().lower()
        if not key or not url:
            continue
        found = ExistingPageForQuery(
            page_url=url,
            impressions=float(impressions or 0),
            average_position=float(position) if position is not None else None,
        )
        current = best.get(key)
        if current is None or found.impressions > current.impressions:
            best[key] = found
    return best


PROMPT_ACTION = (
    "Win a citation for this prompt: the sources answer engines currently cite "
    "are the brief. Cover what they cover, say it more plainly, and make sure the "
    "page states who it is about in terms a model can attribute."
)

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


def _canonical_is_wrong(
    canonical: str | None,
    page_norm: str | None,
    crawl_by_url: dict[str, FactCrawlPageSnapshot] | None,
) -> bool:
    """Whether a page canonicalizing elsewhere is a defect or the point.

    It was treated as a defect every time, which is backwards. Pointing a
    duplicate or a retired URL at the page that should rank is how
    canonicalization is supposed to work: smamarketing.com serves its old
    `/services/ppc` and `/industries/legal` URLs with canonicals aimed at
    `/capabilities/ppc` and `/industries`, which is correct, deliberate, and
    was being reported as six High-priority problems.

    It is a defect only when the target cannot do the job: off-site, missing
    from the crawl, erroring, or itself non-indexable. Then the demand
    arrives somewhere that will never rank, and nobody is getting it.
    """
    if not canonical or not page_norm:
        return False
    if urlsplit(canonical).hostname != urlsplit(page_norm).hostname:
        return True  # Off-site: the demand is being handed to someone else.
    if not crawl_by_url:
        # Without the target's row there is no evidence either way, and
        # guessing produced the false positives this exists to stop.
        return False
    target = crawl_by_url.get(canonical)
    if target is None:
        return True
    if target.status_code is not None and target.status_code >= 400:
        return True
    return not target.indexable


def detect_technical_signal(
    page_url: str,
    crawl: FactCrawlPageSnapshot,
    *,
    page_issue_codes: set[str] | None = None,
    crawl_by_url: dict[str, FactCrawlPageSnapshot] | None = None,
    schema_by_url: dict[str, PageSchema] | None = None,
    schema_crawled_urls: frozenset[str] | None = None,
    impressions: float = 0.0,
    sessions: float = 0.0,
    thresholds: dict[str, Any] | None = None,
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
    # A 200 that says 404. Google drops these exactly as it drops a real
    # error, and nothing in the status code shows it.
    if getattr(crawl, "soft_404", False):
        return DetectedTechnicalSignal(
            audit_signal="soft_404",
            issue_code=None,
            diagnosis=f"Page says it is missing but returns HTTP {status}: {page_url}",
        )
    if getattr(crawl, "blocked_resources", 0):
        count = crawl.blocked_resources
        return DetectedTechnicalSignal(
            audit_signal="blocked_resources",
            issue_code=None,
            diagnosis=(
                f"{count} script{'' if count == 1 else 's'} or stylesheet"
                f"{'' if count == 1 else 's'} this page needs "
                f"{'is' if count == 1 else 'are'} disallowed in robots.txt: {page_url}"
            ),
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
    if canonicalized_elsewhere and _canonical_is_wrong(canonical, page_norm, crawl_by_url):
        return DetectedTechnicalSignal(
            audit_signal="canonical_elsewhere",
            issue_code=None,
            diagnosis=f"Canonical points somewhere unusable: {page_url}",
        )
    # A page nothing links to cannot be reached by a crawler following links
    # or by a visitor browsing the site, however well it ranks. Demand is the
    # qualifier: most orphans are drafts, thank-you pages and old landers, and
    # reporting those would bury the handful that matter. Phase 3.
    orphan_min = float((thresholds or {}).get("orphan_min_impressions", 0) or 0)
    if crawl.inbound_internal_links <= 0 and orphan_min > 0 and impressions >= orphan_min:
        return DetectedTechnicalSignal(
            audit_signal="orphan_page",
            issue_code="no_inlinks",
            diagnosis=(
                f"Orphan page earning {int(impressions):,} impressions with no "
                f"internal links to it: {page_url}"
            ),
        )

    # Title before description, and both separately: the title earns the click
    # and is SERP & CTR work that can be promoted, while the description is
    # upkeep. One signal per page, so the promotable half has to be checked
    # first or it never surfaces. Phase 3.
    if crawl.title == "" or "title_missing" in codes:
        return DetectedTechnicalSignal(
            audit_signal="title_missing",
            issue_code="title_missing",
            diagnosis=f"No title tag on page with demand: {page_url}",
        )
    if crawl.title_duplicate or "title_duplicate" in codes:
        return DetectedTechnicalSignal(
            audit_signal="title_duplicate",
            issue_code="title_duplicate",
            diagnosis=f"Duplicate title on page with demand: {page_url}",
        )
    if crawl.description == "" or "description_missing" in codes:
        return DetectedTechnicalSignal(
            audit_signal="description_missing",
            issue_code="description_missing",
            diagnosis=f"No meta description on page with demand: {page_url}",
        )
    if crawl.description_duplicate or "description_duplicate" in codes:
        return DetectedTechnicalSignal(
            audit_signal="description_duplicate",
            issue_code="description_duplicate",
            diagnosis=f"Duplicate meta description on page with demand: {page_url}",
        )

    # Nothing on the page to convert through, on a page people reach. Last,
    # because every check above is about the page not working at all, and
    # null means the crawl predates the check rather than "counted none".
    cta_min = float((thresholds or {}).get("cta_min_sessions", 0) or 0)
    if (
        cta_min > 0
        and getattr(crawl, "conversion_elements", None) == 0
        and sessions >= cta_min
    ):
        return DetectedTechnicalSignal(
            audit_signal="no_conversion_element",
            issue_code=None,
            diagnosis=(
                f"No form, phone number or call to action on a page taking "
                f"{int(sessions):,} sessions: {page_url}"
            ),
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
    thresholds: dict[str, Any] | None = None,
) -> LeverFinding | None:
    detected = detect_technical_signal(
        page.normalized_url,
        crawl,
        page_issue_codes=page_issue_codes,
        crawl_by_url=crawl_by_url,
        schema_by_url=schema_by_url,
        schema_crawled_urls=schema_crawled_urls,
        impressions=page.impressions,
        sessions=page_ctx.ga4_sessions if page_ctx else 0.0,
        thresholds=thresholds,
    )
    if detected is None:
        return None
    lever = signal_lever(detected.audit_signal)

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
        urgency_override = max(LEVER_INPUTS[lever].urgency, 90.0)
    finding = _make_finding(
        lever=lever,
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
    prescription: Prescription | None = None,
) -> LeverFinding:
    inputs = LEVER_INPUTS[lever]
    # Recorded rather than derived later: the finding knows its own kind, and
    # a dismissal has to be countable against it long after the finding is gone.
    evidence_json = {**evidence_json, "rule_family": rule_family(lever, evidence_json)}
    # The prescription is the finding's point, so it rides in the evidence
    # where every consumer — card, API, report — already looks.
    if prescription is not None:
        evidence_json = {**evidence_json, **prescription.as_dict()}
        action_override = action_override or prescription.action_text()
    urgency = urgency_override if urgency_override is not None else inputs.urgency
    breakdown = score_breakdown(
        impact=impact,
        confidence=inputs.confidence,
        urgency=urgency,
        effort=inputs.effort,
        thresholds=_SCORE_WEIGHTS.get(),
    )
    priority_score = breakdown["total"]
    evidence_json = {**evidence_json, "score_breakdown": breakdown}
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
    #: Referring domains pointing at the donor. A page with links of its own
    #: has more to lend than one that merely gets clicks.
    source_refdomains: int = 0


def _link_gaps(
    db: Session,
    client_id: UUID,
    *,
    period: tuple[date, date] | None,
    targets: set[str],
    max_donors: int = 3,
) -> dict[str, list[LinkGap]]:
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

    # Referring domains per donor, so authority is measured by what links to
    # the page and not only by what it earns. T4.
    refdomains = {
        row.normalized_url: row.refdomains
        for row in db.query(FactSerBacklinkPage).filter(
            FactSerBacklinkPage.client_id == client_id
        )
    }

    candidates: dict[str, dict[str, LinkGap]] = {}
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
                found = candidates.setdefault(target_url, {})
                existing_gap = found.get(source_url)
                if existing_gap is None or source_clicks > existing_gap.source_clicks:
                    found[source_url] = LinkGap(
                        source_url=source_url,
                        shared_query=query,
                        source_clicks=source_clicks,
                        source_refdomains=refdomains.get(source_url, 0),
                    )

    return {
        target: sorted(
            donors.values(),
            key=lambda gap: (-gap.source_refdomains, -gap.source_clicks),
        )[:max_donors]
        for target, donors in candidates.items()
    }


def _internal_linking_finding(
    page: PageDemand,
    crawl: FactCrawlPageSnapshot,
    *,
    page_ctx: PageBusinessContext | None,
    site: SiteBusinessContext,
    lead_rate_ctx: LeadRateContext | None = None,
    classification: PageClassification | None = None,
    link_gap: LinkGap | None = None,
    link_gaps: list[LinkGap] | None = None,
    thresholds: dict[str, float | int] | None = None,
) -> LeverFinding | None:
    if page.average_position < 4 or page.average_position > 20:
        return None
    # The homepage is reached from every page on the site by definition.
    # Telling someone to add internal links to it is advice nobody can act
    # on, and it was going out with "475 inbound links" printed beside it.
    if (urlsplit(page.normalized_url).path or "/").rstrip("/") == "":
        return None
    floor = _link_floor(crawl.word_count, classification, thresholds)
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
    donors = link_gaps or ([link_gap] if link_gap else [])
    if donors:
        lines = [
            f"{gap.source_url} (anchor: \u201c{gap.shared_query}\u201d"
            + (f", {gap.source_refdomains} referring domains" if gap.source_refdomains else "")
            + ")"
            for gap in donors
        ]
        action = (
            "Add links to this page from: "
            + "; ".join(lines)
            + ". Each ranks for the same query and has the authority this page is "
            "missing. The anchor is the shared query — confirm it reads naturally "
            "in the donor's copy before using it verbatim."
        )
    return _make_finding(
        lever=GrowthAction.INTERNAL_LINKING.value,
        rule_key=_rule_key("internal_linking", page.normalized_url),
        diagnosis=diagnosis,
        prescription=classify_link_gap(
            LinkSignals(
                page_url=page.normalized_url,
                position=page.average_position,
                inbound_links=inbound,
                floor=int(floor),
                donors=[
                    Donor(
                        url=gap.source_url,
                        anchor=gap.shared_query,
                        clicks=gap.source_clicks,
                        refdomains=gap.source_refdomains,
                    )
                    for gap in donors
                ],
                recoverable_clicks=float(
                    impact_evidence.get("recoverable_clicks") or 0.0
                ),
            )
        ),
        evidence_json={
            "position": round(page.average_position, 1),
            "link_from": donors[0].source_url if donors else None,
            "link_shared_query": donors[0].shared_query if donors else None,
            "link_donors": [
                {
                    "url": gap.source_url,
                    "anchor": gap.shared_query,
                    "clicks": int(gap.source_clicks),
                    "refdomains": gap.source_refdomains,
                }
                for gap in donors
            ],
            "inbound_internal_links": crawl.inbound_internal_links,
            "inbound_editorial_links": crawl.inbound_editorial_links,
            # The number the floor was actually compared against. Showing the
            # total beside an editorial floor read as a contradiction — "475
            # inbound links (floor 6)" on a page called under-linked.
            "inbound_links_counted": inbound,
            "inbound_links_basis": (
                "editorial" if crawl.source == CRAWL_SOURCE_FIRST_PARTY else "all internal"
            ),
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


def _branded_impression_share(
    db: Session,
    client: Client,
    *,
    period: tuple[date, date] | None,
) -> dict[str, float]:
    """Share of each page's impressions that came from brand searches.

    A page ranking first for the company name has a CTR that reflects the
    brand, not the listing, and judging it against a generic curve reports a
    problem nobody can fix. T6.
    """
    if period is None:
        return {}
    brand = _brand_tokens(client)
    if not brand:
        return {}
    start, end = period
    rows = (
        db.query(
            FactGscQueryPage.normalized_url,
            FactGscQueryPage.query,
            func.sum(FactGscQueryPage.impressions),
        )
        .filter(
            FactGscQueryPage.client_id == client.id,
            FactGscQueryPage.date >= start,
            FactGscQueryPage.date <= end,
        )
        .group_by(FactGscQueryPage.normalized_url, FactGscQueryPage.query)
        .all()
    )
    totals: dict[str, list[float]] = {}
    for url, query, impressions in rows:
        value = float(impressions or 0)
        bucket = totals.setdefault(url, [0.0, 0.0])
        bucket[0] += value
        if any(token in (query or "").lower() for token in brand):
            bucket[1] += value
    return {
        url: (branded / total) for url, (total, branded) in totals.items() if total > 0
    }


#: The band between where CTR work stops paying and where a page stops
#: being close enough to push.
RANK_PUSH_MIN_POSITION = 5.0
RANK_PUSH_MAX_POSITION = 10.0
#: Enough demand that three places is worth a month's work.
RANK_PUSH_MIN_IMPRESSIONS = 200.0


def _rank_push_finding(
    page: PageDemand,
    *,
    site: SiteBusinessContext,
    crawl: FactCrawlPageSnapshot | None,
    classification: PageClassification | None,
    top_query: str | None,
    donors: list[LinkGap],
    ctr_curve: dict[int, float],
    thresholds: dict[str, Any],
) -> LeverFinding | None:
    """Positions six to ten: the band CTR work cannot reach.

    Capping SERP CTR at the top five left these pages with nothing said
    about them, and they are the ones worth most: the term is winnable,
    Google already shows the page for it, and it earns almost nothing where
    it sits.
    """
    low = float(thresholds.get("serp_ctr_max_position", 5))
    high = float(thresholds.get("rank_push_max_position", RANK_PUSH_MAX_POSITION))
    if not (low < page.average_position <= high):
        return None
    if page.impressions < float(
        thresholds.get("rank_push_min_impressions", RANK_PUSH_MIN_IMPRESSIONS)
    ):
        return None

    clicks_at_target = page.impressions * (ctr_at(low, ctr_curve) / 100.0)
    gain = max(0.0, clicks_at_target - page.clicks)
    if gain < MIN_RECOVERABLE_CLICKS:
        return None

    floor = _link_floor(crawl.word_count if crawl else 0, classification, thresholds)
    prescription = classify_rank_push(
        RankPushSignals(
            page_url=page.normalized_url,
            top_query=top_query,
            position=page.average_position,
            impressions=page.impressions,
            clicks=page.clicks,
            clicks_at_target=clicks_at_target,
            inbound_links=crawl.inbound_editorial_links if crawl else None,
            link_floor=int(floor),
            donors=[
                RankPushDonor(url=g.source_url, anchor=g.shared_query, clicks=g.source_clicks)
                for g in donors
            ],
            word_count=crawl.word_count if crawl else None,
        )
    )
    impact, impact_evidence = normalize_business_impact(
        site=site,
        estimated_incremental_leads=downstream_lead_opportunity(
            gain, site.site_lead_rate_pct
        ),
        recoverable_clicks=gain,
        data_confidence="medium",
    )
    return _make_finding(
        lever=GrowthAction.SERP_CTR.value,
        rule_key=_rule_key("rank_push", page.normalized_url),
        diagnosis=(
            f"Position {page.average_position:.0f} on {int(page.impressions):,} "
            f"impressions, below where clicks happen: {page.normalized_url}"
        ),
        evidence_json={
            "gate": "rank_push",
            "promotion_class": "actionable",
            **impact_evidence,
        },
        baseline_metrics_json={
            "impressions": page.impressions,
            "average_position": round(page.average_position, 1),
        },
        impact=impact,
        page_url=page.normalized_url,
        prescription=prescription,
    )


def _serp_ctr_finding(
    page: PageDemand,
    *,
    page_ctx: PageBusinessContext | None,
    top_query: str | None = None,
    crawl: FactCrawlPageSnapshot | None = None,
    brand: str | None = None,
    ai_overview: bool = False,
    site: SiteBusinessContext,
    lead_rate_ctx: LeadRateContext | None = None,
    classification: PageClassification | None = None,
    ctr_curve: dict[int, float] | None = None,
    branded_share: float = 0.0,
    thresholds: dict[str, Any] | None = None,
) -> LeverFinding | None:
    if page.impressions < 1000:
        return None
    # Position one included. A page ranking first and under-clicked is the
    # cheapest fix on the site, and excluding it assumed first place cannot
    # under-perform — which an AI Overview above it comfortably disproves. T6.
    #
    # The top is where it stops. On the measured curve position six earns
    # 0.73% and position eight 0.47%, so a page there with *zero* clicks has
    # under four to win back from a thousand impressions — less than the
    # five-click floor this rule already required. The old range of ten was
    # therefore dead below about five without saying so. Writing a better
    # listing cannot buy a click that is not on offer; outside the top five
    # the work is rank, not the listing.
    max_position = float((thresholds or {}).get("serp_ctr_max_position", 5))
    if page.average_position < 1 or page.average_position > max_position:
        return None
    # Brand searches convert at their own rate and are not a listing problem:
    # someone typing the company name clicks whatever is there. T6.
    if branded_share >= BRANDED_SHARE_MAX:
        return None
    expected = ctr_at(page.average_position, ctr_curve or {})
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
        prescription=classify_ctr_gap(
            CtrSignals(
                page_url=page.normalized_url,
                top_query=top_query or "",
                impressions=page.impressions,
                clicks=page.clicks,
                ctr_percent=page.ctr_percent,
                expected_ctr_percent=expected,
                recoverable_clicks=recoverable,
                title=crawl.title if crawl else None,
                description=crawl.description if crawl else None,
                brand=brand,
                ai_overview=ai_overview,
            )
        )
        if top_query
        else None,
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


def _top_query_per_page(
    db: Session, client_id: UUID, *, period: tuple[date, date] | None
) -> dict[str, str]:
    """The query each page draws most of its impressions from.

    A title rewrite has to lead with something, and the page's own biggest
    query is the only honest candidate — guessing from the URL slug would
    put the wrong phrase in front of a real edit.
    """
    if period is None:
        return {}
    start, end = period
    rows = (
        db.query(
            FactGscQueryPage.normalized_url,
            FactGscQueryPage.query,
            func.sum(FactGscQueryPage.impressions).label("impressions"),
        )
        .filter(
            FactGscQueryPage.client_id == client_id,
            FactGscQueryPage.date >= start,
            FactGscQueryPage.date <= end,
        )
        .group_by(FactGscQueryPage.normalized_url, FactGscQueryPage.query)
        .all()
    )
    best: dict[str, tuple[float, str]] = {}
    for url, query, impressions in rows:
        if not url or not query:
            continue
        total = float(impressions or 0)
        current = best.get(url)
        if current is None or total > current[0]:
            best[url] = (total, query)
    return {url: query for url, (_, query) in best.items()}


def _ai_overview_queries(db: Session, client_id: UUID) -> frozenset[str]:
    """Queries whose SERP carries an AI Overview, lowercased."""
    rows = (
        db.query(FactSerDomainKeyword.keyword, FactSerDomainKeyword.serp_features)
        .filter(FactSerDomainKeyword.client_id == client_id)
        .all()
    )
    return frozenset(
        (keyword or "").strip().lower()
        for keyword, features in rows
        if keyword and has_ai_overview(features)
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
    link_gaps: dict[str, list[LinkGap]] | None = None,
    thresholds: dict[str, float | int] | None = None,
    page_ctr_curve: dict[int, float] | None = None,
    branded_shares: dict[str, float] | None = None,
    top_queries: dict[str, str] | None = None,
    ai_overview_queries: frozenset[str] = frozenset(),
    client_brand: str | None = None,
) -> list[LeverFinding]:
    findings: list[LeverFinding] = []
    issue_map = issues_by_url or {}
    gaps = link_gaps or {}
    ctr_curve = page_ctr_curve or {}
    branded = branded_shares or {}
    top_queries = top_queries or {}
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
                thresholds=thresholds,
            )
            if finding is None:
                finding = _internal_linking_finding(
                    page,
                    crawl,
                    page_ctx=page_ctx,
                    site=site,
                    lead_rate_ctx=lead_rate_ctx,
                    classification=classification,
                    link_gap=(gaps.get(page.normalized_url) or [None])[0],
                    link_gaps=gaps.get(page.normalized_url),
                    thresholds=thresholds,
                )
        if finding is None:
            finding = _serp_ctr_finding(
                page,
                page_ctx=page_ctx,
                site=site,
                lead_rate_ctx=lead_rate_ctx,
                classification=classification,
                ctr_curve=ctr_curve,
                branded_share=branded.get(page.normalized_url, 0.0),
                top_query=top_queries.get(page.normalized_url),
                thresholds=thresholds,
                crawl=crawl,
                brand=client_brand,
                ai_overview=bool(
                    ai_overview_queries
                    and top_queries.get(page.normalized_url) in ai_overview_queries
                ),
            )
        if finding is None:
            # Below the top five a better listing buys nothing, so the work
            # is rank. This is the band SERP CTR deliberately stops at.
            finding = _rank_push_finding(
                page,
                site=site,
                crawl=crawl,
                classification=classification,
                top_query=top_queries.get(page.normalized_url),
                donors=(link_gaps or {}).get(page.normalized_url, []),
                ctr_curve=ctr_curve,
                thresholds=thresholds or {},
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
                thresholds=thresholds,
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


def _keyword_market_data(
    db: Session, client_id: UUID
) -> dict[str, tuple[float | None, bool]]:
    """Difficulty and SERP shape per keyword, from the domain-keywords fact.

    The rank-tracker fact carries neither. Its `earned_serp_features` lists
    the features the client *won*, which for a keyword that does not rank is
    empty — the inverse of the question "is there an AI Overview sitting
    above this result". The domain-keywords pipeline stores the SERP's own
    features and a difficulty score, so the two are joined on the keyword
    text, which is the only key they share.
    """
    out: dict[str, tuple[float | None, bool]] = {}

    # Domain keywords first: they are the only source carrying the SERP's own
    # features, so they are what can say an AI Overview sits above a result.
    for keyword, difficulty, features in (
        db.query(
            FactSerDomainKeyword.keyword,
            FactSerDomainKeyword.difficulty,
            FactSerDomainKeyword.serp_features,
        )
        .filter(FactSerDomainKeyword.client_id == client_id)
        .all()
    ):
        key = (keyword or "").strip().lower()
        if key:
            out[key] = (
                float(difficulty) if difficulty is not None else None,
                has_ai_overview(features),
            )

    # Then the keyword database, which covers terms the client does not rank
    # for — the ones every "nothing ranks for this" estimate is about, and
    # the ones the domain endpoint by definition cannot see. It carries no
    # SERP features, so an AI Overview already found above is kept.
    for keyword, difficulty in (
        db.query(FactSerKeywordMetric.keyword, FactSerKeywordMetric.difficulty)
        .filter(
            FactSerKeywordMetric.client_id == client_id,
            FactSerKeywordMetric.difficulty.isnot(None),
        )
        .all()
    ):
        key = (keyword or "").strip().lower()
        if not key:
            continue
        _, ai_overview = out.get(key, (None, False))
        out[key] = (float(difficulty), ai_overview)

    return out


def _keyword_page_map(db: Session, client_id: UUID) -> dict[str, tuple[str | None, bool]]:
    """What a person said about which page owns each term.

    Returns `(page_url, recorded)`. A recorded row with no URL means "no
    page owns this yet", which is an answer — asking for it again is the
    engine forgetting what it was told.
    """
    rows = (
        db.query(KeywordPageMap.keyword, KeywordPageMap.page_url)
        .filter(KeywordPageMap.client_id == client_id)
        .all()
    )
    return {
        (keyword or "").strip().lower(): (page_url or None, True)
        for keyword, page_url in rows
        if keyword
    }


def _keyword_prescription(
    keyword: str,
    volume: float,
    difficulty: float | None,
    existing: ExistingPageForQuery | None,
    crawl_by_url: dict[str, FactCrawlPageSnapshot],
    mapping: tuple[str | None, bool] = (None, False),
) -> Prescription:
    """Playbook 7's decision tree, with the crawl answering "can it rank".

    Which page we are talking about is decided once, here, and everything
    downstream reads that page. Deciding it in two places named one page
    and quoted another's title.
    """
    has_gsc_page = bool(existing) and (
        existing.impressions >= KEYWORD_PAGE_MATCH_MIN_IMPRESSIONS
    )
    mapped_url, mapping_recorded = mapping
    target_url = mapped_url or (existing.page_url if has_gsc_page else None)
    crawl = crawl_by_url.get(target_url) if target_url else None

    canonical_elsewhere = False
    if crawl is not None and crawl.canonical_url:
        canonical_elsewhere = _normalize_canonical(
            crawl.canonical_url
        ) != _normalize_canonical(crawl.normalized_url)

    return classify_keyword_gap(
        KeywordSignals(
            keyword=keyword,
            volume=volume,
            difficulty=difficulty,
            page_url=existing.page_url if existing else None,
            page_impressions=existing.impressions if existing else 0.0,
            page_position=existing.average_position if existing else None,
            mapped_url=mapped_url,
            mapping_recorded=mapping_recorded,
            indexable=crawl.indexable if crawl else None,
            canonical_elsewhere=canonical_elsewhere,
            in_sitemap=crawl.in_sitemap if crawl else None,
            inbound_internal_links=crawl.inbound_internal_links if crawl else None,
            title=crawl.title if crawl else None,
        )
    )


def _ai_visibility_keyword_findings(
    db: Session,
    client_id: UUID,
    *,
    site: SiteBusinessContext,
    thresholds: dict[str, float | int],
    period: tuple[date, date] | None = None,
    crawl_by_url: dict[str, FactCrawlPageSnapshot] | None = None,
) -> list[LeverFinding]:
    crawl_by_url = crawl_by_url or {}
    min_volume = float(thresholds.get("ai_visibility_min_keyword_volume", 50))
    top_n = int(thresholds.get("ai_visibility_keyword_top_n", 25))
    rows = db.query(FactSerKeyword).filter(FactSerKeyword.client_id == client_id).all()
    market = _keyword_market_data(db, client_id)
    existing_pages = _pages_for_queries(db, client_id, period=period)
    keyword_map = _keyword_page_map(db, client_id)
    candidates: list[tuple[float, LeverFinding]] = []
    for row in rows:
        volume = _keyword_volume(row)
        difficulty, ai_overview = market.get((row.keyword or "").strip().lower(), (None, False))
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
            difficulty=difficulty,
            ai_overview=ai_overview,
            thresholds=thresholds,
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
            action_override=(
                keyword_action(signal, row.keyword, row.ranking_url)
                if signal != "keyword_not_ranking"
                else None
            ),
            prescription=(
                _keyword_prescription(
                    row.keyword,
                    volume,
                    difficulty,
                    existing_pages.get((row.keyword or "").strip().lower()),
                    crawl_by_url,
                    keyword_map.get((row.keyword or "").strip().lower(), (None, False)),
                )
                if signal == "keyword_not_ranking"
                else None
            ),
        )
        # Prefer fallouts over not-ranking when sorting; volume is secondary.
        rank_boost = {"keyword_fell_top5": 1e9, "keyword_fell_top10": 1e8}.get(signal, 0.0)
        candidates.append((rank_boost + volume, finding))

    candidates.sort(key=lambda row: row[0], reverse=True)
    return [finding for _, finding in candidates[:top_n]]


#: Words too common to tell two pages apart.
_PROMPT_STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "best", "by", "can", "do",
        "does", "for", "from", "how", "in", "is", "it", "me", "my", "of", "on",
        "or", "should", "that", "the", "to", "top", "what", "when", "which",
        "who", "why", "with", "you", "your",
    }
)


def _best_page_for_prompt(
    prompt: str, page_titles: dict[str, str], *, require_clear_winner: bool = False
) -> str | None:
    """The page whose title and URL best match a phrase.

    Vector similarity is what the playbook asks for and there are no
    embeddings yet, so this is shared terms over the title and the URL
    slug, with two guards learnt from getting it wrong.

    A candidate carrying qualifiers the phrase does not is penalised: for
    "seo services", `/capabilities/local-seo` shares both words and is
    still the wrong page, because "local" narrows it to a different term.

    `require_clear_winner` refuses to answer on a tie. Naming a page is a
    claim that someone will act on, and two pages scoring the same means we
    do not know which.
    """
    terms = _match_terms(prompt)
    if not terms:
        return None

    scored: list[tuple[float, str]] = []
    for url, title in page_titles.items():
        candidate = _match_terms(title) | _match_terms(
            urlsplit(url).path.replace("-", " ").replace("/", " ")
        )
        shared = terms & candidate
        if len(shared) < 2:
            continue
        # Words the candidate adds that the phrase never asked for. "Local"
        # on a page matched to "seo services" is not a near miss, it is a
        # different service.
        extra = len(candidate - terms - _MATCH_GENERIC)
        scored.append((len(shared) - 0.5 * extra, url))

    if not scored:
        return None
    scored.sort(key=lambda row: (-row[0], row[1]))
    if require_clear_winner and len(scored) > 1 and scored[0][0] == scored[1][0]:
        return None
    return scored[0][1]


#: Words that appear on every page of a site and say nothing about which.
_MATCH_GENERIC = frozenset(
    {"capabilities", "services", "service", "solutions", "page", "home", "index"}
)


def _match_terms(text: str) -> set[str]:
    return {
        word
        for word in re.findall(r"[a-z0-9]+", (text or "").lower())
        if word not in _PROMPT_STOPWORDS and len(word) > 2
    }


def _ai_visibility_prompt_findings(
    db: Session,
    client_id: UUID,
    period: tuple[date, date] | None,
    *,
    site: SiteBusinessContext,
    thresholds: dict[str, float | int],
    blocked_crawlers: tuple[str, ...] = (),
    crawl_by_url: dict[str, FactCrawlPageSnapshot] | None = None,
) -> list[LeverFinding]:
    if period is None:
        return []
    page_titles = {
        url: crawl.title or "" for url, crawl in (crawl_by_url or {}).items()
    }
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
            prescription=classify_prompt_gap(
                PromptSignals(
                    prompt=prompt_text,
                    checks=len(rows),
                    blocked_crawlers=blocked_crawlers,
                    best_page=_best_page_for_prompt(prompt_text, page_titles),
                    # SE Visible holds who is cited instead; it is not
                    # ingested, so the card asks a person to read it.
                    citations_known=False,
                )
            ),
        )
        candidates.append((volume + len(rows), finding))

    candidates.sort(key=lambda row: row[0], reverse=True)
    return [finding for _, finding in candidates[:top_n]]


def _blocked_ai_crawlers(
    site_codes: set[str], raw_by_code: dict[str, dict[str, Any]]
) -> tuple[str, ...]:
    """AI crawlers robots.txt turns away, from the site-level crawl issue."""
    if "ai_crawlers_blocked" not in site_codes:
        return ()
    agents = (raw_by_code.get("ai_crawlers_blocked") or {}).get("agents") or []
    return tuple(str(agent) for agent in agents)


def _ai_visibility_findings(
    db: Session,
    client_id: UUID,
    period: tuple[date, date] | None,
    *,
    site: SiteBusinessContext,
    thresholds: dict[str, float | int],
    crawl_by_url: dict[str, FactCrawlPageSnapshot] | None = None,
    blocked_crawlers: tuple[str, ...] = (),
) -> list[LeverFinding]:
    """Ranking + AI citation findings.

    Structured data / GEO Grader schema signals are deferred to Content Opportunities.
    """
    findings = _ai_visibility_keyword_findings(
        db,
        client_id,
        site=site,
        thresholds=thresholds,
        period=period,
        crawl_by_url=crawl_by_url,
    )
    findings.extend(
        _ai_visibility_prompt_findings(
            db,
            client_id,
            period,
            site=site,
            thresholds=thresholds,
            blocked_crawlers=blocked_crawlers,
            crawl_by_url=crawl_by_url,
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
    # Managed channels only, which the name always claimed and the query never
    # did. Counting paid and direct alongside organic measured a rate the
    # engagement does not move, so a paid campaign ending read as the organic
    # conversion path breaking. T1.
    leads = (
        db.query(func.coalesce(func.sum(FactGa4Event.event_count), 0))
        .filter(
            FactGa4Event.client_id == client_id,
            FactGa4Event.date >= start,
            FactGa4Event.date <= end,
            FactGa4Event.event_name.in_(lead_events),
            FactGa4Event.channel.in_(MANAGED_CHANNELS),
        )
        .scalar()
    )
    sessions = (
        db.query(func.coalesce(func.sum(FactGa4Traffic.sessions), 0))
        .filter(
            FactGa4Traffic.client_id == client_id,
            FactGa4Traffic.date >= start,
            FactGa4Traffic.date <= end,
            FactGa4Traffic.channel.in_(MANAGED_CHANNELS),
        )
        .scalar()
    )
    sessions_f = float(sessions or 0)
    if sessions_f <= 0:
        return None
    return (float(leads or 0) / sessions_f) * 100


def _managed_sessions(
    db: Session, client_id: UUID, period: tuple[date, date] | None
) -> float:
    if period is None:
        return 0.0
    start, end = period
    return float(
        db.query(func.coalesce(func.sum(FactGa4Traffic.sessions), 0))
        .filter(
            FactGa4Traffic.client_id == client_id,
            FactGa4Traffic.date >= start,
            FactGa4Traffic.date <= end,
            FactGa4Traffic.channel.in_(MANAGED_CHANNELS),
        )
        .scalar()
        or 0
    )


#: What OrganicIQ actually moves. Paid and direct belong on the dashboard and
#: not in a rule about whether the organic conversion path is working.
MANAGED_CHANNELS = (OrganicChannel.ORGANIC_SEARCH, OrganicChannel.AI_REFERRAL)


#: A page converts "below the site" only when the gap is worth someone's
#: afternoon. Measured in leads rather than percentage points: a page five
#: points under the site rate is noise at forty sessions and a serious problem
#: at four thousand, and only the lead count tells the two apart.
CONVERSION_PAGE_MIN_SHORTFALL = 3.0
#: Half the site's own rate. A page merely under the average is not a finding —
#: half of every site's pages are, by definition.
CONVERSION_PAGE_RATE_RATIO = 0.5


#: A page needs this many leads in the earlier window to have been
#: "converting" at all. Below it a fall to zero is one lead not arriving.
PAGE_DROP_MIN_PRIOR_LEADS = 3.0
#: And enough traffic for a rate to mean anything. Five leads from twelve
#: sessions is a 42% conversion rate, which is an attribution artefact
#: rather than a page worth prescribing against.
PAGE_DROP_MIN_PRIOR_SESSIONS = 50.0
#: How many of these to raise. The list is a queue, not an inventory.
PAGE_DROP_MAX_FINDINGS = 5


def _converting_page_dropped_findings(
    db: Session,
    client: Client,
    *,
    period: tuple[date, date] | None,
    site: SiteBusinessContext,
    crawl_by_url: dict[str, FactCrawlPageSnapshot],
    thresholds: dict[str, Any],
) -> list[LeverFinding]:
    """Pages that used to convert and stopped. Playbook lever 2.

    Leads are sessions times conversion rate, so this never says "the page
    is underperforming" without first saying which of the two moved. When
    the traffic went, the card says so and points at the lever that can do
    something about it, rather than prescribing a rewrite that cannot work.
    """
    if period is None:
        return []
    lead_events = _lead_event_names(db, client.id)
    if not lead_events:
        return []

    start, end = period
    span = (end - start).days + 1
    before_end = start - timedelta(days=1)
    before_start = before_end - timedelta(days=span - 1)

    leads_now = _leads_by_page(db, client.id, lead_events, start, end)
    leads_before = _leads_by_page(db, client.id, lead_events, before_start, before_end)
    sessions_now = _sessions_by_page(db, client.id, start, end)
    sessions_before = _sessions_by_page(db, client.id, before_start, before_end)

    candidates: list[tuple[float, LeverFinding]] = []
    for url, prior_leads in leads_before.items():
        if prior_leads < PAGE_DROP_MIN_PRIOR_LEADS:
            continue
        before_sessions = sessions_before.get(url, 0.0)
        if before_sessions < PAGE_DROP_MIN_PRIOR_SESSIONS:
            continue
        now_sessions = sessions_now.get(url, 0.0)
        now_leads = leads_now.get(url, 0.0)
        lost = prior_leads - now_leads
        if lost <= 0:
            continue

        crawl = crawl_by_url.get(url)
        prescription = classify_page_drop(
            PageDropSignals(
                page_url=url,
                sessions_now=now_sessions,
                sessions_before=before_sessions,
                rate_now=(now_leads / now_sessions * 100.0) if now_sessions else 0.0,
                rate_before=prior_leads / before_sessions * 100.0,
                leads_lost=lost,
                conversion_elements=(
                    crawl.conversion_elements if crawl is not None else None
                ),
                # GA4 carries no device dimension and no Core Web Vitals are
                # stored, so the mobile and speed branches cannot fire yet.
                # Passing None is the honest input; inventing one is not.
                mobile_rate=None,
                desktop_rate=None,
                mobile_lcp_seconds=None,
                changed_on=None,
            )
        )
        if prescription is None:
            continue

        impact, impact_evidence = normalize_business_impact(
            site=site,
            leads_at_risk=lost,
            data_confidence="high",
        )
        finding = _make_finding(
            lever=GrowthAction.CONVERSION_PATH.value,
            rule_key=_rule_key("page_dropped", url),
            diagnosis=(
                f"{prior_leads:.0f} leads to {now_leads:.0f} on {url} — "
                f"{prescription.summary.lower()}"
            ),
            evidence_json={
                "gate": "converting_page_dropped",
                "promotion_class": "actionable",
                "prior_leads": round(prior_leads, 1),
                "current_leads": round(now_leads, 1),
                "compared_with": [before_start.isoformat(), before_end.isoformat()],
                **impact_evidence,
            },
            baseline_metrics_json={"leads": prior_leads, "sessions": before_sessions},
            impact=impact,
            page_url=url,
            prescription=prescription,
        )
        candidates.append((lost, finding))

    candidates.sort(key=lambda row: -row[0])
    return [finding for _, finding in candidates[:PAGE_DROP_MAX_FINDINGS]]


def _conversion_page_findings(
    pages: list[PageDemand],
    *,
    page_contexts: dict[str, PageBusinessContext],
    classifications: dict[str, PageClassification],
    site: SiteBusinessContext,
    page_type_rates: dict[str, float] | None = None,
    page_type_support: dict[str, tuple[int, int]] | None = None,
    thresholds: dict[str, float | int] | None = None,
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

    rates = page_type_rates or {}
    support = page_type_support or {}
    limits = thresholds or {}
    min_pages = int(limits.get("gate3_page_type_min_pages", 5))
    min_leads = int(limits.get("gate3_page_type_min_leads", 10))

    def comparison_for(classification: PageClassification | None) -> tuple[float, str]:
        """The rate this page should be judged against. T3.

        A blog post converting at 0.4% is doing its job; a service page at
        0.4% is not. Measuring both against one sitewide number flags every
        blog on a site with good service pages, and excuses every service page
        on a site with a big blog.
        """
        if classification is not None:
            key = classification.page_type.value
            pages_seen, leads_seen = support.get(key, (0, 0))
            rate = rates.get(key)
            if rate and pages_seen >= min_pages and leads_seen >= min_leads:
                return rate, key
        return site_rate, "site"

    findings: list[LeverFinding] = []
    for page in pages:
        ctx = page_contexts.get(page.normalized_url)
        if ctx is None or ctx.ga4_sessions <= 0:
            continue
        classification = classifications.get(page.normalized_url)
        if classification is not None and not classification.eligible_for_growth_action:
            continue

        benchmark, benchmark_source = comparison_for(classification)
        expected = ctx.ga4_sessions * (benchmark / 100.0)
        shortfall = expected - ctx.ga4_leads
        if shortfall < CONVERSION_PAGE_MIN_SHORTFALL:
            continue
        page_rate = ctx.page_lead_rate_pct or 0.0
        if page_rate >= benchmark * CONVERSION_PAGE_RATE_RATIO:
            continue

        none_at_all = ctx.ga4_leads == 0
        diagnosis = (
            f"{int(ctx.ga4_sessions):,} sessions and no conversions: {page.normalized_url}"
            if none_at_all
            else (
                f"Converting at {page_rate:.2f}% against {benchmark:.2f}% for "
                f"{'the site' if benchmark_source == 'site' else benchmark_source + ' pages'}: "
                f"{page.normalized_url}"
            )
        )
        action = (
            "Work the conversion path on this page — CTA placement, form length, and "
            "whether the offer matches what the visitor searched for. "
            f"At the site's own rate it would be producing about {shortfall:.0f} more "
            "leads per period."
        )

        # The shortfall is already a lead count, which is the engine's unit, so
        # it goes through the shared normaliser rather than its own arithmetic.
        # High confidence: these are the page's own measured sessions and leads.
        impact, impact_evidence = normalize_business_impact(
            site=site,
            estimated_incremental_leads=shortfall,
            data_confidence="high",
        )

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
                    "benchmark_rate_pct": round(benchmark, 2),
                    "benchmark_source": benchmark_source,
                    "expected_leads": round(expected, 1),
                    "shortfall_leads": round(shortfall, 1),
                    "no_conversions_at_all": none_at_all,
                    "promotion_class": "actionable",
                    **impact_evidence,
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
#: Above this share of branded impressions a page's CTR says more about the
#: brand than the listing.
BRANDED_SHARE_MAX = 0.5


#: Kept for the impression check: a ranking that is not even being shown is a
#: different problem from one being shown and not clicked.
VISIBILITY_IMPRESSION_RATIO = 0.1
DAYS_PER_MONTH_VISIBILITY = 365 / 12


def _visibility_without_traffic_findings(
    db: Session,
    client: Client,
    pages: list[PageDemand],
    *,
    period: tuple[date, date] | None,
    site: SiteBusinessContext,
    thresholds: dict[str, float | int] | None = None,
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
    traffic_by_url = {page.normalized_url: (page.impressions, page.clicks) for page in pages}
    ctr_curve, curve_source = build_client_ctr_curve(db, client.id, period)
    capture_ratio = float((thresholds or {}).get("gate2_capture_ratio", 0.5))

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
        impressions, actual_clicks = traffic_by_url.get(url, (0.0, 0.0))
        expected = volume * (period_days / DAYS_PER_MONTH_VISIBILITY)
        if expected <= 0:
            continue

        # What the position should earn, from this client's own curve where it
        # has one. A flat tenth treated position one and position ten alike,
        # which is the whole thing a CTR curve exists to avoid. T2.
        expected_ctr = ctr_at(position, ctr_curve)
        expected_clicks = expected * (expected_ctr / 100.0)
        if expected_clicks <= 0 or actual_clicks >= expected_clicks * capture_ratio:
            continue

        share = (impressions / expected) * 100 if expected else 0.0

        # Scored in leads like everything else. The searches this ranking is
        # not reaching, converted at the position's own click rate and then at
        # the site's lead rate. Confidence is low: the volume figure is a
        # third-party estimate and the lead rate is the site's, not the page's.
        missed_clicks = max(0.0, expected_clicks - actual_clicks)
        impact, impact_evidence = normalize_business_impact(
            site=site,
            estimated_incremental_leads=downstream_lead_opportunity(
                missed_clicks, site.site_lead_rate_pct
            ),
            recoverable_clicks=missed_clicks,
            data_confidence="low",
        )
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
                    "expected_ctr_pct": round(expected_ctr, 2),
                    "expected_clicks": round(expected_clicks, 1),
                    "actual_clicks": int(actual_clicks),
                    "ctr_curve_source": curve_source,
                    "capture_ratio": capture_ratio,
                    "missed_clicks": round(missed_clicks, 1),
                    "promotion_class": "actionable",
                    **impact_evidence,
                },
                baseline_metrics_json={"search_volume": volume, "position": position},
                impact=impact,
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
#: What a new page can realistically reach. Scoring a cluster as if it would
#: take position one would make every content gap the biggest finding on the
#: board.
CLUSTER_TARGET_POSITION = 8.0


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
    site: SiteBusinessContext,
    thresholds: dict[str, Any] | None = None,
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

    limits = thresholds or {}
    min_phrase = int(limits.get("cluster_min_phrase_words", 2))
    generic = {str(term).strip().lower() for term in limits.get("cluster_generic_terms") or []}
    excluded = {
        str(topic).strip().lower() for topic in limits.get("cluster_excluded_topics") or []
    }
    brand = _brand_tokens(client) | generic
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
        # A single shared word is a coincidence of vocabulary, not a subject:
        # "guide" joins a hundred unrelated queries. A phrase is a subject. T5.
        if len(shared) < min_phrase:
            continue
        # Read the words off the busiest query so they come out in the order a
        # person would say them, not alphabetically.
        busiest = max(entries, key=lambda row: row[1])[0]
        order = {word: index for index, word in enumerate(_cluster_tokens(busiest, brand))}
        label = " ".join(sorted(shared, key=lambda word: order.get(word, 99)))
        if label.lower() in excluded or any(term in label.lower() for term in excluded):
            continue
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

        # Scored in leads, like everything else. A new page would not take the
        # whole cluster, so the estimate is what a modest page-one position
        # earns, converted at the site's lead rate. Confidence is low — this is
        # a page that does not exist yet, judged on a heuristic grouping.
        winnable_clicks = total * (expected_ctr_percent(CLUSTER_TARGET_POSITION) / 100.0)
        impact, impact_evidence = normalize_business_impact(
            site=site,
            estimated_incremental_leads=downstream_lead_opportunity(
                winnable_clicks, site.site_lead_rate_pct
            ),
            recoverable_clicks=winnable_clicks,
            data_confidence="low",
        )
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
                    "winnable_clicks": round(winnable_clicks, 1),
                    "promotion_class": "actionable",
                    **impact_evidence,
                },
                baseline_metrics_json={"impressions": total, "best_position": best},
                impact=impact,
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


#: A page whose average position moved less than this did not lose its
#: rankings, whatever happened to its impressions.
RANKING_SLIP_POSITIONS = 3.0


def _page_positions(
    db: Session, client_id: UUID, now: tuple[date, date], before: tuple[date, date]
) -> dict[str, tuple[float | None, float | None]]:
    """Average position per URL in each window, for telling demand from decay.

    Impressions falling says nothing on its own: a page can lose them by
    slipping down the results or because fewer people are searching. The
    position is what separates the two, and the fixes are opposite —
    rewrite the page, or leave it alone.
    """

    def _avg(window: tuple[date, date]) -> dict[str, float]:
        start, end = window
        rows = (
            db.query(
                FactGscPage.normalized_url,
                func.sum(FactGscPage.average_position * FactGscPage.impressions),
                func.sum(FactGscPage.impressions),
            )
            .filter(
                FactGscPage.client_id == client_id,
                FactGscPage.date >= start,
                FactGscPage.date <= end,
                FactGscPage.impressions > 0,
            )
            .group_by(FactGscPage.normalized_url)
            .all()
        )
        out: dict[str, float] = {}
        for url, weighted, impressions in rows:
            total = float(impressions or 0)
            if url and total > 0:
                out[url] = float(weighted or 0) / total
        return out

    current, prior = _avg(now), _avg(before)
    return {
        url: (current.get(url), prior.get(url))
        for url in set(current) | set(prior)
    }


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
    site: SiteBusinessContext,
    thresholds: dict[str, Any] | None = None,
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

    limits = thresholds or {}
    flat_band = float(limits.get("decay_impressions_flat_pct", 10.0))
    light_min_drop = float(limits.get("light_refresh_min_drop_pct", 20.0))

    now = _page_totals(db, client.id, period)
    before = _page_totals(db, client.id, earlier)
    if not before:
        return []
    positions = _page_positions(db, client.id, period, earlier)

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
        if drop_pct < light_min_drop:
            continue
        if drop_pct - site_drop_pct < DECAY_EXCESS_OVER_SITE_PCT:
            continue

        impressions_change = (
            ((current_impressions - prior_impressions) / prior_impressions * 100)
            if prior_impressions > 0
            else 0.0
        )
        # Clicks falling while impressions hold is not decay. The page is
        # still being shown as often and chosen less, which is the listing or
        # something now sitting above it — a different job from rewriting the
        # page, and routed accordingly rather than silently dropped. T7.
        held = abs(impressions_change) <= flat_band
        lost = prior_clicks - current_clicks
        against = "the same period last year" if yoy else "earlier in the history"

        # ── Playbook 5: impressions tell three stories apart ──
        # Clicks down with impressions holding is the listing losing the
        # click, which is a different job from rewriting the page and routes
        # to SERP CTR. Clicks and impressions both down with rankings holding
        # is the market, and there is nothing to do about that.
        position_now, position_before = positions.get(url, (None, None))
        rankings_held = (
            position_now is not None
            and position_before is not None
            and position_now - position_before <= RANKING_SLIP_POSITIONS
        )
        evidence = {
            "prior_clicks": int(prior_clicks),
            "current_clicks": int(current_clicks),
            "prior_impressions": int(prior_impressions),
            "current_impressions": int(current_impressions),
            "drop_pct": round(drop_pct, 1),
            "impressions_change_pct": round(impressions_change, 1),
            "average_position_before": (
                round(position_before, 1) if position_before is not None else None
            ),
            "average_position_now": (
                round(position_now, 1) if position_now is not None else None
            ),
        }

        if held:
            prescription = Prescription(
                cause="ctr_loss",
                evidence=evidence,
                steps=[
                    Step(
                        "Open the SERP for this page's top query and record what sits above it",
                        target=url,
                        detail="An AI Overview, a video carousel or a new local pack "
                        "takes the click without taking the ranking.",
                        human=True,
                    ),
                    Step(
                        "Rewrite the title to lead with the query in the first 40 characters",
                        target=url,
                        detail="Keep it under 60 characters, add one specific — a number, "
                        "an audience or an outcome — and move the brand to the end.",
                    ),
                    Step(
                        "Rewrite the meta description to answer the query in sentence one",
                        target=url,
                        detail="Proof in sentence two, call to action third, 155 characters.",
                    ),
                ],
                expected_impact=f"about {int(lost):,} clicks a period",
                verify_metric="ctr_top5_queries",
                verify_after_days=28,
                routed_to=GrowthAction.SERP_CTR.value,
            )
            diagnosis = (
                f"Clicks down {drop_pct:.0f}% on {against} with impressions flat: {url}"
            )
        elif rankings_held:
            prescription = Prescription(
                cause="demand_fell",
                evidence=evidence,
                steps=[
                    Step(
                        "Record the volume trend for this page's terms and leave the page alone",
                        target=url,
                        detail="Rankings held and impressions fell, so fewer people are "
                        "searching. A refresh cannot buy back demand that is not there.",
                        human=True,
                    ),
                ],
                expected_impact="No recovery available — demand, not the page",
                verify_metric="keyword_volume_trend",
                verify_after_days=56,
            )
            diagnosis = (
                f"Search demand for {url} fell {drop_pct:.0f}% on {against} while its "
                f"rankings held"
            )
        else:
            prescription = Prescription(
                cause="true_decay",
                evidence=evidence,
                steps=[
                    Step(
                        "List the subtopics the pages now outranking this one cover and it does not",
                        target=url,
                        detail="Those sections are the refresh brief.",
                        human=True,
                    ),
                    Step(
                        "Update the facts, figures and screenshots, then add the missing sections",
                        target=url,
                        detail="Change the visible date only once the content really changed.",
                    ),
                    Step(
                        "Reclaim the referring domains this page lost",
                        target=url,
                    ),
                ],
                expected_impact=f"about {int(lost):,} clicks a period",
                verify_metric="average_position_lost_queries",
                verify_after_days=56,
            )
            diagnosis = (
                f"Down {drop_pct:.0f}% on {against}: {url} "
                f"({int(prior_clicks):,} clicks to {int(current_clicks):,})"
            )
        cause = prescription.cause

        # Scored in leads: the clicks this page used to bring and no longer
        # does, at the site's lead rate. Medium confidence — the clicks are
        # measured, the lead rate is the site's rather than the page's, and a
        # refresh does not always win all of it back.
        impact, impact_evidence = normalize_business_impact(
            site=site,
            leads_at_risk=downstream_lead_opportunity(lost, site.site_lead_rate_pct),
            recoverable_clicks=lost,
            data_confidence="medium",
        )
        finding = _make_finding(
            # Routed by cause, not by lever of origin: a page losing the
            # click is CTR work wherever it was found.
            lever=(
                GrowthAction.SERP_CTR.value if held else GrowthAction.AI_VISIBILITY.value
            ),
            rule_key=_rule_key("decaying_page", url),
            diagnosis=diagnosis,
            prescription=prescription,
            evidence_json={
                "gate": "decaying_page",
                "prior_clicks": int(prior_clicks),
                "current_clicks": int(current_clicks),
                "prior_impressions": int(prior_impressions),
                "current_impressions": int(current_impressions),
                "drop_pct": round(drop_pct, 1),
                "impressions_change_pct": round(impressions_change, 1),
                "site_drop_pct": round(site_drop_pct, 1),
                "cause": cause,
                "compared_with": [earlier[0].isoformat(), earlier[1].isoformat()],
                "year_over_year": yoy,
                "promotion_class": "actionable",
                **impact_evidence,
            },
            baseline_metrics_json={"clicks": prior_clicks, "impressions": prior_impressions},
            impact=impact,
            page_url=url,
        )
        candidates.append((lost, finding))

    candidates.sort(key=lambda row: -row[0])
    return [finding for _, finding in candidates[:DECAY_MAX_FINDINGS]]


def _blocking_only_findings(
    db: Session,
    client: Client,
    *,
    crawl_by_url: dict[str, FactCrawlPageSnapshot],
    already_seen: set[str],
    period: tuple[date, date] | None,
    page_contexts: dict[str, PageBusinessContext],
    classifications: dict[str, PageClassification],
    site: SiteBusinessContext,
    issues_by_url: dict[str, set[str]] | None,
    thresholds: dict[str, float | int],
) -> list[LeverFinding]:
    """Blocking technical problems on pages the demand gate dropped. B2.

    A page needs thirty impressions to enter the pipeline, which is the right
    bar for "is this worth optimising" and exactly the wrong one for "is this
    broken": a page noindexed last month draws nothing *because* it is broken,
    so the gate hides the page by the same mechanism that damaged it.

    Eligibility is therefore read from the period before, or from the page
    being one the site clearly means to rank — in the sitemap, or a commercial
    or conversion page. Only blocking signals are emitted; upkeep on a page
    with no demand is not worth anyone's attention.
    """
    if period is None:
        return []
    min_prior = float(thresholds.get("technical_blocking_min_prior_impressions", 30))
    prior_totals = _page_totals(db, client.id, previous_period(*period))

    findings: list[LeverFinding] = []
    for url, crawl in crawl_by_url.items():
        if url in already_seen:
            continue
        classification = classifications.get(url)
        intended = classification is not None and classification.page_type in {
            PageType.COMMERCIAL,
            PageType.CONVERSION,
        }
        prior_impressions = prior_totals.get(url, (0.0, 0.0))[1]
        if not (prior_impressions >= min_prior or crawl.in_sitemap or intended):
            continue

        detected = detect_technical_signal(
            url,
            crawl,
            page_issue_codes=(issues_by_url or {}).get(url),
            crawl_by_url=crawl_by_url,
        )
        if detected is None or is_core_work_signal(detected.audit_signal):
            continue

        # Scored on what the page used to earn, since what it earns now is the
        # symptom. Inferred: the loss is real but the recovery is an estimate.
        impact, impact_evidence = normalize_business_impact(
            site=site,
            estimated_incremental_leads=downstream_lead_opportunity(
                prior_totals.get(url, (0.0, 0.0))[0], site.site_lead_rate_pct
            ),
            recoverable_clicks=prior_totals.get(url, (0.0, 0.0))[0],
            data_confidence="medium",
        )
        findings.append(
            _make_finding(
                lever=GrowthAction.TECHNICAL_SEO.value,
                rule_key=_rule_key("technical", url),
                diagnosis=f"{detected.diagnosis} (no current demand — it stopped)",
                action_override=TECHNICAL_ACTIONS.get(detected.audit_signal),
                evidence_json={
                    "audit_signal": detected.audit_signal,
                    "issue_code": detected.issue_code,
                    "eligibility": "prior_period"
                    if prior_impressions >= min_prior
                    else ("sitemap" if crawl.in_sitemap else "intended_page"),
                    "prior_impressions": int(prior_impressions),
                    "in_sitemap": crawl.in_sitemap,
                    "status_code": crawl.status_code,
                    "indexable": crawl.indexable,
                    "promotion_class": "actionable",
                    **impact_evidence,
                },
                baseline_metrics_json={"prior_impressions": prior_impressions},
                impact=impact,
                page_url=url,
            )
        )
    return findings


def _collapse_by_page(findings: list[LeverFinding]) -> list[LeverFinding]:
    """One card per URL, keeping the highest-scoring and noting the rest.

    Several rules can be right about the same page at once. Listing each
    one makes a single page look like a backlog, and whoever opens it has
    to work out that three rows are one job.
    """
    best: dict[str, LeverFinding] = {}
    others: dict[str, list[LeverFinding]] = {}
    out: list[LeverFinding] = []
    for finding in findings:
        url = finding.page_url
        # Suppressed and core-work rows are not competing for attention, so
        # collapsing them would hide them rather than tidy them. Nor is a
        # tracking fault the same kind of thing as a page converting badly:
        # one says the page is weak, the other says the number saying so
        # cannot be trusted, and folding the second into the first loses it.
        gate = str(finding.evidence_json.get("gate") or "")
        if (
            not url
            or finding.core_work
            or finding.suppressed_by
            or gate.startswith("tracking")
        ):
            out.append(finding)
            continue
        current = best.get(url)
        if current is None:
            best[url] = finding
        elif finding.priority_score > current.priority_score:
            best[url] = finding
            others.setdefault(url, []).append(current)
        else:
            others.setdefault(url, []).append(finding)

    for url, finding in best.items():
        hidden = others.get(url) or []
        if hidden:
            finding.evidence_json["also_found_on_this_page"] = [
                {
                    "diagnosis": row.diagnosis,
                    "cause": row.evidence_json.get("cause"),
                    "score": row.priority_score,
                }
                for row in sorted(hidden, key=lambda r: -r.priority_score)
            ]
        out.append(finding)
    return out


def cap_per_url_impact(findings: list[LeverFinding]) -> None:
    """Stop several rules claiming the same upside on one page. B4.

    Internal linking, SERP CTR and a deep refresh on the same URL are three
    descriptions of one page's unrealised traffic, not three separate prizes.
    Summed, they made a single page look like the biggest opportunity on the
    site by counting its upside three times.

    The cap is the largest single finding on that URL — the most any one of
    them claims is the most the page can give — and the capped total is split
    between them in proportion to what each claimed. Raw values are kept for
    display, because the honest answer to "what is this worth" is the
    uncapped figure; the cap is about not adding them up.
    """
    by_url: dict[str, list[LeverFinding]] = {}
    for finding in findings:
        if finding.page_url and finding.impact > 0:
            by_url.setdefault(finding.page_url, []).append(finding)

    for rows in by_url.values():
        if len(rows) < 2:
            continue
        total = sum(row.impact for row in rows)
        cap = max(row.impact for row in rows)
        if total <= cap:
            continue
        scale = cap / total
        for row in rows:
            row.evidence_json = {
                **row.evidence_json,
                "raw_impact": round(row.impact, 1),
                "impact_shared_with": len(rows) - 1,
            }
            row.impact = round(row.impact * scale, 1)
            row.priority_score = score_finding(
                impact=row.impact,
                confidence=row.confidence,
                urgency=row.urgency,
                effort=row.effort,
            )


#: A page that picked up links and did not move is worth looking at; one that
#: picked up a single link is noise.
PR_MIN_NEW_REFDOMAINS = 2
#: How long to give a link to show up in rankings before asking why it has not.
PR_SETTLING_DAYS = 30


def _pr_push_findings(
    db: Session,
    client: Client,
    pages: list[PageDemand],
    *,
    period: tuple[date, date] | None,
    site: SiteBusinessContext,
) -> list[LeverFinding]:
    """Pages that earned links recently and no traffic with them.

    Backlinks as an authority score is a vanity number. Backlinks as events —
    this page picked up three referring domains last month — is a question
    with an answer: did the push work?

    When it did, nothing is reported; the win shows up in the traffic. When it
    did not, that is a page holding fresh authority it is not converting into
    rankings, which is a cheap thing to fix compared with earning the links
    again.
    """
    if period is None:
        return []
    start, end = period
    since = end - timedelta(days=PR_SETTLING_DAYS)

    rows = (
        db.query(FactSerBacklinkPage)
        .filter(
            FactSerBacklinkPage.client_id == client.id,
            FactSerBacklinkPage.first_seen.isnot(None),
            FactSerBacklinkPage.first_seen >= since,
            FactSerBacklinkPage.refdomains >= PR_MIN_NEW_REFDOMAINS,
        )
        .all()
    )
    if not rows:
        return []

    demand = {page.normalized_url: page for page in pages}
    findings: list[LeverFinding] = []
    for row in rows:
        page = demand.get(row.normalized_url)
        position = page.average_position if page else None
        # Already ranking well: the links did their job and there is nothing
        # to report. Saying "this worked" is the report's job, not a finding's.
        if position is not None and position <= 10:
            continue

        clicks = page.clicks if page else 0.0
        impact, impact_evidence = normalize_business_impact(
            site=site,
            recoverable_clicks=max(0.0, (page.impressions if page else 0.0) * 0.05),
            data_confidence="low",
        )
        where = f"ranking {position:.0f}" if position is not None else "drawing no search traffic"
        findings.append(
            _make_finding(
                lever=GrowthAction.AI_VISIBILITY.value,
                rule_key=_rule_key("pr_push_unconverted", row.normalized_url),
                diagnosis=(
                    f"Earned {row.refdomains} referring domains and is still {where}: "
                    f"{row.normalized_url}"
                ),
                action_override=(
                    "This page has fresh authority and is not using it. Check it targets "
                    "a query worth ranking for, that it is internally linked from the "
                    "pages about the same subject, and that nothing technical is holding "
                    "it back — earning the links again is far more expensive than this."
                ),
                evidence_json={
                    "gate": "pr_push_unconverted",
                    "refdomains": row.refdomains,
                    "backlinks": row.backlinks,
                    "first_seen": row.first_seen.isoformat() if row.first_seen else None,
                    "average_position": round(position, 1) if position is not None else None,
                    "clicks": int(clicks),
                    "promotion_class": "actionable",
                    **impact_evidence,
                },
                baseline_metrics_json={"refdomains": row.refdomains},
                impact=impact,
                page_url=row.normalized_url,
            )
        )
    return findings


def _pages_active_before(
    db: Session,
    client_id: UUID,
    *,
    period: tuple[date, date] | None,
) -> set[str]:
    """URLs that drew traffic in the period before this one.

    Used to decide which findings survive Gate 0. A page that was earning
    impressions last period and is now returning 5xx is broken whatever the
    conversion tag is doing — that finding does not depend on lead data being
    trustworthy, so suppressing it would hide the most urgent thing on the site
    behind the second most urgent.
    """
    if period is None:
        return set()
    prior = previous_period(*period)
    active = {
        url
        for url, (clicks, impressions) in _page_totals(db, client_id, prior).items()
        if clicks > 0 or impressions > 0
    }
    sessions_rows = (
        db.query(FactGa4Traffic.normalized_url)
        .filter(
            FactGa4Traffic.client_id == client_id,
            FactGa4Traffic.date >= prior[0],
            FactGa4Traffic.date <= prior[1],
            FactGa4Traffic.sessions > 0,
        )
        .distinct()
        .all()
    )
    active.update(url for (url,) in sessions_rows if url)
    return active


def survives_tracking_gate(finding: LeverFinding, active_before: set[str]) -> bool:
    """Whether a finding stays promotable while Gate 0 is failing. B1."""
    if finding.lever != GrowthAction.TECHNICAL_SEO.value:
        return False
    if finding.core_work:
        # Upkeep is never promoted anyway; letting it through here would only
        # make the exception look broader than it is.
        return False
    return bool(finding.page_url) and finding.page_url in active_before


def _sessions_between(db: Session, client_id: UUID, start: date, end: date) -> float:
    return float(
        db.query(func.coalesce(func.sum(FactGa4Traffic.sessions), 0))
        .filter(
            FactGa4Traffic.client_id == client_id,
            FactGa4Traffic.date >= start,
            FactGa4Traffic.date <= end,
        )
        .scalar()
        or 0
    )


def _search_clicks_between(db: Session, client_id: UUID, start: date, end: date) -> float:
    """Search clicks, as the witness that does not depend on our own tag."""
    return float(
        db.query(func.coalesce(func.sum(FactGscPage.clicks), 0))
        .filter(
            FactGscPage.client_id == client_id,
            FactGscPage.date >= start,
            FactGscPage.date <= end,
        )
        .scalar()
        or 0
    )


def _tracking_failure_finding(
    db: Session,
    client: Client,
    *,
    period: tuple[date, date] | None,
    site: SiteBusinessContext,
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

    # Every lead the fortnight should have produced is unaccounted for, so
    # that is the impact — in leads, like everything else.
    impact, impact_evidence = normalize_business_impact(
        site=site,
        leads_at_risk=expected if expected > 0 else None,
        data_confidence="high",
    )

    # Which part of tracking broke. Four faults wear this one label and they
    # have four different fixes, so the finding has to say which. Playbook 1.
    prior_window_start = window_start - timedelta(days=TRACKING_SILENCE_DAYS)
    prescription = classify_tracking_break(
        TrackingSignals(
            sessions_now=sessions,
            sessions_before=_sessions_between(
                db, client.id, prior_window_start, window_start - timedelta(days=1)
            ),
            search_clicks_now=_search_clicks_between(db, client.id, window_start, end),
            search_clicks_before=_search_clicks_between(
                db, client.id, prior_window_start, window_start - timedelta(days=1)
            ),
            leads_now=leads,
            # No CRM is wired, so the form and the event cannot be told apart
            # from data. The prescription says so and asks for one test that
            # separates them, rather than guessing at one of the two.
            crm_leads_now=None,
        )
    )
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
            **impact_evidence,
        },
        baseline_metrics_json={},
        # Before suppression existed this was pinned at 100 to force it to the
        # top of the list. It no longer has to win on score: when it fires,
        # nothing else can be promoted at all.
        impact=impact,
        severity=100.0,
        urgency_override=100.0,
        prescription=prescription,
    )


def _ai_sov_falling_finding(
    db: Session,
    client: Client,
    *,
    period: tuple[date, date] | None,
    site: SiteBusinessContext,
    thresholds: dict[str, Any],
) -> LeverFinding | None:
    """Share of the tracked prompt set that mentions the brand, falling. N1.

    The per-prompt rule says a prompt never cites you, which is a fact about
    one prompt and stays true for months. This asks whether the set as a whole
    is moving, which is the question someone running the account actually has.

    `ai_sov` on the prompt fact is never populated by the ingest, so this uses
    the tracker's own presence percentage — the share of checked prompts that
    mentioned the brand, which is what share of voice means here.
    """
    if period is None or not thresholds.get("rule_ai_sov_falling_enabled"):
        return None

    _, end = period
    window = int(thresholds.get("ai_sov_window_days", 30))
    start = end - timedelta(days=window)

    rows = (
        db.query(FactSerAiTrackerStats)
        .filter(
            FactSerAiTrackerStats.client_id == client.id,
            FactSerAiTrackerStats.metric_date >= start,
            FactSerAiTrackerStats.metric_date <= end,
        )
        .order_by(FactSerAiTrackerStats.metric_date)
        .all()
    )
    points = [
        (row.metric_date, float(row.mention_presence_pct))
        for row in rows
        if row.mention_presence_pct is not None
    ]
    if len(points) < 2:
        return None

    (_, first), (_, last) = points[0], points[-1]
    floor = float(thresholds.get("ai_sov_min_presence_pct", 5.0))
    if first < floor:
        # A 20% relative fall from 2% is half a percentage point, which is one
        # prompt changing its mind. Relative moves need a base to be relative to.
        return None

    drop_pct = ((first - last) / first) * 100.0
    if drop_pct < float(thresholds.get("ai_sov_drop_pct", 20.0)):
        return None

    volume = max(float(len(rows)), 50.0)
    impact, impact_evidence = score_ai_visibility_impact(
        signal="ai_sov_falling",
        volume=volume,
        site=site,
    )
    return _make_finding(
        lever=GrowthAction.AI_VISIBILITY.value,
        rule_key=_rule_key("ai_sov_falling", str(client.id)),
        diagnosis=(
            f"AI share of voice fell from {first:.1f}% to {last:.1f}% of tracked "
            f"prompts over {window} days"
        ),
        evidence_json={
            "audit_signal": "ai_sov_falling",
            "promotion_class": "actionable",
            "window_days": window,
            "presence_start_pct": round(first, 2),
            "presence_end_pct": round(last, 2),
            "relative_drop_pct": round(drop_pct, 1),
            "checks_in_window": len(rows),
            **impact_evidence,
        },
        baseline_metrics_json={"presence_start_pct": round(first, 2)},
        impact=impact,
        action_override=(
            "Find which prompts stopped mentioning the brand and what is being "
            "cited instead. A falling share is usually a competitor publishing "
            "the answer you used to own, not a ranking change."
        ),
    )


#: A 3xx landing here is a redirect to nowhere in particular — the link
#: equity arrives and the visitor has to start again.
_GENERIC_REDIRECT_PATHS = frozenset({"", "/", "/home", "/index", "/index.html"})


def _link_reclamation_findings(
    db: Session,
    client: Client,
    *,
    crawl_by_url: dict[str, FactCrawlPageSnapshot],
    site: SiteBusinessContext,
    thresholds: dict[str, Any],
) -> list[LeverFinding]:
    """Broken URLs that other sites still link to. N2.

    A 404 on a page nobody links to is housekeeping. A 404 on a page with
    referring domains is somebody else's link pointing at nothing, and the
    authority it carries stops at the error. The same is true of a redirect
    that dumps every inbound link on the homepage: the link survives, the
    relevance does not.
    """
    if not thresholds.get("rule_link_reclamation_enabled"):
        return []

    min_domains = float(thresholds.get("reclaim_min_refdomains", 1))
    linked = {
        row.normalized_url: row
        for row in db.query(FactSerBacklinkPage)
        .filter(
            FactSerBacklinkPage.client_id == client.id,
            FactSerBacklinkPage.refdomains >= min_domains,
        )
        .all()
    }
    if not linked:
        return []

    findings: list[LeverFinding] = []
    for url, backlinks in linked.items():
        crawl = crawl_by_url.get(url)
        if crawl is None or crawl.status_code is None:
            continue
        status = crawl.status_code
        broken = status >= 400
        dumped = False
        if 300 <= status < 400 and crawl.redirect_url:
            target_path = urlsplit(crawl.redirect_url).path.rstrip("/").lower()
            dumped = target_path in _GENERIC_REDIRECT_PATHS
        if not broken and not dumped:
            continue

        impact, impact_evidence = normalize_business_impact(
            site=site,
            recoverable_clicks=float(backlinks.refdomains),
            strategic_priority=4,
            data_confidence="medium",
        )
        findings.append(
            _make_finding(
                lever=GrowthAction.TECHNICAL_SEO.value,
                rule_key=_rule_key("link_reclaim", url),
                diagnosis=(
                    f"HTTP {status} on a URL {backlinks.refdomains} domains still "
                    f"link to: {url}"
                    if broken
                    else (
                        f"{backlinks.refdomains} linking domains land on the homepage "
                        f"via this redirect: {url}"
                    )
                ),
                evidence_json={
                    "audit_signal": "link_reclamation",
                    "promotion_class": "actionable",
                    "status_code": status,
                    "redirect_url": crawl.redirect_url,
                    "refdomains": backlinks.refdomains,
                    "backlinks": backlinks.backlinks,
                    **impact_evidence,
                },
                baseline_metrics_json={"refdomains": backlinks.refdomains},
                impact=impact,
                page_url=url,
                action_override=(
                    "Restore the page, or 301 it to the closest page on the same "
                    "subject. Pointing it at the homepage keeps the link and throws "
                    "away what it was about."
                ),
            )
        )
    return findings


def _ai_referral_segment(
    db: Session,
    client_id: UUID,
    *,
    period: tuple[date, date] | None,
    lead_events: list[str],
) -> dict[str, dict[str, float]]:
    """Sessions and leads arriving from AI assistants, per page. N4.

    Reported as its own segment because it answers a question the organic
    numbers cannot: whether the work is earning anything from the surfaces
    that do not report impressions.
    """
    if period is None:
        return {}
    start, end = period
    out: dict[str, dict[str, float]] = {}
    sessions = (
        db.query(
            FactGa4Traffic.normalized_url,
            func.coalesce(func.sum(FactGa4Traffic.sessions), 0),
        )
        .filter(
            FactGa4Traffic.client_id == client_id,
            FactGa4Traffic.date >= start,
            FactGa4Traffic.date <= end,
            FactGa4Traffic.channel == OrganicChannel.AI_REFERRAL,
        )
        .group_by(FactGa4Traffic.normalized_url)
        .all()
    )
    for url, total in sessions:
        if url and float(total) > 0:
            out.setdefault(url, {"sessions": 0.0, "leads": 0.0})["sessions"] = float(total)

    if lead_events:
        leads = (
            db.query(
                FactGa4Event.normalized_url,
                func.coalesce(func.sum(FactGa4Event.event_count), 0),
            )
            .filter(
                FactGa4Event.client_id == client_id,
                FactGa4Event.date >= start,
                FactGa4Event.date <= end,
                FactGa4Event.channel == OrganicChannel.AI_REFERRAL,
                FactGa4Event.event_name.in_(lead_events),
            )
            .group_by(FactGa4Event.normalized_url)
            .all()
        )
        for url, total in leads:
            if url and float(total) > 0:
                out.setdefault(url, {"sessions": 0.0, "leads": 0.0})["leads"] = float(total)
    return out


def _tracking_anomaly_findings(
    db: Session,
    client: Client,
    *,
    period: tuple[date, date] | None,
    site: SiteBusinessContext,
    thresholds: dict[str, Any],
) -> list[LeverFinding]:
    """Gate 0, the two failures that are not total silence. Phase 3.

    The silence check asks whether the site records any conversions at all,
    which misses the two ways tracking goes wrong on a site that still
    converts: one form stops and the total hides it, or one event starts
    firing twice and the total flatters it.

    Neither suppresses anything. Silence makes every score below it a
    fiction, which is what earns that gate its veto; these two make *some*
    scores wrong, and the honest response is to say which.
    """
    if period is None:
        return []
    lead_events = _lead_event_names(db, client.id)
    if not lead_events:
        return []

    _, end = period
    days = int(thresholds.get("partial_break_days", 14))
    window_start = end - timedelta(days=days - 1)
    findings: list[LeverFinding] = []

    current = _leads_by_page(db, client.id, lead_events, window_start, end)
    site_leads_now = sum(current.values())
    if site_leads_now <= 0:
        # Nothing recorded anywhere is the silence gate's business, not this
        # one, and reporting both would say the same thing twice.
        return []

    # ── Partial break ──
    # What the page should have produced is its own prior rate applied to the
    # traffic it is *still getting*. Reading it from history alone said a
    # deleted page had stopped converting: smamarketing.com/geo-grader is a
    # 404, so of course no one filled in its form, and the engine called that
    # a broken tag. A page with no visitors produces no leads by arithmetic,
    # which is not a finding — if the page is gone, the status-error and
    # link-reclamation rules are the ones with something to say.
    before = window_start - timedelta(days=1)
    prior = _leads_by_page(db, client.id, lead_events, None, before)
    prior_sessions = _sessions_by_page(db, client.id, None, before)
    now_sessions = _sessions_by_page(db, client.id, window_start, end)
    min_expected = float(thresholds.get("partial_break_min_expected_leads", 3))
    if prior:
        for url, prior_leads in sorted(prior.items(), key=lambda row: -row[1]):
            if current.get(url, 0.0) > 0:
                continue
            sessions_now = now_sessions.get(url, 0.0)
            sessions_before = prior_sessions.get(url, 0.0)
            if sessions_now <= 0 or sessions_before <= 0:
                continue
            expected = sessions_now * (prior_leads / sessions_before)
            if expected < min_expected:
                continue
            impact, impact_evidence = normalize_business_impact(
                site=site,
                leads_at_risk=expected,
                data_confidence="high",
            )
            findings.append(
                _make_finding(
                    lever=GrowthAction.CONVERSION_PATH.value,
                    rule_key=_rule_key("tracking_partial", url),
                    diagnosis=(
                        f"No conversions from this page in {days} days while the rest "
                        f"of the site still converts: {url}"
                    ),
                    evidence_json={
                        "gate": "tracking_partial",
                        "audit_signal": "tracking_partial",
                        "promotion_class": "actionable",
                        "window_days": days,
                        "window_start": window_start.isoformat(),
                        "window_end": end.isoformat(),
                        "expected_leads": round(expected, 1),
                        "site_leads_in_window": round(site_leads_now, 1),
                        "lead_events": lead_events,
                        **impact_evidence,
                    },
                    baseline_metrics_json={"prior_leads": round(prior_leads, 1)},
                    impact=impact,
                    page_url=url,
                    action_override=(
                        "Submit this page's form yourself and confirm the event fires. "
                        "The rest of the site is still recording conversions, so this "
                        "is one form or one template, not the tag."
                    ),
                )
            )
            break  # One is a finding; a list of them is the silence gate.

    # ── Spike ──
    multiple = float(thresholds.get("lead_spike_multiple", 3.0))
    floor = float(thresholds.get("lead_spike_min_leads", 10))
    sessions_now_total = sum(now_sessions.values())
    sessions_before_total = sum(prior_sessions.values())
    if sessions_before_total > 0 and sessions_now_total > 0 and site_leads_now >= floor:
        # Against the rate, not the raw count: a fortnight with twice the
        # traffic should have twice the leads, and calling that a spike would
        # flag every good month.
        expected_site = sessions_now_total * (sum(prior.values()) / sessions_before_total)
        if expected_site > 0 and site_leads_now >= expected_site * multiple:
            # The excess over the usual rate is the number of recorded leads
            # that may not exist. That is a real quantity in the same currency
            # as everything else — and it is exactly what is wrong with the
            # period if the event is firing twice.
            suspect = site_leads_now - expected_site
            impact, impact_evidence = normalize_business_impact(
                site=site,
                leads_at_risk=suspect,
                data_confidence="high",
            )
            findings.append(
                _make_finding(
                    lever=GrowthAction.CONVERSION_PATH.value,
                    rule_key=_rule_key("tracking_spike", str(client.id)),
                    diagnosis=(
                        f"{int(site_leads_now):,} conversions in {days} days against "
                        f"{expected_site:.0f} expected — more than {multiple:g}x the "
                        f"usual rate"
                    ),
                    evidence_json={
                        "gate": "tracking_spike",
                        "audit_signal": "tracking_spike",
                        "promotion_class": "actionable",
                        "window_days": days,
                        "leads": round(site_leads_now, 1),
                        "expected_leads": round(expected_site, 1),
                        "multiple": round(site_leads_now / expected_site, 1),
                        "suspect_leads": round(suspect, 1),
                        "lead_events": lead_events,
                        **impact_evidence,
                    },
                    baseline_metrics_json={"expected_leads": round(expected_site, 1)},
                    impact=impact,
                    severity=60.0,
                    action_override=(
                        "Check the event for double firing or form spam before trusting "
                        "this period's numbers. Every impact score here is computed from "
                        "leads, so an inflated count inflates the queue."
                    ),
                )
            )

    return findings


def _sessions_by_page(
    db: Session, client_id: UUID, start: date | None, end: date
) -> dict[str, float]:
    query = db.query(
        FactGa4Traffic.normalized_url,
        func.coalesce(func.sum(FactGa4Traffic.sessions), 0),
    ).filter(FactGa4Traffic.client_id == client_id, FactGa4Traffic.date <= end)
    if start is not None:
        query = query.filter(FactGa4Traffic.date >= start)
    return {
        url: float(total)
        for url, total in query.group_by(FactGa4Traffic.normalized_url).all()
        if url and float(total) > 0
    }


def _leads_by_page(
    db: Session,
    client_id: UUID,
    lead_events: list[str],
    start: date | None,
    end: date,
) -> dict[str, float]:
    query = db.query(
        FactGa4Event.normalized_url,
        func.coalesce(func.sum(FactGa4Event.event_count), 0),
    ).filter(
        FactGa4Event.client_id == client_id,
        FactGa4Event.date <= end,
        FactGa4Event.event_name.in_(lead_events),
    )
    if start is not None:
        query = query.filter(FactGa4Event.date >= start)
    return {
        url: float(total)
        for url, total in query.group_by(FactGa4Event.normalized_url).all()
        if url and float(total) > 0
    }


def _recorded_day_span(db: Session, client_id: UUID, *, before: date) -> int:
    """Days of history behind the window, so a rate can be a rate.

    Measured from the first recorded day rather than assumed, because a client
    onboarded three weeks ago has three weeks of history and dividing by a
    year would make every page look broken.
    """
    first = (
        db.query(func.min(FactGa4Event.date))
        .filter(FactGa4Event.client_id == client_id, FactGa4Event.date < before)
        .scalar()
    )
    if first is None:
        return 0
    return max(0, (before - first).days)


#: Behind the plan by less than this is a normal month, not a finding.
CONVERSION_PLAN_SHORTFALL_RATIO = 0.8
#: Below where the client started by more than this is going backwards.
CONVERSION_BASELINE_RATIO = 0.9


#: A page needs this much traffic before its rate is worth naming as the
#: place to start.
SITE_CONVERSION_MIN_PAGE_SESSIONS = 50.0


def _site_conversion_signals(
    db: Session,
    client: Client,
    *,
    from_date: date,
    to_date: date,
    site_goal: float | None = None,
) -> SiteConversionSignals:
    """Where the lost leads sit, by page and by channel.

    Device and new-versus-returning are in the playbook and not in our GA4
    query, so the prescription asks for them by hand rather than pretending
    the segments were checked.
    """
    lead_events = _lead_event_names(db, client.id)
    span = (to_date - from_date).days + 1
    prev_end = from_date - timedelta(days=1)
    prev_start = prev_end - timedelta(days=span - 1)

    now = _leads_by_page(db, client.id, lead_events, from_date, to_date)
    before = _leads_by_page(db, client.id, lead_events, prev_start, prev_end)
    loss_by_group = sorted(
        (
            (url, before.get(url, 0.0) - now.get(url, 0.0))
            for url in set(before) | set(now)
        ),
        key=lambda row: -row[1],
    )

    def _by_channel(start: date, end: date) -> dict[str, float]:
        if not lead_events:
            return {}
        rows = (
            db.query(
                FactGa4Event.channel,
                func.coalesce(func.sum(FactGa4Event.event_count), 0),
            )
            .filter(
                FactGa4Event.client_id == client.id,
                FactGa4Event.date >= start,
                FactGa4Event.date <= end,
                FactGa4Event.event_name.in_(lead_events),
            )
            .group_by(FactGa4Event.channel)
            .all()
        )
        return {
            (channel.value if hasattr(channel, "value") else str(channel)): float(total)
            for channel, total in rows
        }

    channel_now, channel_before = (
        _by_channel(from_date, to_date),
        _by_channel(prev_start, prev_end),
    )
    loss_by_channel = sorted(
        (
            (name, channel_before.get(name, 0.0) - channel_now.get(name, 0.0))
            for name in set(channel_before) | set(channel_now)
        ),
        key=lambda row: -row[1],
    )

    def _total(start: date, end: date) -> float | None:
        if not lead_events:
            return None
        value = (
            db.query(func.coalesce(func.sum(FactGa4Event.event_count), 0))
            .filter(
                FactGa4Event.client_id == client.id,
                FactGa4Event.date >= start,
                FactGa4Event.date <= end,
                FactGa4Event.event_name.in_(lead_events),
            )
            .scalar()
        )
        return float(value or 0)

    year = timedelta(days=365)
    earliest = (
        db.query(func.min(FactGa4Event.date))
        .filter(FactGa4Event.client_id == client.id)
        .scalar()
    )
    has_two_years = earliest is not None and earliest <= from_date - year - timedelta(days=span)

    # Where a site short of plan buys the gap back cheapest: the pages with
    # the traffic and the worst rate.
    sessions_now = _sessions_by_page(db, client.id, from_date, to_date)
    weakest = sorted(
        (
            (url, sessions, (now.get(url, 0.0) / sessions * 100.0))
            for url, sessions in sessions_now.items()
            if sessions >= SITE_CONVERSION_MIN_PAGE_SESSIONS
        ),
        key=lambda row: (row[2], -row[1]),
    )

    return SiteConversionSignals(
        weakest_pages=weakest[:5],
        period_goal=float(site_goal) if site_goal else None,
        leads_now=sum(now.values()),
        leads_before=sum(before.values()),
        loss_by_group=[row for row in loss_by_group if row[1] > 0],
        loss_by_channel=[row for row in loss_by_channel if row[1] > 0],
        leads_year_ago=_total(from_date - year, to_date - year) if has_two_years else None,
        leads_year_before_that=(
            _total(prev_start - year, prev_end - year) if has_two_years else None
        ),
    )


def _conversion_portfolio(
    db: Session,
    client: Client,
    *,
    from_date: date,
    to_date: date,
    dashboard: dict[str, Any],
    site: SiteBusinessContext,
    thresholds: dict[str, float | int] | None = None,
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
    thresholds = thresholds or {}
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

    # How many leads the window should have produced at the previous rate.
    # A rate that halved on four expected leads halved on noise, and saying so
    # out loud to a client costs more credibility than staying quiet. T1.
    # Each trigger expects against the rate it is comparing to. Using the
    # previous rate for both would silence "below baseline" on exactly the
    # client it is for: a site that has always converted badly has a low
    # previous rate, so it would never expect enough leads to qualify.
    managed_sessions = _managed_sessions(db, client.id, current_period)
    min_expected = float(thresholds.get("gate1_min_expected_leads", 10))
    expected_leads = managed_sessions * (previous_rate / 100.0)
    enough_sample = expected_leads >= min_expected

    # ── Trigger 1: something broke recently ──
    # Traffic has to be holding, or this is a traffic problem wearing a
    # conversion problem's clothes.
    falling = enough_sample and sessions_change_pct >= -5 and lead_rate_change_pct <= -10

    # ── Trigger 2: we have gone backwards from where we started ──
    expected_at_baseline = (
        managed_sessions * (float(baseline_rate) / 100.0) if baseline_rate else 0.0
    )
    below_baseline = (
        expected_at_baseline >= min_expected
        and baseline_rate is not None
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
        prescription=classify_site_conversion(
            _site_conversion_signals(
                db,
                client,
                from_date=from_date,
                to_date=to_date,
                site_goal=site.period_lead_goal,
            )
        ),
        evidence_json={
            "gate": "site_conversion",
            "lead_rate_change_pct": round(lead_rate_change_pct, 1),
            "sessions_change_pct": round(sessions_change_pct, 1),
            "tracking_validated": True,
            # Every trigger is recorded, not just the one that led, so the
            # reader can see whether this is one problem or three.
            # Raw lead events: no qualified-lead field exists on this client,
            # so an MQL and a newsletter signup weigh the same. T1.
            "lead_source": "raw",
            "expected_leads": round(expected_leads, 1),
            "expected_leads_at_baseline": round(expected_at_baseline, 1),
            "managed_sessions": int(managed_sessions),
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
    issue_raw_by_code = _site_issue_payloads(db, client.id)
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
    # Set for the whole run so every finding is scored on this client's
    # weights, including the ones built deep inside the per-page cascade.
    _SCORE_WEIGHTS.set(thresholds)
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
        < _link_floor(crawl.word_count, classifications.get(page.normalized_url), thresholds)
    }
    link_gaps = _link_gaps(
        db,
        client.id,
        period=gsc_period,
        targets=under_linked,
        max_donors=int(thresholds.get("link_max_donors", 3)),
    )

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
            thresholds=thresholds,
            page_ctr_curve=build_client_ctr_curve(db, client.id, gsc_period)[0],
            branded_shares=_branded_impression_share(db, client, period=gsc_period),
            top_queries=_top_query_per_page(db, client.id, period=gsc_period),
            ai_overview_queries=_ai_overview_queries(db, client.id),
            client_brand=client.client_name,
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
        crawl_by_url=crawl_by_url,
        blocked_crawlers=_blocked_ai_crawlers(site_issue_codes, issue_raw_by_code),
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
        thresholds=thresholds,
    )
    if conversion is not None:
        _enrich_finding(conversion, classification=None, page_ctx=None)
        findings.append(conversion)

    # ── Pages that were converting and stopped ──
    dropped = _converting_page_dropped_findings(
        db,
        client,
        period=ga4_period,
        site=site,
        crawl_by_url=crawl_by_url,
        thresholds=thresholds,
    )
    for finding in dropped:
        _enrich_finding(
            finding,
            classification=classifications.get(finding.page_url or ""),
            page_ctx=page_contexts.get(finding.page_url or ""),
        )
    findings.extend(dropped)

    # ── Blocking problems the demand gate would otherwise hide ──
    findings.extend(
        _blocking_only_findings(
            db,
            client,
            crawl_by_url=crawl_by_url,
            already_seen={page.normalized_url for page in pages},
            period=gsc_period,
            page_contexts=page_contexts,
            classifications=classifications,
            site=site,
            issues_by_url=issues_by_url,
            thresholds=thresholds,
        )
        if crawl_ready
        else []
    )
    for finding in findings:
        if finding.evidence_json.get("eligibility"):
            _enrich_finding(
                finding,
                classification=classifications.get(finding.page_url or ""),
                page_ctx=page_contexts.get(finding.page_url or ""),
            )

    # ── Pages that used to perform ──
    findings.extend(
        _decaying_page_findings(
            db, client, period=gsc_period, fact_min=fact_min, site=site,
            thresholds=thresholds,
        )
    )
    for finding in findings:
        if finding.evidence_json.get("gate") == "decaying_page":
            _enrich_finding(
                finding,
                classification=classifications.get(finding.page_url or ""),
                page_ctx=page_contexts.get(finding.page_url or ""),
            )

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
            page_type_rates=page_type_rates,
            page_type_support=page_type_rate_support(page_contexts, classifications),
            thresholds=thresholds,
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
    overridden = _overridden_rule_families(
        db, client.id, reset_days=int(thresholds.get("contested_reset_days", 90))
    )
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
    # ── Phase 4 ──
    # Each behind a flag that defaults on, so a client who disagrees with a
    # new rule can switch it off without waiting for a deploy.
    reclaimed = _link_reclamation_findings(
        db, client, crawl_by_url=crawl_by_url, site=site, thresholds=thresholds
    )
    for finding in reclaimed:
        _enrich_finding(
            finding,
            classification=classifications.get(finding.page_url or ""),
            page_ctx=page_contexts.get(finding.page_url or ""),
        )
    findings.extend(reclaimed)

    # N4: AI assistants do not report impressions, so the organic numbers on a
    # page finding cannot say whether that surface is earning anything. This
    # rides along on every page finding as its own segment.
    ai_segment = _ai_referral_segment(
        db,
        client.id,
        period=ga4_period,
        lead_events=_lead_event_names(db, client.id),
    )
    if ai_segment:
        for finding in findings:
            segment = ai_segment.get(finding.page_url or "")
            if segment:
                finding.evidence_json["ai_referral_sessions"] = round(
                    segment["sessions"], 1
                )
                finding.evidence_json["ai_referral_leads"] = round(segment["leads"], 1)

    # The two Gate 0 anomalies that are not total silence. They compete on
    # impact like anything else — only silence has a veto. Phase 3.
    findings.extend(
        _tracking_anomaly_findings(
            db, client, period=ga4_period, site=site, thresholds=thresholds
        )
    )

    tracking = _tracking_failure_finding(db, client, period=ga4_period, site=site)
    if tracking is not None:
        _enrich_finding(tracking, classification=None, page_ctx=None)
        # Computed only when the gate actually fires, which is rare.
        active_before = _pages_active_before(db, client.id, period=gsc_period)
        for finding in findings:
            if not survives_tracking_gate(finding, active_before):
                finding.suppressed_by = tracking.rule_key
        findings.append(tracking)

    # ── C1 ──
    # Confidence read from the evidence instead of from the lever. It is
    # recorded on every finding and applied only when the client opts in: the
    # 60 gate has never rejected anything, so switching this on without
    # looking first would silently stop promoting work for reasons nobody has
    # seen. `scripts/confidence_distribution.py` reads the recorded scores.
    gsc_age_days = (date.today() - gsc_period[1]).days if gsc_period else None
    apply_scores = bool(thresholds.get("data_driven_confidence_enabled"))
    for finding in findings:
        lever_ceiling = (
            LEVER_INPUTS[finding.lever].confidence
            if finding.lever in LEVER_INPUTS
            else finding.confidence
        )
        scored = data_confidence(
            lever_ceiling,
            finding.evidence_json,
            thresholds,
            data_age_days=gsc_age_days,
        )
        finding.evidence_json["data_driven_confidence"] = scored
        finding.evidence_json["lever_confidence"] = lever_ceiling
        if apply_scores and scored != finding.confidence:
            finding.confidence = scored
            finding.priority_score = score_finding(
                impact=finding.impact,
                confidence=finding.confidence,
                urgency=finding.urgency,
                effort=finding.effort,
            )

    # Before sorting, or a page counted three times outranks pages counted once.
    cap_per_url_impact(findings)

    # And one card per page. Aquaman's /pool-leak-emergency appeared three
    # times — as a page that stopped converting, as the page a site-wide
    # drop was concentrated on, and again below the threshold — which reads
    # as three problems and is one. The highest-scoring card wins and the
    # rest ride along in its evidence, so nothing is lost.
    findings = _collapse_by_page(findings)

    findings.sort(key=lambda row: row.priority_score, reverse=True)

    # ── S1 ──
    # Size every finding and re-order the top of the queue by what it costs.
    # Only the order moves: promotion still turns on impact and confidence, so
    # nothing is promoted or blocked for being cheap or expensive. Confined to
    # the top N because the tail is not work anyone is choosing between.
    top_n = int(thresholds.get("effort_reorder_top_n", 25))
    for finding in findings:
        size = effort_class(finding.lever, finding.evidence_json)
        finding.evidence_json["effort_class"] = size
        finding.evidence_json["ranking_score"] = ranking_score(
            impact=finding.impact,
            confidence=finding.confidence,
            effort=size,
            thresholds=thresholds,
        )
    head = findings[:top_n]
    head.sort(key=lambda row: row.evidence_json["ranking_score"], reverse=True)
    findings[:top_n] = head

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
