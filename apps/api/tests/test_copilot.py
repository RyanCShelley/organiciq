"""The copilot: the chat loop, its tools, and the endpoint around them.

The model is a scripted fake. What is under test is everything we own: tools
run against the right client, errors come back to the model instead of
raising, the conversation is stored, and nobody reaches another client.
"""

from __future__ import annotations

import json
from datetime import date

from app.api.routers import copilot as copilot_router
from app.copilot import playbook
from app.copilot.chat import run_chat, system_prompt
from app.copilot.gateway import GatewayError
from app.copilot.tools import ToolContext, compact, run_tool
from app.main import app
from app.models.copilot import CopilotConversation, CopilotMessage
from app.models.decision import MonthlyRecord

from tests.conftest import client_header


class ScriptedGateway:
    """Returns the queued assistant messages in order and records what it saw."""

    def __init__(self, *replies: dict):
        self.replies = list(replies)
        self.seen: list[list[dict]] = []

    def complete(self, messages, tools):
        self.seen.append([dict(m) for m in messages])
        return self.replies.pop(0)


def tool_call(name: str, args: dict | None = None, call_id: str = "c1") -> dict:
    return {
        "content": None,
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(args or {})},
            }
        ],
    }


def _record(db, client, month="2026-10"):
    db.add(
        MonthlyRecord(
            client_id=client.id,
            month=month,
            data_through=date(2026, 10, 12),
            constraint_name="visibility",
            held_since="2026-09",
            confidence="high",
            record={"actions": [], "candidates": []},
        )
    )
    db.commit()


def test_loop_runs_tool_then_answers(db, client_a):
    _record(db, client_a)
    gw = ScriptedGateway(
        tool_call("get_month_plan", {"month": "2026-10"}),
        {"content": "<think>hmm</think>Visibility is the constraint for 2026-10."},
    )
    result = run_chat(ToolContext(db, client_a), gw, [], "What is the constraint?", max_rounds=4)

    assert result.reply == "Visibility is the constraint for 2026-10."
    assert result.rounds == 2 and not result.exhausted
    assert [m["role"] for m in result.messages] == ["assistant", "tool", "assistant"]
    tool_payload = json.loads(result.messages[1]["content"])
    assert tool_payload["constraint"] == "visibility"
    # The second model call saw the tool result.
    assert gw.seen[1][-1]["role"] == "tool"


def test_loop_gives_up_after_max_rounds(db, client_a):
    gw = ScriptedGateway(*[tool_call("get_data_health") for _ in range(3)])
    result = run_chat(ToolContext(db, client_a), gw, [], "?", max_rounds=3)
    assert result.exhausted
    assert "narrower" in result.reply


def test_bad_tool_calls_become_errors_the_model_can_read(db, client_a):
    ctx = ToolContext(db, client_a)
    assert "unknown tool" in run_tool(ctx, "drop_tables", "{}")["error"]
    assert "month must look like" in run_tool(ctx, "get_month_plan", '{"month": "October"}')["error"]
    assert "error" in run_tool(ctx, "get_month_plan", "{not json")
    assert "query is required" in run_tool(ctx, "search_playbook", "{}")["error"]


def test_month_plan_is_scoped_to_the_client(db, client_a, client_b):
    _record(db, client_b)
    out = run_tool(ToolContext(db, client_a), "get_month_plan", {"month": "2026-10"})
    assert out["found"] is False


def test_playbook_search_finds_the_process():
    hits = playbook.search("how many growth actions does the Lift plan get")
    assert hits and "Lift 3" in hits[0].text


def test_system_prompt_carries_client_and_process():
    prompt = system_prompt("Acme", "acme.example", date(2026, 10, 15))
    assert "Acme" in prompt and "2026-10-15" in prompt and "Visibility gates Traffic" in prompt


def test_compact_bounds_size_and_marks_cuts():
    big = {"rows": [{"url": "x" * 500, "n": i} for i in range(500)]}
    out = compact(big, max_chars=2000)
    assert len(json.dumps(out)) <= 2000
    assert "_truncated" in json.dumps(out)


