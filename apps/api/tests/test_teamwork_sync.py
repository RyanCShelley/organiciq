"""A subtask completed in Teamwork marks its part done; the page is then checked, and a tick is not taken for proof."""

from __future__ import annotations

from app.integrations import teamwork
from app.models.annotation import Annotation
from app.models.engine_task import EngineTask
from app.services import page_diagnostic as pd
from app.services import task_verify, teamwork_sync
from tests.conftest import client_header
from tests.test_task_verify import URL, confirm, crawl, page, reload

PARTS = [{"id": "S-5", "name": "Reread the title and description"}, {"id": "V-4", "name": "Add internal links"}]


def sent(client, db, client_a, admin_user, parts=PARTS, **over):
    crawl(db, client_a)
    h, task = confirm(client, client_a, admin_user, parts, **over)
    row = db.get(EngineTask, task["id"])
    row.teamwork_task_id = "900"
    row.teamwork_subtasks = {f"part-{i + 1}": str(1000 + i) for i in range(len(parts))}
    db.commit()
    return h, task


def tw(monkeypatch, done: dict[str, tuple[str, str] | None]):
    monkeypatch.setattr(teamwork, "configured", lambda: True)
    monkeypatch.setattr(teamwork, "task_status", lambda tid, **_: teamwork.TaskStatus(True, done[tid][1], done[tid][0]) if done.get(tid) else teamwork.TaskStatus(False, None, None))


def test_the_status_is_read_from_teamwork_v3():
    body = {"task": {"id": 1, "status": "completed", "completedAt": "2026-11-09T15:00:00Z", "completedBy": 7}, "included": {"users": {"7": {"firstName": "Beth", "lastName": "Smith"}}}}
    s = teamwork.parse_task_status(body)
    assert s.done and s.completed_by == "Beth Smith" and s.completed_at.startswith("2026-11-09")
    assert teamwork.parse_task_status({"task": {"status": "new"}}).done is False
    assert teamwork.parse_task_status({"task": {"status": "reopened", "completedAt": "2026-11-09T15:00:00Z"}}).done is False


def test_a_completed_subtask_marks_its_part_done_with_who_and_when(client, db, client_a, admin_user, monkeypatch):
    sent(client, db, client_a, admin_user)
    t = db.query(EngineTask).one()
    tw(monkeypatch, {"1000": ("Beth Smith", "2026-11-09T15:00:00Z"), "1001": None})
    out = teamwork_sync.sync_task(db, client_a, t)
    assert out["marked"] == 1
    t = reload(db, t.id)
    part = t.parts[0]
    assert part["status"] == "done" and part["done_by"] == "Beth Smith in Teamwork" and part["done_how"] == "The Teamwork subtask was completed by Beth Smith on 2026-11-09."
    assert t.parts[1]["status"] == "open" and db.query(Annotation).count() == 1


def test_a_tick_in_teamwork_is_not_proof_the_page_shows_it(client, db, client_a, admin_user, monkeypatch):
    h, task = sent(client, db, client_a, admin_user)
    t = db.query(EngineTask).one()
    tw(monkeypatch, {"1000": ("Beth Smith", "2026-11-09T15:00:00Z"), "1001": None})
    teamwork_sync.sync_task(db, client_a, t)
    task_verify.check_task(db, client_a, reload(db, t.id), fetch=page())  # the page still has the old title
    part = reload(db, t.id).parts[0]
    assert part["status"] == "done" and not part.get("verified_how") and part["last_check"]["result"] == "not_live"
    task_verify.check_task(db, client_a, reload(db, t.id), fetch=page(title="A brand new title"))
    part = reload(db, t.id).parts[0]
    assert part["verified_how"] and part["done_by"] == "Beth Smith in Teamwork"


def test_the_action_ships_when_every_subtask_is_completed(client, db, client_a, admin_user, monkeypatch):
    sent(client, db, client_a, admin_user)
    t = db.query(EngineTask).one()
    tw(monkeypatch, {"1000": ("Beth", "2026-11-09T15:00:00Z"), "1001": ("Beth", "2026-11-09T16:00:00Z")})
    assert teamwork_sync.sync_task(db, client_a, t)["marked"] == 2
    assert reload(db, t.id).status == "shipped"


def test_a_part_a_person_took_back_is_left_alone_unless_checked_by_hand(client, db, client_a, admin_user, monkeypatch):
    h, task = sent(client, db, client_a, admin_user)
    client.patch(f"/v2/engine/tasks/{task['id']}/parts/0", json={"done": True}, headers=h)
    client.patch(f"/v2/engine/tasks/{task['id']}/parts/0", json={"done": False}, headers=h)
    tw(monkeypatch, {"1000": ("Beth", "2026-11-09T15:00:00Z"), "1001": None})
    t = reload(db, task["id"])
    assert teamwork_sync.sync_task(db, client_a, t)["marked"] == 0
    assert teamwork_sync.sync_task(db, client_a, reload(db, task["id"]), force=True)["marked"] == 1


def test_a_teamwork_error_is_reported_and_marks_nothing(client, db, client_a, admin_user, monkeypatch):
    sent(client, db, client_a, admin_user)
    t = db.query(EngineTask).one()
    monkeypatch.setattr(teamwork, "configured", lambda: True)

    def down(tid, **_):
        raise teamwork.TeamworkError("Teamwork did not answer: timeout")

    monkeypatch.setattr(teamwork, "task_status", down)
    out = teamwork_sync.sync_task(db, client_a, t)
    assert out["marked"] == 0 and "did not answer" in out["error"]


def test_a_single_suggestion_is_done_only_when_all_its_subtasks_are(client, db, client_a, admin_user, monkeypatch):
    crawl(db, client_a)
    h = client_header(client_a.id, admin_user.email)
    task = client.post("/v2/engine/tasks", json={"month": "2026-11", "kind": "prescription", "rule_id": "S-5", "search": "q", "page": URL, "title": "Rewrite the title", "steps": ["Write it.", "Publish it."], "evidence": []}, headers=h).json()["task"]
    row = db.get(EngineTask, task["id"])
    row.teamwork_task_id, row.teamwork_subtasks = "900", {"step-1": "2000", "step-2": "2001"}
    db.commit()
    tw(monkeypatch, {"2000": ("Beth", "2026-11-09T15:00:00Z"), "2001": None})
    assert teamwork_sync.sync_task(db, client_a, db.get(EngineTask, task["id"]))["marked"] == 0
    tw(monkeypatch, {"2000": ("Beth", "2026-11-09T15:00:00Z"), "2001": ("Beth", "2026-11-09T16:00:00Z")})
    assert teamwork_sync.sync_task(db, client_a, reload(db, task["id"]))["marked"] == 1


def test_the_check_route_asks_teamwork_then_the_page(client, db, client_a, admin_user, monkeypatch):
    h, task = sent(client, db, client_a, admin_user)
    tw(monkeypatch, {"1000": ("Beth Smith", "2026-11-09T15:00:00Z"), "1001": None})
    monkeypatch.setattr(pd, "_fetch", page(title="A brand new title"))
    res = client.post(f"/v2/engine/tasks/{task['id']}/check", headers=h).json()
    assert res["check"]["teamwork"]["marked"] == 1 and res["task"]["parts"][0]["status"] == "done" and res["task"]["parts"][0]["verified_how"] and res["task"]["parts"][0]["done_how"]
