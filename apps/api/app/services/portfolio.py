"""Every client's month on one screen.

Read entirely from the saved monthly records. The engine already decided each
of these things and wrote them down; recomputing them here would give a
portfolio that could disagree with the client page it links to, which is the
failure the saved record exists to prevent.

So nothing in this module measures anything. It counts.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.decision import MonthlyRecord

#: The ladder, then the two outcomes that are not a failing branch. Fixed
#: order so a bar chart does not reshuffle itself between months.
CONSTRAINT_ORDER = (
    "visibility",
    "traffic",
    "leads",
    "visibility_expansion",
    "withheld",
)

CONSTRAINT_LABEL = {
    "visibility": "Visibility",
    "traffic": "Traffic",
    "leads": "Leads",
    "visibility_expansion": "Visibility expansion",
    "withheld": "Withheld",
}


def _branch_status(record: dict, branch: str) -> str | None:
    for row in record.get("branches") or []:
        if row.get("branch") == branch:
            return row.get("status")
    return None


def _client_row(client: Client, row: MonthlyRecord) -> dict[str, Any]:
    record = row.record or {}
    actions = record.get("actions") or []
    return {
        "client_id": str(client.id),
        "slug": client.slug,
        "client": client.client_name or client.slug,
        "plan": record.get("plan"),
        "constraint": row.constraint_name,
        "constraint_label": CONSTRAINT_LABEL.get(
            row.constraint_name, row.constraint_name
        ),
        "visibility": _branch_status(record, "visibility"),
        "traffic": _branch_status(record, "traffic"),
        "leads": _branch_status(record, "leads"),
        "confidence": row.confidence,
        "held_since": row.held_since,
        "slots": record.get("action_slots") or 0,
        "filled": len(actions),
        "spillover": sum(1 for a in actions if a.get("spillover")),
        "empty": len(record.get("empty_slots") or []),
        "data_gaps": [
            gap.get("input")
            for gap in (record.get("data_gaps") or [])
            if gap.get("input")
        ],
        "overridden": record.get("override") == "manual",
    }


def portfolio(
    db: Session,
    *,
    month: str | None = None,
    allowed_client_ids: set[str] | None = None,
) -> dict[str, Any]:
    """One row per client for the given month, plus the totals.

    With no month, each client's newest saved run — which is what somebody
    opening the page means by "where is everything". Clients run at different
    times, so insisting on one month would hide a client whose run is a day
    older than the rest.

    `allowed_client_ids` narrows it before anything is counted. Filtering the
    rows afterwards would leave totals describing clients the reader cannot
    open, which is both a leak and a number nobody can check.
    """
    query = (
        db.query(MonthlyRecord, Client)
        .join(Client, Client.id == MonthlyRecord.client_id)
        .order_by(MonthlyRecord.month.desc())
    )
    if month:
        query = query.filter(MonthlyRecord.month == month)
    if allowed_client_ids is not None:
        if not allowed_client_ids:
            query = query.filter(False)
        else:
            query = query.filter(MonthlyRecord.client_id.in_(allowed_client_ids))

    newest: dict[str, tuple[MonthlyRecord, Client]] = {}
    for record, client in query.all():
        # Ordered newest first, so the first row seen for a client is its
        # newest run.
        newest.setdefault(str(client.id), (record, client))

    rows = sorted(
        (_client_row(client, record) for record, client in newest.values()),
        key=lambda r: (
            CONSTRAINT_ORDER.index(r["constraint"])
            if r["constraint"] in CONSTRAINT_ORDER
            else len(CONSTRAINT_ORDER),
            -r["filled"],
            r["client"].lower(),
        ),
    )

    # Withheld clients have no plan this month, so their slots are not
    # capacity that went unused — counting them would make the fill rate a
    # statement about data outages rather than about the work.
    planned = [r for r in rows if r["constraint"] != "withheld"]
    capacity = sum(r["slots"] for r in planned)
    filled = sum(r["filled"] for r in planned)

    months = sorted({r for r in (rec.month for rec, _ in newest.values())}, reverse=True)

    return {
        "month": month or (months[0] if months else None),
        "mixed_months": len(months) > 1,
        "totals": {
            "clients": len(rows),
            "run": len(planned),
            "withheld": len(rows) - len(planned),
            "capacity": capacity,
            "filled": filled,
            "empty": sum(r["empty"] for r in planned),
            "spillover": sum(r["spillover"] for r in planned),
            "leads_blocked": sum(1 for r in rows if r["leads"] == "blocked"),
            "on_visibility": sum(1 for r in rows if r["constraint"] == "visibility"),
        },
        "by_constraint": [
            {
                "constraint": key,
                "label": CONSTRAINT_LABEL[key],
                "clients": sum(1 for r in rows if r["constraint"] == key),
            }
            for key in CONSTRAINT_ORDER
        ],
        # Which missing input costs the most clients. Ordered by how many,
        # because that is the order worth fixing them in.
        "data_gaps": [
            {"input": name, "clients": count}
            for name, count in sorted(
                _gap_counts(rows).items(), key=lambda kv: (-kv[1], kv[0])
            )
        ],
        "clients": rows,
    }


def _gap_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        for gap in row["data_gaps"]:
            counts[gap] = counts.get(gap, 0) + 1
    return counts
