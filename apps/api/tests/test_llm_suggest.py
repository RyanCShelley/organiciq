"""Suggested questions: written around the client's brand, kept only when they follow the group's rule, never saved."""

from __future__ import annotations

import json

from app.llm_visibility import platforms
from app.models.llm_visibility import ClientLlmPrompt, ClientLlmSettings
from tests.conftest import client_header


def settings(db, client):
    db.add(ClientLlmSettings(client_id=client.id, brand_name="Acme Soap", brand_patterns=["acme soap", "acme"], competitors={"rival.com": {"name": "Rival", "patterns": ["rival"]}}))
    db.commit()


def fake_model(monkeypatch, payload, key="anthropic"):
    monkeypatch.setattr(platforms, "api_key", lambda p: "k" if p == key else "")
    seen = {}

    def ask(platform, prompt):
        seen["platform"], seen["prompt"] = platform, prompt
        return platforms.PlatformAnswer(text=payload if isinstance(payload, str) else json.dumps(payload))

    monkeypatch.setattr(platforms, "ask", ask)
    return seen


def call(client, db, client_a, admin_user):
    return client.post("/v2/llm/prompts/suggest", headers=client_header(client_a.id, admin_user.email))


def test_it_needs_the_brand_set_up_first(client, db, client_a, admin_user, monkeypatch):
    fake_model(monkeypatch, {})
    res = call(client, db, client_a, admin_user)
    assert res.status_code == 400 and "brand name" in res.json()["detail"]


def test_brand_questions_must_name_the_brand_and_niche_questions_must_not(client, db, client_a, admin_user, monkeypatch):
    settings(db, client_a)
    seen = fake_model(monkeypatch, {
        "brand_check": ["Is Acme Soap lavender bar soap good for dry skin?", "What is the best lavender soap for dry skin?", "Acme Soap or Rival: which gentle soap is better?"],
        "niche": ["What is the best lavender bar soap for dry skin?", "Is Acme Soap worth buying for sensitive skin?", "Which soap would Rival recommend for sensitive skin?"],
    })
    out = call(client, db, client_a, admin_user).json()
    groups = {g["topic_cluster"]: g["prompts"] for g in out["groups"]}
    assert groups["Brand check"] == ["Is Acme Soap lavender bar soap good for dry skin?", "Acme Soap or Rival: which gentle soap is better?"]
    assert groups["Niche categories"] == ["What is the best lavender bar soap for dry skin?"]
    assert out["platform"] == "anthropic" and seen["platform"] == "anthropic"
    assert "Acme Soap" in seen["prompt"] and "Rival" in seen["prompt"]


def test_a_question_already_asked_is_not_suggested_again_and_nothing_is_saved(client, db, client_a, admin_user, monkeypatch):
    settings(db, client_a)
    db.add(ClientLlmPrompt(client_id=client_a.id, prompt="Is Acme Soap any good?", prompt_key="is acme soap any good?", topic_cluster="Brand check"))
    db.commit()
    fake_model(monkeypatch, {"brand_check": ["Is Acme Soap any good?", "Is Acme Soap shampoo bar worth buying?"], "niche": []})
    out = call(client, db, client_a, admin_user).json()
    assert out["groups"][0]["prompts"] == ["Is Acme Soap shampoo bar worth buying?"]
    assert db.query(ClientLlmPrompt).count() == 1


def test_it_says_so_when_no_platform_has_a_key_or_the_answer_is_unusable(client, db, client_a, admin_user, monkeypatch):
    settings(db, client_a)
    monkeypatch.setattr(platforms, "api_key", lambda p: "")
    res = call(client, db, client_a, admin_user)
    assert res.status_code == 502 and "API key" in res.json()["detail"]
    fake_model(monkeypatch, "Sure! Here are some ideas.")
    assert call(client, db, client_a, admin_user).status_code == 502


