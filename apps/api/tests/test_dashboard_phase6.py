from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from app.models.config import ConversionDefinition, OrganicChannel
from app.models.ga4 import FactGa4Event, FactGa4Traffic
from app.models.gsc import FactGscDaily, FactGscPage
from app.models.job import DataWatermark, ValidationStatus
from app.models.seranking import (
    FactSerAiTrackerStats,
    FactSerCompetitor,
    FactSerKeyword,
    FactSerSiteSummary,
)
from app.services.dashboard import (
    build_dashboard,
    period_lead_goal,
    previous_period,
    _ai_tracker_metrics,
    _search_sov,
)
from tests.conftest import client_header, date_window


def _watermark(db, client_id, source: str, fact_through: date) -> None:
    db.add(
        DataWatermark(
            id=uuid4(),
            client_id=client_id,
            source=source,
            fact_through_date=fact_through,
            validation_status=ValidationStatus.PASSED,
        )
    )


def test_period_lead_goal_scales_to_dashboard_window():
    start = date(2026, 6, 4)
    end = date(2026, 9, 1)
    goal, days = period_lead_goal(25, start, end)
    assert days == 90
    assert goal == 75

    monthly_goal, monthly_days = period_lead_goal(25, date(2026, 8, 1), date(2026, 8, 30))
    assert monthly_days == 30
    assert monthly_goal == 25


def test_dashboard_lead_goal_progress_uses_period_target(db, client_a):
    start = date(2026, 6, 4)
    end = date(2026, 9, 1)
    client_a.monthly_lead_goal = 25
    _watermark(db, client_a.id, "ga4", end)
    db.add(
        ConversionDefinition(
            id=uuid4(),
            client_id=client_a.id,
            event_name="generate_lead",
            conversion_name="Lead",
            conversion_type="lead",
            is_primary=True,
            active=True,
        )
    )
    db.add(
        FactGa4Event(
            id=uuid4(),
            client_id=client_a.id,
            date=end,
            raw_url="https://example.com/",
            normalized_url="https://example.com/",
            session_source="google",
            session_medium="organic",
            channel=OrganicChannel.ORGANIC_SEARCH,
            event_name="generate_lead",
            event_count=30,
        )
    )
    db.commit()

    payload = build_dashboard(db, client_a, start, end)
    assert payload["conversions"]["monthly_lead_goal"] == 25
    assert payload["conversions"]["period_lead_goal"] == 75
    assert payload["conversions"]["goal_period_days"] == 90
    assert payload["conversions"]["goal_progress_pct"] == 40.0


