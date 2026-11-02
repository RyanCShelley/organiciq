"""The monthly review: calendar-month maths, the summary wording, and revenue."""

from __future__ import annotations

from datetime import date

import pytest

from app.models.integration import ConnectionStatus, Integration, IntegrationProvider
from app.services import monthly_review as mr
from tests.conftest import client_header


def test_month_ranges_and_the_month_before():
    assert mr.parse_month("2026-09") == (date(2026, 9, 1), date(2026, 9, 30))
    assert mr.parse_month("2028-02")[1] == date(2028, 2, 29)
    assert mr.previous_month("2026-01") == "2025-12"
    assert mr.previous_month("2026-09") == "2026-08"
    assert mr.last_complete_month(date(2026, 10, 29)) == "2026-09"
    assert mr.last_complete_month(date(2027, 1, 3)) == "2026-12"


@pytest.mark.parametrize("bad", ["", "2026-13", "2026-9", "September", "2026-00"])
def test_a_bad_month_is_refused(bad):
    with pytest.raises(ValueError):
        mr.parse_month(bad)


def test_percentage_change_handles_missing_and_zero():
    assert mr.pct_change(218, 116) == 87.9
    assert mr.pct_change(5, 0) is None
    assert mr.pct_change(None, 3) is None
    assert mr.pct_change(0, 4) == -100.0


def _dash(*, sessions, leads, organic_sessions=0, organic_leads=0, clicks=0, impressions=0, goal=None, progress=None):
    return {
        "traffic": {
            "ga4_sessions": {"current": sessions},
            "gsc_clicks": {"current": clicks},
            "by_channel": [{"channel": "organic_search", "label": "Organic Search", "sessions": organic_sessions, "conversions": organic_leads}],
            "top_pages": [{"page": "https://x.test/", "ga4_sessions": 10, "previous_ga4_sessions": 8, "ga4_key_events": 2, "gsc_clicks": 1}] * 7,
        },
        "conversions": {
            "leads": {"current": leads},
            "lead_rate": {"current": 3.0},
            "leads_by_channel": [{"channel": "organic_search", "leads": organic_leads}],
            "period_lead_goal": goal,
            "goal_progress_pct": progress,
            "final_lead_goal": 288,
            "goal_checkpoint": {"month": 3, "projected": 192},
        },
        "visibility": {"search": {"gsc_impressions": {"current": impressions}, "average_position": {"current": None}, "keyword_distribution": {"top_3": 1}}},
        "baseline": {"projection": {"baseline_version": 1}},
        "service_reporting": {"settings": {"organiciq": True}, "rows": [], "outside_services": None, "note": "n"},
        "freshness": [{"source": "ga4", "available": True}, {"source": "se_ranking_ai", "available": False}],
    }


def test_the_review_compares_with_the_calendar_month_before_and_reads_the_goal():
    review = mr.assemble(
        _dash(sessions=6407, leads=218, organic_sessions=574, organic_leads=24, goal=192, progress=113.5),
        _dash(sessions=9723, leads=116, organic_sessions=748, organic_leads=15),
        month="2026-09", model="ecommerce", revenue=None,
    )
    assert review["noun"] == "orders" and review["previous_month"] == "2026-08"
    assert review["conversions"] == {"current": 218.0, "previous": 116.0, "change_pct": 87.9}
    assert review["sessions"]["change_pct"] == -34.1
    assert review["organic_conversions"]["current"] == 24.0
    assert review["goal"]["period_goal"] == 192 and review["goal"]["baseline_version"] == 1
    assert len(review["top_pages"]) == 5


