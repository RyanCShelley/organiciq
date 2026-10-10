"""Assign, skip and send — the writes that turn a saved plan into work.

Guard teeth, in order of what would hurt most:
  * a uid the record does not contain is refused, so the endpoint is not an
    open write to a table keyed by a caller-chosen string;
  * a skip without a reason is refused;
  * clearing the assignee returns the slot to `planned`, rather than leaving
    it `assigned` with nobody on it;
  * `stale` fires when a re-run puts a different action in the slot, which is
    the hazard the Re-run button on the client page introduces.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.decision import MonthlyRecord
from app.models.user import User
from tests.conftest import client_header

MONTH = "2026-10"


def _record(client: Client, *, action_id: str = "V-1", url: str = "/a") -> dict:
    return {
        "client": client.slug,
        "month": MONTH,
        "actions": [
            {
                "action_uid": f"{client.slug}-{MONTH}-s1",
                "slot": 1,
                "id": action_id,
                "title": "Put the term in the title",
                "branch": "visibility",
                "spillover": False,
                "target_url": url,
                "term": "seo agency",
                "score": 1.0,
                "effort_min": 30,
                "why": "The page never says it.",
                "done_when": "It says it.",
                "metric": "Term position",
                "check_on": "2026-11-07",
            }
        ],
        "incidents": [],
    }


@pytest.fixture
def saved_run(db: Session, client_a: Client) -> MonthlyRecord:
    row = MonthlyRecord(
        client_id=client_a.id,
        month=MONTH,
        run_saved_at=datetime.now(timezone.utc),
        constraint_name="visibility",
        held_since=MONTH,
        confidence="medium",
        record=_record(client_a),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _uid(client_a: Client) -> str:
    return f"{client_a.slug}-{MONTH}-s1"


def test_uid_outside_the_record_is_refused(client, client_a, admin_user, saved_run):
    response = client.post(
        f"/decisions/records/{MONTH}/slots/not-a-slot/assign",
        headers=client_header(client_a.id, admin_user.email),
        json={"assignee_user_id": None, "due": None},
    )
    assert response.status_code == 404
    assert "not a slot" in response.json()["detail"]


def test_assign_then_clear_returns_the_slot_to_planned(
    client, client_a, admin_user, saved_run
):
    headers = client_header(client_a.id, admin_user.email)
    uid = _uid(client_a)

    assigned = client.post(
        f"/decisions/records/{MONTH}/slots/{uid}/assign",
        headers=headers,
        json={"assignee_user_id": str(admin_user.id), "due": "2026-10-20"},
    )
    assert assigned.status_code == 200
    body = assigned.json()
    assert body["status"] == "assigned"
    assert body["assignee_user_id"] == str(admin_user.id)
    assert body["due"] == "2026-10-20"

    cleared = client.post(
        f"/decisions/records/{MONTH}/slots/{uid}/assign",
        headers=headers,
        json={"assignee_user_id": None, "due": None},
    )
    assert cleared.status_code == 200
    # Not "assigned to nobody", which reads as handled and is not.
    assert cleared.json()["status"] == "planned"


def test_a_skip_needs_a_reason(client, client_a, admin_user, saved_run):
    headers = client_header(client_a.id, admin_user.email)
    uid = _uid(client_a)

    refused = client.post(
        f"/decisions/records/{MONTH}/slots/{uid}/skip",
        headers=headers,
        json={"reason": "   "},
    )
    assert refused.status_code == 422

    skipped = client.post(
        f"/decisions/records/{MONTH}/slots/{uid}/skip",
        headers=headers,
        json={"reason": "Client is mid-migration on this page."},
    )
    assert skipped.status_code == 200
    assert skipped.json()["status"] == "skipped"
    assert skipped.json()["skip_reason"] == "Client is mid-migration on this page."

    undone = client.post(
        f"/decisions/records/{MONTH}/slots/{uid}/skip",
        headers=headers,
        json={"undo": True},
    )
    assert undone.status_code == 200
    assert undone.json()["status"] == "planned"
    assert undone.json()["skip_reason"] is None


def test_a_rerun_that_changes_the_slot_marks_the_assignment_stale(
    client, db, client_a, admin_user, saved_run
):
    headers = client_header(client_a.id, admin_user.email)
    uid = _uid(client_a)

    client.post(
        f"/decisions/records/{MONTH}/slots/{uid}/assign",
        headers=headers,
        json={"assignee_user_id": str(admin_user.id), "due": None},
    )

    fresh = client.get(f"/decisions/records/{MONTH}/workflow", headers=headers)
    assert fresh.json()["actions"][0]["stale"] is False

    # A re-run puts a different action in slot 1. The uid is keyed on the slot
    # number, so the assignment survives — and must say that it no longer
    # points at what somebody agreed to.
    saved_run.record = _record(client_a, action_id="V-4", url="/b")
    db.add(saved_run)
    db.commit()

    after = client.get(f"/decisions/records/{MONTH}/workflow", headers=headers)
    row = after.json()["actions"][0]
    assert row["stale"] is True
    assert row["assignee_user_id"] == str(admin_user.id)


def test_send_without_teamwork_configured_says_so(
    client, client_a, admin_user, saved_run
):
    headers = client_header(client_a.id, admin_user.email)
    response = client.post(
        f"/decisions/records/{MONTH}/slots/{_uid(client_a)}/send", headers=headers
    )
    assert response.status_code == 502
    assert "Teamwork" in response.json()["detail"]


def test_workflow_reports_teamwork_not_ready_without_a_tasklist(
    client, client_a, admin_user, saved_run
):
    response = client.get(
        f"/decisions/records/{MONTH}/workflow",
        headers=client_header(client_a.id, admin_user.email),
    )
    assert response.status_code == 200
    assert response.json()["teamwork_ready"] is False


def test_assignees_include_admins_and_assigned_team(
    client, client_a, admin_user, team_user
):
    response = client.get(
        "/decisions/assignees",
        headers=client_header(client_a.id, admin_user.email),
    )
    assert response.status_code == 200
    emails = {row["email"] for row in response.json()}
    assert admin_user.email in emails
    assert team_user.email in emails
