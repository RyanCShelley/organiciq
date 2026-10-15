"""The engine suggests; a person decides.

SMA's October had 67 viable actions — five in slots, four named as skipped,
and 58 that existed nowhere a reader could see them. The engine ranks on what
it can measure, and it does not know the team is on a larger project this
month or that the capabilities pages are being rebuilt.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.decisions.slots import Prescription
from app.decisions.triage import Branch
from app.models.client import Client
from app.models.decision import EngineAction, MonthlyRecord
from app.services.monthly_run import action_uid
from tests.conftest import client_header

MONTH = "2026-10"


def _prescription(action_id: str = "V-1", url: str = "/a", term: str = "seo") -> Prescription:
    return Prescription(
        action_id=action_id,
        title=f"Do {action_id} on {url}",
        branch=Branch.VISIBILITY,
        target_url=url,
        term=term,
        score=1.0,
        effort_min=30,
        why="w",
        done_when="d",
        metric="Term position",
    )


def _record(db: Session, client: Client, uids: list[str]) -> MonthlyRecord:
    row = MonthlyRecord(
        client_id=client.id,
        month=MONTH,
        run_saved_at=datetime.now(timezone.utc),
        constraint_name="visibility",
        held_since=MONTH,
        confidence="medium",
        record={
            "actions": [],
            "incidents": [],
            "candidates": [
                {
                    "action_uid": uid,
                    "slot": 1 if index == 0 else None,
                    "id": "V-1",
                    "title": f"Action {index}",
                    "branch": "visibility",
                    "target_url": f"/p{index}",
                    "term": "seo",
                    "not_slotted_because": None if index == 0 else "Slots were taken.",
                }
                for index, uid in enumerate(uids)
            ],
        },
    )
    db.add(row)
    db.commit()
    return row


# ── The uid ─────────────────────────────────────────────────────────────────


def test_the_uid_names_the_action_not_the_slot():
    """The slot number was the key, so a re-run that reshuffled the order
    carried an assignment onto a different action — and anything outside the
    slots had no name at all, which is why none of them could be assigned."""
    first = action_uid("sma", MONTH, _prescription(url="/a"))
    again = action_uid("sma", MONTH, _prescription(url="/a"))
    other_page = action_uid("sma", MONTH, _prescription(url="/b"))
    other_action = action_uid("sma", MONTH, _prescription(action_id="V-4", url="/a"))

    assert first == again
    assert first != other_page
    assert first != other_action
    assert first.startswith("sma-2026-10-v-1-")


def test_a_different_month_is_a_different_uid():
    assert action_uid("sma", "2026-09", _prescription()) != action_uid(
        "sma", "2026-10", _prescription()
    )


# ── Choosing ────────────────────────────────────────────────────────────────


def test_an_action_the_engine_left_out_can_be_put_in(
    client, db: Session, client_a: Client, admin_user
):
    uids = ["u-slotted", "u-left-out"]
    _record(db, client_a, uids)
    headers = client_header(client_a.id, admin_user.email)

    response = client.post(
        f"/decisions/records/{MONTH}/slots/u-left-out/in-plan",
        headers=headers,
        json={"in_plan": True, "reason": "The team is rebuilding this page anyway"},
    )
    assert response.status_code == 200
    assert response.json()["in_plan"] is True
    assert "rebuilding" in response.json()["in_plan_reason"]


def test_an_action_the_engine_chose_can_be_taken_out(
    client, db: Session, client_a: Client, admin_user
):
    _record(db, client_a, ["u-slotted", "u-left-out"])
    response = client.post(
        f"/decisions/records/{MONTH}/slots/u-slotted/in-plan",
        headers=client_header(client_a.id, admin_user.email),
        json={"in_plan": False},
    )
    assert response.status_code == 200
    assert response.json()["in_plan"] is False


def test_clearing_the_choice_hands_it_back_to_the_engine(
    client, db: Session, client_a: Client, admin_user
):
    """Not frozen at whatever it last said: a re-run with better data should
    be free to change its mind about anything nobody has an opinion on."""
    _record(db, client_a, ["u-slotted"])
    headers = client_header(client_a.id, admin_user.email)
    client.post(
        f"/decisions/records/{MONTH}/slots/u-slotted/in-plan",
        headers=headers,
        json={"in_plan": False},
    )
    cleared = client.post(
        f"/decisions/records/{MONTH}/slots/u-slotted/in-plan",
        headers=headers,
        json={"in_plan": None},
    )
    assert cleared.json()["in_plan"] is None


def test_a_uid_outside_the_record_is_still_refused(
    client, db: Session, client_a: Client, admin_user
):
    _record(db, client_a, ["u-slotted"])
    response = client.post(
        f"/decisions/records/{MONTH}/slots/invented/in-plan",
        headers=client_header(client_a.id, admin_user.email),
        json={"in_plan": True},
    )
    assert response.status_code == 404


def test_a_chosen_action_can_be_assigned_like_any_other(
    client, db: Session, client_a: Client, admin_user
):
    """Once it is in the plan it is work, so it has to behave like work."""
    _record(db, client_a, ["u-slotted", "u-left-out"])
    headers = client_header(client_a.id, admin_user.email)
    client.post(
        f"/decisions/records/{MONTH}/slots/u-left-out/in-plan",
        headers=headers,
        json={"in_plan": True},
    )
    assigned = client.post(
        f"/decisions/records/{MONTH}/slots/u-left-out/assign",
        headers=headers,
        json={"assignee_email": admin_user.email, "due": None},
    )
    assert assigned.status_code == 200
    assert assigned.json()["status"] == "assigned"
    row = db.query(EngineAction).filter(EngineAction.uid == "u-left-out").one()
    assert row.in_plan is True and row.assignee_email == admin_user.email.lower()


def test_a_refresh_or_new_page_the_engine_left_out_can_be_put_in_and_assigned(
    client, db: Session, client_a: Client, admin_user
):
    """The retainer pools keep their candidates under their own keys; the
    override has to find them there too, not only among growth actions."""
    row = MonthlyRecord(
        client_id=client_a.id,
        month=MONTH,
        run_saved_at=datetime.now(timezone.utc),
        constraint_name="visibility",
        held_since=MONTH,
        confidence="medium",
        record={
            "actions": [],
            "incidents": [],
            "update_candidates": [
                {"action_uid": "u-refresh", "slot": None, "id": "U-1", "title": "Refresh",
                 "target_url": "/old", "not_slotted_because": "Slots were taken."}
            ],
            "content_candidates": [
                {"action_uid": "u-newpage", "slot": None, "id": "C-2", "title": "Write",
                 "target_url": "", "term": "heat pumps", "not_slotted_because": "Slots were taken."}
            ],
        },
    )
    db.add(row)
    db.commit()
    headers = client_header(client_a.id, admin_user.email)

    for uid in ("u-refresh", "u-newpage"):
        put = client.post(
            f"/decisions/records/{MONTH}/slots/{uid}/in-plan",
            headers=headers,
            json={"in_plan": True},
        )
        assert put.status_code == 200 and put.json()["in_plan"] is True

        back = client.post(
            f"/decisions/records/{MONTH}/slots/{uid}/in-plan",
            headers=headers,
            json={"in_plan": None},
        )
        assert back.json()["in_plan"] is None
