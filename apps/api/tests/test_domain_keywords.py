"""Untracked keyword discovery via SE Ranking Domain Analysis.

/domain/keywords is metered at 100 credits per request, so the cost controls
matter as much as the parsing: one request per run, never in the daily sync.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from app.ingestion.seranking import client as ser_client
from app.ingestion.seranking.pipeline_domain import resolve_source
from app.models.client import Client
from app.models.seranking import FactSerDomainKeyword, FactSerKeyword
from tests.conftest import client_header


# --- Cost controls ----------------------------------------------------------


def test_domain_keywords_is_absent_from_the_daily_sync():
    """
    100 credits a run. At 35 clients a daily schedule is ~105,000 credits a
    month for data nobody asked for.
    """
    from app.services.daily_sync import _PROVIDER_SOURCES

    every_scheduled_source = {s for sources in _PROVIDER_SOURCES.values() for s in sources}
    assert "se_ranking_domain_keywords" not in every_scheduled_source


def test_domain_keywords_is_still_a_runnable_job_source():
    from app.services.jobs import _job_handlers

    assert "se_ranking_domain_keywords" in _job_handlers()


def test_fetch_makes_exactly_one_request(monkeypatch):
    """Each extra page is another 100 credits, so it must not paginate."""
    calls: list[dict] = []

    def fake_request(**kwargs):
        calls.append(kwargs)
        return [{"keyword": f"kw-{i}", "volume": 100} for i in range(1000)]

    monkeypatch.setattr(ser_client, "_request", fake_request)
    rows = ser_client.list_domain_keywords(api_key="k", domain="example.com")

    assert len(calls) == 1, "one request per run — pagination costs 100 credits a page"
    assert len(rows) == 1000
    assert calls[0]["params"]["limit"] == 1000
    assert calls[0]["params"]["order_field"] == "volume"


def test_fetch_caps_the_limit_at_the_api_maximum(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(
        ser_client, "_request", lambda **kw: calls.append(kw) or []
    )
    ser_client.list_domain_keywords(api_key="k", domain="example.com", limit=99999)
    assert calls[0]["params"]["limit"] == 1000


# --- Response parsing -------------------------------------------------------


def test_bare_array_response_is_parsed(monkeypatch):
    monkeypatch.setattr(
        ser_client, "_request", lambda **kw: [{"keyword": "seo"}, {"keyword": "geo"}]
    )
    assert [r["keyword"] for r in ser_client.list_domain_keywords(api_key="k", domain="d")] == [
        "seo",
        "geo",
    ]


def test_wrapped_response_is_tolerated(monkeypatch):
    """Docs describe a bare array; tolerate a wrapper rather than silently returning none."""
    monkeypatch.setattr(ser_client, "_request", lambda **kw: {"keywords": [{"keyword": "seo"}]})
    assert len(ser_client.list_domain_keywords(api_key="k", domain="d")) == 1


def test_unexpected_response_yields_no_rows(monkeypatch):
    monkeypatch.setattr(ser_client, "_request", lambda **kw: "nope")
    assert ser_client.list_domain_keywords(api_key="k", domain="d") == []


# --- Region resolution ------------------------------------------------------


def test_region_maps_from_primary_market(db, tier):
    c = Client(
        id=uuid4(),
        client_name="UK Co",
        slug="uk-co",
        domain="ukco.com",
        tier_id=tier.id,
        timezone="UTC",
        primary_market="United Kingdom",
        status="active",
    )
    assert resolve_source(c) == "uk"


def test_region_falls_back_rather_than_failing(db, tier):
    c = Client(
        id=uuid4(),
        client_name="Odd",
        slug="odd",
        domain="odd.com",
        tier_id=tier.id,
        timezone="UTC",
        primary_market="Somewhere Unmapped",
        status="active",
    )
    assert resolve_source(c) == "us"


# --- The untracked diff -----------------------------------------------------


def _domain_kw(client_id, keyword, volume):
    return FactSerDomainKeyword(
        id=uuid4(),
        client_id=client_id,
        keyword=keyword,
        volume=Decimal(volume),
        position=Decimal(5),
    )


def _tracked_kw(client_id, keyword):
    return FactSerKeyword(
        id=uuid4(),
        client_id=client_id,
        keyword_id=str(uuid4()),
        keyword=keyword,
        site_engine_id="1",
    )


def test_untracked_excludes_tracked_keywords(client, db, client_a, admin_user):
    db.add(_domain_kw(client_a.id, "seo services", 1000))
    db.add(_domain_kw(client_a.id, "geo agency", 500))
    db.add(_tracked_kw(client_a.id, "seo services"))
    db.commit()

    res = client.get("/watch-list/untracked", headers=client_header(client_a.id, admin_user.email))
    body = res.json()

    assert res.status_code == 200
    assert body["domain_keywords"] == 2
    assert body["tracked_keywords"] == 1
    assert body["untracked_total"] == 1
    assert [row["keyword"] for row in body["items"]] == ["geo agency"]


def test_untracked_match_is_case_insensitive(client, db, client_a, admin_user):
    db.add(_domain_kw(client_a.id, "SEO Services", 1000))
    db.add(_tracked_kw(client_a.id, "seo services"))
    db.commit()

    body = client.get(
        "/watch-list/untracked", headers=client_header(client_a.id, admin_user.email)
    ).json()

    assert body["untracked_total"] == 0, "casing must not create phantom opportunities"


def test_untracked_is_ordered_by_volume(client, db, client_a, admin_user):
    db.add(_domain_kw(client_a.id, "small", 10))
    db.add(_domain_kw(client_a.id, "huge", 9000))
    db.add(_domain_kw(client_a.id, "mid", 500))
    db.commit()

    body = client.get(
        "/watch-list/untracked", headers=client_header(client_a.id, admin_user.email)
    ).json()

    assert [row["keyword"] for row in body["items"]] == ["huge", "mid", "small"]


def test_untracked_is_empty_before_any_fetch(client, db, client_a, admin_user):
    body = client.get(
        "/watch-list/untracked", headers=client_header(client_a.id, admin_user.email)
    ).json()

    assert body["untracked_total"] == 0
    assert body["fetched_at"] is None
