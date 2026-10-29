"""The monthly engine run: last month, on the fifth.

Search Console lags about three days, so by the fifth the month before has
closed out. Until this existed, connecting a client filled its warehouse and
left its Decision Engine page empty until somebody visited and pressed Run —
and nothing re-ran on the first of the month either.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.config import OrganicChannel
from app.models.decision import MonthlyRecord
from app.models.ga4 import FactGa4Traffic
from app.models.gsc import FactGscPage
from app.services.monthly_run import maybe_run_month

NOV_5 = date(2026, 11, 5)


@pytest.fixture(autouse=True)
def _open_the_gate(monkeypatch):
    """Hour and day gates off, so each test pins one thing."""
    from app.core import settings as settings_module

    settings = settings_module.get_settings()
    monkeypatch.setattr(settings, "monthly_run_enabled", True, raising=False)
    monkeypatch.setattr(settings, "monthly_run_hour_utc", 0, raising=False)
    monkeypatch.setattr(settings, "monthly_run_day", 5, raising=False)
    return settings


def _with_data(db: Session, client: Client, through: date = date(2026, 10, 31)):
    db.add(
        FactGa4Traffic(
            client_id=client.id,
            date=through,
            raw_url="https://x.test/",
            normalized_url="https://x.test/",
            channel=OrganicChannel.ORGANIC_SEARCH,
            sessions=10,
        )
    )
    db.add(
        FactGscPage(
            client_id=client.id,
            date=through,
            raw_url="https://x.test/",
            normalized_url="https://x.test/",
            impressions=100,
            clicks=5,
        )
    )
    db.commit()


def _records(db: Session, client: Client) -> list[str]:
    return [
        r.month
        for r in db.query(MonthlyRecord).filter(MonthlyRecord.client_id == client.id)
    ]


def test_it_runs_the_month_before_not_the_one_we_are_in(
    db: Session, client_a: Client
):
    _with_data(db, client_a)
    assert maybe_run_month(db, today=NOV_5) is True
    # November is three days old on the fifth; October is the month to judge.
    assert _records(db, client_a) == ["2026-10"]


def test_it_waits_for_the_fifth(db: Session, client_a: Client):
    _with_data(db, client_a)
    # Search Console lags about three days, so the first is too early.
    assert maybe_run_month(db, today=date(2026, 11, 4)) is False
    assert _records(db, client_a) == []


def test_it_runs_once_a_month(db: Session, client_a: Client):
    _with_data(db, client_a)
    assert maybe_run_month(db, today=NOV_5) is True
    assert maybe_run_month(db, today=NOV_5 + timedelta(days=1)) is False
    assert len(_records(db, client_a)) == 1


def test_the_next_month_runs_again(db: Session, client_a: Client):
    _with_data(db, client_a)
    maybe_run_month(db, today=NOV_5)
    _with_data(db, client_a, through=date(2026, 11, 30))
    assert maybe_run_month(db, today=date(2026, 12, 5)) is True
    assert sorted(_records(db, client_a)) == ["2026-10", "2026-11"]


def test_it_replaces_a_run_made_mid_month(db: Session, client_a: Client):
    """A partial run is exactly what the complete one supersedes.

    The engine reads the same facts every time, so there is no answer
    somebody preferred that needs protecting — and assignments survive,
    because they are keyed on the slot uid.
    """
    _with_data(db, client_a)
    db.add(
        MonthlyRecord(
            client_id=client_a.id,
            month="2026-10",
            run_saved_at=datetime(2026, 10, 12, tzinfo=timezone.utc),
            data_through=date(2026, 10, 6),
            constraint_name="visibility",
            held_since="2026-10",
            confidence="low",
            record={"actions": [], "incidents": []},
        )
    )
    db.commit()

    assert maybe_run_month(db, today=NOV_5) is True
    rows = db.query(MonthlyRecord).filter(MonthlyRecord.client_id == client_a.id).all()
    assert len(rows) == 1
    # Replaced, not added beside.
    assert rows[0].data_through != date(2026, 10, 6)


def test_a_client_with_no_data_at_all_is_skipped(db: Session, client_a: Client):
    # Running it would produce noise rather than an answer. A client whose
    # sync has merely gone stale is not skipped — it gets a Withheld record
    # saying so, which is a more useful thing to open than an empty page.
    assert maybe_run_month(db, today=NOV_5) is True
    assert _records(db, client_a) == []


def test_disabling_it_stops_it(db: Session, client_a: Client, _open_the_gate, monkeypatch):
    _with_data(db, client_a)
    monkeypatch.setattr(_open_the_gate, "monthly_run_enabled", False, raising=False)
    assert maybe_run_month(db, today=NOV_5) is False
    assert _records(db, client_a) == []


def test_one_bad_client_does_not_stop_the_rest(
    db: Session, client_a: Client, client_b: Client, monkeypatch
):
    _with_data(db, client_a)
    _with_data(db, client_b)

    import app.services.monthly_run as mr

    original = mr.build_record
    seen: list[str] = []

    def explode(db_, client, **kw):
        seen.append(client.slug)
        if len(seen) == 1:
            raise RuntimeError("one bad client")
        return original(db_, client, **kw)

    monkeypatch.setattr(mr, "build_record", explode)
    assert maybe_run_month(db, today=NOV_5) is True
    # The second client still got its run.
    assert len(seen) == 2


def test_failed_client_retries_without_repeating_successful_client(db,client_a,client_b,monkeypatch):
    from app.services import monthly_run
    _with_data(db,client_a);_with_data(db,client_b)
    calls=[]
    def run(db,c,**kw):
        calls.append(c.slug)
        if c.id==client_b.id and calls.count(c.slug)==1:
            raise RuntimeError('temporary source failure')
    monkeypatch.setattr(monthly_run,'save_record',run)
    assert maybe_run_month(db,today=NOV_5)
    assert maybe_run_month(db,today=NOV_5)
    assert calls.count(client_a.slug)==1
    assert calls.count(client_b.slug)==2
    assert maybe_run_month(db,today=NOV_5) is False
