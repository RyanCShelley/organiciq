"""Lock a baseline as a version, and read the versions back.

Anyone on staff may lock. What stops a bad baseline is not who, but the rules:
every blocker the analysis raised has to be acknowledged, a re-baseline has to say
why, and the numbers are recomputed here from the source so the screen cannot
hand in figures of its own.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models.baseline import BaselineVersion
from app.models.client import Client
from app.schemas import BaselineLockRequest, ClientUpdate
from app.services import baseline_series, clients as client_service

INITIAL = "initial"
REBASELINE_REASONS = {
    "relaunch": "The site was relaunched or migrated",
    "tracking_change": "Lead or traffic tracking changed",
    "definition_change": "What counts as a lead changed",
    "correction": "The earlier baseline was wrong",
}
MIN_NOTE_CHARS = 10
GOAL_HORIZON_MONTHS = 12


def _summary(row: BaselineVersion) -> dict[str, Any]:
    num = lambda value: None if value is None else float(value)  # noqa: E731
    return {
        "version": row.version,
        "status": row.status,
        "reason_code": row.reason_code,
        "reason_note": row.reason_note,
        "locked_by": row.locked_by,
        "locked_at": row.locked_at.isoformat() if row.locked_at else None,
        "method_version": row.method_version,
        "source_type": row.source_type,
        "regime_start": row.regime_start,
        "window_from": row.window_from,
        "window_to": row.window_to,
        "lead_events": row.lead_events,
        "acknowledged": row.acknowledged,
        "monthly_sessions": num(row.monthly_sessions),
        "monthly_organic_sessions": num(row.monthly_organic_sessions),
        "lead_rate_pct": num(row.lead_rate_pct),
        "monthly_leads": num(row.monthly_leads),
        "goal_monthly_leads": num(row.goal_monthly_leads),
    }


def list_versions(db: Session, client: Client) -> list[dict[str, Any]]:
    rows = (
        db.query(BaselineVersion)
        .filter(BaselineVersion.client_id == client.id)
        .order_by(BaselineVersion.version.desc())
        .all()
    )
    return [_summary(row) for row in rows]


def get_version(db: Session, client: Client, version: int) -> dict[str, Any] | None:
    row = (
        db.query(BaselineVersion)
        .filter(BaselineVersion.client_id == client.id, BaselineVersion.version == version)
        .one_or_none()
    )
    return None if row is None else {**_summary(row), "snapshot": row.snapshot}


def _projection_record(result: dict[str, Any], version: int, window_end: date, window_start: date) -> dict[str, Any]:
    """The shape the dashboard already reads, plus what says how it was made."""
    projection = result["projection"]
    days = (window_end - window_start).days + 1
    return {
        "generated_on": date.today().isoformat(),
        "baseline_as_of": window_end.isoformat(),
        "window": {
            "from": window_start.isoformat(),
            "to": window_end.isoformat(),
            "period_days": days,
            "scaled_to_days": 30,
            "requested_from": window_start.isoformat(),
            "requested_days": days,
            "fully_covered": True,
        },
        "plan": projection["plan"],
        "plan_label": projection["plan_label"],
        "goal_horizon_months": projection["goal_horizon_months"],
        "suggested_monthly_lead_goal": projection["suggested_monthly_lead_goal"],
        "checkpoints": projection["checkpoints"],
        "baseline_version": version,
        "method_version": result["method_version"],
        "goal_basis": result["goal_basis"],
        "ranges": result["ranges"],
    }


def lock(db: Session, client: Client, user_email: str, request: BaselineLockRequest) -> dict[str, Any]:
    result = baseline_series.build_result(
        db,
        client,
        source=request.source,
        csv_text=request.csv_text,
        regime_start=request.regime_start,
        lead_events=request.lead_events or None,
        half_life_months=request.half_life_months,
        acknowledged=request.acknowledged,
        months=request.months,
        as_of=request.as_of,
    )
    open_blockers = [
        flag for flag in result["flags"] if flag["level"] == baseline_series.BLOCKER and not flag["acknowledged"]
    ]
    if open_blockers:
        raise ValueError(
            "Acknowledge or fix these before locking: "
            + "; ".join(f"{flag['code']} — {flag['message']}" for flag in open_blockers)
        )

    latest = (
        db.query(BaselineVersion.version)
        .filter(BaselineVersion.client_id == client.id)
        .order_by(BaselineVersion.version.desc())
        .first()
    )
    version = (latest[0] + 1) if latest else 1
    note = (request.reason_note or "").strip() or None
    if version == 1:
        reason = request.reason_code or INITIAL
        if reason != INITIAL:
            raise ValueError("The first baseline's reason is “initial”.")
    else:
        reason = request.reason_code or ""
        if reason not in REBASELINE_REASONS:
            raise ValueError(
                "A new baseline needs a reason: " + ", ".join(REBASELINE_REASONS) + "."
            )
        if not note or len(note) < MIN_NOTE_CHARS:
            raise ValueError(f"Say why in a sentence (at least {MIN_NOTE_CHARS} characters).")

    window = result["window"]
    window_start = date(int(window["from"][:4]), int(window["from"][5:7]), 1)
    window_end = baseline_series.month_end(window["to"])
    baseline, goal = result["baseline"], result["goal_basis"]
    source = result["source"]
    row = BaselineVersion(
        client_id=client.id,
        version=version,
        reason_code=reason,
        reason_note=note,
        locked_by=user_email,
        status=result["status"],
        method_version=result["method_version"],
        source_type=source["type"],
        regime_start=window["regime_start"],
        window_from=window["from"],
        window_to=window["to"],
        lead_events=source.get("lead_events") or [],
        acknowledged=sorted(set(request.acknowledged)),
        monthly_sessions=Decimal(str(baseline["monthly_sessions"])),
        monthly_organic_sessions=(
            None if baseline["monthly_organic_sessions"] is None else Decimal(str(baseline["monthly_organic_sessions"]))
        ),
        lead_rate_pct=Decimal(str(baseline["lead_rate_pct"])),
        monthly_leads=Decimal(str(baseline["monthly_leads"])),
        goal_monthly_leads=Decimal(str(goal["monthly_leads"])),
        snapshot=result,
    )
    db.add(row)
    db.flush()

    suggested_goal = int(result["projection"]["suggested_monthly_lead_goal"])
    goal_to_set = request.monthly_lead_goal
    if goal_to_set is None and client.monthly_lead_goal is None:
        goal_to_set = suggested_goal
    update = {
        "baseline_as_of": window_end,
        "baseline_period_start": window_start,
        "baseline_period_end": window_end,
        "baseline_monthly_sessions": int(round(baseline["monthly_sessions"])),
        "baseline_monthly_leads": int(round(baseline["monthly_leads"])),
        "baseline_lead_rate_pct": baseline["lead_rate_pct"],
        "baseline_source": "baseline_series",
        "baseline_notes": f"v{version} {reason}" + (f": {note}" if note else ""),
        "baseline_projection_json": _projection_record(result, version, window_end, window_start),
    }
    if goal_to_set is not None:
        update["monthly_lead_goal"] = int(goal_to_set)
    client_service.update_client(db, client, ClientUpdate(**update))

    return {
        "version": _summary(row),
        "monthly_lead_goal": client.monthly_lead_goal,
        "suggested_monthly_lead_goal": suggested_goal,
        "goal_set_by_lock": goal_to_set is not None,
    }
