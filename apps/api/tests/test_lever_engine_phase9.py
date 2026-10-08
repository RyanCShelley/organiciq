from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.decisions.ctr_curve import expected_ctr_percent
from app.models.config import ConversionDefinition, OrganicChannel
from app.models.crawl import FactCrawlPageSnapshot
from app.services.lever_engine import active_crawl_source
from app.models.ga4 import FactGa4Event, FactGa4Traffic
from app.models.gsc import FactGscPage
from app.models.job import DataWatermark, ValidationStatus
from app.services.lever_engine import diagnose, score_finding
from tests.conftest import date_window, seed_required_sources


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


def test_score_formula_matches_spec():
    score = score_finding(impact=73, confidence=75, urgency=55, effort=30)
    secondary = 0.15 * 75 + 0.15 * 55 + 0.1 * (100 - 30)
    expected = round(0.6 * 73 + secondary * min(1.0, 73 / 20), 1)
    assert score == expected


def test_score_formula_impact_led_low_business_impact():
    score = score_finding(impact=1.6, confidence=80, urgency=50, effort=20)
    secondary = 0.15 * 80 + 0.15 * 50 + 0.1 * (100 - 20)
    expected = round(0.6 * 1.6 + secondary * (1.6 / 20), 1)
    assert score == expected
    assert score < 10


def test_score_formula_does_not_apply_critical_override_floor():
    score = score_finding(impact=4.6, confidence=85, urgency=90, effort=45)
    assert score < 20


def test_expected_ctr_curve():
    assert expected_ctr_percent(4) == 1.71
    assert expected_ctr_percent(5) == 1.08
    assert expected_ctr_percent(10) == 0.58


def test_without_gsc_the_run_continues_on_what_is_left(db, client_a):
    """GA4 still has sessions and leads, so the conversion rules still have
    something to say. Search Console's absence makes them quiet, not wrong."""
    start, end = date_window(7)
    seed_required_sources(db, client_a.id, end, skip=("search_console",))
    result = diagnose(db, client_a, from_date=start, to_date=end)
    assert result.ready is True
    assert result.readiness["search_console"] is False
    assert any(
        row.get("rule_id") == "Search Console" for row in result.coverage
    ), "the missing source must be named in coverage"


def test_internal_linking_cascade(db, client_a):
    start, end = date_window(14)
    page = "https://example.com/blog/schema-org-vs-google-structured-data-rich-results"
    _watermark(db, client_a.id, "gsc_pages", end)
    db.add(
        FactGscPage(
            id=uuid4(),
            client_id=client_a.id,
            date=end,
            raw_url=page,
            normalized_url=page,
            country="usa",
            device="DESKTOP",
            impressions=Decimal("2911"),
            clicks=Decimal("2"),
            ctr=Decimal("0.0007"),
            average_position=Decimal("14.2"),
        )
    )
    db.add(
        FactCrawlPageSnapshot(
            id=uuid4(),
            client_id=client_a.id,
            source=active_crawl_source(),
            snapshot_date=end,
            raw_url=page,
            normalized_url=page,
            indexable=True,
            status_code=200,
            inbound_internal_links=6,
            word_count=2500,
            title="Schema blog post",
            description="A long-form comparison of schema approaches.",
        )
    )
    db.commit()

    seed_required_sources(db, client_a.id, end)
    result = diagnose(db, client_a, from_date=start, to_date=end)
    assert result.ready is True
    assert result.readiness["crawl_audit"] is True
    internal = [row for row in result.findings if row.lever == "internal_linking"]
    assert len(internal) == 1
    assert internal[0].confidence == 75
    assert internal[0].evidence_json["impact_basis"] == "fallback"
    assert internal[0].impact < 50


def test_diagnose_uses_available_overlap_when_range_extends(db, client_a):
    start = date(2026, 6, 1)
    end = date(2026, 9, 1)
    fact_start = date(2026, 6, 4)
    fact_end = date(2026, 8, 29)
    _watermark(db, client_a.id, "gsc_pages", fact_end)
    db.add(
        FactGscPage(
            id=uuid4(),
            client_id=client_a.id,
            date=fact_start,
            raw_url="https://example.com/start",
            normalized_url="https://example.com/start",
            country="usa",
            device="DESKTOP",
            impressions=Decimal("100"),
            clicks=Decimal("1"),
            ctr=Decimal("0.01"),
            average_position=Decimal("12"),
        )
    )
    db.add(
        FactGscPage(
            id=uuid4(),
            client_id=client_a.id,
            date=fact_end,
            raw_url="https://example.com/",
            normalized_url="https://example.com/",
            country="usa",
            device="DESKTOP",
            impressions=Decimal("5000"),
            clicks=Decimal("10"),
            ctr=Decimal("0.002"),
            average_position=Decimal("8"),
        )
    )
    db.commit()

    seed_required_sources(db, client_a.id, end)
    result = diagnose(db, client_a, from_date=start, to_date=end)
    assert result.ready is True
    assert result.analysis_from == fact_start
    assert result.analysis_to == fact_end
    assert result.partial_message is None


