"""Baseline snapshot builder.

The window used to be a fixed 30 days ending at the GA4 watermark, so "baseline
as of August 1" was impossible to express. It is now anchored on the requested
date with a 90-day default lookback, and the projection is frozen alongside it.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from app.models.config import ConversionDefinition, OrganicChannel
from app.models.ga4 import FactGa4Event, FactGa4Traffic
from app.models.job import DataWatermark, ValidationStatus
from app.services import baseline_snapshot

LEAD_EVENT = "generate_lead"


def _lead_definition(db, client_id) -> None:
    db.add(
        ConversionDefinition(
            id=uuid4(),
            client_id=client_id,
            event_name=LEAD_EVENT,
            conversion_name="Lead",
            conversion_type="lead",
            is_primary=True,
            active=True,
        )
    )


def _watermark(db, client_id, through: date) -> None:
    row = (
        db.query(DataWatermark)
        .filter(DataWatermark.client_id == client_id, DataWatermark.source == "ga4")
        .one_or_none()
    )
    if row is None:
        row = DataWatermark(id=uuid4(), client_id=client_id, source="ga4")
        db.add(row)
    row.fact_through_date = through
    row.validation_status = ValidationStatus.PASSED


def _daily_facts(db, client_id, *, start: date, days: int, sessions: int, leads: int) -> None:
    """One row per day so period length is what actually varies."""
    for offset in range(days):
        day = start + timedelta(days=offset)
        db.add(
            FactGa4Traffic(
                id=uuid4(),
                client_id=client_id,
                date=day,
                raw_url="https://example.com/",
                normalized_url="https://example.com/",
                session_source="google",
                session_medium="organic",
                channel=OrganicChannel.ORGANIC_SEARCH,
                sessions=Decimal(sessions),
                active_users=Decimal(sessions),
                views=Decimal(sessions),
            )
        )
        if leads:
            db.add(
                FactGa4Event(
                    id=uuid4(),
                    client_id=client_id,
                    date=day,
                    raw_url="https://example.com/",
                    normalized_url="https://example.com/",
                    session_source="google",
                    session_medium="organic",
                    channel=OrganicChannel.ORGANIC_SEARCH,
                    event_name=LEAD_EVENT,
                    event_count=leads,
                )
            )


def _seed(db, client, *, watermark: date, start: date, days: int, sessions=100, leads=2):
    _lead_definition(db, client.id)
    _watermark(db, client.id, watermark)
    _daily_facts(db, client.id, start=start, days=days, sessions=sessions, leads=leads)
    db.commit()


# --- S3: the window anchors on the requested date ---------------------------


def test_window_anchors_on_requested_baseline_date(db, client_a):
    """"Baseline as of August 1" must end August 1, not at the watermark."""
    _seed(db, client_a, watermark=date(2026, 9, 30), start=date(2026, 4, 1), days=200)

    preview = baseline_snapshot.preview_baseline_from_ga4(
        db, client_a, as_of=date(2026, 8, 1), lookback_days=90
    )

    assert preview["window"]["to"] == "2026-08-01"
    assert preview["window"]["from"] == "2026-05-04"  # 90 days ending Aug 1
    assert preview["baseline_as_of"] == "2026-08-01"


def test_window_defaults_to_watermark_when_no_date_given(db, client_a):
    _seed(db, client_a, watermark=date(2026, 9, 30), start=date(2026, 4, 1), days=200)

    preview = baseline_snapshot.preview_baseline_from_ga4(db, client_a)

    assert preview["window"]["to"] == "2026-09-30"
    assert preview["window"]["period_days"] == 90


def test_baseline_date_beyond_available_facts_is_rejected(db, client_a):
    _seed(db, client_a, watermark=date(2026, 8, 31), start=date(2026, 6, 1), days=90)

    with pytest.raises(ValueError, match="only run through"):
        baseline_snapshot.preview_baseline_from_ga4(db, client_a, as_of=date(2026, 12, 1))


# --- S4: 90-day default, averaged to monthly --------------------------------


def test_ninety_day_window_scales_to_a_monthly_average(db, client_a):
    _seed(
        db, client_a, watermark=date(2026, 8, 31), start=date(2026, 1, 1), days=250,
        sessions=10, leads=1,
    )

    preview = baseline_snapshot.preview_baseline_from_ga4(
        db, client_a, as_of=date(2026, 8, 31), lookback_days=90
    )

    # 10 sessions/day over 90 days, scaled to a 30-day month.
    assert preview["window"]["period_days"] == 90
    assert preview["baseline_monthly_sessions"] == 300
    assert preview["baseline_monthly_leads"] == 30
    assert preview["baseline_lead_rate_pct"] == pytest.approx(10.0, abs=0.01)


def test_shorter_lookback_is_honoured(db, client_a):
    _seed(db, client_a, watermark=date(2026, 8, 31), start=date(2026, 1, 1), days=250)

    preview = baseline_snapshot.preview_baseline_from_ga4(
        db, client_a, as_of=date(2026, 8, 31), lookback_days=30
    )

    assert preview["window"]["period_days"] == 30


def test_partial_coverage_is_reported_not_hidden(db, client_a):
    """
    A 90-day window over 40 days of facts must say so rather than averaging the
    short span and presenting it as 90 days.
    """
    _seed(db, client_a, watermark=date(2026, 8, 31), start=date(2026, 7, 23), days=40)

    preview = baseline_snapshot.preview_baseline_from_ga4(
        db, client_a, as_of=date(2026, 8, 31), lookback_days=90
    )
    window = preview["window"]

    assert window["requested_days"] == 90
    assert window["period_days"] == 40
    assert window["fully_covered"] is False
    assert window["from"] == "2026-07-23"


def test_full_coverage_is_flagged(db, client_a):
    _seed(db, client_a, watermark=date(2026, 8, 31), start=date(2026, 1, 1), days=250)

    preview = baseline_snapshot.preview_baseline_from_ga4(
        db, client_a, as_of=date(2026, 8, 31), lookback_days=90
    )

    assert preview["window"]["fully_covered"] is True


def test_too_few_days_is_refused(db, client_a):
    _seed(db, client_a, watermark=date(2026, 8, 31), start=date(2026, 8, 29), days=3)

    with pytest.raises(ValueError, match="at least"):
        baseline_snapshot.preview_baseline_from_ga4(db, client_a, as_of=date(2026, 8, 31))


# --- S5: the projection is frozen with the baseline -------------------------


def test_apply_persists_the_projection(db, client_a):
    _seed(db, client_a, watermark=date(2026, 8, 31), start=date(2026, 1, 1), days=250)

    updated, preview = baseline_snapshot.apply_baseline_from_ga4(
        db, client_a, as_of=date(2026, 8, 31), lookback_days=90
    )

    stored = updated.baseline_projection_json
    assert stored is not None, "checkpoints were computed and thrown away before"
    assert stored["generated_on"] == date.today().isoformat()
    assert stored["baseline_as_of"] == "2026-08-31"
    assert stored["window"]["period_days"] == 90

    labels = [c["label"] for c in stored["checkpoints"]]
    assert labels == ["Today", "3 months", "6 months", "9 months", "12 months"]
    assert preview["projection_generated_on"] == stored["generated_on"]


def test_apply_records_the_anchored_window_on_the_client(db, client_a):
    _seed(db, client_a, watermark=date(2026, 9, 30), start=date(2026, 1, 1), days=280)

    updated, _ = baseline_snapshot.apply_baseline_from_ga4(
        db, client_a, as_of=date(2026, 8, 1), lookback_days=90
    )

    assert updated.baseline_as_of == date(2026, 8, 1)
    assert updated.baseline_period_end == date(2026, 8, 1)
    assert updated.baseline_period_start == date(2026, 5, 4)


def test_rerun_replaces_the_frozen_projection(db, client_a):
    """Re-running is manual and on demand; it must overwrite, not append."""
    _seed(db, client_a, watermark=date(2026, 9, 30), start=date(2026, 1, 1), days=280)

    baseline_snapshot.apply_baseline_from_ga4(
        db, client_a, as_of=date(2026, 7, 1), lookback_days=90
    )
    updated, _ = baseline_snapshot.apply_baseline_from_ga4(
        db, client_a, as_of=date(2026, 9, 1), lookback_days=90
    )

    assert updated.baseline_projection_json["baseline_as_of"] == "2026-09-01"
    assert updated.baseline_as_of == date(2026, 9, 1)