def test_a_json_answer_wrapped_in_a_code_fence_is_read(client, db, client_a, admin_user, monkeypatch):
    settings(db, client_a)
    fake_model(monkeypatch, '```json\n{"brand_check": ["Is Acme Soap goat milk soap good for eczema?"], "niche": []}\n```', key="openai")
    out = call(client, db, client_a, admin_user).json()
    assert out["platform"] == "openai" and out["groups"][0]["prompts"] == ["Is Acme Soap goat milk soap good for eczema?"]



def test_the_overview_says_when_a_run_is_queued_and_how_far_a_running_one_has_got(client, db, client_a, admin_user):
    from datetime import date

    from app.models.job import SyncJob, SyncJobStatus
    from app.models.llm_visibility import LlmResponse, LlmRun

    h = client_header(client_a.id, admin_user.email)
    assert client.get("/v2/llm/overview", headers=h).json()["queued"] is False
    db.add(SyncJob(client_id=client_a.id, source="llm_visibility", start_date=date.today(), end_date=date.today(), status=SyncJobStatus.QUEUED))
    db.commit()
    assert client.get("/v2/llm/overview", headers=h).json()["queued"] is True

    run = LlmRun(client_id=client_a.id, status="running", platforms=["openai"], total_calls=10)
    db.add(run)
    db.commit()
    for i in range(4):
        db.add(LlmResponse(run_id=run.id, client_id=client_a.id, platform="openai", query_text=f"q{i}", topic_cluster="T", visibility_type="Not visible"))
    db.commit()
    running = client.get("/v2/llm/overview", headers=h).json()["running"]
    assert running["total_calls"] == 10 and running["answered"] == 4


def _run_with_brands(db, client):
    from app.models.llm_visibility import LlmResponse, LlmRun

    run = LlmRun(client_id=client.id, status="complete")
    db.add(run)
    db.flush()
    for platform in ("openai", "gemini", "anthropic"):
        db.add(LlmResponse(run_id=run.id, client_id=client.id, query_text="best natural sunscreen", platform=platform,
                           other_brands_mentioned=["Badger", "Rival"], cited_urls=["https://www.badgerbalm.com/spf", "https://rival.com/x"]))
    db.add(LlmResponse(run_id=run.id, client_id=client.id, query_text="mineral spf", platform="openai", other_brands_mentioned=["Badger"], cited_urls=[]))
    db.commit()


def test_brands_the_ai_names_are_counted_with_a_website_from_the_sources_it_cites(client, db, client_a, admin_user):
    settings(db, client_a)
    client_a.competitor_domains = ["rival.com"]  # Rival is already listed, so it is not offered again
    db.commit()
    _run_with_brands(db, client_a)
    out = client.get("/v2/llm/competitors-seen", headers=client_header(client_a.id, admin_user.email)).json()
    assert [b["brand"] for b in out["brands"]] == ["Badger"]
    badger = out["brands"][0]
    assert badger["mentions"] == 4 and badger["prompts"] == 2 and badger["domain"] == "badgerbalm.com" and badger["platforms"] == ["anthropic", "gemini", "openai"]


def test_adding_a_seen_brand_lists_it_as_a_competitor_until_the_limit(client, db, client_a, admin_user):
    settings(db, client_a)
    client_a.competitor_domains = ["rival.com"]
    db.commit()
    h = client_header(client_a.id, admin_user.email)
    out = client.post("/v2/llm/competitors", json={"domain": "https://www.badgerbalm.com/", "name": "Badger"}, headers=h).json()
    assert [c["domain"] for c in out["competitors"]] == ["rival.com", "badgerbalm.com"]
    client.post("/v2/llm/competitors", json={"domain": "third.com", "name": "Third"}, headers=h)
    full = client.post("/v2/llm/competitors", json={"domain": "fourth.com", "name": "Fourth"}, headers=h)
    assert full.status_code == 400 and "already has 3" in full.json()["detail"]