def test_chat_endpoint_stores_the_conversation(db, client, client_a, team_user):
    gw = ScriptedGateway(tool_call("get_data_health"), {"content": "All sources are not connected."})
    app.dependency_overrides[copilot_router._gateway] = lambda: gw
    headers = client_header(client_a.id, team_user.email)

    resp = client.post("/copilot/chat", json={"message": "Is the data ok?"}, headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["reply"] == "All sources are not connected." and not body["incomplete"]

    rows = (
        db.query(CopilotMessage)
        .filter(CopilotMessage.conversation_id == body["conversation_id"])
        .order_by(CopilotMessage.seq)
        .all()
    )
    assert [r.role for r in rows] == ["user", "assistant", "tool", "assistant"]
    assert [r.seq for r in rows] == [1, 2, 3, 4]
    assert rows[1].tool_calls and rows[2].tool_call_id == "c1"

    # A follow-up in the same conversation replays the stored history.
    gw2 = ScriptedGateway({"content": "Same answer."})
    app.dependency_overrides[copilot_router._gateway] = lambda: gw2
    resp2 = client.post(
        "/copilot/chat",
        json={"message": "And now?", "conversation_id": body["conversation_id"]},
        headers=headers,
    )
    assert resp2.status_code == 200
    roles = [m["role"] for m in gw2.seen[0]]
    assert roles == ["system", "user", "assistant", "tool", "assistant", "user"]


def test_conversation_is_not_reachable_from_another_clients_page(
    db, client, client_a, client_b, admin_user, team_user
):
    gw = ScriptedGateway({"content": "hi"})
    app.dependency_overrides[copilot_router._gateway] = lambda: gw
    first = client.post(
        "/copilot/chat",
        json={"message": "hello"},
        headers=client_header(client_a.id, team_user.email),
    ).json()

    # Same conversation id, other client's header, even for an admin.
    other = client.post(
        "/copilot/chat",
        json={"message": "peek", "conversation_id": first["conversation_id"]},
        headers=client_header(client_b.id, admin_user.email),
    )
    assert other.status_code == 404


def test_team_member_without_assignment_is_refused(db, client, client_b, team_user):
    gw = ScriptedGateway({"content": "hi"})
    app.dependency_overrides[copilot_router._gateway] = lambda: gw
    resp = client.post(
        "/copilot/chat",
        json={"message": "hello"},
        headers=client_header(client_b.id, team_user.email),
    )
    assert resp.status_code == 403
    assert db.query(CopilotConversation).count() == 0


def test_unconfigured_copilot_answers_503(client, client_a, team_user):
    # No dependency override: LLM_BASE_URL is empty in the suite.
    resp = client.post(
        "/copilot/chat",
        json={"message": "hello"},
        headers=client_header(client_a.id, team_user.email),
    )
    assert resp.status_code == 503


def test_model_outage_is_a_502_and_stores_nothing(db, client, client_a, team_user):
    class Down:
        def complete(self, messages, tools):
            raise GatewayError("connection refused")

    app.dependency_overrides[copilot_router._gateway] = lambda: Down()
    resp = client.post(
        "/copilot/chat",
        json={"message": "hello"},
        headers=client_header(client_a.id, team_user.email),
    )
    assert resp.status_code == 502
    assert db.query(CopilotMessage).count() == 0
    assert db.query(CopilotConversation).count() == 0


def test_rating_a_reply(db, client, client_a, team_user):
    gw = ScriptedGateway({"content": "answer"})
    app.dependency_overrides[copilot_router._gateway] = lambda: gw
    headers = client_header(client_a.id, team_user.email)
    body = client.post("/copilot/chat", json={"message": "q"}, headers=headers).json()

    resp = client.post(
        f"/copilot/messages/{body['message_id']}/rating",
        json={"rating": -1, "correction": "It should have named the data gap."},
        headers=headers,
    )
    assert resp.status_code == 204
    row = db.get(CopilotMessage, body["message_id"])
    assert row.rating == -1 and row.correction.startswith("It should")
