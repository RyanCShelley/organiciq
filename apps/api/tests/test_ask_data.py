"""Ask the data: the read-only door, the question loop, the cost cap."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest

from app.ask import engine, sql
from app.core.settings import get_settings
from app.models.config import OrganicChannel
from app.models.ga4 import FactGa4Traffic
from app.models.ask_data import AskDataLog
from tests.conftest import client_header


def traffic(db, client, sessions):
    db.add(FactGa4Traffic(client_id=client.id, date=date(2026, 10, 5), raw_url="https://x.example/", normalized_url="https://x.example/", session_source="s",
                          session_medium="m", channel=OrganicChannel.ORGANIC_SEARCH, sessions=Decimal(sessions), active_users=Decimal(1), views=Decimal(1)))
    db.commit()


@pytest.mark.parametrize("query", [
    "update facts_ga4_traffic set sessions = 0",
    "select 1; select 2",
    "select set_config('app.client_id', 'x', true)",
    "select pg_read_file('/etc/passwd')",
    "select * from facts_ga4_traffic -- hi",
    "delete from facts_ga4_traffic",
    "set role postgres",
    "",
])
def test_anything_but_one_plain_select_is_refused(query):
    with pytest.raises(sql.QueryRejected):
        sql.check(query)


def test_a_query_sees_only_its_own_clients_rows_and_only_the_listed_tables(db, client_a, client_b):
    traffic(db, client_a, 100)
    traffic(db, client_b, 999)
    mine = sql.run(db, client_a.id, "select sum(sessions) from facts_ga4_traffic")
    assert mine["rows"] == [["100"]]
    theirs = sql.run(db, client_b.id, "select sum(sessions) from facts_ga4_traffic")
    assert theirs["rows"] == [["999"]]
    assert "permission denied" in sql.run(db, client_a.id, "select * from clients")["error"]
    assert "permission denied" in sql.run(db, client_a.id, "select * from integrations")["error"]


def test_the_session_is_back_to_normal_after_a_question(db, client_a):
    traffic(db, client_a, 5)
    sql.run(db, client_a.id, "select 1")
    assert db.execute(__import__("sqlalchemy").text("select current_user")).scalar() != "ask_data_reader"
    assert db.query(FactGa4Traffic).count() == 1  # the owner still sees its table


def test_results_are_capped(db, client_a):
    for i in range(60):
        db.add(FactGa4Traffic(client_id=client_a.id, date=date(2026, 9, 1), raw_url=f"https://x.example/{i}", normalized_url=f"https://x.example/{i}", session_source="s",
                              session_medium="m", channel=OrganicChannel.ORGANIC_SEARCH, sessions=Decimal(1), active_users=Decimal(1), views=Decimal(1)))
    db.commit()
    out = sql.run(db, client_a.id, "select normalized_url from facts_ga4_traffic")
    assert len(out["rows"]) == sql.MAX_ROWS and out["truncated"] is True


def fake_model(monkeypatch, seen: list):
    """First turn: ask for one query. Second: answer from what came back."""
    calls = {"n": 0}

    def call(model, system, messages):
        calls["n"] += 1
        seen.append({"model": model, "system": system, "messages": json.loads(json.dumps(messages))})
        if calls["n"] == 1:
            return {"stop_reason": "tool_use", "usage": {"input_tokens": 1000, "output_tokens": 100},
                    "content": [{"type": "text", "text": "Checking."}, {"type": "tool_use", "id": "t1", "name": "run_sql", "input": {"query": "select sum(sessions) from facts_ga4_traffic"}}]}
        return {"stop_reason": "end_turn", "usage": {"input_tokens": 2000, "output_tokens": 200}, "content": [{"type": "text", "text": "Organic search had 100 visits (facts_ga4_traffic)."}]}

    monkeypatch.setattr(engine, "_call", call)


def test_a_question_is_answered_from_the_clients_data_and_logged_with_its_cost(client, db, client_a, client_b, admin_user, monkeypatch):
    traffic(db, client_a, 100)
    traffic(db, client_b, 999)
    seen: list = []
    fake_model(monkeypatch, seen)
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "k")
    h = client_header(client_a.id, admin_user.email)
    made = client.post("/v2/ask", json={"question": "How many organic visits?", "depth": "quick"}, headers=h)
    assert made.status_code == 202
    out = client.get(f"/v2/ask/{made.json()['id']}", headers=h).json()
    assert out["status"] == "done" and "100 visits" in out["answer"] and out["model"] == "claude-sonnet-5-5"
    assert out["queries"] == [{"query": "select sum(sessions) from facts_ga4_traffic", "rows": 1, "error": None}]
    # 3,000 in and 300 out at $2 / $10 per million.
    assert out["cost_usd"] == 0.009
    # What the model was shown for the query is this client's 100, never the other's 999.
    result = json.loads(seen[1]["messages"][-1]["content"][0]["content"])
    assert result["rows"] == [["100"]]
    assert "facts_ga4_traffic(" in seen[0]["system"]


def test_a_follow_up_carries_the_conversation(client, db, client_a, admin_user, monkeypatch):
    seen: list = []
    fake_model(monkeypatch, seen)
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "k")
    h = client_header(client_a.id, admin_user.email)
    client.post("/v2/ask", json={"question": "And last month?", "depth": "deep", "history": [{"role": "user", "content": "Visits in October?"}, {"role": "assistant", "content": "100."}]}, headers=h)
    assert [m["content"] for m in seen[0]["messages"]][:3] == ["Visits in October?", "100.", "And last month?"] and seen[0]["model"] == "claude-opus-5-5"


def test_a_client_past_its_monthly_limit_is_refused(client, db, client_a, admin_user, monkeypatch):
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "k")
    monkeypatch.setattr(get_settings(), "ask_monthly_cap_usd", 1.0)
    db.add(AskDataLog(client_id=client_a.id, asked_by="x", depth="quick", model="m", question="q", status="done", cost_usd=Decimal("1.2")))
    db.commit()
    res = client.post("/v2/ask", json={"question": "Anything?", "depth": "quick"}, headers=client_header(client_a.id, admin_user.email))
    assert res.status_code == 400 and "used its $1" in res.json()["detail"]
    listing = client.get("/v2/ask", headers=client_header(client_a.id, admin_user.email)).json()
    assert listing["spend"]["left_usd"] == 0 and listing["spend"]["used_usd"] == 1.2


def test_a_failure_is_reported_not_hidden(client, db, client_a, admin_user, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("The model did not answer (529).")

    monkeypatch.setattr(engine, "_call", boom)
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "k")
    h = client_header(client_a.id, admin_user.email)
    qid = client.post("/v2/ask", json={"question": "Anything at all?", "depth": "quick"}, headers=h).json()["id"]
    out = client.get(f"/v2/ask/{qid}", headers=h).json()
    assert out["status"] == "failed" and "529" in out["error"]
    assert client.get(f"/v2/ask/{qid}", headers=client_header(__import__("uuid").uuid4(), admin_user.email)).status_code in (403, 404)
