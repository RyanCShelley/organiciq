"""Visibility candidates: bands, expected gain, strong or possible, and the bucket filter."""

from __future__ import annotations

from datetime import date

import pytest

from app.decisions import visibility_candidates as vc
from app.models.gsc import FactGscDaily, FactGscQueryPage
from app.models.watchlist import WatchlistBucket, WatchlistKeyword
from tests.conftest import client_header


def test_the_ctr_curve_never_rises_with_a_worse_position():
    values = [vc.smoothed_ctr(float(p)) for p in range(1, 21)]
    assert all(a >= b for a, b in zip(values, values[1:]))
    assert vc.smoothed_ctr(1) > vc.smoothed_ctr(3) > vc.smoothed_ctr(5) > vc.smoothed_ctr(14)


@pytest.mark.parametrize(
    "position,band",
    [(1.2, None), (1.6, "2-3"), (3.4, "2-3"), (3.6, "4-10"), (10.4, "4-10"), (10.6, "11-20"), (20.4, "11-20"), (20.6, None), (45, None)],
)
def test_a_position_lands_in_the_right_band(position, band):
    found = vc.band_for(position)
    assert (found.key if found else None) == band


def test_a_higher_page_is_worth_more_than_a_lower_one_at_the_same_volume():
    near_top = vc.expected_extra_clicks(1000, 2.0, vc.BANDS[0])  # 2 -> 1
    mid = vc.expected_extra_clicks(1000, 6.0, vc.BANDS[1])  # 6 -> 3
    low = vc.expected_extra_clicks(1000, 14.0, vc.BANDS[2])  # 14 -> 5
    assert near_top > mid > low > 0


def test_windows_are_three_complete_months_and_the_three_before():
    span = vc.windows(date(2026, 9, 1))
    assert span["current"] == (date(2026, 7, 1), date(2026, 9, 30))
    assert span["previous"] == (date(2026, 4, 1), date(2026, 6, 30))
    assert span["last_year"] == (date(2025, 7, 1), date(2025, 9, 30))
    assert vc.windows(date(2026, 2, 1))["current"] == (date(2025, 12, 1), date(2026, 2, 28))


def _row(db, client_a, day, query, url, impressions, clicks, position):
    db.add(
        FactGscQueryPage(
            client_id=client_a.id, date=day, query=query, raw_url=url, normalized_url=url, country="usa",
            device="DESKTOP", impressions=impressions, clicks=clicks, ctr=0, average_position=position,
        )
    )


def _bucket(db, client_a, terms):
    bucket = WatchlistBucket(client_id=client_a.id, name="Sun care", name_key="sun care", sort_order=0)
    db.add(bucket)
    db.flush()
    for term, volume in terms:
        db.add(WatchlistKeyword(client_id=client_a.id, bucket_id=bucket.id, keyword=term, keyword_key=term, volume=volume))
    db.commit()
    return bucket


def test_candidates_are_ranked_by_expected_gain_and_labelled_strong_or_possible(db, client_a):
    bucket = _bucket(db, client_a, [("tanning oil", 10000), ("after sun lotion", 9100), ("aloe gel", 500)])
    url_a, url_b = "https://shop.example/tan", "https://shop.example/aloe"
    # A strong rank-3 search, a strong rank-12 search, and a tiny rank-5 search (possible).
    _row(db, client_a, date(2026, 8, 10), "tanning oil", url_a, 2000, 40, 3.0)
    _row(db, client_a, date(2026, 8, 11), "best tanning oil", url_a, 1000, 5, 12.0)
    _row(db, client_a, date(2026, 8, 12), "tanning oil spf", url_a, 30, 1, 5.0)
    # Another page also shows for "tanning oil", with fewer impressions: the first one is kept.
    _row(db, client_a, date(2026, 8, 13), "tanning oil", url_b, 100, 0, 9.0)
    # Not in the bucket, and out of the bands.
    _row(db, client_a, date(2026, 8, 14), "face wash", url_b, 5000, 50, 4.0)
    _row(db, client_a, date(2026, 8, 15), "tanning oil sale", url_a, 800, 99, 1.0)
    _row(db, client_a, date(2026, 8, 16), "tanning oil near me", url_a, 800, 1, 48.0)
    db.commit()

    out = vc.build(db, client_a, "2026-09", bucket.id)
    searches = [c["search"] for c in out["candidates"]]
    assert searches == ["tanning oil", "best tanning oil", "tanning oil spf"]
    first, second, third = out["candidates"]
    assert first["band"] == "2-3" and first["target_position"] == 1 and first["strength"] == "strong"
    assert first["page"] == url_a and first["pages_for_search"] == 2
    assert second["band"] == "11-20" and second["strength"] == "strong"
    assert third["strength"] == "possible" and third["reason"] == "only 30 impressions in 3 months"
    assert out["counts"] == {"strong": 2, "possible": 1, "listed": 3, "found": 3}
    assert "face wash" not in searches and "tanning oil sale" not in searches


