"""C1: confidence built from the evidence, not from the lever."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.decisions.confidence import data_confidence
from app.decisions.thresholds import DEFAULT_DECISION_THRESHOLDS, merge_thresholds
from app.models.config import ConversionDefinition, OrganicChannel
from app.models.decision import DecisionThreshold
from app.models.ga4 import FactGa4Event, FactGa4Traffic
from app.models.gsc import FactGscPage
from app.models.job import DataWatermark, ValidationStatus
from app.services.lever_engine import diagnose
from tests.conftest import seed_required_sources

LIMITS = merge_thresholds(None)


def test_tier_discounts_a_weaker_source():
    measured = data_confidence(80, {"data_confidence": "high"}, LIMITS)
    inferred = data_confidence(80, {"data_confidence": "medium"}, LIMITS)
    guessed = data_confidence(80, {"data_confidence": "low"}, LIMITS)
    assert measured == 80
    assert inferred == 72
    assert guessed == 60
    assert measured > inferred > guessed


def test_lever_constant_is_the_ceiling():
    """Clean data cannot make a rule more trustworthy than its own kind."""
    generous = dict(LIMITS, confidence_tier_high=5.0)
    assert data_confidence(70, {"data_confidence": "high"}, generous) == 70


def test_thin_lead_estimate_is_discounted():
    thin = data_confidence(80, {"estimated_incremental_leads": 1.2}, LIMITS)
    solid = data_confidence(80, {"estimated_incremental_leads": 40.0}, LIMITS)
    assert thin == 64
    assert solid == 80


def test_impressions_only_stand_in_when_no_lead_estimate_was_made():
    """A lead estimate is the harder inference, so it wins when both exist."""
    both = data_confidence(
        80, {"estimated_incremental_leads": 40.0, "impressions": 5}, LIMITS
    )
    assert both == 80
    assert data_confidence(80, {"impressions": 5}, LIMITS) == 64


def test_a_finding_carrying_neither_is_not_thin():
    """Technical checks count no leads; that is their shape, not a weakness."""
    assert data_confidence(85, {"data_confidence": "high"}, LIMITS) == 85


def test_stale_data_is_discounted():
    fresh = data_confidence(80, {}, LIMITS, data_age_days=3)
    stale = data_confidence(80, {}, LIMITS, data_age_days=60)
    assert fresh == 80
    assert stale == 68


def test_list_thresholds_survive_a_per_client_override():
    """These were being dropped, leaving two keys tunable only by deploy."""
    merged = merge_thresholds({"cluster_generic_terms": ["quick", "reliable"]})
    assert merged["cluster_generic_terms"] == ["quick", "reliable"]
    assert DEFAULT_DECISION_THRESHOLDS["cluster_generic_terms"] == []


def _seed_falling_lead_rate(db, client_a, end: date, prev_end: date) -> None:
    for source in ("ga4", "gsc_pages"):
        db.add(
            DataWatermark(
                id=uuid4(),
                client_id=client_a.id,
                source=source,
                fact_through_date=end,
                validation_status=ValidationStatus.PASSED,
            )
        )
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
    for day, sessions, leads in [(end, Decimal("300"), 3), (prev_end, Decimal("300"), 15)]:
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


def test_score_is_recorded_without_changing_recommendations(db, client_a):
    """Off by default: the 60 gate has never rejected anything, and which
    findings it would start rejecting has to be looked at before it does."""
    end, prev_end = date(2026, 8, 31), date(2026, 8, 1)
    _seed_falling_lead_rate(db, client_a, end, prev_end)

    result = diagnose(db, client_a, from_date=date(2026, 8, 2), to_date=end)
    conversion = [row for row in result.recommendations if row.lever == "conversion_path"]
    assert len(conversion) == 1

    finding = conversion[0]
    scored = finding.evidence_json["data_driven_confidence"]
    assert finding.evidence_json["lever_confidence"] == finding.confidence
    assert scored < finding.confidence


def test_enabling_the_flag_applies_the_score(db, client_a):
    end, prev_end = date(2026, 8, 31), date(2026, 8, 1)
    _seed_falling_lead_rate(db, client_a, end, prev_end)
    db.add(
        DecisionThreshold(
            id=uuid4(),
            client_id=client_a.id,
            thresholds={"data_driven_confidence_enabled": 1},
        )
    )
    db.commit()

    result = diagnose(db, client_a, from_date=date(2026, 8, 2), to_date=end)
    conversion = [row for row in result.findings if row.lever == "conversion_path"]
    assert len(conversion) == 1
    finding = conversion[0]
    assert finding.confidence == finding.evidence_json["data_driven_confidence"]
    assert finding.confidence < finding.evidence_json["lever_confidence"]
