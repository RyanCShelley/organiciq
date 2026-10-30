"""Watchlist visibility from Search Console and Bing, and the Bing pull behind it."""

from __future__ import annotations

from datetime import date

import httpx
import pytest

from app.core.settings import get_settings
from app.integrations import bing
from app.models.bing_stats import FactBingQueryStat
from app.models.client_bing_site import ClientBingSite
from app.models.gsc import FactGscQueryPage
from app.models.watchlist import WatchlistBucket, WatchlistKeyword
from app.services import bing_sync
from app.services import review_visibility as rv
from tests.conftest import client_header


def test_bing_dates_are_epoch_milliseconds():
    assert bing.parse_bing_date("/Date(1770336000000)/") == date(2026, 2, 6)
    with pytest.raises(bing.BingError):
        bing.parse_bing_date("2026-02-06")


def test_bing_rows_are_read_and_no_click_position_becomes_none(monkeypatch):
    body = {
        "d": [
            {"Date": "/Date(1770336000000)/", "Query": " Mineral Sunscreen ", "Impressions": 5, "Clicks": 1, "AvgImpressionPosition": 3, "AvgClickPosition": 2},
            {"Date": "/Date(1770336000000)/", "Query": "tanning oil", "Impressions": 2, "Clicks": 0, "AvgImpressionPosition": 9, "AvgClickPosition": -1},
            {"Date": "/Date(1770336000000)/", "Query": "  ", "Impressions": 9},
        ]
    }
    monkeypatch.setattr(bing.httpx, "get", lambda *a, **k: httpx.Response(200, json=body, request=httpx.Request("GET", "https://x")))
    rows = bing.query_stats("key", "https://site/")
    assert [r["query"] for r in rows] == ["Mineral Sunscreen", "tanning oil"]
    assert rows[0]["avg_click_position"] == 2.0 and rows[1]["avg_click_position"] is None


def test_a_refused_bing_key_is_an_error_not_an_empty_list(monkeypatch):
    monkeypatch.setattr(bing.httpx, "get", lambda *a, **k: httpx.Response(401, request=httpx.Request("GET", "https://x")))
    with pytest.raises(bing.BingError, match="refused"):
        bing.query_stats("bad", "https://site/")


def _site(db, client_a, url="https://shop.example/"):
    db.add(ClientBingSite(client_id=client_a.id, site_url=url, status="connected"))
    db.commit()


def test_sync_needs_a_key_and_a_saved_site(db, client_a, monkeypatch):
    monkeypatch.setattr(get_settings(), "bing_webmaster_api_key", "")
    with pytest.raises(bing_sync.BingNotReady, match="BING_WEBMASTER_API_KEY"):
        bing_sync.sync_query_stats(db, client_a)
    monkeypatch.setattr(get_settings(), "bing_webmaster_api_key", "k")
    with pytest.raises(bing_sync.BingNotReady, match="Bing site"):
        bing_sync.sync_query_stats(db, client_a)


def test_sync_merges_repeats_and_is_safe_to_run_twice(db, client_a, monkeypatch):
    monkeypatch.setattr(get_settings(), "bing_webmaster_api_key", "k")
    _site(db, client_a)
    week = date(2026, 9, 4)
    rows = [
        {"week_start": week, "query": "Tanning Oil", "impressions": 10, "clicks": 1, "avg_impression_position": 5.0, "avg_click_position": 4.0},
        {"week_start": week, "query": "tanning oil", "impressions": 6, "clicks": 0, "avg_impression_position": 7.0, "avg_click_position": None},
    ]
    monkeypatch.setattr(bing, "query_stats", lambda key, site: rows)

    first = bing_sync.sync_query_stats(db, client_a)
    assert first["rows"] == 1 and first["weeks"] == 1
    assert db.query(FactBingQueryStat).one().impressions == 16

    bing_sync.sync_query_stats(db, client_a)
    assert db.query(FactBingQueryStat).count() == 1