def test_diagnose_typical_gsc_lag_has_no_partial_banner(db, client_a):
    start = date(2026, 8, 11)
    end = date(2026, 9, 9)
    fact_end = date(2026, 9, 6)
    _watermark(db, client_a.id, "gsc_pages", fact_end)
    db.add(
        FactGscPage(
            id=uuid4(),
            client_id=client_a.id,
            date=start,
            raw_url="https://example.com/",
            normalized_url="https://example.com/",
            country="usa",
            device="DESKTOP",
            impressions=Decimal("100"),
            clicks=Decimal("1"),
            ctr=Decimal("0.01"),
            average_position=Decimal("10"),
        )
    )
    db.add(
        FactGscPage(
            id=uuid4(),
            client_id=client_a.id,
            date=fact_end,
            raw_url="https://example.com/",
            normalized_url="https://example.com/",
            country="usa",
            device="DESKTOP",
            impressions=Decimal("200"),
            clicks=Decimal("2"),
            ctr=Decimal("0.01"),
            average_position=Decimal("9"),
        )
    )
    db.commit()

    seed_required_sources(db, client_a.id, end)
    result = diagnose(db, client_a, from_date=start, to_date=end)
    assert result.ready is True
    assert result.analysis_to == fact_end
    assert result.partial_message is None


def test_diagnose_not_ready_when_range_has_no_overlap(db, client_a):
    _watermark(db, client_a.id, "gsc_pages", date(2026, 8, 31))
    db.add(
        FactGscPage(
            id=uuid4(),
            client_id=client_a.id,
            date=date(2026, 8, 31),
            raw_url="https://example.com/",
            normalized_url="https://example.com/",
            country="usa",
            device="DESKTOP",
            impressions=Decimal("100"),
            clicks=Decimal("1"),
            ctr=Decimal("0.01"),
            average_position=Decimal("10"),
        )
    )
    db.commit()

    result = diagnose(db, client_a, from_date=date(2026, 1, 1), to_date=date(2026, 3, 31))
    assert result.ready is False
    assert result.message is not None
    assert "No Search Console page facts overlap" in result.message


def test_conversion_portfolio_rule(db, client_a):
    start = date(2026, 8, 2)
    end = date(2026, 8, 31)
    prev_end = date(2026, 8, 1)
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
    _watermark(db, client_a.id, "gsc_pages", end)
    db.add(
        FactGscPage(
            id=uuid4(),
            client_id=client_a.id,
            date=end,
            raw_url="https://example.com/",
            normalized_url="https://example.com/",
            country="",
            device="",
            impressions=Decimal("100"),
            clicks=Decimal("1"),
            ctr=Decimal("0.01"),
            average_position=Decimal("10"),
        )
    )
    # One lead rather than none: a rate that falls to exactly zero while
    # traffic holds is the tracking-failure shape, and Gate 0 suppresses
    # everything when it sees it. This rule is about a falling rate, so the
    # fixture keeps the tag alive and lets the rate fall 5% -> 1%.
    # Sized past the small-sample guard: at the prior 5% rate these sessions
    # should produce 15 leads, so a fall to 1% is a real signal rather than a
    # handful of coin flips.
    for day, sessions, leads in [
        (end, Decimal("300"), 3),
        (prev_end, Decimal("300"), 15),
    ]:
        db.add(
            FactGa4Traffic(
                id=uuid4(),
                client_id=client_a.id,
                date=day,
                raw_url="https://example.com/",
                normalized_url="https://example.com/",
                session_source="google",
                session_medium="organic",
                channel=OrganicChannel.ORGANIC_SEARCH,
                sessions=sessions,
                active_users=sessions,
                views=sessions,
            )
        )
        if leads:
            db.add(
                FactGa4Event(
                    id=uuid4(),
                    client_id=client_a.id,
                    date=day,
                    raw_url="https://example.com/",
                    normalized_url="https://example.com/",
                    session_source="google",
                    session_medium="organic",
                    channel=OrganicChannel.ORGANIC_SEARCH,
                    event_name="generate_lead",
                    event_count=leads,
                )
            )
    db.commit()

    seed_required_sources(db, client_a.id, end)
    result = diagnose(db, client_a, from_date=start, to_date=end)
    conversion = [
        row
        for row in result.findings
        if row.evidence_json.get("gate") == "site_conversion"
    ]
    assert len(conversion) == 1
    assert conversion[0].confidence == 70
    assert conversion[0].evidence_json["leads_at_risk"] > 0
    assert conversion[0].evidence_json["impact_basis"] == "downstream"