def test_the_summary_says_what_moved_and_what_is_missing():
    review = mr.assemble(
        _dash(sessions=6407, leads=218, organic_sessions=574, goal=192, progress=113.5),
        _dash(sessions=9723, leads=116, organic_sessions=748),
        month="2026-09", model="ecommerce", revenue=None,
    )
    text = " ".join(review["summary"])
    assert "Orders: 218 in 2026-09, up 88% on 2026-08 (116)" in text
    assert "114% of this period's goal of 192" in text
    assert "Sessions: 6,407, down 34%" in text
    assert "no Search Console data" in text  # clicks and impressions are zero
    assert "No data yet from: se_ranking_ai" in text


def test_search_numbers_appear_only_when_there_are_some():
    with_search = mr.assemble(
        _dash(sessions=100, leads=5, clicks=420, impressions=9000),
        _dash(sessions=100, leads=5, clicks=300, impressions=8000),
        month="2026-09", model=None, revenue=None,
    )
    assert with_search["has_search_data"] is True and with_search["noun"] == "leads"
    assert "Search Console: 420 clicks, up 40% on 2026-08" in " ".join(with_search["summary"])


def test_revenue_in_the_summary_names_the_organic_share():
    revenue = {
        "status": "measured",
        "revenue": {"current": 15000.0, "previous": 12000.0, "change_pct": 25.0},
        "organic_revenue": {"current": 2100.0, "previous": 1800.0, "change_pct": 16.7},
    }
    review = mr.assemble(_dash(sessions=1, leads=1), _dash(sessions=1, leads=1), month="2026-09", model="ecommerce", revenue=revenue)
    assert "Revenue: 15,000 in 2026-09, up 25% on 2026-08; 2,100 of it came through organic search." in review["summary"]


def test_unreadable_revenue_is_said_not_hidden():
    review = mr.assemble(
        _dash(sessions=1, leads=1), _dash(sessions=1, leads=1), month="2026-09", model="ecommerce",
        revenue={"status": "unavailable", "reason": "GA4 is not connected for this client."},
    )
    assert any("Revenue could not be read: GA4 is not connected" in line for line in review["summary"])


def _ga4(db, client_a, monkeypatch, report):
    row = (
        db.query(Integration)
        .filter(Integration.client_id == client_a.id, Integration.provider == IntegrationProvider.GA4)
        .one_or_none()
    )
    if row is None:
        row = Integration(client_id=client_a.id, provider=IntegrationProvider.GA4)
        db.add(row)
    row.external_property_id = "properties/1"
    row.connection_status = ConnectionStatus.CONNECTED
    db.commit()
    monkeypatch.setattr(mr, "run_report", report)
    monkeypatch.setattr(mr, "access_token_for_client", lambda db, cid: "t")
    monkeypatch.setattr(mr, "client_has_google_credentials", lambda db, cid: True)
    mr._REVENUE_CACHE.clear()


def _row(channel, revenue, orders):
    return {"dimensionValues": [{"value": channel}], "metricValues": [{"value": str(revenue)}, {"value": str(orders)}]}


def test_revenue_splits_organic_from_the_rest_and_compares_months(db, client_a, monkeypatch):
    def report(**kw):
        september = kw["start_date"] == date(2026, 9, 1)
        return (
            [_row("Organic Search", 2000, 20), _row("Direct", 8000, 70), _row("Paid Search", 1000, 10)]
            if september
            else [_row("Organic Search", 1000, 10), _row("Direct", 7000, 60)]
        )

    _ga4(db, client_a, monkeypatch, report)
    out = mr.revenue_for(db, client_a, "2026-09")
    assert out["status"] == "measured"
    assert out["revenue"] == {"current": 11000.0, "previous": 8000.0, "change_pct": 37.5}
    assert out["organic_revenue"]["current"] == 2000.0 and out["organic_revenue"]["change_pct"] == 100.0
    assert out["orders"]["current"] == 100.0
    assert out["average_order_value"]["current"] == 110.0