def test_dashboard_aggregates_validated_facts(db, client, client_a, admin_user):
    start, end = date_window(7)
    prev_start, prev_end = previous_period(start, end)

    _watermark(db, client_a.id, "ga4", end)
    _watermark(db, client_a.id, "gsc_pages", end)
    _watermark(db, client_a.id, "se_ranking_search", end)
    _watermark(db, client_a.id, "se_ranking_ai", end)

    db.add(
        ConversionDefinition(
            id=uuid4(),
            client_id=client_a.id,
            event_name="generate_lead",
            conversion_name="Lead",
            conversion_type="lead",
            is_primary=True,
            active=True,
        )
    )

    db.add(
        FactGa4Event(
            id=uuid4(),
            client_id=client_a.id,
            date=end,
            raw_url="https://example.com/",
            normalized_url="https://example.com/",
            session_source="google",
            session_medium="organic",
            channel=OrganicChannel.ORGANIC_SEARCH,
            event_name="generate_lead",
            event_count=3,
        )
    )
    db.add(
        FactGa4Event(
            id=uuid4(),
            client_id=client_a.id,
            date=prev_end,
            raw_url="https://example.com/",
            normalized_url="https://example.com/",
            session_source="google",
            session_medium="organic",
            channel=OrganicChannel.ORGANIC_SEARCH,
            event_name="generate_lead",
            event_count=1,
        )
    )
    db.add(
        FactGa4Traffic(
            id=uuid4(),
            client_id=client_a.id,
            date=end,
            raw_url="https://example.com/",
            normalized_url="https://example.com/",
            session_source="google",
            session_medium="organic",
            channel=OrganicChannel.ORGANIC_SEARCH,
            sessions=Decimal("100"),
            active_users=Decimal("80"),
            views=Decimal("150"),
        )
    )
    db.add(
        FactGa4Traffic(
            id=uuid4(),
            client_id=client_a.id,
            date=prev_end,
            raw_url="https://example.com/",
            normalized_url="https://example.com/",
            session_source="google",
            session_medium="organic",
            channel=OrganicChannel.ORGANIC_SEARCH,
            sessions=Decimal("50"),
            active_users=Decimal("40"),
            views=Decimal("60"),
        )
    )
    db.add(
        FactGscDaily(
            id=uuid4(),
            client_id=client_a.id,
            date=end,
            impressions=Decimal("1000"),
            clicks=Decimal("40"),
            ctr=Decimal("0.04"),
            average_position=Decimal("5"),
        )
    )
    db.add(
        FactGscDaily(
            id=uuid4(),
            client_id=client_a.id,
            date=prev_end,
            impressions=Decimal("500"),
            clicks=Decimal("10"),
            ctr=Decimal("0.02"),
            average_position=Decimal("8"),
        )
    )
    db.add(
        FactGscPage(
            id=uuid4(),
            client_id=client_a.id,
            date=end,
            raw_url="https://example.com/page",
            normalized_url="https://example.com/page",
            country="",
            device="",
            impressions=Decimal("1000"),
            clicks=Decimal("40"),
            ctr=Decimal("0.04"),
            average_position=Decimal("5"),
        )
    )
    db.add(
        FactGscPage(
            id=uuid4(),
            client_id=client_a.id,
            date=prev_end,
            raw_url="https://example.com/page",
            normalized_url="https://example.com/page",
            country="",
            device="",
            impressions=Decimal("500"),
            clicks=Decimal("10"),
            ctr=Decimal("0.02"),
            average_position=Decimal("8"),
        )
    )
    db.add(
        FactSerKeyword(
            id=uuid4(),
            client_id=client_a.id,
            site_engine_id="1",
            keyword_id="kw1",
            keyword="brand term",
            current_position=Decimal("4"),
            visibility=Decimal("12.5"),
            checked_at=end,
        )
    )
    db.add(
        FactSerAiTrackerStats(
            id=uuid4(),
            client_id=client_a.id,
            metric_date=end,
            prompts_count=40,
            mention_presence_pct=Decimal("2.5"),
            link_presence_pct=Decimal("5"),
            mention_top3_pct=Decimal("2.5"),
            link_top3_pct=Decimal("5"),
        )
    )
    db.commit()

    payload = build_dashboard(db, client_a, start, end)
    assert payload["conversions"]["configured"] is True
    assert payload["conversions"]["leads"]["current"] == 3
    assert payload["conversions"]["leads"]["previous"] == 1
    assert payload["conversions"]["lead_rate"]["current"] == 3.0
    assert payload["traffic"]["gsc_clicks"]["current"] == 40.0
    assert payload["traffic"]["ga4_sessions"]["current"] == 100.0
    assert payload["visibility"]["search"]["gsc_impressions"]["current"] == 1000.0
    assert payload["visibility"]["ai"]["mention_presence"]["current"] == 2.5
    assert payload["visibility"]["ai"]["link_presence"]["current"] == 5.0
    assert payload["visibility"]["ai"]["mention_top3_presence"]["current"] == 2.5
    assert payload["visibility"]["ai"]["link_top3_presence"]["current"] == 5.0
    assert payload["visibility"]["ai"]["tracked_prompt_source"] == "airt_statistics"
    assert payload["visibility"]["ai"]["prompt_count"] == 40


def test_dashboard_respects_watermark_cutoff(db, client, client_a, admin_user):
    start, end = date_window(7)
    cutoff = end - timedelta(days=2)
    _watermark(db, client_a.id, "ga4", cutoff)

    db.add(
        FactGa4Traffic(
            id=uuid4(),
            client_id=client_a.id,
            date=end,
            raw_url="https://example.com/",
            normalized_url="https://example.com/",
            session_source="direct",
            session_medium="(none)",
            channel=OrganicChannel.DIRECT_UNATTRIBUTED,
            sessions=Decimal("999"),
            active_users=Decimal("999"),
            views=Decimal("999"),
        )
    )
    db.commit()

    payload = build_dashboard(db, client_a, start, end)
    assert payload["traffic"]["ga4_sessions"]["current"] == 0.0


