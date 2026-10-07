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
    DismissalReason,
    GrowthAction,
)
from app.services.decision_types import DiagnoseResult, LeverFinding
from app.services.lever_engine import diagnose


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
            readiness={
                "search_console": False,
                "analytics": False,
                "crawl_audit": False,
                "ai_visibility": False,
            },
            formula="",
            requested_from=from_date,
            requested_to=to_date,
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


def _priority_band(score: float, thresholds: dict[str, float | int] | None = None) -> DecisionPriority:
    high = float((thresholds or {}).get("high_priority_threshold", 70))
    medium = float((thresholds or {}).get("medium_priority_threshold", 50))
    if score >= high:
        return DecisionPriority.HIGH
    if score >= medium:
        return DecisionPriority.MEDIUM
    return DecisionPriority.LOW


def _decision_type_for_lever(lever: str) -> DecisionType:
    if lever == GrowthAction.CONVERSION_PATH.value:
        return DecisionType.BOTTLENECK
    if lever in {GrowthAction.TECHNICAL_SEO.value, GrowthAction.SERP_CTR.value}:
        return DecisionType.BOTTLENECK if lever == GrowthAction.TECHNICAL_SEO.value else DecisionType.OPPORTUNITY
    return DecisionType.OPPORTUNITY


def _growth_action_for_lever(lever: str) -> GrowthAction | None:
    if lever == "search_opportunity":
        return None
    return GrowthAction(lever)


def _priority_from_finding(
    finding: LeverFinding,
    thresholds: dict[str, float | int] | None = None,
) -> DecisionPriority:
    band = finding.priority_band
    if band == "high":
        return DecisionPriority.HIGH
    if band == "medium":
        return DecisionPriority.MEDIUM
    if band == "low":
        return DecisionPriority.LOW
    return _priority_band(finding.priority_score, thresholds)


