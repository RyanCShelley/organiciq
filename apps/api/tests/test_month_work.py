"""A month's work by tool, for the plan and the monthly review."""

from __future__ import annotations

from tests.conftest import client_header

PARTS = [{"id": "S-5", "name": "Reread the title and description"}, {"id": "A-1", "name": "Answer the question at the top"}, {"id": "V-4", "name": "Add internal links"}, {"id": "L-S2", "name": "A step by hand"}]


def seed(client, client_a, admin_user, page="https://clienta.example/a"):
    h = client_header(client_a.id, admin_user.email)
    task = client.post("/v2/engine/tasks", json={"month": "2026-10", "kind": "growth_action", "rule_id": "GA", "search": "s", "page": page, "title": "Grow a", "steps": [f"# {i + 1}. {p['name']}" for i, p in enumerate(PARTS)], "evidence": [], "parts": PARTS}, headers=h).json()["task"]
    return h, task


def test_the_plan_counts_the_months_parts_by_the_tool_that_does_them(client, db, client_a, admin_user):
    h, task = seed(client, client_a, admin_user)
    client.patch(f"/v2/engine/tasks/{task['id']}/parts/0", json={"done": True}, headers=h)
    work = client.get("/v2/engine/tasks?month=2026-10", headers=h).json()["work"]
    assert (work["actions"], work["parts"], work["done"], work["open"], work["seen_live"]) == (1, 4, 1, 3, 0)
    tools = {t["tool"]: t for t in work["by_tool"]}
    assert [t["tool"] for t in work["by_tool"]] == ["ctr", "optimizer", "inlinks", "none"]
    assert (tools["ctr"]["done"], tools["ctr"]["open"]) == (1, 0) and tools["none"]["label"] == "By hand" and tools["optimizer"]["items"][0]["kind"] == "opening"
    assert tools["inlinks"]["path"] == "/inlinks" and tools["inlinks"]["items"][0]["page"] == "https://clienta.example/a"


def test_a_dropped_action_is_not_counted(client, db, client_a, admin_user):
    h, task = seed(client, client_a, admin_user)
    client.patch(f"/v2/engine/tasks/{task['id']}", json={"status": "dropped"}, headers=h)
    assert client.get("/v2/engine/tasks?month=2026-10", headers=h).json()["work"]["parts"] == 0


def test_the_monthly_review_carries_the_same_numbers(client, db, client_a, admin_user):
    h, task = seed(client, client_a, admin_user)
    client.patch(f"/v2/engine/tasks/{task['id']}/parts/2", json={"done": True}, headers=h)
    review = client.get("/v2/review?month=2026-10", headers=h)
    assert review.status_code == 200 and review.json()["work"]["done"] == 1 and review.json()["work"]["parts"] == 4
