"""Content refreshes on three sources (Search Console, Bing, Analytics), and pages grouped by how close they are to what the site is going after."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import numpy as np
import pytest

from app.models.bing_stats import FactBingQueryStat
from app.models.gsc import FactGscPage
from app.models.watchlist import WatchlistBucket, WatchlistKeyword
from app.services import inlinks, keyword_matcher
from tests.conftest import client_header
from tests.test_content import gsc, page, traffic

BASE = "https://shop.example/"
A, B, C, D, E = (BASE + p for p in ("pool-leak-detection", "pool-leak-repair", "company-news", "steady", "tracking"))
VOCAB = ["leak", "detection", "pool", "repair", "news", "truck", "steady", "tracking"]


@pytest.fixture(autouse=True)
def fake_meaning(monkeypatch):
    """Words stand in for meaning: two texts sharing words are alike, and no model is loaded."""
    def vec(text):
        v = np.array([float(text.lower().count(w)) for w in VOCAB], dtype="float32") + 0.01
        return v / np.linalg.norm(v)

    monkeypatch.setattr(keyword_matcher, "page_text", lambda p: p.title or "")
    monkeypatch.setattr(keyword_matcher, "embed_pages", lambda pages: np.array([vec(p.title or "") for p in pages]))
    monkeypatch.setattr(keyword_matcher, "_embed", lambda texts: np.array([vec(t) for t in texts]))


def gsc_page(db, client, day, url, clicks, impressions):
    db.add(FactGscPage(client_id=client.id, date=day, raw_url=url, normalized_url=url, impressions=Decimal(impressions), clicks=Decimal(clicks), ctr=Decimal(0), average_position=Decimal(5)))


def seed(db, client):
    page(db, client, "pool-leak-detection", "Pool leak detection guide")
    page(db, client, "pool-leak-repair", "Pool leak repair costs")           # alike a watchlist term, not named by it
    page(db, client, "company-news", "Company news: our new truck")          # nothing to do with the terms
    page(db, client, "steady", "Steady page")
    page(db, client, "tracking", "Tracking page")
    # (last year's clicks, this year's) over the same three months, and Analytics sessions a month last year and now
    plan = {A: (300, 100, 120, 40), B: (200, 60, 0, 0), C: (400, 80, 150, 30), D: (1000, 900, 400, 380), E: (100, 60, 300, 30)}
    for url, (clicks_ly, clicks, sessions_ly, sessions) in plan.items():
        for month in (8, 9, 10):
            gsc_page(db, client, date(2025, month, 12), url, clicks_ly / 3, clicks_ly * 10 / 3)
            gsc_page(db, client, date(2026, month, 12), url, clicks / 3, clicks * 10 / 3)
            if sessions_ly:
                traffic(db, client, date(2025, month, 5), url, sessions_ly)
                traffic(db, client, date(2026, month, 5), url, sessions)
    gsc(db, client, date(2026, 10, 10), "leak detection", A, 500, 30, 4.0)          # the page Search Console shows for the watchlist term
    gsc(db, client, date(2026, 10, 10), "leak detection near me", A, 300, 10, 5.0)
    for query, clicks_ly, clicks in (("leak detection near me", 40, 10),):
        db.add(FactBingQueryStat(client_id=client.id, week_start=date(2025, 9, 1), query=query, query_key=query, impressions=400, clicks=clicks_ly))
        db.add(FactBingQueryStat(client_id=client.id, week_start=date(2026, 9, 7), query=query, query_key=query, impressions=100, clicks=clicks))
    bucket = WatchlistBucket(client_id=client.id, name="Leak detection", name_key="leak detection", sort_order=0)
    db.add(bucket)
    db.flush()
    db.add(WatchlistKeyword(client_id=client.id, bucket_id=bucket.id, keyword="leak detection", keyword_key="leak detection", volume=320, source="csv"))
    db.commit()


def test_pages_are_judged_on_search_console_and_bing_and_grouped_by_how_close_they_are_to_the_topics(client, db, client_a, admin_user):
    seed(db, client_a)
    out = client.get("/v2/content/refreshes", params={"month": "2026-10"}, headers=client_header(client_a.id, admin_user.email)).json()
    by = {p["url"]: p for p in out["pages"]}
    assert out["search_available"] is True and out["bing_available"] is True and out["topics_known"] is True
    ratio = out["site"]["clicks"]["current"] / out["site"]["clicks"]["last_year"]

    a = by[A]
    assert a["tier"] == "topic" and a["topics"][0]["term"] == "leak detection" and a["in_focus"] is False
    assert a["search"]["clicks"] == {"current": 100, "last_year": 300, "change_pct": -67}
    assert a["at_stake"] == round((300 * ratio - 100) / 3), "clicks lost a month, against the site's own trend"
    assert a["bing"]["clicks"] == {"current": 10, "last_year": 40, "change_pct": -75}, "the Bing search is counted for the page Search Console shows for it"
    assert any(r.startswith("Search Console clicks are -67%") for r in a["reasons"]) and any(r.startswith("Bing clicks are -75%") for r in a["reasons"])

    b = by[B]
    assert b["tier"] == "related" and b["on_topic"] is False and b["related"]["term"] == "leak detection" and b["related"]["topic"] == "Leak detection" and b["related"]["similarity"] >= 0.35
    assert b["sessions"]["current"] == 0 and any(r.startswith("Related to the topic “Leak detection”") for r in b["reasons"]), "found from Search Console alone: it has no Analytics rows"

    c = by[C]
    assert c["tier"] == "unrelated" and c["reasons"][0] == "Not on a target topic." and c["at_stake"] > b["at_stake"], "the biggest loss is not related to what the site is going after"
    assert [p["url"] for p in out["pages"]][:2] == [A, B], "tied to a term, then related, then the rest"
    assert [p["tier"] for p in out["pages"]] == sorted((p["tier"] for p in out["pages"]), key={"topic": 0, "related": 1, "unrelated": 2}.get)
    assert D not in by, "a steady page is not listed"
    assert out["counts"]["related"] >= 1 and out["counts"]["off_topic"] >= 1


def test_a_fall_only_in_analytics_is_flagged_as_a_possible_tracking_gap(client, db, client_a, admin_user):
    seed(db, client_a)
    out = client.get("/v2/content/refreshes", params={"month": "2026-10"}, headers=client_header(client_a.id, admin_user.email)).json()
    e = {p["url"]: p for p in out["pages"]}[E]
    assert e["tracking_gap"] is True and e["at_stake"] == 0, "Search Console clicks held up with the site"
    assert any("may be a tracking gap" in r for r in e["reasons"]) and out["counts"]["tracking_gap"] == 1


def test_without_last_years_search_console_data_the_list_falls_back_to_analytics_and_says_so(client, db, client_a, admin_user):
    from app.models.gsc import FactGscPage as Page

    seed(db, client_a)
    db.query(Page).filter(Page.date < date(2026, 1, 1)).delete()
    db.commit()
    out = client.get("/v2/content/refreshes", params={"month": "2026-10"}, headers=client_header(client_a.id, admin_user.email)).json()
    assert out["search_available"] is False and any("too little Search Console data" in n for n in out["notes"])
    assert all(p["tracking_gap"] is False for p in out["pages"])
    assert {p["url"]: p["at_stake"] for p in out["pages"]}[C] > 0, "sessions lost stand in"
