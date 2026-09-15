"""Untracked prompt discovery via SE Ranking AI Search.

This is the most expensive source in the system: 200 credits per *returned
prompt*, not per request. The API's own default of 100 would cost 20,000
credits for one engine. The cost controls are the part that matters most here.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from app.ingestion.seranking import client as ser_client
from app.models.seranking import FactSerAiPrompt, FactSerAiSearchPrompt
from tests.conftest import client_header


# --- Cost controls ----------------------------------------------------------


def test_ai_search_is_absent_from_the_daily_sync():
    """At 200 credits a prompt, a scheduled run would be ruinous."""
    from app.services.daily_sync import _PROVIDER_SOURCES

    scheduled = {s for sources in _PROVIDER_SOURCES.values() for s in sources}
    assert "se_ranking_ai_search" not in scheduled


def test_ai_search_is_a_runnable_job_source():
    from app.services.jobs import _job_handlers

    assert "se_ranking_ai_search" in _job_handlers()


def test_credit_cost_is_per_prompt_not_per_request():
    assert ser_client.ai_search_credit_cost(10) == 2000
    assert ser_client.ai_search_credit_cost(50) == 10_000
    assert ser_client.ai_search_credit_cost(0) == 0


def test_default_limit_is_conservative():
    """The API defaults to 100 (20,000 credits); ours must not."""
    assert ser_client.AI_SEARCH_DEFAULT_LIMIT <= 10
    assert ser_client.ai_search_credit_cost(ser_client.AI_SEARCH_DEFAULT_LIMIT) <= 2000


def test_limit_is_capped_well_below_the_api_maximum(monkeypatch):
    """The API allows 1000 — 200,000 credits in one call."""
    calls: list[dict] = []
    monkeypatch.setattr(
        ser_client, "_request", lambda **kw: calls.append(kw) or {"prompts": [], "total": 0}
    )

    ser_client.list_ai_search_prompts_by_target(
        api_key="k", target="example.com", engine="chatgpt", limit=999
    )

    assert calls[0]["params"]["limit"] == ser_client.AI_SEARCH_MAX_LIMIT
    assert ser_client.AI_SEARCH_MAX_LIMIT <= 50


def test_fetch_makes_exactly_one_request(monkeypatch):
    """Pagination would multiply a per-row cost."""
    calls: list[dict] = []
    monkeypatch.setattr(
        ser_client,
        "_request",
        lambda **kw: calls.append(kw)
        or {"total": 500, "date": "2026-09-15", "prompts": [{"prompt": f"p{i}"} for i in range(50)]},
    )

    ser_client.list_ai_search_prompts_by_target(
        api_key="k", target="example.com", engine="chatgpt", limit=50
    )

    assert len(calls) == 1
    assert calls[0]["params"]["offset"] == 0


def test_unknown_engine_is_refused(monkeypatch):
    """A typo must not silently bill against the wrong engine."""
    monkeypatch.setattr(ser_client, "_request", lambda **kw: {"prompts": []})

    with pytest.raises(ValueError, match="Unsupported AI engine"):
        ser_client.list_ai_search_prompts_by_target(
            api_key="k", target="example.com", engine="chatgtp"
        )


def test_job_refuses_to_run_without_an_explicit_engine(db, client_a):
    """Defaulting the engine would spend money on an assumption."""
    from datetime import date as date_cls

    from app.ingestion.seranking.pipeline_ai_search import run_seranking_ai_search_job
    from app.models.job import SyncJob, SyncJobStatus

    job = SyncJob(
        client_id=client_a.id,
        source="se_ranking_ai_search",
        start_date=date_cls.today(),
        end_date=date_cls.today(),
        status=SyncJobStatus.QUEUED,
        params_json={},
    )
    db.add(job)
    db.commit()

    out = run_seranking_ai_search_job(db, job)

    assert out.status == SyncJobStatus.FAILED
    assert "engine must be chosen" in (out.error_message or "")


# --- Response parsing -------------------------------------------------------


def test_response_is_parsed(monkeypatch):
    monkeypatch.setattr(
        ser_client,
        "_request",
        lambda **kw: {
            "total": 2,
            "date": "2026-09-15",
            "prompts": [
                {"prompt": "best geo agency", "volume": 320, "type": "Brand"},
                {"prompt": "what is geo", "volume": 110, "type": "Link"},
            ],
        },
    )

    out = ser_client.list_ai_search_prompts_by_target(
        api_key="k", target="example.com", engine="perplexity"
    )

    assert out["total"] == 2
    assert out["date"] == "2026-09-15"
    assert [p["prompt"] for p in out["prompts"]] == ["best geo agency", "what is geo"]


def test_unexpected_response_yields_nothing(monkeypatch):
    monkeypatch.setattr(ser_client, "_request", lambda **kw: "nope")
    out = ser_client.list_ai_search_prompts_by_target(
        api_key="k", target="example.com", engine="chatgpt"
    )
    assert out == {"total": 0, "date": None, "prompts": []}


# --- The untracked diff -----------------------------------------------------


def _discovered(client_id, prompt, engine="chatgpt", volume=100):
    return FactSerAiSearchPrompt(
        id=uuid4(),
        client_id=client_id,
        engine=engine,
        prompt=prompt,
        volume=Decimal(volume),
    )


def _tracked(client_id, prompt):
    return FactSerAiPrompt(
        id=uuid4(),
        client_id=client_id,
        llm_id="1",
        prompt_id=str(uuid4()),
        prompt=prompt,
        engine="chatgpt",
    )


def test_untracked_excludes_tracked_prompts(client, db, client_a, admin_user):
    db.add(_discovered(client_a.id, "best geo agency", volume=900))
    db.add(_discovered(client_a.id, "what is geo", volume=200))
    db.add(_tracked(client_a.id, "best geo agency"))
    db.commit()

    body = client.get(
        "/watch-list/untracked-prompts", headers=client_header(client_a.id, admin_user.email)
    ).json()

    assert body["discovered_prompts"] == 2
    assert body["tracked_prompts"] == 1
    assert body["untracked_total"] == 1
    assert [row["prompt"] for row in body["items"]] == ["what is geo"]


def test_untracked_prompt_match_is_case_insensitive(client, db, client_a, admin_user):
    db.add(_discovered(client_a.id, "Best GEO Agency"))
    db.add(_tracked(client_a.id, "best geo agency"))
    db.commit()

    body = client.get(
        "/watch-list/untracked-prompts", headers=client_header(client_a.id, admin_user.email)
    ).json()

    assert body["untracked_total"] == 0


def test_engines_are_reported_separately(client, db, client_a, admin_user):
    """Each engine is paid for separately, so the UI must show which are stale."""
    db.add(_discovered(client_a.id, "a", engine="chatgpt"))
    db.add(_discovered(client_a.id, "b", engine="perplexity"))
    db.commit()

    body = client.get(
        "/watch-list/untracked-prompts", headers=client_header(client_a.id, admin_user.email)
    ).json()

    assert set(body["engines_fetched"]) == {"chatgpt", "perplexity"}


def test_untracked_prompts_empty_before_any_run(client, client_a, admin_user):
    body = client.get(
        "/watch-list/untracked-prompts", headers=client_header(client_a.id, admin_user.email)
    ).json()

    assert body["untracked_total"] == 0
    assert body["engines_fetched"] == {}


# --- Per-client ceiling -----------------------------------------------------


def test_default_client_ceiling_is_five():
    """Five prompts = 1,000 credits. The starting point, not the API's 100."""
    assert ser_client.ai_search_limit_for(None) == 5
    assert ser_client.AI_SEARCH_DEFAULT_LIMIT == 5
    assert ser_client.AI_SEARCH_DEFAULT_ENGINE == "chatgpt"


