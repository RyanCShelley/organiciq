"""Traffic and Leads candidate lists: the plan's tests, applied to sites where the answer is known."""

from __future__ import annotations

from datetime import date

import pytest

from app.decisions import leads_candidates as lc
from app.decisions import traffic_candidates as tc
from app.models.config import ConversionDefinition, OrganicChannel
from app.models.ga4 import FactGa4Event, FactGa4Traffic
from app.models.gsc import FactGscQueryPage
from app.models.watchlist import WatchlistBucket, WatchlistKeyword
from tests.conftest import client_header

ORG = OrganicChannel.ORGANIC_SEARCH
PAID = OrganicChannel.PAID_SEARCH


def traffic(db, client_a, day, url, sessions, engaged=None, channel=ORG):
    db.add(
        FactGa4Traffic(
            client_id=client_a.id, date=day, raw_url=url, normalized_url=url, channel=channel,
            sessions=sessions, active_users=sessions, views=sessions,
            engaged_sessions=sessions if engaged is None else engaged,
        )
    )


def event(db, client_a, day, url, count, name="purchase", channel=ORG):
    db.add(
        FactGa4Event(
            client_id=client_a.id, date=day, raw_url=url, normalized_url=url, channel=channel,
            event_name=name, event_count=count,
        )
    )


# ── judge: the thresholds ────────────────────────────────────────────────────


def unit(current, previous, cur3, ly3):
    return {"current": current, "previous": previous, "cur3": cur3, "ly3": ly3}


@pytest.mark.parametrize(
    "current,previous,sudden",
    [(70, 100, True), (71, 100, False), (0, 100, True), (30, 99, False), (60, 80, False)],
)
def test_sudden_needs_a_drop_of_30_percent_on_100_or_more_sessions(current, previous, sudden):
    assert tc.judge(unit(current, previous, 0, 0), None)["sudden"] is sudden


def test_slow_bleed_is_measured_against_the_site_not_against_zero():
    # The whole site kept 75% of last year. A page keeping 30% kept 40% of the site's share: a bleed.
    bleeding = tc.judge(unit(10, 10, 90, 300), site_ratio=0.75)
    assert bleeding["slow_bleed"] is True and bleeding["at_stake"] > 0
    # A page keeping 70% against a site keeping 75% is just the site's trend.
    assert tc.judge(unit(10, 10, 210, 300), site_ratio=0.75)["slow_bleed"] is False


def test_slow_bleed_needs_a_150_session_baseline_otherwise_it_is_only_possible():
    small = tc.judge(unit(5, 5, 10, 100), site_ratio=0.9)
    assert small["slow_bleed"] is False and small["possible"] is True
    assert small["at_stake"] > 0


def test_without_last_year_the_slow_bleed_test_cannot_run():
    j = tc.judge(unit(10, 10, 30, 0), site_ratio=None)
    assert j["slow_bleed"] is False and j["soft_slow"] is False


# ── traffic: the list ────────────────────────────────────────────────────────

SEP = "2026-09"


def months(db, client_a, url, by_month):
    """by_month: {(year, month): sessions}"""
    for (y, m), n in by_month.items():
        traffic(db, client_a, date(y, m, 15), url, n)


def test_a_sudden_drop_and_a_slow_bleed_are_flagged_and_a_steady_page_is_not(db, client_a):
    # Last year Jul-Sep: 100 a month each. This year the site holds about steady.
    steady, dropped, bleeding = "https://shop.example/steady", "https://shop.example/dropped", "https://shop.example/bleeding"
    months(db, client_a, steady, {(2025, 7): 100, (2025, 8): 100, (2025, 9): 100, (2026, 7): 100, (2026, 8): 100, (2026, 9): 100})
    # Fell off a cliff in September on a strong August.
    months(db, client_a, dropped, {(2025, 7): 100, (2025, 8): 100, (2025, 9): 100, (2026, 7): 150, (2026, 8): 200, (2026, 9): 60})
    # Slowly lost most of its traffic across the year.
    months(db, client_a, bleeding, {(2025, 7): 200, (2025, 8): 200, (2025, 9): 200, (2026, 7): 40, (2026, 8): 35, (2026, 9): 30})
    db.commit()

    out = tc.build(db, client_a, SEP)
    by = {c["key"]: c for c in out["candidates"]}
    assert out["site"]["has_last_year"] is True
    assert by[dropped]["flag"] == "sudden" and by[dropped]["strength"] == "strong" and by[dropped]["at_stake"] == 140.0
    assert by[bleeding]["flag"] == "slow_bleed" and by[bleeding]["strength"] == "strong"
    assert by[steady]["flag"] is None and by[steady]["strength"] == "possible"
    # Strong rows come first, biggest stake first.
    order = [c["key"] for c in out["candidates"] if c["level"] == "page"]
    assert order.index(dropped) < order.index(steady) and order.index(bleeding) < order.index(steady)
    assert out["counts"]["strong"] >= 2


