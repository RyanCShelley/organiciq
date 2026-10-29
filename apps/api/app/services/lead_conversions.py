"""One definition of what counts as a lead.

The dashboard, the alerts, the engine's lead branch and the results loop all count
leads from the client's active lead conversion definitions. The baseline calculator
let somebody choose events of its own, so a locked baseline could count one set of
events while the home screen counted another. Locking now keeps the two together:
the events a baseline used become the client's lead conversions, and a difference
has to be agreed to in so many words.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.config import ConversionDefinition

LEAD = "lead"


def active_lead_events(db: Session, client_id: UUID) -> list[str]:
    rows = (
        db.query(ConversionDefinition.event_name)
        .filter(
            ConversionDefinition.client_id == client_id,
            ConversionDefinition.active.is_(True),
            ConversionDefinition.conversion_type == LEAD,
        )
        .order_by(ConversionDefinition.event_name)
        .all()
    )
    return [row[0] for row in rows]


def diff(db: Session, client_id: UUID, events: list[str]) -> dict[str, list[str]]:
    """What making `events` the lead conversions would add, remove and leave."""
    wanted = list(dict.fromkeys(name.strip() for name in events if name and name.strip()))
    current = active_lead_events(db, client_id)
    return {
        "add": [name for name in wanted if name not in current],
        "remove": [name for name in current if name not in wanted],
        "keep": [name for name in wanted if name in current],
    }


def sync(db: Session, client_id: UUID, events: list[str]) -> dict[str, list[str]]:
    """Make `events` exactly the client's active lead conversions.

    Nothing is deleted: a definition that drops out is switched off, so its history
    and name survive and it can be switched back on. Definitions of other types
    (a call, a purchase) are left alone. Exactly one lead stays primary.
    """
    changes = diff(db, client_id, events)
    wanted = changes["add"] + changes["keep"]
    existing = {
        row.event_name: row
        for row in db.query(ConversionDefinition).filter(ConversionDefinition.client_id == client_id)
    }
    for name in wanted:
        row = existing.get(name)
        if row is None:
            db.add(
                ConversionDefinition(
                    client_id=client_id,
                    event_name=name,
                    conversion_name=name,
                    conversion_type=LEAD,
                    is_primary=False,
                    active=True,
                )
            )
        else:
            row.conversion_type = LEAD
            row.active = True
    for name in changes["remove"]:
        row = existing[name]
        row.active = False
        row.is_primary = False
    db.flush()

    leads = [
        row
        for row in db.query(ConversionDefinition).filter(
            ConversionDefinition.client_id == client_id,
            ConversionDefinition.conversion_type == LEAD,
            ConversionDefinition.active.is_(True),
        )
    ]
    primaries = [row for row in leads if row.is_primary]
    if leads and not primaries:
        order = {name: index for index, name in enumerate(wanted)}
        sorted(leads, key=lambda row: order.get(row.event_name, 999))[0].is_primary = True
    for extra in primaries[1:]:
        extra.is_primary = False
    db.flush()
    return changes


def describe(changes: dict[str, list[str]]) -> str:
    parts = []
    if changes["add"]:
        parts.append("adds " + ", ".join(changes["add"]))
    if changes["remove"]:
        parts.append("switches off " + ", ".join(changes["remove"]))
    return " and ".join(parts) or "changes nothing"