def test_dashboard_api_endpoint(db, client, client_a, admin_user):
    start, end = date_window(3)
    _watermark(db, client_a.id, "ga4", end)
    db.commit()

    res = client.get(
        f"/dashboard?from={start.isoformat()}&to={end.isoformat()}",
        headers=client_header(client_a.id, admin_user.email),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["period"]["from"] == start.isoformat()
    assert "freshness" in body


def test_dashboard_requires_valid_date_range(db, client, client_a, admin_user):
    res = client.get(
        "/dashboard?from=2026-08-10&to=2026-08-01",
        headers=client_header(client_a.id, admin_user.email),
    )
    assert res.status_code == 400


def test_dashboard_client_isolation(db, client, client_a, client_b, admin_user):
    start, end = date_window(3)
    _watermark(db, client_a.id, "ga4", end)
    _watermark(db, client_b.id, "ga4", end)

    db.add(
        FactGa4Traffic(
            id=uuid4(),
            client_id=client_a.id,
            date=end,
            raw_url="https://a.example/",
            normalized_url="https://a.example/",
            session_source="google",
            session_medium="organic",
            channel=OrganicChannel.ORGANIC_SEARCH,
            sessions=Decimal("10"),
            active_users=Decimal("8"),
            views=Decimal("12"),
        )
    )
    db.add(
        FactGa4Traffic(
            id=uuid4(),
            client_id=client_b.id,
            date=end,
            raw_url="https://b.example/",
            normalized_url="https://b.example/",
            session_source="google",
            session_medium="organic",
            channel=OrganicChannel.ORGANIC_SEARCH,
            sessions=Decimal("99"),
            active_users=Decimal("80"),
            views=Decimal("120"),
        )
    )
    db.commit()

    res_a = client.get(
        f"/dashboard?from={start.isoformat()}&to={end.isoformat()}",
        headers=client_header(client_a.id, admin_user.email),
    )
    res_b = client.get(
        f"/dashboard?from={start.isoformat()}&to={end.isoformat()}",
        headers=client_header(client_b.id, admin_user.email),
    )
    assert res_a.json()["traffic"]["ga4_sessions"]["current"] == 10.0
    assert res_b.json()["traffic"]["ga4_sessions"]["current"] == 99.0


def test_dashboard_uses_site_summary_visibility(db, client_a):
    end = date.today()
    start = end
    _watermark(db, client_a.id, "se_ranking_search", end)
    db.add(
        FactSerSiteSummary(
            id=uuid4(),
            client_id=client_a.id,
            metric_date=end,
            visibility=Decimal("19"),
            visibility_percent=Decimal("0.08"),
        )
    )
    db.commit()

    payload = build_dashboard(db, client_a, start, end)
    assert payload["visibility"]["search"]["search_visibility"]["current"] == 0.08
    assert payload["visibility"]["search"]["search_visibility_source"] == "site_summary"


def test_search_sov_from_competitor_visibility(db, client_a):
    end = date.today()
    start = end
    period = (start, end)
    _watermark(db, client_a.id, "se_ranking_search", end)

    db.add(
        FactSerSiteSummary(
            id=uuid4(),
            client_id=client_a.id,
            metric_date=end,
            visibility_percent=Decimal("0.08"),
        )
    )
    competitors = [
        ("c1", "16.26"),
        ("c2", "57.01"),
        ("c3", "46.85"),
        ("c4", "0"),
        ("c5", "0.59"),
    ]
    for competitor_id, visibility in competitors:
        db.add(
            FactSerCompetitor(
                id=uuid4(),
                client_id=client_a.id,
                site_engine_id="1315387",
                competitor_id=competitor_id,
                name=competitor_id,
                url=f"https://{competitor_id}.example/",
                visibility=Decimal(visibility),
                metric_date=end,
            )
        )
    db.commit()

    sov = _search_sov(db, client_a.id, period)
    assert sov is not None
    assert round(sov, 4) == 0.0662

    payload = build_dashboard(db, client_a, start, end)
    assert payload["visibility"]["search"]["search_sov"]["current"] == sov
    assert payload["visibility"]["search"]["search_sov_source"] == "competitor_visibility"


def test_ai_tracker_presence_from_facts(db, client_a):
    end = date.today()
    start = end
    _watermark(db, client_a.id, "se_ranking_ai", end)
    db.add(
        FactSerAiTrackerStats(
            id=uuid4(),
            client_id=client_a.id,
            metric_date=end,
            prompts_count=40,
            mention_presence_pct=Decimal("3"),
            link_presence_pct=Decimal("5"),
            mention_top3_pct=Decimal("3"),
            link_top3_pct=Decimal("5"),
        )
    )
    db.commit()

    metrics = _ai_tracker_metrics(db, client_a.id, (start, end))
    assert metrics["mention_presence"] == 3.0
    assert metrics["link_presence"] == 5.0
    assert metrics["mention_top3"] == 3.0
    assert metrics["link_top3"] == 5.0
    assert metrics["prompt_count"] == 40

    payload = build_dashboard(db, client_a, start, end)
    assert payload["visibility"]["ai"]["mention_presence"]["current"] == 3.0
    assert payload["visibility"]["ai"]["link_presence"]["current"] == 5.0
    assert payload["visibility"]["ai"]["mention_top3_presence"]["current"] == 3.0
    assert payload["visibility"]["ai"]["link_top3_presence"]["current"] == 5.0
    assert payload["visibility"]["ai"]["tracked_prompt_source"] == "airt_statistics"
