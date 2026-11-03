"""Confirming a prescription or suggestion as a task, planning against the allowance, sending to Teamwork."""

from __future__ import annotations

import pytest

from app.integrations import teamwork
from app.models.engine_task import EngineTask
from tests.conftest import client_header

BODY = {
    "month": "2026-10",
    "kind": "suggestion",
    "rule_id": "S-1",
    "search": "Spf 15 Mineral Sunscreen",
    "page": "https://shop.example/products/spf-15",
    "title": "Use the phrasing people actually search",
    "why": "The page already ranks for these longer searches.",
    "steps": ["“sunscreen spf 15”: 315 impressions at position 11.4", "Work the closest natural phrasing into the title."],
    "done_when": None,
    "metric": None,
    "effort_min": None,
    "evidence": ["To confirm: a person's judgment that the wording reads naturally."],
}


def h(client_a, admin_user):
    return client_header(client_a.id, admin_user.email)


def test_confirming_makes_a_task_and_records_who_said_yes(client, db, client_a, admin_user):
    res = client.post("/v2/engine/tasks", json=BODY, headers=h(client_a, admin_user))
    assert res.status_code == 200
    body = res.json()
    assert body["created"] is True
    task = body["task"]
    assert task["status"] == "confirmed" and task["kind"] == "suggestion"
    assert task["confirmed_by"] == admin_user.email
    assert task["search"] == "spf 15 mineral sunscreen"  # the same search, however it was typed
    assert len(task["steps"]) == 2


def test_confirming_the_same_thing_twice_is_one_task(client, db, client_a, admin_user):
    first = client.post("/v2/engine/tasks", json=BODY, headers=h(client_a, admin_user)).json()
    again = client.post("/v2/engine/tasks", json={**BODY, "search": "spf 15 mineral sunscreen"}, headers=h(client_a, admin_user)).json()
    assert again["created"] is False and again["task"]["id"] == first["task"]["id"]
    assert db.query(EngineTask).count() == 1


def test_the_plan_counts_pages_against_the_monthly_allowance(client, db, client_a, admin_user):
    for i in range(2):
        client.post("/v2/engine/tasks", json={**BODY, "rule_id": f"S-{i}", "page": f"https://shop.example/p{i}"}, headers=h(client_a, admin_user))
    plan = client.get("/v2/engine/tasks?month=2026-10", headers=h(client_a, admin_user)).json()
    assert len(plan["tasks"]) == 2
    assert plan["allowance"]["used"] == 2 and plan["allowance"]["monthly"] is not None
    assert plan["allowance"]["over"] is (2 > plan["allowance"]["monthly"])


def test_going_over_the_allowance_is_reported_not_blocked(client, db, client_a, admin_user, monkeypatch):
    from app.api.routers import v2_tasks

    monkeypatch.setattr(v2_tasks, "_allowance", lambda c, used: {"monthly": 1, "used": used, "over": used > 1})
    for i in range(3):
        res = client.post("/v2/engine/tasks", json={**BODY, "rule_id": f"S-{i}", "page": f"https://shop.example/p{i}"}, headers=h(client_a, admin_user))
        assert res.status_code == 200
    assert res.json()["allowance"] == {"monthly": 1, "used": 3, "over": True}


def test_dropping_a_task_stops_it_counting_and_confirming_again_brings_it_back(client, db, client_a, admin_user):
    tid = client.post("/v2/engine/tasks", json=BODY, headers=h(client_a, admin_user)).json()["task"]["id"]
    client.patch(f"/v2/engine/tasks/{tid}", json={"status": "dropped"}, headers=h(client_a, admin_user))
    assert client.get("/v2/engine/tasks?month=2026-10", headers=h(client_a, admin_user)).json()["allowance"]["used"] == 0
    back = client.post("/v2/engine/tasks", json=BODY, headers=h(client_a, admin_user)).json()
    assert back["created"] is True and back["task"]["status"] == "confirmed" and back["allowance"]["used"] == 1


