"""Running totals behind the dashboard pacing charts."""

from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

from app.models.config import ConversionDefinition, OrganicChannel
from app.models.ga4 import FactGa4Event, FactGa4Traffic
from app.services.dashboard import _cumulative_series


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


def test_totals_accumulate_across_the_window(db, client_a):
    start = date.today() - timedelta(days=3)
    for offset in range(4):
        db.add(_traffic(client_a.id, start + timedelta(days=offset), 10))
    db.commit()

    rows = _cumulative_series(db, client_a.id, [], (start, date.today()))

    assert [row["sessions"] for row in rows] == [10, 20, 30, 40]


def test_a_quiet_day_flattens_rather_than_breaks_the_line(db, client_a):
    start = date.today() - timedelta(days=2)
    db.add(_traffic(client_a.id, start, 5))
    db.add(_traffic(client_a.id, date.today(), 5))
    db.commit()

    rows = _cumulative_series(db, client_a.id, [], (start, date.today()))

    assert [row["sessions"] for row in rows] == [5, 5, 10]


def test_the_window_starts_the_count_at_zero(db, client_a):
    """History before the window is not carried in — the period stands alone."""
    start = date.today() - timedelta(days=2)
    db.add(_traffic(client_a.id, start - timedelta(days=10), 999))
    db.add(_traffic(client_a.id, start, 4))
    db.commit()

    rows = _cumulative_series(db, client_a.id, [], (start, date.today()))

    assert rows[0]["sessions"] == 4
    assert rows[-1]["sessions"] == 4


def test_leads_accumulate_alongside_sessions(db, client_a):
    _define_lead(db, client_a.id)
    start = date.today() - timedelta(days=1)
    db.add(_traffic(client_a.id, start, 50))
    db.add(_lead_event(client_a.id, start, 2))
    db.add(_lead_event(client_a.id, date.today(), 3))
    db.commit()

    rows = _cumulative_series(db, client_a.id, ["generate_lead"], (start, date.today()))

    assert [row["leads"] for row in rows] == [2, 5]
    assert [row["sessions"] for row in rows] == [50, 50]


def test_one_point_per_day_in_the_window(db, client_a):
    start = date.today() - timedelta(days=10)
    db.add(_traffic(client_a.id, start, 5))
    db.commit()

    rows = _cumulative_series(db, client_a.id, [], (start, date.today()))

    assert len(rows) == 11
    assert rows[-1]["date"] == date.today().isoformat()


def test_no_window_means_no_series(db, client_a):
    assert _cumulative_series(db, client_a.id, [], None) == []


def test_no_facts_means_no_series(db, client_a):
    window = (date.today() - timedelta(days=5), date.today())
    assert _cumulative_series(db, client_a.id, [], window) == []