def test_the_site_row_and_changes_are_reported(db, client_a):
    months(db, client_a, "https://shop.example/a", {(2025, 7): 300, (2025, 8): 300, (2025, 9): 300, (2026, 7): 150, (2026, 8): 150, (2026, 9): 100})
    db.commit()
    out = tc.build(db, client_a, SEP)
    site = next(c for c in out["candidates"] if c["level"] == "site")
    assert site["sessions"] == {"current": 100, "previous": 150, "change_pct": -33.3}
    assert site["three_months"] == {"current": 400, "last_year": 900, "change_pct": -55.6}
    assert site["flag"] == "sudden"  # 150 -> 100 is a 33% drop on 100+ sessions


def test_only_organic_sessions_count(db, client_a):
    url = "https://shop.example/a"
    months(db, client_a, url, {(2026, 9): 50, (2026, 8): 50})
    traffic(db, client_a, date(2026, 9, 3), url, 5000, channel=PAID)
    db.commit()
    page = next(c for c in tc.build(db, client_a, SEP)["candidates"] if c["level"] == "page")
    assert page["sessions"]["current"] == 50


def test_with_no_data_from_last_year_the_note_says_slow_bleed_cannot_run(db, client_a):
    months(db, client_a, "https://shop.example/a", {(2026, 7): 100, (2026, 8): 100, (2026, 9): 40})
    db.commit()
    out = tc.build(db, client_a, SEP)
    assert out["site"]["has_last_year"] is False
    assert any("slow-bleed test cannot run" in n for n in out["notes"])
    assert all(c["flag"] != "slow_bleed" for c in out["candidates"])


def gsc(db, client_a, query, url, impressions=100):
    db.add(
        FactGscQueryPage(
            client_id=client_a.id, date=date(2026, 8, 10), query=query, raw_url=url, normalized_url=url,
            country="usa", device="DESKTOP", impressions=impressions, clicks=1, ctr=0, average_position=8.0,
        )
    )


def bucket(db, client_a, name, terms):
    b = WatchlistBucket(client_id=client_a.id, name=name, name_key=name.lower(), sort_order=0)
    db.add(b)
    db.flush()
    for t in terms:
        db.add(WatchlistKeyword(client_id=client_a.id, bucket_id=b.id, keyword=t, keyword_key=t, volume=100))
    db.commit()
    return b


def test_a_bucket_is_rolled_up_and_a_bucket_scope_lists_only_its_pages(db, client_a):
    sun1, sun2, other = "https://shop.example/sun1", "https://shop.example/sun2", "https://shop.example/other"
    # Each sun page is too small to flag alone; together they fell sharply.
    months(db, client_a, sun1, {(2025, 7): 80, (2025, 8): 80, (2025, 9): 80, (2026, 7): 60, (2026, 8): 60, (2026, 9): 30})
    months(db, client_a, sun2, {(2025, 7): 80, (2025, 8): 80, (2025, 9): 80, (2026, 7): 60, (2026, 8): 60, (2026, 9): 30})
    months(db, client_a, other, {(2025, 7): 500, (2025, 8): 500, (2025, 9): 500, (2026, 7): 500, (2026, 8): 500, (2026, 9): 500})
    gsc(db, client_a, "mineral sunscreen", sun1)
    gsc(db, client_a, "best mineral sunscreen", sun2)
    b = bucket(db, client_a, "Sunscreen", ["mineral sunscreen"])

    whole = tc.build(db, client_a, SEP)
    rolled = next(c for c in whole["candidates"] if c["level"] == "bucket")
    assert rolled["label"] == "Sunscreen" and rolled["sessions"]["current"] == 60 and rolled["sessions"]["previous"] == 120

    scoped = tc.build(db, client_a, SEP, b.id)
    assert {c["key"] for c in scoped["candidates"] if c["level"] == "page"} == {sun1, sun2}
    assert scoped["scope"] == "Sunscreen" and all(c["level"] != "site" for c in scoped["candidates"])