def test_assignee_due_date_and_shipped_can_be_set(client, db, client_a, admin_user):
    tid = client.post("/v2/engine/tasks", json=BODY, headers=h(client_a, admin_user)).json()["task"]["id"]
    out = client.patch(
        f"/v2/engine/tasks/{tid}", json={"assignee_email": "Dana@Example.com", "due": "2026-10-20", "status": "shipped"}, headers=h(client_a, admin_user)
    ).json()
    assert out["assignee_email"] == "dana@example.com" and out["due"] == "2026-10-20"
    assert out["status"] == "shipped" and out["shipped_at"]
    cleared = client.patch(f"/v2/engine/tasks/{tid}", json={"clear_assignee": True, "clear_due": True}, headers=h(client_a, admin_user)).json()
    assert cleared["assignee_email"] is None and cleared["due"] is None


def test_tasks_stay_with_their_client(client, db, client_a, client_b, admin_user):
    tid = client.post("/v2/engine/tasks", json=BODY, headers=h(client_a, admin_user)).json()["task"]["id"]
    other = client_header(client_b.id, admin_user.email)
    assert client.get("/v2/engine/tasks?month=2026-10", headers=other).json()["tasks"] == []
    assert client.patch(f"/v2/engine/tasks/{tid}", json={"status": "shipped"}, headers=other).status_code == 404
    assert client.post(f"/v2/engine/tasks/{tid}/send", headers=other).status_code == 404


def test_a_bad_month_is_refused(client, db, client_a, admin_user):
    assert client.get("/v2/engine/tasks?month=2026-13", headers=h(client_a, admin_user)).status_code == 400
    assert client.post("/v2/engine/tasks", json={**BODY, "month": "October"}, headers=h(client_a, admin_user)).status_code == 400


@pytest.fixture()
def tw(monkeypatch):
    sent = {}
    monkeypatch.setattr(teamwork, "configured", lambda: True)
    monkeypatch.setattr(teamwork, "list_people", lambda *a, **k: [])
    monkeypatch.setattr(teamwork, "person_id_for", lambda email, people: "77" if email == "dana@example.com" else None)

    def create(**kwargs):
        sent.update(kwargs)
        sent["calls"] = sent.get("calls", 0) + 1
        return {"id": 9001, "url": "https://sma.teamwork.com/app/tasks/9001"}

    monkeypatch.setattr(teamwork, "create_task", create)
    return sent


def test_sending_creates_one_teamwork_task_and_a_second_press_does_not_make_a_twin(client, db, client_a, admin_user, tw):
    client_a.teamwork_tasklist_id = "555"
    db.commit()
    tid = client.post("/v2/engine/tasks", json=BODY, headers=h(client_a, admin_user)).json()["task"]["id"]
    client.patch(f"/v2/engine/tasks/{tid}", json={"assignee_email": "dana@example.com", "due": "2026-10-20"}, headers=h(client_a, admin_user))

    first = client.post(f"/v2/engine/tasks/{tid}/send", headers=h(client_a, admin_user))
    second = client.post(f"/v2/engine/tasks/{tid}/send", headers=h(client_a, admin_user))
    assert first.status_code == 200 and first.json()["status"] == "sent"
    assert first.json()["teamwork_task_url"].endswith("/9001") and second.json()["teamwork_task_id"] == "9001"
    assert tw["calls"] == 1
    assert tw["tasklist_id"] == "555" and tw["assignee_teamwork_id"] == "77" and tw["due"] == "2026-10-20"
    assert "Suggested by the Decision engine" in tw["description"]
    assert "1. “sunscreen spf 15”: 315 impressions" in tw["description"] and admin_user.email in tw["description"]


