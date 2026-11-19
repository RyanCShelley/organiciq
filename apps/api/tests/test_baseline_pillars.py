"""Tests for the 3-pillar baseline snapshot (Visibility, Traffic, Leads) and CSV export."""

from __future__ import annotations

import csv
import io
from datetime import date, datetime, timezone
from decimal import Decimal

from app.models.bing_stats import FactBingQueryStat
from app.models.client import Client
from app.models.config import OrganicChannel
from app.models.ga4 import FactGa4Event, FactGa4Traffic
from app.models.gsc import FactGscDaily
from app.models.llm_visibility import LlmResponse, LlmRun
from app.models.seranking import FactSerRanking
from app.models.site_health import SiteHealthSnapshot
from app.models.watchlist import WatchlistBucket, WatchlistKeyword
from app.services.baseline_pillars import build_pillars_snapshot, pillars_to_csv
from tests.conftest import client_header


def test_build_pillars_snapshot_and_csv(db, client_a: Client):
    as_of = date(2026, 11, 18)

    # Visibility: GSC (1 day in 30d window, 1 day earlier in 90d window)
    db.add_all([
        FactGscDaily(
            client_id=client_a.id,
            gsc_site_url="sc-domain:example.com",
            date=date(2026, 11, 10),
            clicks=Decimal("30"),
            impressions=Decimal("300"),
            ctr=Decimal("0.10"),
            average_position=Decimal("5.0"),
        ),
        FactGscDaily(
            client_id=client_a.id,
            gsc_site_url="sc-domain:example.com",
            date=date(2026, 9, 10),
            clicks=Decimal("60"),
            impressions=Decimal("600"),
            ctr=Decimal("0.10"),
            average_position=Decimal("8.0"),
        ),
    ])

    # Visibility: Bing
    db.add(
        FactBingQueryStat(
            client_id=client_a.id,
            week_start=date(2026, 11, 9),
            query="organic seo",
            query_key="organic seo",
            impressions=100,
            clicks=15,
            avg_impression_position=Decimal("4.0"),
        )
    )

    # Visibility: Watchlist + SERP ranking
    bucket = WatchlistBucket(client_id=client_a.id, name="Core", name_key="core", sort_order=0)
    db.add(bucket)
    db.flush()
    db.add(
        WatchlistKeyword(
            client_id=client_a.id,
            bucket_id=bucket.id,
            keyword="organic seo",
            keyword_key="organic seo",
            paired_ai_prompt="Who is best for organic seo?",
        )
    )
    db.add(
        FactSerRanking(
            client_id=client_a.id,
            date=date(2026, 11, 15),
            site_engine_id="1",
            keyword_id="kw1",
            keyword="organic seo",
            position=Decimal("3"),
        )
    )

    # Visibility: LLM + SoV
    run = LlmRun(
        client_id=client_a.id,
        started_at=datetime(2026, 11, 18, 10, 0, tzinfo=timezone.utc),
        status="completed",
        platforms=["ChatGPT"],
    )
    db.add(run)
    db.flush()
    db.add(
        LlmResponse(
            run_id=run.id,
            client_id=client_a.id,
            query_text="Who is best for organic seo?",
            platform="ChatGPT",
            visibility_type="Cited + Mentioned",
            asked_by_name=False,
            brand_mentioned=True,
            url_cited=True,
        )
    )

    # Visibility: Site Health
    db.add(
        SiteHealthSnapshot(
            client_id=client_a.id,
            month="2026-11",
            crawl_date=date(2026, 11, 12),
            payload={"seo": {"score": 92}, "geo": {"score": 71}},
        )
    )

    # Traffic: GA4 (organic + direct across 30d and 90d)
    db.add_all([
        FactGa4Traffic(
            client_id=client_a.id,
            date=date(2026, 11, 10),
            raw_url="https://example.com/services",
            normalized_url="/services",
            channel=OrganicChannel.ORGANIC_SEARCH,
            sessions=Decimal("120"),
        ),
        FactGa4Traffic(
            client_id=client_a.id,
            date=date(2026, 9, 10),
            raw_url="https://example.com/",
            normalized_url="/",
            channel=OrganicChannel.DIRECT_UNATTRIBUTED,
            sessions=Decimal("180"),
        ),
    ])

    # Leads: GA4 events
    db.add_all([
        FactGa4Event(
            client_id=client_a.id,
            date=date(2026, 11, 10),
            raw_url="https://example.com/services",
            normalized_url="/services",
            channel=OrganicChannel.ORGANIC_SEARCH,
            event_name="form_submit",
            event_count=6,
        ),
        FactGa4Event(
            client_id=client_a.id,
            date=date(2026, 9, 10),
            raw_url="https://example.com/",
            normalized_url="/",
            channel=OrganicChannel.ORGANIC_SEARCH,
            event_name="form_submit",
            event_count=9,
        ),
    ])
    db.commit()

    pillars = build_pillars_snapshot(db, client_a, as_of=as_of, lead_events=["form_submit"])

    # Visibility assertions
    assert pillars["visibility"]["gsc"]["clicks"]["recent_30d"] == 30.0
    assert pillars["visibility"]["gsc"]["clicks"]["total_90d"] == 90.0
    assert pillars["visibility"]["gsc"]["clicks"]["avg_30d"] == 30.0
    assert pillars["visibility"]["bing"]["clicks"]["total_90d"] == 15.0
    assert pillars["visibility"]["watchlist"]["tracked_keywords"] == 1
    assert pillars["visibility"]["watchlist"]["paired_ai_prompts"] == 1
    assert pillars["visibility"]["watchlist"]["top_3"] == 1
    assert pillars["visibility"]["llm"]["visibility_rate_pct"] == 100.0
    assert pillars["visibility"]["llm"]["share_of_voice_pct"] == 100.0
    assert pillars["visibility"]["site_health"]["seo_score"] == 92
    assert pillars["visibility"]["site_health"]["geo_score"] == 71

    # Traffic assertions
    assert pillars["traffic"]["total_sessions"]["recent_30d"] == 120.0
    assert pillars["traffic"]["total_sessions"]["total_90d"] == 300.0
    assert pillars["traffic"]["total_sessions"]["avg_30d"] == 100.0
    assert pillars["traffic"]["organic_sessions"]["total_90d"] == 120.0
    assert len(pillars["traffic"]["top_pages"]) == 2

    # Leads assertions
    assert pillars["leads"]["total"]["recent_30d"] == 6.0
    assert pillars["leads"]["total"]["total_90d"] == 15.0
    assert pillars["leads"]["total"]["avg_30d"] == 5.0
    assert pillars["leads"]["lead_rate_30d_pct"] == 5.0
    assert pillars["leads"]["lead_rate_90d_pct"] == 5.0

    # CSV export assertions
    csv_text = pillars_to_csv(pillars)
    rows = list(csv.reader(io.StringIO(csv_text)))
    assert rows[0] == ["Pillar", "Category", "Metric / Item", "30-Day Avg", "Last 30 Days", "90-Day Total", "Notes"]
    pillars_present = {r[0] for r in rows[1:]}
    assert pillars_present == {"Visibility", "Traffic", "Leads"}


def test_baseline_pillars_endpoints(client, client_a: Client, admin_user):
    headers = client_header(client_a.id, admin_user.email)
    res = client.get(f"/clients/{client_a.id}/baseline/pillars", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert "visibility" in body and "traffic" in body and "leads" in body

    csv_res = client.get(f"/clients/{client_a.id}/baseline/pillars/export.csv", headers=headers)
    assert csv_res.status_code == 200
    assert "text/csv" in csv_res.headers["content-type"]
    assert "Pillar,Category,Metric / Item" in csv_res.text
