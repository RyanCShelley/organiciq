"""GA4 fixtures shared by the baseline tests: one declared lead event and daily facts."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from app.models.config import ConversionDefinition, OrganicChannel
from app.models.ga4 import FactGa4Event, FactGa4Traffic
from app.models.job import DataWatermark, ValidationStatus

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
