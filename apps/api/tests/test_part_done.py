"""Done per part: the annotation, the shipping, the undo."""

from __future__ import annotations

from app.models.annotation import Annotation, AnnotationType
from app.models.engine_task import EngineTask
from tests.conftest import client_header

GA = {
    "month": "2026-10", "kind": "growth_action", "rule_id": "GA", "search": "spf 15", "page": "https://shop.example/products/spf-15",
    "title": "Grow spf 15", "why": "w", "steps": ["# 1. Reread the title and description", "Do this.", "# 2. Add internal links", "Do that."], "evidence": [],
    "parts": [{"id": "S-5", "name": "Reread the title and description"}, {"id": "V-4", "name": "Add internal links"}],
}


def make(client, client_a, admin_user, **over):
    h = client_header(client_a.id, admin_user.email)
    return h, client.post("/v2/engine/tasks", json={**GA, **over}, headers=h).json()["task"]


def test_a_part_done_writes_its_annotation_and_undone_removes_it(client, db, client_a, admin_user):
    h, task = make(client, client_a, admin_user)
    res = client.patch(f"/v2/engine/tasks/{task['id']}/parts/0", json={"done": True}, headers=h).json()
    assert [p["status"] for p in res["parts"]] == ["done", "open"] and res["parts"][0]["done_by"] == admin_user.email and res["status"] == "confirmed"
    row = db.query(Annotation).one()
    assert row.engine_uid == f"task:{task['id']}:0" and row.annotation_type == AnnotationType.GROWTH_ACTION and row.growth_action.value == "serp_ctr"
    assert row.page_url == GA["page"] and "Reread the title" in row.description and (row.measurement_end_date - row.measurement_start_date).days == 28
    client.patch(f"/v2/engine/tasks/{task['id']}/parts/0", json={"done": False}, headers=h)
    assert db.query(Annotation).count() == 0


def test_marking_the_same_part_twice_is_one_annotation(client, db, client_a, admin_user):
    h, task = make(client, client_a, admin_user)
    for _ in range(2):
        client.patch(f"/v2/engine/tasks/{task['id']}/parts/1", json={"done": True}, headers=h)
    assert db.query(Annotation).count() == 1 and db.query(Annotation).one().growth_action.value == "internal_linking"


def test_the_action_ships_itself_when_every_part_is_done_and_reopens_when_one_is_not(client, db, client_a, admin_user):
    h, task = make(client, client_a, admin_user)
    client.patch(f"/v2/engine/tasks/{task['id']}/parts/0", json={"done": True}, headers=h)
    last = client.patch(f"/v2/engine/tasks/{task['id']}/parts/1", json={"done": True}, headers=h).json()
    assert last["status"] == "shipped" and last["shipped_at"]
    back = client.patch(f"/v2/engine/tasks/{task['id']}/parts/1", json={"done": False}, headers=h).json()
    assert back["status"] == "confirmed" and back["shipped_at"] is None and db.query(Annotation).count() == 1


def test_marking_the_whole_action_shipped_marks_every_part_and_taking_it_back_reopens_them(client, db, client_a, admin_user):
    h, task = make(client, client_a, admin_user)
    shipped = client.patch(f"/v2/engine/tasks/{task['id']}", json={"status": "shipped"}, headers=h).json()
    assert [p["status"] for p in shipped["parts"]] == ["done", "done"] and db.query(Annotation).count() == 2
    client.patch(f"/v2/engine/tasks/{task['id']}", json={"status": "confirmed"}, headers=h)
    assert db.query(Annotation).count() == 0


def test_a_single_suggestion_shipped_is_one_annotation(client, db, client_a, admin_user):
    h = client_header(client_a.id, admin_user.email)
    task = client.post("/v2/engine/tasks", json={"month": "2026-10", "kind": "prescription", "rule_id": "V-7", "search": "q", "page": "https://shop.example/a", "title": "Mark up the FAQ", "steps": ["Add FAQPage."], "evidence": []}, headers=h).json()["task"]
    client.patch(f"/v2/engine/tasks/{task['id']}", json={"status": "shipped"}, headers=h)
    row = db.query(Annotation).one()
    assert row.growth_action.value == "structured_data_ai" and "Mark up the FAQ" in row.description


def test_a_part_that_is_not_there_is_a_404(client, db, client_a, admin_user):
    h, task = make(client, client_a, admin_user)
    assert client.patch(f"/v2/engine/tasks/{task['id']}/parts/9", json={"done": True}, headers=h).status_code == 404


def test_the_completed_work_list_shows_the_plan_entries_and_notes(client, db, client_a, admin_user):
    h, task = make(client, client_a, admin_user)
    client.patch(f"/v2/engine/tasks/{task['id']}/parts/0", json={"done": True}, headers=h)
    client.post("/v2/annotations", json={"date": "2026-10-20", "description": "Switched the booking form"}, headers=h)
    res = client.get("/v2/annotations", headers=h).json()
    assert res["counts"]["total"] == 2 and res["counts"]["from_plan"] == 1
    plan = next(e for e in res["entries"] if e["from_plan"])
    assert plan["from_plan"] == {"task_id": task["id"], "part": 0} and plan["how"] == "Marked done on the plan" and plan["type_label"] == "Growth action"
    one = client.get("/v2/annotations?page=https://www.shop.example/products/spf-15/", headers=h).json()
    assert one["counts"]["total"] == 1


def test_only_a_note_by_hand_is_removed_and_a_plan_entry_says_how(client, db, client_a, admin_user):
    h, task = make(client, client_a, admin_user)
    client.patch(f"/v2/engine/tasks/{task['id']}/parts/0", json={"done": True}, headers=h)
    note = client.post("/v2/annotations", json={"date": "2026-10-20", "description": "A note by hand"}, headers=h).json()["id"]
    entries = client.get("/v2/annotations", headers=h).json()["entries"]
    plan_id = next(e["id"] for e in entries if e["from_plan"])
    refused = client.delete(f"/v2/annotations/{plan_id}", headers=h)
    assert refused.status_code == 400 and "Mark its part not done" in refused.json()["detail"]
    assert client.delete(f"/v2/annotations/{note}", headers=h).status_code == 200
    edited = client.patch(f"/v2/annotations/{plan_id}", json={"notes": "Title now leads with the service", "result": "improved"}, headers=h).json()
    assert edited["notes"] == "Title now leads with the service" and edited["result"] == "improved"
