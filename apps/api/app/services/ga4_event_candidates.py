"""Which of a client's GA4 events look like leads.

Twenty of twenty-four clients have no `conversion_definitions`, which blocks
the entire Lead branch — L1, L2, L3 and the three lead actions — and makes
every one of them Withheld under the spec. The events themselves have been
in the warehouse the whole time, named by whoever set the property up:
`form_submission`, `phone_call`, `Phone Call / Email Click`, `Conversion`.

The screen that existed asked for one event at a time, typed by hand, with a
label and a type per event. That is why nobody filled it in. This gives the
screen a list to tick instead.

Nothing here decides. A suggestion is a pattern match on a name somebody else
chose, and `Conversion` may be a real lead or a GA4 default left switched on
— only the person who knows the client can say. The engine reads
`conversion_definitions`, which stays human-confirmed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.config import ConversionDefinition
from app.models.ga4 import FactGa4Event

#: Events GA4 collects on its own, through enhanced measurement or by
#: default. None of them is a lead, and they are the bulk of the list, so
#: they are grouped away rather than deleted — a client could in principle
#: have renamed one.
AUTOMATIC_EVENTS = frozenset(
    {
        "page_view", "session_start", "first_visit", "user_engagement",
        "scroll", "click", "view_search_results", "video_start",
        "video_progress", "video_complete", "file_download", "form_start",
        "first_open", "app_remove", "app_update", "os_update",
        "firebase_campaign", "notification_receive",
    }
)

#: Name fragments that usually mean somebody filled something in. Ordered
#: strongest first only for readability; matching is any-of.
_LEAD_PATTERNS = (
    r"\blead\b", r"generate lead",
    r"submi", r"form fill", r"contact", r"enquir", r"inquir",
    # A thank-you event is what fires after something was sent.
    r"thank ?you",
    # Somebody named an event "Conversion" on purpose. GA4 never does.
    r"conversion",
    r"phone", r"\bcall\b", r"tel click", r"click to call",
    r"quote", r"estimate", r"booking", r"\bbook\b", r"appointment",
    r"schedule", r"consult", r"request", r"sign ?up",
    r"\bdemo\b", r"\bapply\b", r"application",
)

#: `form_start` is the trap. Somebody touching a field is not somebody
#: sending it, and the name is one character from the one that counts.
_NEVER_LEAD = frozenset({"form_start", "form_abandon"})

_LEAD_RE = re.compile("|".join(_LEAD_PATTERNS), re.IGNORECASE)


def _spaced(name: str) -> str:
    """Separators become spaces before matching.

    `\bsubmi` never fired on `grade_submit`, because an underscore is a word
    character and there is no boundary in front of it. Every snake_case
    event on the warehouse's list was failing the same way.
    """
    return re.sub(r"[_\-/|.]+", " ", name or "").strip()


def looks_like_a_lead(event_name: str) -> bool:
    """Whether the name reads as somebody submitting something.

    A guess about words, offered to a person. It is never written to
    `conversion_definitions` without them agreeing.
    """
    name = (event_name or "").strip()
    if not name or name.lower() in _NEVER_LEAD:
        return False
    if name.lower() in AUTOMATIC_EVENTS:
        return False
    return bool(_LEAD_RE.search(_spaced(name)))


def suggested_label(event_name: str) -> str:
    """A readable name for the conversion, so the field is not left blank."""
    words = re.split(r"[_\-\s/|]+", (event_name or "").strip())
    cleaned = [w for w in words if w]
    if not cleaned:
        return "Lead"
    return " ".join(w if w.isupper() else w.capitalize() for w in cleaned)


@dataclass(frozen=True)
class EventCandidate:
    event_name: str
    #: Firings in the window. All-time totals flatter an event that stopped
    #: reporting months ago, which is the opposite of what the reader needs.
    event_count: int
    #: How many distinct landing pages it fired on. The sharpest signal on
    #: the screen: a lead event fires on a handful of pages, `page_view`
    #: fires on all of them.
    pages: int
    last_seen: date | None
    automatic: bool
    suggested: bool
    #: Set when the client already has a definition for this event.
    defined: bool
    conversion_name: str | None
    conversion_type: str | None
    is_primary: bool
    active: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_name": self.event_name,
            "event_count": self.event_count,
            "pages": self.pages,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "automatic": self.automatic,
            "suggested": self.suggested,
            "defined": self.defined,
            "conversion_name": self.conversion_name or suggested_label(self.event_name),
            "conversion_type": self.conversion_type or "lead",
            "is_primary": self.is_primary,
            "active": self.active,
        }


def load_event_candidates(
    db: Session, client_id: UUID, *, days: int = 90, today: date | None = None
) -> list[EventCandidate]:
    """Every event this client reports, with what the reader needs to judge it.

    Ordered so the decision is quick: events already defined first, then the
    ones whose names suggest a lead, then everything else by volume.
    """
    end = today or date.today()
    start = end - timedelta(days=days)

    rows = (
        db.query(
            FactGa4Event.event_name,
            func.coalesce(func.sum(FactGa4Event.event_count), 0).label("count"),
            func.count(func.distinct(FactGa4Event.normalized_url)).label("pages"),
            func.max(FactGa4Event.date).label("last_seen"),
        )
        .filter(
            FactGa4Event.client_id == client_id,
            FactGa4Event.date >= start,
            FactGa4Event.date <= end,
            FactGa4Event.event_name.isnot(None),
        )
        .group_by(FactGa4Event.event_name)
        .all()
    )

    existing = {
        row.event_name: row
        for row in db.query(ConversionDefinition)
        .filter(ConversionDefinition.client_id == client_id)
        .all()
    }

    candidates: list[EventCandidate] = []
    for name, count, pages, last_seen in rows:
        current = existing.get(name)
        candidates.append(
            EventCandidate(
                event_name=name,
                event_count=int(count or 0),
                pages=int(pages or 0),
                last_seen=last_seen,
                automatic=name.lower() in AUTOMATIC_EVENTS,
                suggested=looks_like_a_lead(name),
                defined=current is not None,
                conversion_name=current.conversion_name if current else None,
                conversion_type=current.conversion_type if current else None,
                is_primary=bool(current.is_primary) if current else False,
                active=bool(current.active) if current else True,
            )
        )

    # A definition whose event has not fired in the window still has to
    # appear, or saving the screen would silently drop it.
    for name, current in existing.items():
        if any(c.event_name == name for c in candidates):
            continue
        candidates.append(
            EventCandidate(
                event_name=name,
                event_count=0,
                pages=0,
                last_seen=None,
                automatic=name.lower() in AUTOMATIC_EVENTS,
                suggested=looks_like_a_lead(name),
                defined=True,
                conversion_name=current.conversion_name,
                conversion_type=current.conversion_type,
                is_primary=bool(current.is_primary),
                active=bool(current.active),
            )
        )

    candidates.sort(
        key=lambda c: (
            not c.defined,
            c.automatic,
            not c.suggested,
            -c.event_count,
            c.event_name.lower(),
        )
    )
    return candidates
