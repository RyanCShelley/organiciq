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
