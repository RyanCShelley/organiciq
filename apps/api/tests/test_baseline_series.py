"""The baseline from a monthly series.

The fixtures are real monthly figures from two clients (GA4, Oct 2025 to Sep 2026),
because the point of the method is what it does with a relaunch, a tracking start
and a spike, and invented numbers would not have any of those.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.services import baseline_series as bs
from app.services.baseline_series import MonthRow, analyze, normalize_month, parse_csv
from tests.conftest import client_header


def _rows(start: str, sessions: list[float], leads: list[float], organic: list[float] | None = None):
    return [
        MonthRow(
            bs.add_months(start, index),
            sessions[index],
            leads[index],
            organic[index] if organic else None,
        )
        for index in range(len(sessions))
    ]


# SMA: the site was relaunched in September 2026 and traffic stepped down.
SMA = _rows(
    "2025-10",
    [4318, 3527, 3997, 4201, 3201, 3057, 4518, 3905, 5668, 2706, 2928, 1226],
    [16, 29, 38, 45, 15, 15, 26, 19, 27, 27, 8, 13],
)
# ACC Tek: lead tracking began in November 2025 and ramped slowly.
ACC = _rows(
    "2025-10",
    [1100, 1106, 1115, 863, 761, 745, 707, 654, 739, 608, 744, 806],
    [0, 1, 10, 14, 14, 10, 9, 6, 11, 12, 4, 14],
)


# --- months -----------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    ["2026-09", "2026-09-14", "202609", "Sep 2026", "September 2026", "9/2026", "9/14/2026", "2026/09"],
)
def test_every_common_spelling_of_a_month_is_understood(raw):
    assert normalize_month(raw) == "2026-09"


def test_a_date_is_a_month_and_nonsense_is_refused():
    assert normalize_month(date(2026, 9, 30)) == "2026-09"
    for bad in ("2026-13", "soon", "", "13/2026"):
        with pytest.raises(ValueError):
            normalize_month(bad)


# --- csv --------------------------------------------------------------------


def test_csv_wide_form_with_organic_and_odd_headers():
    rows, errors = parse_csv("Month,Total Sessions,Organic Sessions,Form Fills\nSep 2026,\"1,226\",329,13\n2026-08,2928,332,8\n")
    assert errors == []
    assert [r.month for r in rows] == ["2026-08", "2026-09"]
    assert rows[1].sessions == 1226 and rows[1].organic_sessions == 329 and rows[1].leads == 13


def test_csv_lead_columns_are_summed_and_kept_by_event():
    rows, _ = parse_csv("month,sessions,lead_form,lead_call\n2026-09,1000,5,3\n")
    assert rows[0].leads == 8 and rows[0].by_event == {"form": 5, "call": 3}


def test_csv_bad_rows_are_reported_and_skipped_not_fatal():
    rows, errors = parse_csv("month,sessions,leads\n2026-07,100,4\nsoon,100,4\n2026-08,abc,1\n2026-07,100,9\n2026-09,100,-2\n")
    assert [r.month for r in rows] == ["2026-07"]
    assert len(errors) == 4 and "Row 3" in errors[0]


def test_csv_without_the_needed_columns_says_which():
    with pytest.raises(ValueError, match="sessions"):
        parse_csv("month,leads\n2026-09,3\n")
    with pytest.raises(ValueError, match="leads"):
        parse_csv("month,sessions\n2026-09,3\n")
    with pytest.raises(ValueError, match="No usable rows"):
        parse_csv("month,sessions,leads\nsoon,1,1\n")


# --- the numbers ------------------------------------------------------------


def test_sessions_come_from_the_last_three_months_not_the_whole_window():
    result = analyze(ACC, regime_start="2025-12")
    assert result["baseline"]["monthly_sessions"] == round((608 + 744 + 806) / 3, 1)
    assert result["window"]["months"] == 10


def test_the_regime_start_keeps_earlier_months_on_the_chart_but_out_of_the_numbers():
    result = analyze(ACC, regime_start="2025-12")
    in_window = {row["month"]: row["in_window"] for row in result["series"]}
    assert in_window["2025-10"] is False and in_window["2025-12"] is True
    assert result["window"]["regime_start_source"] == "given"


def test_lead_rate_is_decayed_so_a_recent_change_counts_more_than_a_flat_window():
    rising = _rows("2026-01", [1000] * 12, [5] * 6 + [20] * 6)
    decayed = analyze(rising)["baseline"]["lead_rate_pct"]
    flat = analyze(rising)["references"]["pooled_lead_rate_pct_window"]
    assert decayed > flat > 1.0


def test_baseline_leads_are_sessions_times_rate_so_the_three_numbers_agree():
    b = analyze(ACC, regime_start="2025-12")["baseline"]
    assert b["monthly_leads"] == pytest.approx(b["monthly_sessions"] * b["lead_rate_pct"] / 100, rel=0.01)


def test_acc_tek_from_its_first_clean_month_is_stable_and_plausible():
    result = analyze(ACC, regime_start="2025-12")
    assert 1.0 < result["baseline"]["lead_rate_pct"] < 1.8
    assert result["ranges"]["monthly_leads"]["pct"] == 35.0      # 104 leads: no widening
    assert result["status"] == "draft"


# --- ranges and the goal basis ---------------------------------------------


def test_the_goal_is_anchored_on_the_low_end_of_the_lead_range():
    result = analyze(ACC, regime_start="2025-12")
    leads, rng = result["baseline"]["monthly_leads"], result["ranges"]["monthly_leads"]
    assert result["goal_basis"]["monthly_leads"] == pytest.approx(leads * (1 - rng["pct"] / 100), abs=0.02)
    assert result["goal_basis"]["basis"] == "the low end of the lead range"
    # The projection is built from the goal basis; the point projection from the estimate.
    assert result["projection"]["baseline_monthly_leads"] == pytest.approx(result["goal_basis"]["monthly_leads"], abs=0.02)
    assert result["projection_point"]["baseline_monthly_leads"] == pytest.approx(leads, abs=0.02)
    assert result["projection"]["suggested_monthly_lead_goal"] < result["projection_point"]["suggested_monthly_lead_goal"]


def test_the_traffic_decline_in_the_projection_is_still_the_calculators_12_8_percent():
    point = analyze(ACC, regime_start="2025-12")["projection_point"]["checkpoints"]
    assert point[-1]["monthly_sessions"] == pytest.approx(point[0]["monthly_sessions"] * (1 - 0.128), rel=0.001)


def test_few_leads_widen_the_range_and_none_is_a_blocker():
    few = analyze(_rows("2026-01", [1000] * 8, [1, 0, 2, 1, 0, 1, 2, 1]))
    assert few["ranges"]["monthly_leads"]["pct"] > 35
    assert "low_volume" in {f["code"] for f in few["flags"]}
    none = analyze(_rows("2026-01", [1000] * 6, [0] * 6))
    assert none["ranges"]["monthly_leads"]["pct"] == 100.0
    assert "no_leads" in none["blockers"]


def test_a_higher_half_life_forgets_less():
    rows = _rows("2026-01", [1000] * 12, [5] * 6 + [20] * 6)
    fast = analyze(rows, half_life_months=1)["baseline"]["lead_rate_pct"]
    slow = analyze(rows, half_life_months=12)["baseline"]["lead_rate_pct"]
    assert fast > slow
    with pytest.raises(ValueError, match="half-life"):
        analyze(rows, half_life_months=0.1)


# --- regime, blockers and the lock ------------------------------------------


def test_the_relaunch_is_found_and_blocks_a_lock_until_it_is_dealt_with():
    result = analyze(SMA)
    assert result["window"]["suggested_regime_start"] == "2026-09"
    assert "regime_break_unconfirmed" in result["blockers"] and result["can_lock"] is False

    acknowledged = analyze(SMA, acknowledged=["regime_break_unconfirmed"])
    assert acknowledged["can_lock"] is True

    set_start = analyze(SMA, regime_start="2026-09")
    assert "regime_break_unconfirmed" not in set_start["blockers"] and set_start["can_lock"] is True


def test_a_single_month_in_the_new_regime_is_provisional():
    result = analyze(SMA, regime_start="2026-09")
    assert result["status"] == "provisional" and result["window"]["months"] == 1
    assert result["baseline"]["monthly_sessions"] == 1226
    assert "provisional" in {f["code"] for f in result["flags"]}


def test_tracking_that_started_late_is_a_blocker_inside_the_window_and_a_note_outside_it():
    inside = analyze(ACC)
    gap = next(f for f in inside["flags"] if f["code"] == "tracking_gap")
    assert gap["level"] == "blocker" and "2025-10" in gap["months"] and "2025-11" in gap["message"]
    assert inside["can_lock"] is False

    outside = analyze(ACC, regime_start="2025-12")
    codes = {f["code"]: f["level"] for f in outside["flags"]}
    assert codes["tracking_start"] == "info" and "tracking_gap" not in codes


def test_a_month_with_traffic_and_no_leads_mid_window_is_a_gap():
    rows = _rows("2026-01", [1000] * 8, [12, 11, 13, 0, 12, 14, 11, 13])
    flag = next(f for f in analyze(rows)["flags"] if f["code"] == "tracking_gap")
    assert flag["months"] == ["2026-04"]


def test_a_single_month_rise_at_the_end_is_not_read_as_a_new_site():
    rows = _rows("2026-01", [1000, 1010, 990, 1005, 995, 50_000], [5] * 6)
    result = analyze(rows)
    assert result["window"]["suggested_regime_start"] is None


def test_unfinished_months_are_left_out_unless_the_data_runs_to_the_last_day():
    rows = SMA + [MonthRow("2026-10", 340, 0)]
    mid = analyze(rows, as_of=date(2026, 10, 12))
    assert mid["series"][-1]["month"] == "2026-09"
    assert "partial_month_dropped" in {f["code"] for f in mid["flags"]}
    full = analyze(rows, as_of=date(2026, 10, 31))
    assert full["series"][-1]["month"] == "2026-10"


def test_a_missing_month_is_flagged_not_filled():
    rows = [r for r in _rows("2026-01", [1000] * 8, [10] * 8) if r.month != "2026-04"]
    flag = next(f for f in analyze(rows)["flags"] if f["code"] == "missing_months")
    assert flag["months"] == ["2026-04"]


# --- spikes, shifts and definitions ----------------------------------------


def test_a_spam_month_in_the_leads_is_flagged():
    rows = _rows("2026-01", [3000] * 10, [60, 58, 55, 519, 50, 61, 57, 52, 49, 55])
    assert "lead_spike" in {f["code"] for f in analyze(rows)["flags"]}


def test_bot_traffic_in_a_month_is_flagged():
    rows = _rows("2026-01", [25_000] * 9 + [92_838], [80] * 10)
    flag = next(f for f in analyze(rows)["flags"] if f["code"] == "traffic_spike")
    assert flag["months"] == ["2026-10"]


def test_a_recent_fall_is_called_out_against_the_months_before():
    rows = _rows("2026-01", [4000] * 9 + [2400, 2300, 2200], [20] * 12)
    codes = {f["code"] for f in analyze(rows)["flags"]}
    assert "recent_shift_sessions" in codes and "recent_shift_leads" not in codes


def test_a_lead_event_that_replaces_another_mid_window_is_flagged():
    rows = [
        MonthRow(bs.add_months("2026-01", i), 1000, 10, None, {"Lead Generated": 10} if i < 5 else {"Form Submit": 10})
        for i in range(10)
    ]
    flag = next(f for f in analyze(rows)["flags"] if f["code"] == "event_changed")
    assert "Lead Generated" in flag["message"] and "Form Submit" in flag["message"]


def test_blockers_sort_first_and_duplicate_months_are_refused():
    codes = [f["level"] for f in analyze(ACC)["flags"]]
    assert codes == sorted(codes, key={"blocker": 0, "warning": 1, "info": 2}.get)
    with pytest.raises(ValueError, match="more than once"):
        analyze(ACC + [ACC[0]])


def test_organic_sessions_are_reported_only_when_every_recent_month_has_them():
    organic = _rows("2026-01", [1000] * 6, [10] * 6, [400] * 6)
    assert analyze(organic)["baseline"]["monthly_organic_sessions"] == 400
    gappy = [*organic[:5], MonthRow("2026-06", 1000, 10, None)]
    assert analyze(gappy)["baseline"]["monthly_organic_sessions"] is None


def test_the_method_version_travels_with_every_result():
    assert analyze(ACC, regime_start="2025-12")["method_version"] == bs.METHOD_VERSION


# --- GA4 source and the API -------------------------------------------------


def _seed(db, client, *, first_day: date, days: int, through: date):
    from tests.test_baseline_snapshot import _daily_facts, _lead_definition, _watermark

    _lead_definition(db, client.id)
    _watermark(db, client.id, through)
    _daily_facts(db, client.id, start=first_day, days=days, sessions=100, leads=2)
    db.commit()


def test_ga4_months_are_summed_and_the_unfinished_one_is_dropped(db, client_a):
    _seed(db, client_a, first_day=date(2026, 1, 1), days=285, through=date(2026, 10, 12))
    rows, info = bs.series_from_ga4(db, client_a, months=24)
    assert rows[0].month == "2026-01" and rows[-1].month == "2026-10"
    assert rows[0].sessions == 31 * 100 and rows[0].leads == 31 * 2 and rows[0].organic_sessions == 3100
    result = analyze(rows, as_of=info["as_of"])
    assert result["series"][-1]["month"] == "2026-09"


def test_a_first_month_the_facts_only_partly_cover_is_left_out(db, client_a):
    _seed(db, client_a, first_day=date(2026, 1, 15), days=240, through=date(2026, 9, 30))
    rows, info = bs.series_from_ga4(db, client_a, months=24)
    assert rows[0].month == "2026-02" and info["notes"]


def test_the_ga4_source_needs_lead_events_and_data(db, client_a):
    with pytest.raises(ValueError, match="lead conversion"):
        bs.series_from_ga4(db, client_a)


def test_series_endpoint_from_ga4_and_from_csv(client, db, client_a, admin_user):
    _seed(db, client_a, first_day=date(2026, 1, 1), days=285, through=date(2026, 10, 12))
    headers = client_header(client_a.id, admin_user.email)

    got = client.get(
        f"/clients/{client_a.id}/baseline/series?regime_start=2026-03&acknowledge=tracking_gap", headers=headers
    )
    assert got.status_code == 200
    body = got.json()
    assert body["source"]["type"] == "ga4" and body["window"]["from"] == "2026-03"
    # Jul (31 days) + Aug (31) + Sep (30) at 100 a day, averaged.
    assert body["baseline"]["monthly_sessions"] == pytest.approx((3100 + 3100 + 3000) / 3, abs=0.1)
    assert body["can_lock"] is True

    posted = client.post(
        f"/clients/{client_a.id}/baseline/series",
        headers=headers,
        json={"csv_text": "month,sessions,leads\n2026-07,1000,10\n2026-08,1100,12\nbad,1,1\n", "regime_start": "2026-07"},
    )
    assert posted.status_code == 200
    assert posted.json()["source"]["skipped_rows"] and posted.json()["window"]["months"] == 2


def test_the_endpoints_say_what_is_wrong_in_words(client, db, client_a, admin_user):
    headers = client_header(client_a.id, admin_user.email)
    bad = client.post(
        f"/clients/{client_a.id}/baseline/series", headers=headers, json={"csv_text": "month,leads\n2026-07,3\n"}
    )
    assert bad.status_code == 400 and "sessions" in bad.json()["detail"]
    nodata = client.get(f"/clients/{client_a.id}/baseline/series", headers=headers)
    assert nodata.status_code == 400 and "lead conversion" in nodata.json()["detail"]
