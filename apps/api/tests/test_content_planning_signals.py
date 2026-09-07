from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.models.gsc import FactGscPage
from app.models.job import DataWatermark, ValidationStatus
from app.services.lever_engine import diagnose
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


def test_content_planning_excludes_commercial_striking_distance(db, client_a):
    start, end = date_window(14)
    _watermark(db, client_a.id, "gsc_pages", end)
    db.add(
        FactGscPage(
            id=uuid4(),
            client_id=client_a.id,
            date=end,
            raw_url="https://example.com/services/sem",
            normalized_url="https://example.com/services/sem",
            country="usa",
            device="DESKTOP",
            impressions=Decimal("800"),
            clicks=Decimal("2"),
            ctr=Decimal("0.0025"),
            average_position=Decimal("12"),
        )
    )
    db.add(
        FactGscPage(
            id=uuid4(),
            client_id=client_a.id,
            date=end,
            raw_url="https://example.com/blog/schema-org-vs-google",
            normalized_url="https://example.com/blog/schema-org-vs-google",
            country="usa",
            device="DESKTOP",
            impressions=Decimal("900"),
            clicks=Decimal("4"),
            ctr=Decimal("0.004"),
            average_position=Decimal("11"),
        )
    )
    db.commit()

    result = diagnose(db, client_a, from_date=start, to_date=end)
    assert result.ready is True
    urls = {signal.page_url for signal in result.search_opportunities}
    assert "https://example.com/services/sem" not in urls
    assert "https://example.com/blog/schema-org-vs-google" in urls


def test_content_planning_requires_minimum_impressions(db, client_a):
    start, end = date_window(14)
    _watermark(db, client_a.id, "gsc_pages", end)
    db.add(
        FactGscPage(
            id=uuid4(),
            client_id=client_a.id,
            date=end,
            raw_url="https://example.com/blog/low-demand-post",
            normalized_url="https://example.com/blog/low-demand-post",
            country="usa",
            device="DESKTOP",
            impressions=Decimal("80"),
            clicks=Decimal("1"),
            ctr=Decimal("0.0125"),
            average_position=Decimal("10"),
        )
    )
    db.commit()

    result = diagnose(db, client_a, from_date=start, to_date=end)
    assert all(
        signal.page_url != "https://example.com/blog/low-demand-post"
        for signal in result.search_opportunities
    )
