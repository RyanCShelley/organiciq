from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.decisions.ctr_curve import expected_ctr_percent
from app.models.config import ConversionDefinition, OrganicChannel
from app.models.crawl import FactCrawlPageSnapshot
from app.models.ga4 import FactGa4Event, FactGa4Traffic
from app.models.gsc import FactGscPage
from app.models.job import DataWatermark, ValidationStatus
from app.models.seranking import FactSerAiTrackerStats, FactSerSiteSummary
from app.services.lever_engine import diagnose, score_finding
from tests.conftest import date_window


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
    assert score == round(0.4 * 73 + 0.3 * 75 + 0.2 * 55 + 0.1 * (100 - 30), 1)


def test_expected_ctr_curve():
    assert expected_ctr_percent(4) == 8.2
    assert expected_ctr_percent(10) == 2.3


def test_diagnose_not_ready_without_gsc(db, client_a):
    start, end = date_window(7)
    result = diagnose(db, client_a, from_date=start, to_date=end)
    assert result.ready is False
    assert result.readiness["search_console"] is False


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
            snapshot_date=end,
            raw_url=page,
            normalized_url=page,
            indexable=True,
            status_code=200,
            inbound_internal_links=6,
            word_count=2500,
        )
    )
    db.commit()

    result = diagnose(db, client_a, from_date=start, to_date=end)
    assert result.ready is True
    assert result.readiness["crawl_audit"] is True
    internal = [row for row in result.recommendations if row.lever == "internal_linking"]
    assert len(internal) == 1
    assert internal[0].confidence == 75
    assert internal[0].priority_score >= 65


def test_conversion_portfolio_rule(db, client_a):
    start = date(2026, 8, 2)
    end = date(2026, 8, 31)
    prev_start = date(2026, 7, 3)
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
    for day, sessions, leads in [
        (end, Decimal("104"), 0),
        (prev_end, Decimal("100"), 5),
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

    result = diagnose(db, client_a, from_date=start, to_date=end)
    conversion = [row for row in result.recommendations if row.lever == "conversion_path"]
    assert len(conversion) == 1
    assert conversion[0].confidence == 70
    assert conversion[0].urgency == 65


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

    result = diagnose(db, client_a, from_date=start, to_date=end)
    serp = [row for row in result.recommendations if row.lever == "serp_ctr"]
    assert len(serp) == 1