def test_unranked_terms_are_watchlist_terms_with_volume_and_no_impressions(db, client_a):
    bucket = _bucket(db, client_a, [("tanning oil", 10000), ("sun lotion", 9000), ("aloe gel", 0)])
    _row(db, client_a, date(2026, 8, 10), "best tanning oil", "https://shop.example/tan", 500, 5, 8.0)
    db.commit()

    out = vc.build(db, client_a, "2026-09", bucket.id)
    assert [u["keyword"] for u in out["unranked"]] == ["sun lotion"]  # "tanning oil" shows inside a longer search; "aloe gel" has no volume
    assert out["unranked"][0]["strength"] == "possible" and "No competitor" in out["unranked"][0]["note"]


def test_change_against_the_three_months_before_is_shown(db, client_a):
    bucket = _bucket(db, client_a, [("tanning oil", 10000)])
    url = "https://shop.example/tan"
    _row(db, client_a, date(2026, 8, 10), "tanning oil", url, 1000, 10, 8.0)
    _row(db, client_a, date(2026, 5, 10), "tanning oil", url, 500, 5, 11.0)
    db.commit()

    row = vc.build(db, client_a, "2026-09", bucket.id)["candidates"][0]
    assert row["previous"] == {"impressions": 500, "position": 11.0}
    assert row["impressions_change_pct"] == 100.0 and row["position_change"] == 3.0  # moved up 3 places
    assert row["last_year"] is None


def test_the_site_trend_reads_the_daily_totals(db, client_a):
    for day, impressions, clicks in [(date(2026, 8, 1), 1000, 100), (date(2026, 5, 1), 500, 80)]:
        db.add(FactGscDaily(client_id=client_a.id, date=day, impressions=impressions, clicks=clicks, ctr=0, average_position=0))
    db.commit()
    out = vc.build(db, client_a, "2026-09")
    assert out["site_trend"] == {"impressions_change_pct": 100.0, "clicks_change_pct": 25.0}
    assert out["bucket"] is None and out["window"]["has_last_year"] is False


def test_the_whole_site_is_searched_when_no_bucket_is_given(db, client_a):
    _row(db, client_a, date(2026, 8, 10), "face wash", "https://shop.example/w", 400, 4, 6.0)
    db.commit()
    assert [c["search"] for c in vc.build(db, client_a, "2026-09")["candidates"]] == ["face wash"]


def test_the_list_never_holds_more_than_twenty(db, client_a):
    for i in range(30):
        _row(db, client_a, date(2026, 8, 10), f"search {i}", f"https://shop.example/{i}", 200 + i, 1, 6.0)
    db.commit()
    out = vc.build(db, client_a, "2026-09")
    assert len(out["candidates"]) == 20 and out["counts"]["found"] == 30


def test_a_bucket_from_another_client_is_refused(client, db, client_a, client_b, admin_user):
    other = WatchlistBucket(client_id=client_b.id, name="Not mine", name_key="not mine", sort_order=0)
    db.add(other)
    db.commit()
    response = client.get(f"/v2/engine/visibility?bucket_id={other.id}", headers=client_header(client_a.id, admin_user.email))
    assert response.status_code == 404


def test_the_route_refuses_a_bad_month(client, db, client_a, admin_user):
    response = client.get("/v2/engine/visibility?month=2026-13", headers=client_header(client_a.id, admin_user.email))
    assert response.status_code == 400


def test_the_bucket_overview_shows_which_bucket_has_something_to_move(db, client_a):
    busy = _bucket(db, client_a, [("tanning oil", 10000)])
    empty = WatchlistBucket(client_id=client_a.id, name="Moisturizers", name_key="moisturizers", sort_order=1)
    db.add(empty)
    db.flush()
    db.add(WatchlistKeyword(client_id=client_a.id, bucket_id=empty.id, keyword="face oil", keyword_key="face oil", volume=1500))
    _row(db, client_a, date(2026, 8, 10), "tanning oil", "https://shop.example/tan", 2000, 40, 12.0)
    db.commit()

    overview = {b["name"]: b for b in vc.bucket_overview(db, client_a, "2026-09")}
    assert overview["Sun care"]["found"] == 1 and overview["Sun care"]["strong"] == 1
    assert overview["Sun care"]["expected_extra_clicks"] > 0 and overview["Sun care"]["unranked_terms"] == 0
    assert overview["Moisturizers"]["found"] == 0 and overview["Moisturizers"]["unranked_terms"] == 1
    assert overview["Moisturizers"]["expected_extra_clicks"] == 0
    assert busy.id


def test_a_single_impression_reads_as_singular():
    assert vc._only(1) == "only 1 impression in 3 months"
    assert vc._only(30) == "only 30 impressions in 3 months"
