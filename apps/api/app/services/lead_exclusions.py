"""Keep test submissions out of every lead number.

One clause, ANDed into each query that sums lead events, so the incident, the
dashboard and the baseline snapshot cannot disagree about what a lead is.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import and_, func, not_, or_, true
from sqlalchemy.orm import Session

from app.models.config import LeadExclusion
from app.models.ga4 import FactGa4Event


def _rule_clause(rule: LeadExclusion):
    parts = []
    if rule.url_pattern:
        pattern = rule.url_pattern.strip()
        if pattern.endswith("*"):
            parts.append(FactGa4Event.normalized_url.startswith(pattern[:-1], autoescape=True))
        else:
            parts.append(FactGa4Event.normalized_url == pattern)
    if rule.event_name:
        parts.append(FactGa4Event.event_name == rule.event_name)
    if rule.session_source:
        parts.append(FactGa4Event.session_source == rule.session_source)
    if rule.date_from:
        parts.append(FactGa4Event.date >= rule.date_from)
    if rule.date_to:
        parts.append(FactGa4Event.date <= rule.date_to)
    return and_(*parts) if parts else None


def excluded_clause(db: Session, client_id: UUID):
    """True for events that a rule marks as test leads (None if no rules)."""
    clauses = [
        c
        for c in (_rule_clause(r) for r in db.query(LeadExclusion).filter(LeadExclusion.client_id == client_id))
        if c is not None
    ]
    return or_(*clauses) if clauses else None


def not_excluded(db: Session, client_id: UUID):
    """Filter clause that keeps real leads only."""
    clause = excluded_clause(db, client_id)
    return true() if clause is None else not_(clause)


def excluded_leads_since(
    db: Session, client_id: UUID, event_names: list[str], since, until
) -> tuple[float, "object | None"]:
    """Excluded lead events in [since, until]: (count, latest date)."""
    clause = excluded_clause(db, client_id)
    if clause is None or not event_names:
        return 0.0, None
    count, latest = (
        db.query(func.coalesce(func.sum(FactGa4Event.event_count), 0), func.max(FactGa4Event.date))
        .filter(
            FactGa4Event.client_id == client_id,
            FactGa4Event.event_name.in_(event_names),
            FactGa4Event.event_count > 0,
            FactGa4Event.date >= since,
            FactGa4Event.date <= until,
            clause,
        )
        .one()
    )
    return float(count or 0), latest