def test_a_revenue_failure_is_reported_and_not_cached(db, client_a, monkeypatch):
    def broken(**kw):
        raise RuntimeError("quota")

    _ga4(db, client_a, monkeypatch, broken)
    out = mr.revenue_for(db, client_a, "2026-09")
    assert out["status"] == "unavailable" and "quota" in out["reason"]
    assert ("%s" % client_a.id, "2026-09") not in mr._REVENUE_CACHE


def test_revenue_is_cached_briefly(db, client_a, monkeypatch):
    calls = []

    def report(**kw):
        calls.append(kw["start_date"])
        return [_row("Organic Search", 10, 1)]

    _ga4(db, client_a, monkeypatch, report)
    mr.revenue_for(db, client_a, "2026-09")
    mr.revenue_for(db, client_a, "2026-09")
    assert len(calls) == 2  # this month and last, once


def test_the_route_refuses_a_bad_month(client, db, client_a, admin_user):
    response = client.get("/v2/review?month=2026-13", headers=client_header(client_a.id, admin_user.email))
    assert response.status_code == 400


def test_the_summary_is_also_laid_out_in_sections_to_skim():
    review = mr.assemble(
        _dash(sessions=6407, leads=218, organic_sessions=574, goal=192, progress=113.5),
        _dash(sessions=9723, leads=116, organic_sessions=748),
        month="2026-09", model="ecommerce", revenue=None,
    )
    by_title = {s["title"]: {r["label"]: r for r in s["rows"]} for s in review["summary_sections"]}
    orders = by_title["Results"]["Orders"]
    assert orders["value"] == "218" and orders["change"]["text"] == "up 88%" and orders["change"]["tone"] == "good"
    assert orders["detail"] == "114% of this period's goal of 192"
    sessions = by_title["Traffic"]["Sessions"]
    assert sessions["change"] == {"text": "down 34%", "tone": "bad", "against": "on 2026-08 (9,723)"}
    assert "No data for this month" in by_title["Traffic"]["Search Console"]["detail"]


def test_the_visibility_section_names_each_ai_platform_and_the_brand_check():
    pair = lambda cur, prev=None, delta=None: {"current": cur, "previous": prev, "delta": delta}
    review = mr.assemble(_dash(sessions=100, leads=5), _dash(sessions=100, leads=5), month="2026-10", model=None, revenue=None)
    review["visibility"] = {
        "summary": {"terms": 18, "showing_in_google": 6, "on_page_one": 2, "showing_in_bing": 1, "google_impressions": 2699, "google_clicks": 3, "prompts": 12},
        "bing": {"has_data": True},
        "llm": {
            "run_date": "2026-11-02", "in_month": False,
            "summary": {"mentions": pair(0), "citations": pair(0), "visibility_rate": pair(0.0, 0.1, -0.1), "responses": 20},
            "platforms": [{"platform": "openai", "visibility_rate": pair(0.0)}, {"platform": "anthropic", "visibility_rate": pair(0.25)}],
            "brand_check": [{"platform": "openai", "answers": 6, "site_cited": 2}, {"platform": "gemini", "answers": 6, "site_cited": 1}],
        },
    }
    rows = {r["label"]: r for s in mr.sections(review) if s["title"] == "Visibility" for r in s["rows"]}
    assert rows["Google"]["value"] == "6 of 18 terms" and "2 averaging page one" in rows["Google"]["detail"]
    assert rows["AI platforms"]["change"]["text"] == "down 10 points" and "after 2026-10" in rows["AI platforms"]["detail"]
    assert rows["By platform"]["value"] == "ChatGPT 0% · Claude 25%"
    assert rows["Brand check"]["value"] == "3 of 12 answers"


# ---- a finished month is worked out once and kept ----------------------------------------------------------

from datetime import date as _date  # noqa: E402

from app.models.monthly_review import MonthlyReviewSnapshot  # noqa: E402


def _stub(monkeypatch, through, built):
    monkeypatch.setattr(mr, "data_through", lambda db, client: through)

    def build(db, client, month):
        built.append(month)
        return {"month": month, "summary": [f"built {len(built)} times"], "summary_sections": []}

    monkeypatch.setattr(mr, "build_review", build)