def test_the_status_label_reads_google_first_then_bing():
    def engine(impressions, position):
        return {"impressions": {"current": impressions}, "position": {"current": position}}

    assert rv.status_for(engine(0, None), engine(0, None)) == "Not showing"
    assert rv.status_for(engine(4, 2.0), engine(0, None)) == "Barely showing"
    assert rv.status_for(engine(500, 2.4), engine(0, None)) == "Top 3"
    assert rv.status_for(engine(500, 8.0), engine(0, None)) == "Page 1"
    assert rv.status_for(engine(500, 14.0), engine(0, None)) == "Page 2"
    assert rv.status_for(engine(500, 31.0), engine(0, None)) == "Beyond page 2"
    assert rv.status_for(engine(0, None), engine(300, 6.0)) == "Page 1 (Bing)"


def _gsc(db, client_a, day, query, impressions, clicks, position):
    db.add(
        FactGscQueryPage(
            client_id=client_a.id, date=day, query=query, raw_url="https://shop.example/p", normalized_url="https://shop.example/p",
            country="usa", device="DESKTOP", impressions=impressions, clicks=clicks, ctr=0, average_position=position,
        )
    )


def _watchlist(db, client_a):
    bucket = WatchlistBucket(client_id=client_a.id, name="Sun", name_key="sun", sort_order=0)
    db.add(bucket)
    db.flush()
    for term, volume, prompt in [("Tanning Oil", 10000, "what tanning oil should I buy?"), ("mineral sunscreen", 43000, None)]:
        db.add(WatchlistKeyword(client_id=client_a.id, bucket_id=bucket.id, keyword=term, keyword_key=term.lower(), volume=volume, paired_ai_prompt=prompt))
    db.commit()


def test_a_term_is_compared_with_the_month_before_in_google_and_bing(db, client_a):
    _watchlist(db, client_a)
    # Impression-weighted position: (100*4 + 300*8) / 400 = 7.0 in September.
    _gsc(db, client_a, date(2026, 9, 5), "tanning oil", 100, 3, 4.0)
    _gsc(db, client_a, date(2026, 9, 20), "TANNING OIL", 300, 5, 8.0)
    _gsc(db, client_a, date(2026, 8, 10), "tanning oil", 200, 2, 12.0)
    _gsc(db, client_a, date(2026, 9, 6), "tanning oil sale", 999, 9, 1.0)  # a different query: not the term
    db.add_all(
        [
            FactBingQueryStat(client_id=client_a.id, week_start=date(2026, 9, 4), query="tanning oil", query_key="tanning oil", impressions=40, clicks=2, avg_impression_position=5.0),
            FactBingQueryStat(client_id=client_a.id, week_start=date(2026, 8, 7), query="tanning oil", query_key="tanning oil", impressions=20, clicks=0, avg_impression_position=9.0),
        ]
    )
    db.commit()

    out = rv.build_visibility(db, client_a, "2026-09")
    terms = {t["keyword"]: t for b in out["buckets"] for t in b["terms"]}
    tan = terms["Tanning Oil"]
    assert tan["google"]["impressions"] == {"current": 400.0, "previous": 200.0, "change_pct": 100.0}
    assert tan["google"]["position"]["current"] == 7.0 and tan["google"]["position"]["previous"] == 12.0
    assert tan["google"]["clicks"]["current"] == 8.0
    assert tan["bing"]["impressions"]["current"] == 40.0 and tan["bing"]["position"]["previous"] == 9.0
    assert tan["status"] == "Page 1" and tan["prompt"] == "what tanning oil should I buy?"

    sunscreen = terms["mineral sunscreen"]
    assert sunscreen["status"] == "Not showing" and sunscreen["google"]["impressions"]["current"] == 0

    assert out["summary"]["terms"] == 2 and out["summary"]["showing_in_google"] == 1
    assert out["summary"]["on_page_one"] == 1 and out["summary"]["prompts"] == 1
    assert out["bing"]["has_data"] is True


def test_no_watchlist_means_no_visibility_block(db, client_a):
    assert rv.build_visibility(db, client_a, "2026-09") is None


def test_the_sync_route_says_what_is_missing(client, db, client_a, admin_user, monkeypatch):
    monkeypatch.setattr(get_settings(), "bing_webmaster_api_key", "k")
    response = client.post("/v2/connections/bing/sync", headers=client_header(client_a.id, admin_user.email))
    assert response.status_code == 400 and "Bing site" in response.json()["detail"]