def _finding_to_model(
    client_id: UUID,
    finding: LeverFinding,
    from_date: date,
    to_date: date,
    thresholds: dict[str, float | int],
) -> Decision:
    growth_action = _growth_action_for_lever(finding.lever)
    return Decision(
        client_id=client_id,
        rule_key=finding.rule_key,
        decision_type=_decision_type_for_lever(finding.lever),
        growth_action=growth_action,
        diagnostic_layer=finding.stage,
        priority=_priority_from_finding(finding, thresholds),
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

    thresholds = get_thresholds(db, client.id)
    created: list[Decision] = []
    skipped = 0
    # Which rules already have a decision for this window, in one query.
    # Asking per finding meant one round trip each: twenty-six of them on
    # SMA, every time someone pressed Run.
    already = {
        row[0]
        for row in db.query(Decision.rule_key).filter(
            Decision.client_id == client.id,
            Decision.date_range_start == from_date,
            Decision.date_range_end == to_date,
            Decision.rule_key.in_([f.rule_key for f in result.recommended_actions]),
        )
    }
    for finding in result.recommended_actions:
        if finding.rule_key in already:
            skipped += 1
            continue
        decision = _finding_to_model(client.id, finding, from_date, to_date, thresholds)
        db.add(decision)
        created.append(decision)

    db.commit()
    for decision in created:
        db.refresh(decision)
    return created, skipped, result


def ensure_decision_for_rule(
    db: Session,
    client: Client,
    *,
    from_date: date,
    to_date: date,
    rule_key: str,
) -> Decision | None:
    """Upsert a Decision for any diagnose finding (recommended or additional)."""
    existing = (
        db.query(Decision)
        .filter(
            Decision.client_id == client.id,
            Decision.rule_key == rule_key,
            Decision.date_range_start == from_date,
            Decision.date_range_end == to_date,
        )
        .one_or_none()
    )
    if existing is not None:
        return existing

    result = run_diagnose(db, client, from_date=from_date, to_date=to_date)
    if not result.ready:
        return None

    finding = next((row for row in result.findings if row.rule_key == rule_key), None)
    if finding is None:
        finding = next(
            (row for row in result.recommended_actions if row.rule_key == rule_key),
            None,
        )
    if finding is None:
        return None

    thresholds = get_thresholds(db, client.id)
    decision = _finding_to_model(client.id, finding, from_date, to_date, thresholds)
    db.add(decision)
    db.commit()
    db.refresh(decision)
    return decision


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
        # A reason is required, and has to be one of the five. Free text meant
        # the override rule counted "wrong data" — a bug report — as evidence
        # the rule is a bad fit. T8.
        try:
            reason = DismissalReason(str(dismissal_reason or "").strip())
        except ValueError as exc:
            raise ValueError(
                "dismissal_reason must be one of: "
                + ", ".join(item.value for item in DismissalReason)
            ) from exc
        decision.dismissal_reason = reason.value
    else:
        decision.dismissal_reason = None
    db.commit()
    db.refresh(decision)
    return decision


def default_threshold_catalog() -> dict[str, float | int]:
    return dict(DEFAULT_DECISION_THRESHOLDS)


def upsert_keyword_page_map(db, client_id, entries):
    """Record or update which page owns each term.

    Keywords are stored lowercase: a watchlist entry and a Search Console
    query differ in case far more often than in substance, and the engine
    looks the mapping up by the lowercased term.
    """
    from app.models.decision import KeywordPageMap

    wanted = [k for k in ((e.keyword or "").strip().lower() for e in entries) if k]
    # Every row this save might touch, in one query rather than one per
    # entry — a bulk save of a hundred keywords was a hundred round trips.
    existing = {
        row.keyword: row
        for row in db.query(KeywordPageMap).filter(
            KeywordPageMap.client_id == client_id,
            KeywordPageMap.keyword.in_(wanted),
        )
    }
    for entry in entries:
        keyword = entry.keyword.strip().lower()
        if not keyword:
            continue
        row = existing.get(keyword)
        if row is None:
            row = KeywordPageMap(client_id=client_id, keyword=keyword)
            db.add(row)
            # The batched lookup only saw what was in the table when it ran,
            # so a keyword repeated inside one payload has to be matched
            # against what this call has already added.
            existing[keyword] = row
        row.page_url = (entry.page_url or "").strip() or None
        row.note = (entry.note or "").strip() or None
    db.commit()
    return (
        db.query(KeywordPageMap)
        .filter(KeywordPageMap.client_id == client_id)
        .order_by(KeywordPageMap.keyword)
        .all()
    )


def keyword_page_map_view(db, client_id, *, period=None):
    """Every tracked keyword with its mapping and the best guesses at one.

    The map is only useful if it is easy to fill in, and a blank list of
    keywords is not. Each row carries what the engine would have guessed —
    the page Search Console shows and where it ranks — so the decision is
    a confirmation rather than research.
    """
    from datetime import date, timedelta

    from app.models.crawl import FactCrawlPageSnapshot
    from app.models.decision import KeywordPageMap
    from app.models.seranking import FactSerKeyword, FactSerKeywordMetric
    from app.services.lever_engine import (
        _pages_for_queries,
        _rank_position,
        active_crawl_source,
    )

    if period is None:
        today = date.today()
        period = (today - timedelta(days=29), today)

    mapped = {
        (row.keyword or "").strip().lower(): row
        for row in db.query(KeywordPageMap)
        .filter(KeywordPageMap.client_id == client_id)
        .all()
    }
    metrics = {
        (row.keyword or "").strip().lower(): row
        for row in db.query(FactSerKeywordMetric)
        .filter(FactSerKeywordMetric.client_id == client_id)
        .all()
    }
    suggestions = _pages_for_queries(db, client_id, period=period)

    # Where each page points its canonical. Search Console happily reports a
    # retired URL — smamarketing.com/services/local-seo still draws
    # impressions while telling Google to index /capabilities/local-seo —
    # and mapping a term to the page that asked to be ignored would bake the
    # mistake in permanently.
    canonical_of: dict[str, str] = {}
    crawled = (
        db.query(
            FactCrawlPageSnapshot.normalized_url,
            FactCrawlPageSnapshot.canonical_url,
            FactCrawlPageSnapshot.indexable,
        )
        .filter(
            FactCrawlPageSnapshot.client_id == client_id,
            FactCrawlPageSnapshot.source == active_crawl_source(),
        )
        .all()
    )
    for url, canonical, _indexable in crawled:
        if url and canonical and canonical != url:
            canonical_of[url] = canonical

    rows = []
    for tracked in (
        db.query(FactSerKeyword).filter(FactSerKeyword.client_id == client_id).all()
    ):
        keyword = (tracked.keyword or "").strip()
        if not keyword:
            continue
        key = keyword.lower()
        row = mapped.get(key)
        metric = metrics.get(key)
        suggested = suggestions.get(key)
        suggested_url = suggested.page_url if suggested else None
        redirected_from = None
        if suggested_url and suggested_url in canonical_of:
            redirected_from, suggested_url = suggested_url, canonical_of[suggested_url]
        rows.append(
            {
                "keyword": keyword,
                "page_url": row.page_url if row else None,
                "note": row.note if row else None,
                "mapped": row is not None,
                "volume": float(metric.volume) if metric and metric.volume else None,
                "difficulty": (
                    float(metric.difficulty) if metric and metric.difficulty else None
                ),
                "current_position": _rank_position(tracked.current_position),
                "suggested_page_url": suggested_url,
                "suggested_impressions": (
                    round(suggested.impressions) if suggested else None
                ),
                #: Set when the page Search Console reports canonicalises
                #: elsewhere, so the UI can say why it is offering a
                #: different URL than the data literally shows.
                "suggested_instead_of": redirected_from,
            }
        )
    rows.sort(key=lambda r: (r["mapped"], -(r["volume"] or 0), r["keyword"]))

    # Candidate pages for the picker: everything the crawl reached that can
    # actually hold a ranking.
    # Only pages that could actually hold the ranking: a page pointing its
    # canonical elsewhere has asked not to, so offering it in the picker
    # invites exactly the mistake above.
    pages = sorted(
        url
        for url, _canonical, indexable in crawled
        if url and indexable and url not in canonical_of
    )
    return {"keywords": rows, "pages": pages}