def test_client_ceiling_can_be_raised_for_high_value_accounts():
    assert ser_client.ai_search_limit_for(25) == 25


def test_client_ceiling_cannot_exceed_the_global_cap():
    """A per-client setting must not be a way around the absolute ceiling."""
    assert ser_client.ai_search_limit_for(500) == ser_client.AI_SEARCH_MAX_LIMIT


def test_client_ceiling_rejects_nonsense():
    assert ser_client.ai_search_limit_for(0) == 5
    assert ser_client.ai_search_limit_for(-10) == 1


def test_job_clamps_a_request_above_the_client_ceiling(db, client_a, monkeypatch):
    """
    The UI bounds its options, but the job is what spends the money — a crafted
    request must not be able to exceed the client's cap.
    """
    from datetime import date as date_cls

    from app.ingestion.seranking import pipeline_ai_search as pipeline
    from app.models.job import SyncJob, SyncJobStatus

    client_a.ai_search_prompt_limit = 5
    db.commit()

    seen: dict = {}

    def fake_fetch(**kwargs):
        seen.update(kwargs)
        return {"total": 0, "date": None, "prompts": []}

    monkeypatch.setattr(pipeline, "list_ai_search_prompts_by_target", fake_fetch)
    monkeypatch.setattr(
        pipeline, "get_settings", lambda: type("S", (), {"se_ranking_api_key": "k"})()
    )

    job = SyncJob(
        client_id=client_a.id,
        source="se_ranking_ai_search",
        start_date=date_cls.today(),
        end_date=date_cls.today(),
        status=SyncJobStatus.QUEUED,
        params_json={"engine": "chatgpt", "limit": 50},
    )
    db.add(job)
    db.commit()

    pipeline.run_seranking_ai_search_job(db, job)

    assert seen["limit"] == 5, "the client ceiling must bind, not the request"
