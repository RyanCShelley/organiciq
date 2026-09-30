"""Trailing 30-day sessions and leads behind the dashboard comparison charts."""

from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

from app.models.config import ConversionDefinition, OrganicChannel
from app.models.ga4 import FactGa4Event, FactGa4Traffic
from app.services.dashboard import TRAILING_WINDOW_DAYS, _trailing_30_series


def _traffic(client_id, on: date, sessions: int):
    return FactGa4Traffic(
        id=uuid4(),
        client_id=client_id,
        date=on,
        raw_url="https://example.com/",
        normalized_url="https://example.com",
        session_source="google",
        session_medium="organic",
        channel=OrganicChannel.ORGANIC_SEARCH,
        sessions=sessions,
        active_users=sessions,
        views=sessions,
    )


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


def test_first_point_already_holds_a_full_window(db, client_a):
    """The series opens at its true level, not climbing from zero."""
    since = date.today() - timedelta(days=5)
    for offset in range(TRAILING_WINDOW_DAYS):
        db.add(_traffic(client_a.id, since - timedelta(days=offset), 10))
    db.commit()

    rows = _trailing_30_series(db, client_a.id, [], (since, date.today()))

    assert rows[0]["date"] == since.isoformat()
    assert rows[0]["sessions"] == 300


def test_days_roll_out_of_the_window(db, client_a):
    """A single spike leaves the window exactly 30 days later."""
    since = date.today() - timedelta(days=40)
    db.add(_traffic(client_a.id, since, 100))
    db.commit()

    rows = {
        row["date"]: row["sessions"]
        for row in _trailing_30_series(db, client_a.id, [], (since, date.today()))
    }

    assert rows[since.isoformat()] == 100
    last_day_inside = since + timedelta(days=TRAILING_WINDOW_DAYS - 1)
    assert rows[last_day_inside.isoformat()] == 100
    assert rows[(last_day_inside + timedelta(days=1)).isoformat()] == 0


def test_sessions_and_leads_roll_together(db, client_a):
    _define_lead(db, client_a.id)
    since = date.today() - timedelta(days=3)
    db.add(_traffic(client_a.id, since, 80))
    db.add(_lead_event(client_a.id, since, 4))
    db.commit()

    rows = _trailing_30_series(db, client_a.id, ["generate_lead"], (since, date.today()))

    assert rows[0]["sessions"] == 80
    assert rows[0]["leads"] == 4
    assert rows[-1]["date"] == date.today().isoformat()


def test_one_point_per_day_in_the_window(db, client_a):
    since = date.today() - timedelta(days=10)
    db.add(_traffic(client_a.id, since, 5))
    db.commit()

    rows = _trailing_30_series(db, client_a.id, [], (since, date.today()))

    assert len(rows) == 11
    assert rows[-1]["date"] == date.today().isoformat()


def test_the_window_bounds_the_series(db, client_a):
    """A comparison period stops at its own end, not at today."""
    since = date.today() - timedelta(days=20)
    until = date.today() - timedelta(days=11)
    db.add(_traffic(client_a.id, since, 7))
    db.commit()

    rows = _trailing_30_series(db, client_a.id, [], (since, until))

    assert rows[0]["date"] == since.isoformat()
    assert rows[-1]["date"] == until.isoformat()
    assert len(rows) == 10


def test_no_window_means_no_series(db, client_a):
    assert _trailing_30_series(db, client_a.id, [], None) == []


def test_no_facts_means_no_series(db, client_a):
    window = (date.today() - timedelta(days=5), date.today())
    assert _trailing_30_series(db, client_a.id, [], window) == []
