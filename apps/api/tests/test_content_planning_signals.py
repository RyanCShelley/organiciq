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


# --- C1: opportunity types are derived, not a single constant ---------------


def test_opportunity_type_flags_a_ctr_gap():
    """Ranking well but under-clicked is a different job from ranking poorly."""
    from app.services.lever_engine import _classify_opportunity
    from app.decisions.ctr_curve import expected_ctr_percent

    expected = expected_ctr_percent(6.0)
    assert (
        _classify_opportunity(average_position=6.0, ctr_percent=expected * 0.1) == "CTR gap"
    )


def test_opportunity_type_flags_a_near_win():
    from app.services.lever_engine import _classify_opportunity
    from app.decisions.ctr_curve import expected_ctr_percent

    # Healthy CTR for the position, just outside the top few.
    assert (
        _classify_opportunity(average_position=4.5, ctr_percent=expected_ctr_percent(4.5))
        == "Near win"
    )


def test_opportunity_type_defaults_to_striking_distance():
    from app.services.lever_engine import _classify_opportunity
    from app.decisions.ctr_curve import expected_ctr_percent

    assert (
        _classify_opportunity(average_position=14.0, ctr_percent=expected_ctr_percent(14.0))
        == "Striking distance"
    )


def test_opportunity_types_are_not_all_identical():
    from app.services.lever_engine import _classify_opportunity
    from app.decisions.ctr_curve import expected_ctr_percent

    labels = {
        _classify_opportunity(average_position=pos, ctr_percent=expected_ctr_percent(pos) * mult)
        for pos, mult in [(6.0, 0.1), (4.5, 1.0), (14.0, 1.0)]
    }
    assert len(labels) == 3, "the label must distinguish work types, not paint one constant"


# --- C2: SE Ranking cross-reference on content opportunities ----------------


def test_tracked_keywords_join_matches_on_normalized_url(db, client_a):
    """
    Opportunities are page-level and carry no query, so a query-to-keyword text
    match is impossible. The join is on ranking URL instead, which is exact.
    """
    from uuid import uuid4

    from app.models.seranking import FactSerKeyword
    from app.services.lever_engine import _tracked_keywords_by_url

    for keyword, url in [
        ("seo services", "https://example.com/services/seo"),
        ("seo agency", "https://example.com/services/seo/"),  # trailing slash
        ("pricing", "https://example.com/pricing"),
        ("untracked page", None),
    ]:
        db.add(
            FactSerKeyword(
                id=uuid4(),
                client_id=client_a.id,
                keyword_id=str(uuid4()),
                keyword=keyword,
                site_engine_id="1",
                ranking_url=url,
            )
        )
    db.commit()

    counts = _tracked_keywords_by_url(db, client_a.id)

    # Both spellings of the services URL collapse to one normalized key.
    assert counts["https://example.com/services/seo"] == 2
    assert counts["https://example.com/pricing"] == 1
    assert None not in counts


def test_tracked_keywords_defaults_to_zero_when_unmatched(db, client_a):
    from app.services.lever_engine import _tracked_keywords_by_url

    counts = _tracked_keywords_by_url(db, client_a.id)
    assert counts.get("https://example.com/never-seen", 0) == 0