def test_the_list_never_holds_more_than_twenty_and_is_filled_with_the_busiest_pages(db, client_a):
    for i in range(30):
        months(db, client_a, f"https://shop.example/p{i}", {(2026, 8): 40 + i, (2026, 9): 40 + i})
    db.commit()
    out = tc.build(db, client_a, SEP)
    assert len(out["candidates"]) == 20
    steady = [c for c in out["candidates"] if c["level"] == "page"]
    assert steady and all(c["strength"] == "possible" and "no decline" in c["reason"] for c in steady)


def test_a_bucket_from_another_client_is_refused(client, db, client_a, client_b, admin_user):
    other = WatchlistBucket(client_id=client_b.id, name="Not mine", name_key="not mine", sort_order=0)
    db.add(other)
    db.commit()
    for path in ("traffic", "leads"):
        res = client.get(f"/v2/engine/{path}?bucket_id={other.id}", headers=client_header(client_a.id, admin_user.email))
        assert res.status_code == 404, path


# ── leads ────────────────────────────────────────────────────────────────────


def define(db, client_a, name="purchase", type_="lead", active=True):
    db.add(ConversionDefinition(client_id=client_a.id, event_name=name, conversion_name=name, conversion_type=type_, is_primary=False, active=active))
    db.commit()


def page_stats(db, client_a, url, sessions, engaged, conversions):
    traffic(db, client_a, date(2026, 8, 15), url, sessions, engaged=engaged)
    if conversions:
        event(db, client_a, date(2026, 8, 15), url, conversions)


def test_leads_says_conversions_are_needed_when_none_are_defined(db, client_a):
    out = lc.build(db, client_a, SEP)
    assert out["needs"] == "conversions" and out["candidates"] == []


def test_engagement_only_definitions_do_not_count_and_inactive_ones_do_not_either(db, client_a):
    define(db, client_a, "scroll", "engagement")
    define(db, client_a, "old_event", "lead", active=False)
    assert lc.conversion_events(db, client_a.id) == []
    define(db, client_a, "purchase", "ecommerce")
    assert lc.conversion_events(db, client_a.id) == ["purchase"]


def build_site(db, client_a):
    """Twelve qualifying pages, so the worst quarter is three. Median conversion 4%, median engagement 70%."""
    pages = {
        # url: (sessions, engaged, conversions)
        "https://shop.example/great1": (200, 150, 12),   # 6%, 75%
        "https://shop.example/great2": (200, 150, 10),   # 5%, 75%
        "https://shop.example/ok1": (200, 140, 8),       # 4%, 70%
        "https://shop.example/ok2": (200, 140, 8),       # 4%, 70%
        "https://shop.example/ok3": (200, 140, 8),       # 4%, 70%
        "https://shop.example/ok4": (200, 140, 8),
        "https://shop.example/ok5": (200, 140, 8),
        "https://shop.example/ok6": (200, 140, 8),
        "https://shop.example/ok7": (200, 140, 8),
        "https://shop.example/leaky": (400, 120, 4),     # 1%, 30%: worst on both, plenty of sessions
        "https://shop.example/leaky_small": (60, 18, 0), # 0%, 30%: worst on both, too few sessions
        "https://shop.example/engaged_only": (200, 160, 1),  # 0.5%, 80%: low conversion but fine engagement
    }
    for url, (s, e, c) in pages.items():
        page_stats(db, client_a, url, s, e, c)
    page_stats(db, client_a, "https://shop.example/tiny", 20, 1, 0)  # under 50 sessions: not listed, not in the norm
    db.commit()
    return pages


def test_missed_conversions_rank_pages_and_strong_needs_the_worst_quarter_on_both_with_100_sessions(db, client_a):
    define(db, client_a)
    build_site(db, client_a)
    out = lc.build(db, client_a, SEP)
    by = {c["page"].rsplit("/", 1)[-1]: c for c in out["candidates"]}

    assert out["site"]["qualifying_pages"] == 12
    assert out["site"]["median_conversion_rate"] == 4.0 and out["site"]["median_engagement_rate"] == 70.0
    assert "tiny" not in by

    leaky = by["leaky"]
    assert leaky["strength"] == "strong" and leaky["reason"] is None
    assert leaky["missed_conversions"] == round(400 * (0.04 - 0.01), 1) == 12.0
    assert by["leaky_small"]["strength"] == "possible" and "only 60 sessions" in by["leaky_small"]["reason"]
    assert by["engaged_only"]["strength"] == "possible" and "worst quarter of the site on conversion, but not on engagement" in by["engaged_only"]["reason"]
    assert "not in the worst quarter of the site on conversion or engagement" in by["great1"]["reason"]
    assert by["great1"]["missed_conversions"] == 0.0  # above the site's median: nothing missed

    assert out["candidates"][0]["page"].endswith("/leaky")
    assert out["counts"]["strong"] == 1 and out["counts"]["possible"] == 11