# ── AI platforms in the review ───────────────────────────────────────────────

from datetime import datetime, timezone  # noqa: E402

from app.models.llm_visibility import LlmResponse, LlmRun  # noqa: E402


def _ai_run(db, client_a, when, results):
    """`results`: {platform: (cited, mentioned)} for the prompt 'Best sunscreen?'."""
    run = LlmRun(client_id=client_a.id, status="completed", started_at=when, platforms=list(results))
    db.add(run)
    db.flush()
    for platform, (cited, mentioned) in results.items():
        vis = "Cited + Mentioned" if cited and mentioned else "Cited" if cited else "Mentioned" if mentioned else "Not visible"
        db.add(LlmResponse(run_id=run.id, client_id=client_a.id, query_text="Best sunscreen?", platform=platform, visibility_type=vis,
                           url_cited=cited, brand_mentioned=mentioned, topic_cluster="Sun"))
    db.commit()


def _term(db, client_a):
    b = WatchlistBucket(client_id=client_a.id, name="Sun", name_key="sun", sort_order=0)
    db.add(b)
    db.flush()
    db.add(WatchlistKeyword(client_id=client_a.id, bucket_id=b.id, keyword="sunscreen", keyword_key="sunscreen", paired_ai_prompt="Best  sunscreen?"))
    db.add(WatchlistKeyword(client_id=client_a.id, bucket_id=b.id, keyword="tan oil", keyword_key="tan oil"))
    db.commit()


def test_each_term_shows_how_the_platforms_answered_its_prompt_against_the_run_before(db, client_a):
    _term(db, client_a)
    _ai_run(db, client_a, datetime(2026, 8, 20, 12, tzinfo=timezone.utc), {"ChatGPT": (False, False), "Gemini": (False, True)})
    _ai_run(db, client_a, datetime(2026, 9, 20, 12, tzinfo=timezone.utc), {"ChatGPT": (True, True), "Gemini": (False, True)})
    out = rv.build_visibility(db, client_a, "2026-09")
    terms = {t["keyword"]: t for b in out["buckets"] for t in b["terms"]}
    assert terms["sunscreen"]["ai"] == {
        "by_platform": {"ChatGPT": {"cited": True, "named": True}, "Gemini": {"cited": False, "named": True}},
        "platforms": 2, "cited": 1, "mentioned": 2, "previous_cited": 0, "previous_mentioned": 1,
    }
    assert terms["tan oil"]["ai"] is None  # no paired prompt
    llm = out["llm"]
    assert llm["run_date"] == "2026-09-20" and llm["in_month"] is True and llm["previous_run_date"] == "2026-08-20"
    assert llm["summary"]["visibility_rate"] == {"current": 1.0, "previous": 0.5, "delta": 0.5}


def test_a_month_with_no_run_shows_the_latest_one_labelled_as_such_and_none_at_all_shows_nothing(db, client_a):
    _term(db, client_a)
    assert rv.build_visibility(db, client_a, "2026-09")["llm"] is None
    _ai_run(db, client_a, datetime(2026, 10, 30, 12, tzinfo=timezone.utc), {"ChatGPT": (False, False)})
    llm = rv.build_visibility(db, client_a, "2026-09")["llm"]
    assert llm["run_date"] == "2026-10-30" and llm["in_month"] is False


def test_the_review_summary_says_what_the_ai_platforms_did(db, client_a):
    from app.services import monthly_review as mr

    _term(db, client_a)
    _ai_run(db, client_a, datetime(2026, 8, 20, 12, tzinfo=timezone.utc), {"ChatGPT": (False, False), "Gemini": (False, False)})
    _ai_run(db, client_a, datetime(2026, 9, 20, 12, tzinfo=timezone.utc), {"ChatGPT": (True, True), "Gemini": (False, False)})
    review = mr.build_review(db, client_a, "2026-09")
    line = next(x for x in review["summary"] if x.startswith("AI platforms"))
    assert "50% of discovery answers named or cited the brand in the 2026-09-20 run" in line and "up 50 points" in line