def test_serp_ctr_page_rule(db, client_a):
    start, end = date_window(14)
    page = "https://example.com/services"
    _watermark(db, client_a.id, "gsc_pages", end)
    db.add(
        FactGscPage(
            id=uuid4(),
            client_id=client_a.id,
            date=end,
            raw_url=page,
            normalized_url=page,
            country="usa",
            device="DESKTOP",
            impressions=Decimal("1500"),
            clicks=Decimal("3"),
            ctr=Decimal("0.002"),
            average_position=Decimal("5.0"),
        )
    )
    db.commit()

    seed_required_sources(db, client_a.id, end)
    result = diagnose(db, client_a, from_date=start, to_date=end)
    serp = [row for row in result.findings if row.lever == "serp_ctr"]
    assert len(serp) == 1


def test_a_partial_source_set_still_runs(db, client_a):
    """All four used to be required, and the reason was the old cross-lever
    score: a 0-100 impact from three sources was not comparable to one from
    four, so the ranking between levers came out wrong while looking
    authoritative.

    That ranking is gone. A growth action is valued in expected leads a
    month from its own evidence, so a missing source means fewer rules can
    fire, not that the surviving estimates are wrong. Refusing to run for
    nineteen of twenty-four clients was the expensive way to say that some
    rules are quiet.
    """
    start = date(2026, 8, 2)
    end = date(2026, 8, 31)
    seed_required_sources(
        db, client_a.id, end, skip=("search_console", "crawl_audit", "ai_visibility")
    )

    result = diagnose(db, client_a, from_date=start, to_date=end)

    assert result.ready is True
    assert result.readiness["analytics"] is True
    assert result.readiness["search_console"] is False


def test_a_missing_source_is_recorded_as_a_skip_not_a_silence(db, client_a):
    """"No findings" and "never looked" are different statements, and the
    second one has to survive onto the screen."""
    start = date(2026, 8, 2)
    end = date(2026, 8, 31)
    seed_required_sources(db, client_a.id, end, skip=("crawl_audit",))

    result = diagnose(db, client_a, from_date=start, to_date=end)
    skipped = [
        row
        for row in result.coverage
        if str(row.get("status", "")).startswith("skipped:source_missing")
    ]
    assert skipped, "a source that never reported must be recorded"


def test_no_search_and_no_analytics_is_still_nothing_to_reason_about(db, client_a):
    """With neither there is no page, no session and no lead."""
    start, end = date_window(7)
    for model in (DataWatermark, FactGscPage, FactGa4Traffic, FactCrawlPageSnapshot):
        for row in db.query(model).filter(model.client_id == client_a.id):
            db.delete(row)
    db.commit()

    result = diagnose(db, client_a, from_date=start, to_date=end)
    assert result.ready is False
    assert "nothing to reason about" in (result.message or "")




# --- T6 ---------------------------------------------------------------------


def test_position_one_can_under_perform(db, client_a):
    """Excluding it assumed first place cannot be under-clicked, which an AI
    Overview sitting above it comfortably disproves."""
    from app.services.decision_impact import SiteBusinessContext
    from app.services.lever_engine import PageDemand, _serp_ctr_finding

    finding = _serp_ctr_finding(
        PageDemand(
            normalized_url="https://example.com/services",
            impressions=5000.0,
            clicks=25.0,
            average_position=1.0,
            ctr_percent=0.5,
        ),
        page_ctx=None,
        site=SiteBusinessContext(
            site_lead_rate_pct=2.0,
            period_sessions=5000.0,
            period_leads=40,
            period_lead_goal=50,
            p90_page_sessions=400.0,
        ),
    )

    assert finding is not None


def test_a_page_living_on_brand_searches_is_not_a_listing_problem(db, client_a):
    """Someone typing the company name clicks whatever is there."""
    from app.services.decision_impact import SiteBusinessContext
    from app.services.lever_engine import PageDemand, _serp_ctr_finding

    page = PageDemand(
        normalized_url="https://example.com/",
        impressions=5000.0,
        clicks=25.0,
        average_position=1.0,
        ctr_percent=0.5,
    )
    site = SiteBusinessContext(
        site_lead_rate_pct=2.0,
        period_sessions=5000.0,
        period_leads=40,
        period_lead_goal=50,
        p90_page_sessions=400.0,
    )

    assert _serp_ctr_finding(page, page_ctx=None, site=site, branded_share=0.9) is None
    assert _serp_ctr_finding(page, page_ctx=None, site=site, branded_share=0.1) is not None
