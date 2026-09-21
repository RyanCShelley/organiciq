"""Monthly lead history behind the dashboard progress chart."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

from app.models.config import ConversionDefinition, OrganicChannel
from app.models.ga4 import FactGa4Event
from app.services.dashboard import _monthly_lead_actuals


def _lead_event(client_id, on: date, count: int, name: str = "generate_lead"):
    return FactGa4Event(
        id=uuid4(),
        client_id=client_id,
        date=on,
        raw_url="https://example.com/contact",
        normalized_url="https://example.com/contact",
        session_source="google",
        session_medium="organic",
        channel=OrganicChannel.ORGANIC_SEARCH,
        event_name=name,
        event_count=count,
    )


def _define_lead(db, client_id, name: str = "generate_lead"):
    db.add(
        ConversionDefinition(
            id=uuid4(),
            client_id=client_id,
            event_name=name,
            conversion_name="Lead",
            conversion_type="lead",
            is_primary=True,
            active=True,
        )
    )
    db.commit()


def test_groups_lead_events_by_calendar_month(db, client_a):
    _define_lead(db, client_a.id)
    db.add(_lead_event(client_a.id, date(2026, 6, 3), 4))
    db.add(_lead_event(client_a.id, date(2026, 6, 28), 6))
    db.add(_lead_event(client_a.id, date(2026, 7, 15), 9))
    db.commit()

    rows = _monthly_lead_actuals(db, client_a.id, ["generate_lead"], since=date(2026, 6, 1))

    assert [(r["month"], r["leads"]) for r in rows] == [("2026-06", 10), ("2026-07", 9)]


def test_months_are_ordered_and_start_at_the_baseline(db, client_a):
    _define_lead(db, client_a.id)
    db.add(_lead_event(client_a.id, date(2026, 3, 1), 99))
    db.add(_lead_event(client_a.id, date(2026, 6, 1), 5))
    db.commit()

    rows = _monthly_lead_actuals(db, client_a.id, ["generate_lead"], since=date(2026, 6, 14))

    assert [r["month"] for r in rows] == ["2026-06"], "history before the baseline is excluded"


def test_the_month_in_progress_is_flagged_partial(db, client_a):
    """
    A partial month plots as a collapse unless the chart knows it is partial.
    """
    _define_lead(db, client_a.id)
    today = date.today()
    db.add(_lead_event(client_a.id, today, 3))
    db.commit()

    rows = _monthly_lead_actuals(db, client_a.id, ["generate_lead"], since=today.replace(day=1))

    assert rows[-1]["month"] == today.isoformat()[:7]
    assert rows[-1]["partial"] is True


def test_only_defined_lead_events_count(db, client_a):
    _define_lead(db, client_a.id)
    db.add(_lead_event(client_a.id, date(2026, 6, 3), 4))
    db.add(_lead_event(client_a.id, date(2026, 6, 4), 500, name="page_view"))
    db.commit()

    rows = _monthly_lead_actuals(db, client_a.id, ["generate_lead"], since=date(2026, 6, 1))

    assert [(r["month"], r["leads"]) for r in rows] == [("2026-06", 4)]


def test_no_lead_events_defined_yields_nothing(db, client_a):
    db.add(_lead_event(client_a.id, date(2026, 6, 3), 4))
    db.commit()

    assert _monthly_lead_actuals(db, client_a.id, [], since=date(2026, 6, 1)) == []
