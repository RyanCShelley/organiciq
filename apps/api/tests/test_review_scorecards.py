"""The Monthly review's scorecards and its one line."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.models.config import ConversionDefinition, OrganicChannel
from app.models.ga4 import FactGa4Event, FactGa4Traffic
from app.services import review_scorecards as sc
from tests.conftest import client_header


def _traffic(db, client, day, channel, sessions):
    db.add(FactGa4Traffic(id=uuid4(), client_id=client.id, date=day, raw_url="https://x.example/", normalized_url="https://x.example/", session_source="s", session_medium="m",
                          channel=channel, sessions=Decimal(sessions), active_users=Decimal(sessions), views=Decimal(sessions)))


def _event(db, client, day, name, n):
    db.add(FactGa4Event(id=uuid4(), client_id=client.id, date=day, raw_url="https://x.example/", normalized_url="https://x.example/", session_source="s", session_medium="m",
                        channel=OrganicChannel.ORGANIC_SEARCH, event_name=name, event_count=n))


def _define(db, client, event, name, active=True, kind="lead"):
    db.add(ConversionDefinition(id=uuid4(), client_id=client.id, event_name=event, conversion_name=name, conversion_type=kind, is_primary=False, active=active))


def test_a_move_under_five_percent_is_flat():
    assert [sc.verdict(x) for x in (None, 4.9, -4.9, 5, -5, 40, -47)] == ["flat", "flat", "flat", "up", "down", "up", "down"]


def test_traffic_by_channel_this_month_against_last_with_the_rest_as_all_other(db, client_a):
    for day, ch, n in (
        (date(2026, 10, 5), OrganicChannel.ORGANIC_SEARCH, 90), (date(2026, 9, 5), OrganicChannel.ORGANIC_SEARCH, 100),
        (date(2026, 10, 6), OrganicChannel.AI_REFERRAL, 30), (date(2026, 9, 6), OrganicChannel.AI_REFERRAL, 20),
        (date(2026, 10, 7), OrganicChannel.DIRECT_UNATTRIBUTED, 400), (date(2026, 9, 7), OrganicChannel.DIRECT_UNATTRIBUTED, 500),
        (date(2026, 10, 8), OrganicChannel.PAID_SEARCH, 60), (date(2026, 9, 8), OrganicChannel.SOCIAL, 40),
    ):
        _traffic(db, client_a, day, ch, n)
    db.commit()
    mix = {c["key"]: c for c in sc.traffic_mix(db, client_a, "2026-10")}
    assert mix["organic_search"] == {"key": "organic_search", "label": "Organic search", "sessions": 90, "previous": 100, "change_pct": -10.0}
    assert mix["ai_referral"]["change_pct"] == 50.0 and mix["direct_unattributed"]["change_pct"] == -20.0
    assert "referral" not in mix, "a channel with no visits in either month is left out"
    assert mix["other"]["sessions"] == 60 and mix["other"]["previous"] == 40, "paid search this month, social last month"
    assert [c["label"] for c in sc.traffic_mix(db, client_a, "2026-10")][:3] == ["Organic search", "AI referrals", "Direct"]


def test_top_conversions_are_named_by_the_team_ranked_and_only_active_lead_events_count(db, client_a):
    _define(db, client_a, "form_submit", "Form submissions")
    _define(db, client_a, "tel_click", "Phone calls")
    _define(db, client_a, "chat", "Chats")
    _define(db, client_a, "old_event", "Retired", active=False)
    _define(db, client_a, "purchase", "Purchases", kind="purchase")
    for name, now, then in (("form_submit", 214, 360), ("tel_click", 121, 270), ("chat", 5, 2), ("old_event", 999, 999), ("purchase", 999, 999)):
        _event(db, client_a, date(2026, 10, 10), name, now)
        _event(db, client_a, date(2026, 9, 10), name, then)
    # a second event feeding the same named conversion adds to it
    _define(db, client_a, "form_submit_2", "Form submissions")
    _event(db, client_a, date(2026, 10, 11), "form_submit_2", 6)
    db.commit()
    top = sc.top_conversions(db, client_a, "2026-10")
    assert [(t["label"], t["count"], t["previous"]) for t in top] == [("Form submissions", 220, 360), ("Phone calls", 121, 270), ("Chats", 5, 2)]
    assert top[0]["change_pct"] == round((220 - 360) / 360 * 100, 1)
    assert sc.top_conversions(db, client_a, "2025-01") == [] or all(t["count"] == 0 for t in sc.top_conversions(db, client_a, "2025-01"))


def _review(**over):
    base = {
        "month": "2026-10", "noun": "conversions",
        "conversions": {"current": 383, "previous": 727, "change_pct": -47.3}, "sessions": {"current": 6244, "previous": 6407, "change_pct": -2.5},
        "organic_sessions": {"current": 524, "previous": 575, "change_pct": -8.9},
        "goal": {"period_goal": 525, "progress_pct": 73},
        "revenue": {"status": "measured", "revenue": {"current": 8939, "previous": 17204, "change_pct": -48.0}},
        "search": {"impressions": {"current": 43883, "previous": 61000, "change_pct": -29.0}},
        "visibility": {"summary": {"terms": 18, "showing_in_google": 6, "on_page_one": 2, "showing_in_bing": 1, "google_impressions": 2720}, "bing": {"has_data": True},
                       "buckets": [{"terms": [{"google": {"impressions": {"previous": 1800}}}, {"google": {"impressions": {"previous": 1160}}}]}],
                       "llm": {"summary": {"mentions": {"current": 0}, "citations": {"current": 0}}, "runs": 2}},
    }
    return {**base, **over}


def test_the_scorecards_carry_what_each_card_shows_and_the_one_line_says_the_month(db, client_a):
    out = sc.build(db, client_a, _review())
    v, t, c = out["visibility"], out["traffic"], out["conversions"]
    assert v["headline"] == 6 and v["of"] == 18 and v["verdict"] == "down" and v["page_one"] == 2 and v["bing"] == 1 and v["ai_mentions"] == 0 and v["ai_links"] == 0 and v["impressions"] == {"current": 2720, "previous": 2960.0, "change_pct": -8.1}, "the watchlist terms' own impressions, not the whole site's"
    assert t["headline"] == 6244 and t["verdict"] == "flat" and t["organic_change_pct"] == -8.9
    assert c["headline"] == 383 and c["verdict"] == "down" and c["goal"] == 525 and c["goal_progress_pct"] == 73 and c["revenue"]["current"] == 8939
    assert out["headline"] == ("Conversions fell 47% and revenue 48% against September. Traffic held (sessions down 2%) while organic search is down 9%. "
                               "Visibility is down: 6 of 18 terms show in Google and AI platforms do not name the brand yet.")


def test_the_one_line_handles_growth_steady_months_and_missing_parts(db, client_a):
    up = sc.build(db, client_a, _review(conversions={"current": 90, "previous": 60, "change_pct": 50.0}, sessions={"current": 7000, "previous": 6000, "change_pct": 16.7},
                                         revenue={"status": "unavailable", "reason": "x"}, organic_sessions={"current": 1, "previous": 1, "change_pct": 0.0}))["headline"]
    assert up.startswith("Conversions rose 50% against September.") and "Traffic grew (sessions up 17%)." in up and "organic" not in up
    steady = sc.build(db, client_a, _review(conversions={"current": 100, "previous": 98, "change_pct": 2.0}, revenue=None))["headline"]
    assert steady.startswith("Conversions held steady against September.")
    none = sc.build(db, client_a, _review(visibility=None))
    assert none["visibility"]["available"] is False and "Visibility" not in none["headline"]
    mixed = sc.build(db, client_a, _review(conversions={"current": 50, "previous": 100, "change_pct": -50.0}, revenue={"status": "measured", "revenue": {"current": 5, "previous": 5, "change_pct": 0.0}}))["headline"]
    assert mixed.startswith("Conversions fell 50% against September.") and "revenue" not in mixed.split(".")[0]


def test_the_review_route_returns_the_scorecards_even_for_a_month_kept_before_they_existed(client, db, client_a, admin_user, monkeypatch):
    from app.services import monthly_review

    monkeypatch.setattr(monthly_review, "review_for", lambda db_, client_, month, **kw: _review(month=month))
    out = client.get("/v2/review", params={"month": "2026-10"}, headers=client_header(client_a.id, admin_user.email)).json()
    assert out["scorecards"]["conversions"]["headline"] == 383 and out["scorecards"]["headline"].startswith("Conversions fell 47%")


def test_each_card_gets_six_months_ending_with_the_month_and_a_month_with_no_data_is_none(db, client_a):
    from app.models.gsc import FactGscQueryPage
    from app.models.watchlist import WatchlistBucket, WatchlistKeyword

    assert sc.trend_months("2026-02") == ["2025-09", "2025-10", "2025-11", "2025-12", "2026-01", "2026-02"]
    _define(db, client_a, "form_submit", "Form submissions")
    b = WatchlistBucket(client_id=client_a.id, name="SPF", name_key="spf", sort_order=0)
    db.add(b)
    db.flush()
    db.add(WatchlistKeyword(client_id=client_a.id, bucket_id=b.id, keyword="natural spf", keyword_key="natural spf"))
    for day, sessions, leads, imp in ((date(2026, 8, 3), 100, 4, 50), (date(2026, 9, 3), 120, 6, 80), (date(2026, 10, 3), 90, 3, 65)):
        _traffic(db, client_a, day, OrganicChannel.ORGANIC_SEARCH, sessions)
        _event(db, client_a, day, "form_submit", leads)
        db.add(FactGscQueryPage(client_id=client_a.id, date=day, query="Natural SPF", raw_url="https://x.example/", normalized_url="https://x.example/", country="usa", device="DESKTOP",
                                impressions=Decimal(imp), clicks=Decimal(1), ctr=Decimal(0), average_position=Decimal(5)))
    db.commit()
    months = sc.trend_months("2026-10")
    assert months == ["2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]
    assert [p["value"] for p in sc.traffic_trend(db, client_a, months)] == [None, None, None, 100, 120, 90]
    assert [p["value"] for p in sc.conversions_trend(db, client_a, months)] == [None, None, None, 4, 6, 3]
    assert [p["value"] for p in sc.visibility_trend(db, client_a, months)] == [None, None, None, 50, 80, 65], "the watchlist term's impressions, matched without case"
    out = sc.build(db, client_a, _review())
    assert [p["month"] for p in out["traffic"]["trend"]] == months and len(out["conversions"]["trend"]) == 6 and len(out["visibility"]["trend"]) == 6


def test_a_client_with_no_conversion_events_or_watchlist_has_empty_trends(db, client_a):
    months = sc.trend_months("2026-10")
    assert all(p["value"] is None for p in sc.conversions_trend(db, client_a, months)) and all(p["value"] is None for p in sc.visibility_trend(db, client_a, months))


def _rank(db, client, day, kid, keyword, pos):
    from app.models.seranking import FactSerRanking

    db.add(FactSerRanking(id=uuid4(), client_id=client.id, date=day, site_engine_id="e1", keyword_id=kid, keyword=keyword, position=Decimal(pos)))


def test_rank_check_counts_keywords_found_in_the_top_100_on_the_last_check_and_names_the_best_and_the_biggest_drop(db, client_a):
    for day, a, b, c in ((date(2026, 10, 15), 2, 34, 0), (date(2026, 10, 31), 17, 66, 0)):
        _rank(db, client_a, day, "1", "tanning oil", a)
        _rank(db, client_a, day, "2", "tanning oil with spf", b)
        _rank(db, client_a, day, "3", "lotion", c)
    _rank(db, client_a, date(2026, 10, 31), "4", "natural sunscreen", 11)
    db.commit()
    rc = sc.rank_check(db, client_a, "2026-10")
    assert rc["tracked"] == 4 and rc["ranked"] == 3 and rc["top10"] == 0
    assert rc["best"] == {"keyword": "natural sunscreen", "position": 11}
    assert rc["biggest_drop"] == {"keyword": "tanning oil with spf", "from": 34, "to": 66}
    assert rc["checked_on"] == "2026-10-31"


def test_rank_check_is_none_without_checks_in_the_month(db, client_a):
    assert sc.rank_check(db, client_a, "2026-10") is None


def test_each_section_gets_a_plain_read_from_its_numbers():
    vis = {"available": True, "headline": 6, "of": 18, "page_one": 4, "verdict": "flat"}
    traffic = {"headline": 100, "change_pct": -2, "channels": [{"key": "organic_search", "sessions": 10, "change_pct": -9.0}, {"key": "ai_referral", "sessions": 2, "change_pct": 27.0}, {"key": "direct_unattributed", "sessions": 80, "change_pct": -3.0}]}
    conv = {"noun": "conversions", "headline": 383, "change_pct": -47, "goal": 525, "goal_progress_pct": 73.0}
    reads = sc.section_reads("2026-10", "2026-09", vis, traffic, conv)
    assert reads["visibility"].startswith("12 of 18 watchlist terms never show in Google.") and "reach is the gap, not rank" in reads["visibility"]
    assert reads["traffic"] == "Organic is down 9%, but AI referrals are up 27%. Direct is more than half of all visits."
    assert reads["conversions"] == "Conversions are at 73% of this period's goal, and down 47% on September."
    empty = sc.section_reads("2026-10", "2026-09", {"available": False}, {"headline": None, "change_pct": None, "channels": []}, {"noun": "orders", "headline": None, "change_pct": None})
    assert empty == {"visibility": None, "traffic": None, "conversions": None}
