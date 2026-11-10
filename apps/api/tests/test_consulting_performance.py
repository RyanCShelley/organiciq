"""The monthly performance report's numbers: outcomes with year-over-year and a three-month run, and one table per topic."""

from __future__ import annotations

from datetime import date

from app.models.config import ConversionDefinition, OrganicChannel
from app.models.ga4 import FactGa4Event, FactGa4Traffic
from app.models.seranking import FactSerRanking
from app.services import consulting_performance as cp

URL = "https://clienta.example/"


def traffic(db, client, day, sessions, channel=OrganicChannel.ORGANIC_SEARCH, source="google", url=URL):
    db.add(FactGa4Traffic(client_id=client.id, date=day, raw_url=url, normalized_url=url, session_source=source, session_medium="organic", channel=channel, sessions=sessions, active_users=sessions, views=sessions))


def event(db, client, day, name, count, channel=OrganicChannel.ORGANIC_SEARCH, source="google", url=URL):
    db.add(FactGa4Event(client_id=client.id, date=day, raw_url=url, normalized_url=url, session_source=source, session_medium="organic", channel=channel, event_name=name, event_count=count))


def rank(db, client, day, keyword, position, volume=1000):
    db.add(FactSerRanking(client_id=client.id, date=day, site_engine_id="s", keyword_id=keyword, keyword=keyword, position=position, volume=volume))


def seed(db, client):
    db.add_all([ConversionDefinition(client_id=client.id, event_name="demo_request", conversion_name="Demo request", conversion_type="lead"), ConversionDefinition(client_id=client.id, event_name="form_submit", conversion_name="Form submission", conversion_type="lead")])
    for month, organic, demo, form in ((date(2025, 10, 5), 2000, 30, 80), (date(2026, 8, 5), 1500, 40, 70), (date(2026, 9, 5), 1600, 50, 90), (date(2026, 10, 5), 1800, 70, 80)):
        traffic(db, client, month, organic)
        event(db, client, month, "demo_request", demo)
        event(db, client, month, "form_submit", form)
    traffic(db, client, date(2026, 10, 6), 40, OrganicChannel.AI_REFERRAL, "chatgpt.com", "https://clienta.example/ai")
    traffic(db, client, date(2026, 10, 7), 10, OrganicChannel.AI_REFERRAL, "gemini.google.com", "https://clienta.example/ai")
    traffic(db, client, date(2026, 9, 6), 20, OrganicChannel.AI_REFERRAL, "chatgpt", "https://clienta.example/ai")
    event(db, client, date(2026, 10, 6), "demo_request", 5, OrganicChannel.AI_REFERRAL, "chatgpt.com", "https://clienta.example/ai")
    rank(db, client, date(2026, 10, 1), "what is mpls", 25)
    rank(db, client, date(2026, 10, 31), "what is mpls", 2)
    rank(db, client, date(2026, 10, 1), "sd-wan", 8)
    rank(db, client, date(2026, 10, 31), "sd-wan", 0)
    rank(db, client, date(2026, 9, 30), "what is mpls", 12)
    db.commit()


def test_conversions_are_key_actions_with_previous_month_last_year_and_a_run(db, client_a):
    seed(db, client_a)
    out = cp.build(db, client_a, "2026-10")
    c = out["outcomes"]["conversions"]
    assert c["value"] == 155 and c["vs_previous"] == {"value": 140, "change_pct": 10.7} and c["vs_last_year"] == {"value": 110, "change_pct": 40.9}
    assert [r["value"] for r in c["run"]] == [110, 140, 155] and [r["month"] for r in c["run"]] == ["2026-08", "2026-09", "2026-10"]
    demo = next(r for r in out["key_actions"]["rows"] if r["label"] == "Demo request")
    assert (demo["count"], demo["previous"], demo["last_year"]) == (75, 50, 30)
    assert out["key_actions"]["total"] == {"count": 155, "previous": 140, "change_pct": 10.7}


def test_traffic_is_organic_visits_with_the_same_comparisons(db, client_a):
    seed(db, client_a)
    t = cp.build(db, client_a, "2026-10")["outcomes"]["traffic"]
    assert t["value"] == 1800 and t["vs_previous"]["change_pct"] == 12.5 and t["vs_last_year"]["change_pct"] == -10.0 and [r["value"] for r in t["run"]] == [1500, 1600, 1800]


def test_visibility_is_tracked_keywords_in_the_top_10_and_rankings_show_start_and_end(db, client_a):
    seed(db, client_a)
    out = cp.build(db, client_a, "2026-10")
    v = out["outcomes"]["visibility"]
    assert v["value"] == 1.0 and v["vs_previous"]["value"] == 0.0 and [r["value"] for r in v["run"]] == [None, 0.0, 1.0]
    rows = {r["keyword"]: r for r in out["rankings"]["rows"]}
    assert (rows["what is mpls"]["start"], rows["what is mpls"]["end"], rows["what is mpls"]["change"]) == (25.0, 2.0, 23.0)
    assert rows["sd-wan"]["start"] == 8.0 and rows["sd-wan"]["end"] is None and rows["sd-wan"]["state"] == "lost"
    assert out["rankings"]["checked_from"] == "2026-10-01" and out["rankings"]["checked_to"] == "2026-10-31"


def test_ai_assistant_visits_are_grouped_by_platform_with_key_actions(db, client_a):
    seed(db, client_a)
    rows = {r["label"]: r for r in cp.build(db, client_a, "2026-10")["ai_assistants"]}
    assert rows["ChatGPT"]["sessions"] == 40 and rows["ChatGPT"]["previous"] == 20 and rows["ChatGPT"]["change_pct"] == 100.0 and rows["ChatGPT"]["key_actions"] == 5
    assert rows["Gemini"]["sessions"] == 10 and rows["Gemini"]["previous"] == 0 and rows["Gemini"]["change_pct"] is None


def test_organic_landing_pages_carry_key_actions(db, client_a):
    seed(db, client_a)
    pages = cp.build(db, client_a, "2026-10")["landing_pages"]
    assert pages[0]["page"] == URL and pages[0]["sessions"] == 1800 and pages[0]["previous"] == 1600 and pages[0]["key_actions"] >= 70


def test_a_client_with_nothing_synced_gets_empty_outcomes_not_made_up_ones(db, client_a):
    out = cp.build(db, client_a, "2026-10")
    assert out["outcomes"] == {"conversions": None, "visibility": None, "traffic": None} and out["landing_pages"] == [] and out["ai_assistants"] == [] and out["key_actions"]["has_definitions"] is False