def test_a_prescription_says_a_rule_prescribed_it(client, db, client_a, admin_user, tw):
    client_a.teamwork_tasklist_id = "555"
    db.commit()
    tid = client.post("/v2/engine/tasks", json={**BODY, "kind": "prescription", "rule_id": "V-7"}, headers=h(client_a, admin_user)).json()["task"]["id"]
    client.post(f"/v2/engine/tasks/{tid}/send", headers=h(client_a, admin_user))
    assert "Recommended by the Decision engine from a check of the page and its data." in tw["description"]


def test_an_unknown_assignee_still_sends_unassigned(client, db, client_a, admin_user, tw):
    client_a.teamwork_tasklist_id = "555"
    db.commit()
    tid = client.post("/v2/engine/tasks", json=BODY, headers=h(client_a, admin_user)).json()["task"]["id"]
    client.patch(f"/v2/engine/tasks/{tid}", json={"assignee_email": "nobody@example.com"}, headers=h(client_a, admin_user))
    assert client.post(f"/v2/engine/tasks/{tid}/send", headers=h(client_a, admin_user)).status_code == 200
    assert tw["assignee_teamwork_id"] is None


def test_sending_says_what_is_missing(client, db, client_a, admin_user, monkeypatch):
    tid = client.post("/v2/engine/tasks", json=BODY, headers=h(client_a, admin_user)).json()["task"]["id"]
    monkeypatch.setattr(teamwork, "configured", lambda: False)
    res = client.post(f"/v2/engine/tasks/{tid}/send", headers=h(client_a, admin_user))
    assert res.status_code == 400 and "not set up on this install" in res.json()["detail"]

    monkeypatch.setattr(teamwork, "configured", lambda: True)
    client_a.teamwork_tasklist_id = None
    db.commit()
    res = client.post(f"/v2/engine/tasks/{tid}/send", headers=h(client_a, admin_user))
    assert res.status_code == 400 and "no Teamwork tasklist" in res.json()["detail"]


def test_a_teamwork_failure_is_reported_and_leaves_the_task_unsent(client, db, client_a, admin_user, monkeypatch):
    client_a.teamwork_tasklist_id = "555"
    db.commit()
    tid = client.post("/v2/engine/tasks", json=BODY, headers=h(client_a, admin_user)).json()["task"]["id"]
    monkeypatch.setattr(teamwork, "configured", lambda: True)

    def boom(**kwargs):
        raise teamwork.TeamworkError("Teamwork rejected the credentials.")

    monkeypatch.setattr(teamwork, "create_task", boom)
    res = client.post(f"/v2/engine/tasks/{tid}/send", headers=h(client_a, admin_user))
    assert res.status_code == 502 and "rejected the credentials" in res.json()["detail"]
    assert db.query(EngineTask).one().teamwork_task_id is None


def test_the_text_version_works_without_teamwork(client, db, client_a, admin_user):
    tid = client.post("/v2/engine/tasks", json=BODY, headers=h(client_a, admin_user)).json()["task"]["id"]
    out = client.get(f"/v2/engine/tasks/{tid}/text", headers=h(client_a, admin_user)).json()
    assert out["name"].startswith("Use the phrasing") and "Checklist" in out["text"]


def test_the_assignee_picker_lists_everyone_in_teamwork(client, db, client_a, admin_user, monkeypatch):
    from app.api.routers import v2_tasks

    v2_tasks._PEOPLE_CACHE.update(at=0.0, rows=[])
    monkeypatch.setattr(teamwork, "configured", lambda: True)
    monkeypatch.setattr(teamwork, "list_people", lambda *a, **k: [teamwork.Person(id="2", email="zed@x.co", name="Zed"), teamwork.Person(id="1", email="amy@x.co", name="Amy")])
    res = client.get("/v2/engine/tasks/people", headers=h(client_a, admin_user))
    assert res.status_code == 200 and [p["name"] for p in res.json()] == ["Amy", "Zed"]
    v2_tasks._PEOPLE_CACHE.update(at=0.0, rows=[])
