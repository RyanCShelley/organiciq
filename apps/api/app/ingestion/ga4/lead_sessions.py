"""The union of visits producing selected lead events, measured by GA4.

Do not derive this from event counts or sum event-specific session counts. A
single filtered sessions report lets GA4 deduplicate across selected outcomes.
The denominator uses the identical period and site-folder scope without the
lead-event filter. Source/metadata validation is shared with ingestion.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
import re
from typing import Any

from app.core.urls import normalize_path_prefix
from app.ingestion.ga4.client import run_report


def _scope_filter(path_prefix: str | None) -> dict[str, Any] | None:
    prefix = normalize_path_prefix(path_prefix)
    if not prefix:
        return None
    return {"filter": {"fieldName": "landingPage", "stringFilter": {
        "matchType": "FULL_REGEXP", "value": re.escape(prefix) + r"(?:/.*|\?.*)?", "caseSensitive": False,
    }}}


def _sessions(rows) -> Decimal:
    if not getattr(rows, "complete", False):
        raise ValueError("Lead-session report completeness was not verified")
    if len(rows) > 1:
        raise ValueError("Lead-session measurement requires an aggregate report")
    if not rows:
        return Decimal(0)
    values = rows[0].get("metricValues") or []
    if len(values) != 1 or "value" not in values[0]:
        raise ValueError("Lead-session report omitted its sessions metric")
    value = Decimal(values[0]["value"])
    if not value.is_finite() or value < 0 or value != value.to_integral_value():
        raise ValueError("Lead-session count is invalid")
    return value


def fetch_lead_session_measurement(
    *, access_token: str, property_id: str, start_date: date, end_date: date,
    lead_events: list[str], path_prefix: str | None = None,
) -> dict[str, Any]:
    """Read a period measurement; no database writes or target changes.

    No configured lead events means unknown, not a zero conversion rate.
    These are whole-site/folder results, not a channel-scoped agency result.
    Persist the explicit definition and matching period before using a result
    in a dashboard or engine comparison; do not add period rates together.
    """
    names = sorted(set(name for name in lead_events if name))
    definition = {
        "basis": "sessions_with_selected_lead_event", "lead_events": names,
        "period": [start_date.isoformat(), end_date.isoformat()],
        "path_scope": normalize_path_prefix(path_prefix), "channel_scope": "all_channels",
    }
    if not names:
        return {**definition, "status": "not_configured", "sessions": None,
            "lead_sessions": None, "conversion_rate_pct": None}
    if end_date < start_date:
        raise ValueError("Lead-session period is reversed")
    scope = _scope_filter(path_prefix)
    selected = {"filter": {"fieldName": "eventName", "inListFilter": {
        "values": names, "caseSensitive": True,
    }}}
    numerator_filter = {"andGroup": {"expressions": [scope, selected]}} if scope else selected
    args = dict(access_token=access_token, property_id=property_id,
        start_date=start_date, end_date=end_date, dimensions=[], metrics=["sessions"])
    denominator_rows = run_report(**args, dimension_filter=scope)
    numerator_rows = run_report(**args, dimension_filter=numerator_filter)
    denominator, numerator = _sessions(denominator_rows), _sessions(numerator_rows)
    # Independent report estimates can occasionally disagree. Expose that as
    # unavailable instead of clamping an impossible rate into a passing KPI.
    if numerator > denominator:
        raise ValueError("Lead sessions exceed the matching session denominator")
    return {**definition, "status": "measured" if denominator else "no_sessions",
        "sessions": int(denominator), "lead_sessions": int(numerator),
        "conversion_rate_pct": float(numerator / denominator * 100) if denominator else None,
        "source_metadata": {"sessions": denominator_rows.pages, "lead_sessions": numerator_rows.pages}}
