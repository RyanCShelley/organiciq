"""Content gaps (searches with no page) and content refreshes (pages worth updating), the model drafts for each, and setting items aside."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSnapshot
from app.models.ga4 import FactGa4Traffic
from app.models.gsc import FactGscQueryPage
from app.models.seranking import FactSerCompetitorKeyword, FactSerKeyword, FactSerKeywordMetric
from app.services.content_gap_signals import MIN_CRAWLED_PAGES
from tests.conftest import client_header

DAY = date(2026, 10, 1)
OLD, STEADY = "https://shop.example/old-guide", "https://shop.example/steady"


def page(db, client, slug, title=None, words=900, updated=None):
    url = f"https://shop.example/{slug}"
    db.add(FactCrawlPageSnapshot(id=uuid4(), client_id=client.id, source=CRAWL_SOURCE_FIRST_PARTY, snapshot_date=DAY, raw_url=url, normalized_url=url, status_code=200, indexable=True,
                                 word_count=words, inbound_internal_links=3, inbound_editorial_links=1, redirect_count=0, title=title or slug.title(), sections=[], content_updated_on=updated))
    return url


def price(db, client, term, volume=500, difficulty=20):
    db.add(FactSerKeywordMetric(id=uuid4(), client_id=client.id, keyword=term, source="us", volume=volume, difficulty=difficulty, data_found=True, fetched_at=DAY))


def gsc(db, client, day, query, url, impressions, clicks, position):
    db.add(FactGscQueryPage(client_id=client.id, date=day, query=query, raw_url=url, normalized_url=url, country="usa", device="DESKTOP",
                            impressions=Decimal(impressions), clicks=Decimal(clicks), ctr=Decimal(0), average_position=Decimal(position)))


def traffic(db, client, day, url, sessions):
    from app.models.ga4 import OrganicChannel

    db.add(FactGa4Traffic(client_id=client.id, date=day, raw_url=url, normalized_url=url, session_source="google", session_medium="organic", channel=OrganicChannel.ORGANIC_SEARCH,
                          sessions=Decimal(sessions), active_users=Decimal(sessions), views=Decimal(sessions), engaged_sessions=Decimal(sessions)))


def seed_gaps(db, client):
    filler = [page(db, client, f"filler-{i}", f"Filler {i}") for i in range(MIN_CRAWLED_PAGES)]
    db.add(FactSerKeyword(id=uuid4(), client_id=client.id, site_engine_id="1", keyword_id="k1", keyword="aeo agency", volume=500))
    price(db, client, "aeo agency")                                   # a tracked term no page carries
    gsc(db, client, date.today(), "schema markup audit", filler[0], 400, 2, 22.0)   # shown for it, no page about it
    price(db, client, "schema markup audit", 900, 30)
    db.add(FactSerCompetitorKeyword(client_id=client.id, competitor_domain="rival.com", keyword="local seo checklist", position=Decimal(3), volume=Decimal(700), difficulty=Decimal(25), fetched_at=DAY))
    db.commit()


def h(client_a, admin_user):
    return client_header(client_a.id, admin_user.email)


def test_gaps_join_search_console_competitors_and_the_watchlist_ranked_by_opportunity(client, db, client_a, admin_user):
    seed_gaps(db, client_a)
    out = client.get("/v2/content/gaps", headers=h(client_a, admin_user)).json()
    by = {g["term"]: g for g in out["gaps"]}
    assert set(by) >= {"aeo agency", "schema markup audit", "local seo checklist"}
    assert by["schema markup audit"]["sources"] == ["searched"] and by["schema markup audit"]["impressions"] == 400
    assert by["local seo checklist"]["sources"] == ["competitor"] and by["local seo checklist"]["competitors"][0]["domain"] == "rival.com"
    assert by["aeo agency"]["sources"] == ["watchlist"] and by["aeo agency"]["action"] == "Write a new page"
    assert by["schema markup audit"]["priced"] is True
    assert [g["opportunity"] for g in out["gaps"]] == sorted((g["opportunity"] for g in out["gaps"]), reverse=True)
    assert out["counts"]["gaps"] == len(out["gaps"]) and out["counts"]["competitor"] == 1


def test_a_search_with_no_volume_data_is_still_a_gap_listed_after_the_ranked_ones(client, db, client_a, admin_user):
    seed_gaps(db, client_a)
    gsc(db, client_a, date.today(), "unpriced gap term", "https://shop.example/filler-1", 300, 1, 25.0)
    db.commit()
    out = client.get("/v2/content/gaps", headers=h(client_a, admin_user)).json()
    terms = [g["term"] for g in out["gaps"]]
    waiting = next(g for g in out["gaps"] if g["term"] == "unpriced gap term")
    assert waiting["priced"] is False and waiting["volume"] is None and terms[-1] == "unpriced gap term"
    assert any("no volume data yet" in n for n in out["notes"])


def test_a_site_the_crawl_could_not_read_says_so_instead_of_listing_gaps(client, db, client_a, admin_user):
    page(db, client_a, "only")
    db.commit()
    out = client.get("/v2/content/gaps", headers=h(client_a, admin_user)).json()
    assert out["gaps"] == [] and "too few" in out["blocked"]


def test_a_gap_can_be_set_aside_and_restored_and_a_search_finds_one(client, db, client_a, admin_user):
    seed_gaps(db, client_a)
    hd = h(client_a, admin_user)
    assert client.post("/v2/content/ignore", json={"area": "gap", "key": "aeo agency"}, headers=hd).status_code == 200
    assert client.post("/v2/content/ignore", json={"area": "gap", "key": "aeo agency"}, headers=hd).status_code == 200, "setting it aside twice is harmless"
    out = client.get("/v2/content/gaps", headers=hd).json()
    assert "aeo agency" not in [g["term"] for g in out["gaps"]] and out["ignored_total"] == 1
    assert [g["term"] for g in client.get("/v2/content/gaps", params={"ignored": True}, headers=hd).json()["gaps"]] == ["aeo agency"]
    assert [g["term"] for g in client.get("/v2/content/gaps", params={"q": "checklist"}, headers=hd).json()["gaps"]] == ["local seo checklist"]
    client.post("/v2/content/restore", json={"area": "gap", "key": "aeo agency"}, headers=hd)
    assert "aeo agency" in [g["term"] for g in client.get("/v2/content/gaps", headers=hd).json()["gaps"]]


def _enable(monkeypatch, reply, seen):
    from app.core.settings import get_settings
    from app.schema_tools import llm
    from app.services import content_briefs
    from app.services.page_diagnostic import Fetched

    monkeypatch.setattr(get_settings(), "anthropic_api_key", "k")
    monkeypatch.setattr(content_briefs, "read_page", lambda url, domain: Fetched(status=200, final_url=url, headers={}, body="<html><body><nav>menu</nav><h1>Guide</h1><p>Plain words about the guide.</p></body></html>"))

    def call(depth, prompt, **kw):
        seen["prompt"], seen["depth"] = prompt, depth
        return reply, 2000, 500

    monkeypatch.setattr(llm, "call", call)


def test_the_model_writes_a_brief_for_a_gap_from_its_evidence(client, db, client_a, admin_user, monkeypatch):
    seed_gaps(db, client_a)
    seen: dict = {}
    _enable(monkeypatch, json.dumps({"working_title": "Local SEO Checklist for Small Shops", "page_type": "guide", "angle": "A checklist.", "sections": ["Claim your profile", "Fix citations"],
                                      "questions": ["What is local SEO?"], "entities": ["Google Business Profile"], "target_words": 1400, "avoid": ["Thin lists"],
                                      "link_from": [{"url": "https://shop.example/filler-0", "anchor_idea": "local checklist"}]}), seen)
    hd = h(client_a, admin_user)
    assert client.post("/v2/content/draft", json={"kind": "brief", "key": "local seo checklist", "depth": "deep"}, headers=hd).status_code == 202
    draft = client.get("/v2/content/gaps/brief", params={"term": "local seo checklist"}, headers=hd).json()["draft"]
    assert draft["status"] == "done" and draft["depth"] == "deep" and draft["cost_usd"] > 0
    assert draft["working_title"].startswith("Local SEO") and draft["sections"] == ["Claim your profile", "Fix citations"] and draft["link_from"][0]["anchor_idea"] == "local checklist"
    assert "rival.com ranks at position 3.0" in seen["prompt"] and "volume 700" in seen["prompt"]


def test_a_brief_for_a_search_that_is_no_longer_a_gap_fails_with_a_plain_reason(client, db, client_a, admin_user, monkeypatch):
    seed_gaps(db, client_a)
    _enable(monkeypatch, "{}", {})
    hd = h(client_a, admin_user)
    client.post("/v2/content/draft", json={"kind": "brief", "key": "not a gap"}, headers=hd)
    draft = client.get("/v2/content/gaps/brief", params={"term": "not a gap"}, headers=hd).json()["draft"]
    assert draft["status"] == "failed" and "no longer a gap" in draft["error"]


def test_the_model_finds_missing_topics_and_a_dismissed_one_is_never_suggested_again(client, db, client_a, admin_user, monkeypatch):
    seed_gaps(db, client_a)
    seen: dict = {}
    _enable(monkeypatch, json.dumps({"topics": [{"label": "Sunscreen for kids", "why": "Searches show parents.", "content_type": "guide", "priority": "high", "example_searches": ["kids spf"], "next_to": "sunscreen"},
                                                 {"label": "Reef safe spf", "why": "w", "priority": "weird", "example_searches": []}]}), seen)
    hd = h(client_a, admin_user)
    client.post("/v2/content/topics/dismiss", json={"label": "Reef safe spf"}, headers=hd)
    assert client.post("/v2/content/draft", json={"kind": "topics", "key": "x"}, headers=hd).status_code == 202
    out = client.get("/v2/content/topics", headers=hd).json()
    assert [t["label"] for t in out["draft"]["topics"]] == ["Sunscreen for kids"], "a topic the team said is out of scope is dropped"
    assert out["dismissed"] == ["Reef safe spf"] and "Reef safe spf" in seen["prompt"] and "schema markup audit" in seen["prompt"]


def test_the_model_needs_its_key_and_respects_the_monthly_limit(client, db, client_a, admin_user, monkeypatch):
    from app.core.settings import get_settings

    seed_gaps(db, client_a)
    hd = h(client_a, admin_user)
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "")
    assert "key is not set" in client.post("/v2/content/draft", json={"kind": "topics", "key": "x"}, headers=hd).json()["detail"]
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "k")
    monkeypatch.setattr(get_settings(), "ask_monthly_cap_usd", 0.0)
    assert "used its" in client.post("/v2/content/draft", json={"kind": "topics", "key": "x"}, headers=hd).json()["detail"]


# ── refreshes ────────────────────────────────────────────────────────────────


def seed_refresh(db, client):
    page(db, client, "old-guide", "Old guide", words=250, updated=date(2024, 1, 1))
    page(db, client, "steady", "Steady", updated=date(2026, 6, 1))
    for year, per in ((2025, {OLD: 400, STEADY: 1000}), (2026, {OLD: 100, STEADY: 1000})):
        for m in (8, 9, 10):
            for url, n in per.items():
                traffic(db, client, date(year, m, 5), url, n)
    gsc(db, client, date(2026, 6, 10), "old guide topic", OLD, 600, 60, 3.0)     # the three months before
    gsc(db, client, date(2026, 10, 10), "old guide topic", OLD, 600, 10, 8.0)    # the last three months
    gsc(db, client, date(2026, 10, 10), "shared search", OLD, 200, 5, 6.0)
    gsc(db, client, date(2026, 10, 10), "shared search", STEADY, 120, 4, 9.0)
    db.commit()


def test_refreshes_rank_the_pages_losing_more_than_the_site_and_say_why(client, db, client_a, admin_user):
    seed_refresh(db, client_a)
    out = client.get("/v2/content/refreshes", params={"month": "2026-10"}, headers=h(client_a, admin_user)).json()
    assert [p["url"] for p in out["pages"]] == [OLD], "the steady page is not listed"
    old = out["pages"][0]
    assert old["label"] == "losing" and old["status"] == "Losing traffic" and old["at_stake"] > 0 and old["stale"] and old["thin"]
    assert any("-75%" in r for r in old["reasons"]) and any("Only 250 words" in r for r in old["reasons"]) and any("months ago" in r for r in old["reasons"])
    assert out["counts"]["losing"] == 1 and out["counts"]["stale"] == 1 and out["counts"]["thin"] == 1
    assert out["competing"][0]["query"] == "shared search" and {p["url"] for p in out["competing"][0]["pages"]} == {OLD, STEADY}


def test_a_refresh_can_be_set_aside_found_by_search_and_a_bad_month_is_refused(client, db, client_a, admin_user):
    seed_refresh(db, client_a)
    hd = h(client_a, admin_user)
    client.post("/v2/content/ignore", json={"area": "refresh", "key": OLD}, headers=hd)
    out = client.get("/v2/content/refreshes", params={"month": "2026-10"}, headers=hd).json()
    assert out["pages"] == [] and out["ignored_total"] == 1
    assert [p["url"] for p in client.get("/v2/content/refreshes", params={"month": "2026-10", "ignored": True}, headers=hd).json()["pages"]] == [OLD]
    assert [p["url"] for p in client.get("/v2/content/refreshes", params={"month": "2026-10", "q": "steady"}, headers=hd).json()["pages"]] == [STEADY], "a page can be found by search however healthy it is"
    assert client.get("/v2/content/refreshes", params={"month": "October"}, headers=hd).status_code == 400


def test_a_page_opens_to_its_months_lost_searches_competitors_and_depth(client, db, client_a, admin_user, monkeypatch):
    from app.services import content_refresh
    from app.services.page_diagnostic import Fetched

    seed_refresh(db, client_a)
    body = "<html><body><h1>Guide</h1><p>According to the report, 42% of shops grew in 2025.</p><ul><li>One</li><li>Two</li></ul></body></html>"
    monkeypatch.setattr(content_refresh, "read_page", lambda url, domain: Fetched(status=200, final_url=url, headers={}, body=body))
    out = client.get("/v2/content/refreshes/page", params={"url": OLD, "month": "2026-10"}, headers=h(client_a, admin_user)).json()
    assert out["sessions"][-1] == {"month": "2026-10", "sessions": 100} and len(out["sessions"]) == 15
    assert out["lost"][0]["query"] == "old guide topic" and out["lost"][0]["clicks_lost"] > 0
    assert out["competing"][0]["query"] == "shared search" and out["read"]["ok"] is True
    assert out["depth"]["score"] > 0 and out["depth"]["signals"]["list_items"] == 2 and out["plan"] is None


def test_the_model_plans_a_refresh_from_the_pages_lost_searches(client, db, client_a, admin_user, monkeypatch):
    seed_refresh(db, client_a)
    seen: dict = {}
    _enable(monkeypatch, json.dumps({"diagnosis": "It lost its answer.", "keep": ["The intro"], "add": [{"section": "A comparison table", "why": "old guide topic"}], "change": [{"what": "Update the 2024 figures", "why": "stale"}],
                                      "remove": [], "merge_with": "", "target_words": 1500}), seen)
    from app.services import content_refresh
    from app.services.page_diagnostic import Fetched

    monkeypatch.setattr(content_refresh, "read_page", lambda url, domain: Fetched(status=200, final_url=url, headers={}, body="<html><body><p>x</p></body></html>"))
    hd = h(client_a, admin_user)
    assert client.post("/v2/content/draft", json={"kind": "refresh", "key": OLD, "month": "2026-10"}, headers=hd).status_code == 202
    plan = client.get("/v2/content/refreshes/page", params={"url": OLD, "month": "2026-10"}, headers=hd).json()["plan"]
    assert plan["status"] == "done" and plan["add"][0]["why"] == "old guide topic" and plan["change"][0]["what"].startswith("Update") and plan["month"] == "2026-10"
    assert "“old guide topic”: clicks 60 → 10" in seen["prompt"] and "Depth score" in seen["prompt"] and "shared search" in seen["prompt"]