def test_a_finished_month_with_complete_data_is_built_once_and_then_read_back(db, client_a, monkeypatch):
    built = []
    _stub(monkeypatch, {"search_console": _date(2026, 10, 31), "ga4": _date(2026, 11, 1)}, built)
    monkeypatch.setattr(mr, "lock_status", lambda m, t, today=None: (True, None))
    first = mr.review_for(db, client_a, "2026-10", who="ryan@example.com")
    again = mr.review_for(db, client_a, "2026-10")
    assert built == ["2026-10"]  # the second call read the kept copy
    assert first["locked"] is True and again["locked"] is True and again["summary"] == ["built 1 times"]
    assert again["locked_by"] == "ryan@example.com" and again["data_through"]["search_console"] == "2026-10-31"
    assert db.query(MonthlyReviewSnapshot).count() == 1


def test_a_month_whose_data_is_not_complete_yet_is_not_locked_and_says_why(db, client_a, monkeypatch):
    built = []
    _stub(monkeypatch, {"search_console": _date(2026, 10, 28), "ga4": _date(2026, 11, 1)}, built)
    out = mr.review_for(db, client_a, "2026-10")
    mr.review_for(db, client_a, "2026-10")
    assert out["locked"] is False and "Search Console reaches Oct 28" in out["lock_note"] and "Not locked" not in out["lock_note"] and "Oct 31" in out["lock_note"]
    assert built == ["2026-10", "2026-10"] and db.query(MonthlyReviewSnapshot).count() == 0


def test_the_lock_rule_by_itself():
    full = {"search_console": _date(2026, 10, 31), "ga4": _date(2026, 10, 31)}
    assert mr.lock_status("2026-10", full, today=_date(2026, 11, 2)) == (True, None)
    assert mr.lock_status("2026-11", full, today=_date(2026, 11, 20))[0] is False  # still in progress
    assert mr.lock_status("2026-10", {"search_console": None, "ga4": None}, today=_date(2026, 11, 2))[0] is False
    only_ga4 = {"search_console": None, "ga4": _date(2026, 10, 31)}
    assert mr.lock_status("2026-10", only_ga4, today=_date(2026, 11, 2)) == (True, None)  # a client without Search Console data


def test_running_again_replaces_the_kept_copy(db, client_a, monkeypatch):
    built = []
    _stub(monkeypatch, {"search_console": _date(2026, 10, 31), "ga4": _date(2026, 10, 31)}, built)
    monkeypatch.setattr(mr, "lock_status", lambda m, t, today=None: (True, None))
    mr.review_for(db, client_a, "2026-10")
    out = mr.review_for(db, client_a, "2026-10", rerun=True, who="ryan@example.com")
    assert built == ["2026-10", "2026-10"] and out["summary"] == ["built 2 times"] and out["locked_by"] == "ryan@example.com"
    assert db.query(MonthlyReviewSnapshot).count() == 1


def test_the_review_endpoint_reads_the_kept_copy_and_rerun_is_available(client, db, client_a, admin_user, monkeypatch):
    from tests.conftest import client_header

    built = []
    _stub(monkeypatch, {"search_console": _date(2026, 10, 31), "ga4": _date(2026, 10, 31)}, built)
    monkeypatch.setattr(mr, "lock_status", lambda m, t, today=None: (True, None))
    h = client_header(client_a.id, admin_user.email)
    assert client.get("/v2/review?month=2026-10", headers=h).json()["locked"] is True
    assert client.get("/v2/review?month=2026-10", headers=h).json()["summary"] == ["built 1 times"]
    assert client.post("/v2/review/rerun?month=2026-10", headers=h).json()["summary"] == ["built 2 times"]
    assert client.post("/v2/review/rerun?month=nope", headers=h).status_code == 400
