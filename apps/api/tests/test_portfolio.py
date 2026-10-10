"""The portfolio: every client's month, counted from the saved runs.

Two things it must not do. It must not recompute anything — a row here that
disagreed with the client's own page would make both unusable — and it must
not count clients the reader cannot open, which is both a leak and a total
nobody can check.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.decision import MonthlyRecord
from app.services.portfolio import portfolio
from tests.conftest import client_header

MONTH = "2026-10"


def _save(
    db: Session,
    client: Client,
    *,
    constraint: str = "visibility",
    month: str = MONTH,
    slots: int = 5,
    actions: int = 3,
    spillover: int = 0,
    leads: str = "fail",
    gaps: list[str] | None = None,
):
    db.add(
        MonthlyRecord(
            client_id=client.id,
            month=month,
            run_saved_at=datetime.now(timezone.utc),
            constraint_name=constraint,
            held_since=month,
            confidence="medium",
            record={
                "plan": "enterprise",
                "action_slots": slots,
                "actions": [
                    {"action_uid": f"a{i}", "spillover": i < spillover}
                    for i in range(actions)
                ],
                "empty_slots": [{"slot": n} for n in range(slots - actions)],
                "branches": [
                    {"branch": "visibility", "status": "fail"},
                    {"branch": "traffic", "status": "pass"},
                    {"branch": "leads", "status": leads},
                ],
                "data_gaps": [{"input": g} for g in (gaps or [])],
            },
        )
    )
    db.commit()


def test_totals_count_the_saved_runs(db: Session, client_a: Client, client_b: Client):
    _save(db, client_a, slots=5, actions=3, spillover=1)
    _save(db, client_b, constraint="traffic", slots=3, actions=3)

    data = portfolio(db)
    assert data["totals"]["clients"] == 2
    assert data["totals"]["capacity"] == 8
    assert data["totals"]["filled"] == 6
    assert data["totals"]["empty"] == 2
    assert data["totals"]["spillover"] == 1
    assert data["totals"]["on_visibility"] == 1


def test_a_withheld_client_is_not_counted_as_unused_capacity(
    db: Session, client_a: Client, client_b: Client
):
    _save(db, client_a, slots=5, actions=5)
    # Withheld: there is no plan this month, so its slots are not capacity
    # that went unused. Counting them makes the fill rate a statement about
    # data outages rather than about the work.
    _save(db, client_b, constraint="withheld", slots=5, actions=0)

    data = portfolio(db)
    assert data["totals"]["withheld"] == 1
    assert data["totals"]["run"] == 1
    assert data["totals"]["capacity"] == 5
    assert data["totals"]["filled"] == 5
    assert data["totals"]["empty"] == 0


def test_clients_are_ordered_down_the_ladder(
    db: Session, client_a: Client, client_b: Client
):
    _save(db, client_a, constraint="withheld")
    _save(db, client_b, constraint="visibility")
    rows = portfolio(db)["clients"]
    assert [r["constraint"] for r in rows] == ["visibility", "withheld"]


def test_only_the_newest_run_per_client_is_shown(db: Session, client_a: Client):
    _save(db, client_a, month="2026-09", constraint="traffic")
    _save(db, client_a, month="2026-10", constraint="visibility")

    data = portfolio(db)
    assert len(data["clients"]) == 1
    assert data["clients"][0]["constraint"] == "visibility"
    assert data["month"] == "2026-10"


def test_asking_for_a_month_pins_it(db: Session, client_a: Client):
    _save(db, client_a, month="2026-09", constraint="traffic")
    _save(db, client_a, month="2026-10", constraint="visibility")
    data = portfolio(db, month="2026-09")
    assert data["clients"][0]["constraint"] == "traffic"


def test_gaps_are_ranked_by_how_many_clients_they_cost(
    db: Session, client_a: Client, client_b: Client
):
    _save(db, client_a, gaps=["serp features", "scroll depth"])
    _save(db, client_b, gaps=["serp features"])
    assert portfolio(db)["data_gaps"][0] == {"input": "serp features", "clients": 2}


def test_scoping_narrows_the_totals_not_just_the_rows(
    db: Session, client_a: Client, client_b: Client
):
    _save(db, client_a, slots=5, actions=5)
    _save(db, client_b, slots=3, actions=3)

    data = portfolio(db, allowed_client_ids={str(client_a.id)})
    assert [r["client_id"] for r in data["clients"]] == [str(client_a.id)]
    # Not 8: a total describing a client the reader cannot open is a number
    # nobody can check.
    assert data["totals"]["capacity"] == 5
    assert data["totals"]["clients"] == 1


def test_no_access_means_no_rows_and_zero_totals(db: Session, client_a: Client):
    _save(db, client_a)
    data = portfolio(db, allowed_client_ids=set())
    assert data["clients"] == []
    assert data["totals"]["clients"] == 0


def test_the_endpoint_scopes_to_what_the_caller_can_see(
    client, db: Session, client_a: Client, client_b: Client, admin_user, team_user
):
    _save(db, client_a, slots=5, actions=5)
    _save(db, client_b, slots=3, actions=3)

    as_admin = client.get("/decisions/portfolio", headers=client_header(client_a.id, admin_user.email))
    assert as_admin.status_code == 200
    assert as_admin.json()["totals"]["clients"] == 2

    # team_user is assigned client_a only.
    as_team = client.get("/decisions/portfolio", headers=client_header(client_a.id, team_user.email))
    assert as_team.status_code == 200
    assert as_team.json()["totals"]["clients"] == 1
    assert as_team.json()["totals"]["capacity"] == 5
