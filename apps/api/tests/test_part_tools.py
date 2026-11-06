"""Each part of a growth action points at the tool that carries it out."""

from __future__ import annotations

from app.services import part_tools
from tests.conftest import client_header

GA = {
    "month": "2026-10", "kind": "growth_action", "rule_id": "GA", "search": "spf 15", "page": "https://shop.example/products/spf-15",
    "title": "Grow spf 15", "why": "w", "steps": ["# 1. Reread the title and description", "Do this.", "# 2. Add internal links", "Do that."],
    "evidence": [],
}


def test_a_part_id_belongs_to_one_tool():
    assert part_tools.tool_for("S-5")["key"] == "ctr"
    assert part_tools.tool_for("V-4")["key"] == "inlinks"
    assert part_tools.tool_for("V-7")["key"] == "schema"
    assert part_tools.tool_for("A-1")["key"] == "optimizer" and part_tools.tool_for("A-1")["kind"] == "opening"
    assert part_tools.tool_for("S-2")["kind"] == "faq" and part_tools.tool_for("S-3")["key"] == "refresh"
    assert part_tools.tool_for("L-S2") is None


def test_parts_are_read_back_from_the_headings_of_an_older_task():
    assert part_tools.from_steps(GA["steps"]) == [{"id": "S-5", "name": "Reread the title and description"}, {"id": "V-4", "name": "Add internal links"}]


def test_a_confirmed_action_returns_its_parts_with_their_tools(client, db, client_a, admin_user):
    res = client.post("/v2/engine/tasks", json={**GA, "parts": [{"id": "S-5", "name": "Reread the title and description"}, {"id": "V-4", "name": "Add internal links"}]}, headers=client_header(client_a.id, admin_user.email))
    parts = res.json()["task"]["parts"]
    assert [(p["id"], p["tool"], p["status"]) for p in parts] == [("S-5", "ctr", "open"), ("V-4", "inlinks", "open")]
    assert parts[0]["tool_path"] == "/ctr" and parts[0]["tool_param"] == "page"


def test_a_task_confirmed_without_parts_gets_them_from_its_steps(client, db, client_a, admin_user):
    parts = client.post("/v2/engine/tasks", json=GA, headers=client_header(client_a.id, admin_user.email)).json()["task"]["parts"]
    assert [p["id"] for p in parts] == ["S-5", "V-4"]