def test_only_organic_sessions_and_conversions_count_for_leads(db, client_a):
    define(db, client_a)
    url = "https://shop.example/a"
    page_stats(db, client_a, url, 100, 70, 4)
    traffic(db, client_a, date(2026, 8, 20), url, 9000, channel=PAID)
    event(db, client_a, date(2026, 8, 20), url, 500, channel=PAID)
    db.commit()
    row = lc.build(db, client_a, SEP)["candidates"][0]
    assert row["sessions"] == 100 and row["conversions"] == 4 and row["conversion_rate"] == 4.0


def test_a_bucket_scope_keeps_the_sites_own_norm(db, client_a):
    define(db, client_a)
    build_site(db, client_a)
    gsc(db, client_a, "leaky thing", "https://shop.example/leaky")
    b = bucket(db, client_a, "Leaky", ["leaky thing"])
    out = lc.build(db, client_a, SEP, b.id)
    assert [c["page"].rsplit("/", 1)[-1] for c in out["candidates"]] == ["leaky"]
    assert out["site"]["median_conversion_rate"] == 4.0  # the site's norm, not the bucket's


def test_an_ecommerce_client_hears_orders_not_leads(db, client_a):
    define(db, client_a)
    client_a.business_model = "ecommerce"
    db.commit()
    assert lc.build(db, client_a, SEP)["noun"] == {"plural": "orders", "singular": "order"}
    client_a.business_model = None
    db.commit()
    assert lc.build(db, client_a, SEP)["noun"]["plural"] == "leads"


def test_the_routes_answer_and_refuse_a_bad_month(client, db, client_a, admin_user):
    h = client_header(client_a.id, admin_user.email)
    assert client.get("/v2/engine/traffic", headers=h).status_code == 200
    assert client.get("/v2/engine/leads", headers=h).json()["needs"] == "conversions"
    assert client.get("/v2/engine/traffic?month=2026-13", headers=h).status_code == 400
    assert client.get("/v2/engine/leads?month=nope", headers=h).status_code == 400


def test_ties_at_the_cutoff_cannot_pull_half_the_site_into_the_worst_quarter():
    values = {f"p{i}": 0.7 for i in range(8)}  # eight pages, all level
    assert len(lc._worst_quarter(values)) == 2  # a quarter of eight, not all of them
    assert len(lc._worst_quarter({"a": 0.1})) == 1


def test_ga4s_not_set_placeholder_is_never_listed_as_a_page(db, client_a):
    define(db, client_a)
    months(db, client_a, "(not set)", {(2026, 8): 500, (2026, 9): 500})
    traffic(db, client_a, date(2026, 9, 10), "https://shop.example/real", 80)
    traffic(db, client_a, date(2026, 8, 20), "(not set)", 500, engaged=5)
    page_stats(db, client_a, "https://shop.example/real", 200, 140, 8)
    db.commit()
    assert [c["key"] for c in tc.build(db, client_a, SEP)["candidates"] if c["level"] == "page"] == ["https://shop.example/real"]
    assert [c["page"] for c in lc.build(db, client_a, SEP)["candidates"]] == ["https://shop.example/real"]


def test_a_sharp_drop_on_tiny_numbers_says_too_small_not_no_decline(db, client_a):
    months(db, client_a, "https://shop.example/tiny", {(2026, 7): 40, (2026, 8): 25, (2026, 9): 10})
    months(db, client_a, "https://shop.example/steady", {(2026, 8): 40, (2026, 9): 40})
    db.commit()
    by = {c["key"]: c for c in tc.build(db, client_a, SEP)["candidates"] if c["level"] == "page"}
    assert by["https://shop.example/tiny"]["reason"] == "too small to judge: 25 sessions the month before, 10 last month"
    assert "no decline flagged" in by["https://shop.example/steady"]["reason"]
