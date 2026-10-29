"""Wipe baselines so every client can be re-baselined with the new calculator.

A baseline is the locked versions, the numbers copied onto the client from them, the
frozen projection, and the goals those produced: the plan-end monthly lead goal and
hand corrections to the projected goals. With the projection gone the home screen
falls back to the monthly goal, so leaving an old goal behind would put the old
baseline back on screen; both go. Nothing else on the client is touched, and lead
conversion definitions are kept.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.baseline import BaselineVersion
from app.models.client import Client

CONFIRMATION = "RESET"

BASELINE_COLUMNS = (
    "baseline_as_of",
    "baseline_period_start",
    "baseline_period_end",
    "baseline_monthly_sessions",
    "baseline_monthly_leads",
    "baseline_lead_rate_pct",
    "baseline_source",
    "baseline_notes",
    "baseline_projection_json",
)
GOAL_COLUMNS = ("monthly_lead_goal", "lead_goal_overrides")


def _plain(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "__float__") and not isinstance(value, (int, float)):
        return float(value)
    return value


def _clients(db: Session, client_ids: list[UUID] | None) -> list[Client]:
    query = db.query(Client).order_by(Client.client_name)
    if client_ids:
        query = query.filter(Client.id.in_(client_ids))
    return query.all()


def _has_something(client: Client, versions: int) -> bool:
    return (
        versions > 0
        or any(getattr(client, name) is not None for name in BASELINE_COLUMNS)
        or client.monthly_lead_goal is not None
        or bool(client.lead_goal_overrides)
    )


def _version_counts(db: Session) -> dict[UUID, int]:
    counts: dict[UUID, int] = {}
    for client_id, in db.query(BaselineVersion.client_id):
        counts[client_id] = counts.get(client_id, 0) + 1
    return counts


def preview(db: Session, client_ids: list[UUID] | None = None) -> dict[str, Any]:
    counts = _version_counts(db)
    rows = []
    for client in _clients(db, client_ids):
        versions = counts.get(client.id, 0)
        if not _has_something(client, versions):
            continue
        rows.append(
            {
                "client_id": str(client.id),
                "slug": client.slug,
                "client_name": client.client_name,
                "versions": versions,
                "has_baseline": any(getattr(client, name) is not None for name in BASELINE_COLUMNS),
                "baseline_as_of": _plain(client.baseline_as_of),
                "monthly_lead_goal": client.monthly_lead_goal,
                "goal_corrections": len(client.lead_goal_overrides or {}),
            }
        )
    return {
        "clients": rows,
        "totals": {"clients": len(rows), "versions": sum(row["versions"] for row in rows)},
    }


def reset(db: Session, client_ids: list[UUID] | None = None) -> dict[str, Any]:
    """Clear baselines and goals, and return what was removed so a copy can be kept."""
    counts = _version_counts(db)
    removed = []
    deleted = 0
    for client in _clients(db, client_ids):
        versions = counts.get(client.id, 0)
        if not _has_something(client, versions):
            continue
        saved_versions = [
            {
                "version": row.version,
                "reason_code": row.reason_code,
                "reason_note": row.reason_note,
                "locked_by": row.locked_by,
                "locked_at": _plain(row.locked_at),
                "window_from": row.window_from,
                "window_to": row.window_to,
                "monthly_sessions": _plain(row.monthly_sessions),
                "lead_rate_pct": _plain(row.lead_rate_pct),
                "monthly_leads": _plain(row.monthly_leads),
                "lead_events": row.lead_events,
            }
            for row in db.query(BaselineVersion)
            .filter(BaselineVersion.client_id == client.id)
            .order_by(BaselineVersion.version)
        ]
        removed.append(
            {
                "client_id": str(client.id),
                "slug": client.slug,
                "client_name": client.client_name,
                "client_fields": {
                    name: _plain(getattr(client, name)) for name in (*BASELINE_COLUMNS, *GOAL_COLUMNS)
                },
                "versions": saved_versions,
            }
        )
        deleted += db.query(BaselineVersion).filter(BaselineVersion.client_id == client.id).delete(
            synchronize_session=False
        )
        for name in BASELINE_COLUMNS:
            setattr(client, name, None)
        client.monthly_lead_goal = None
        client.lead_goal_overrides = {}
    db.commit()
    return {"reset_clients": len(removed), "versions_deleted": deleted, "removed": removed}
