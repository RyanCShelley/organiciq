from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.models.config import ConversionDefinition, OrganicChannel
from app.models.ga4 import FactGa4Event, FactGa4Traffic
from app.models.gsc import FactGscQueryPage
from app.models.job import DataWatermark, ValidationStatus
from app.services.decisions import evaluate_and_store, list_decisions
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


def test_evaluate_stores_conversion_bottleneck(db, client_a):
    start = date(2026, 6, 4)
    end = date(2026, 9, 1)
    prev_start = date(2026, 3, 6)
    prev_end = date(2026, 6, 3)

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
    for day, sessions, leads in [
        (end, Decimal("200"), 5),
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

    created, skipped = evaluate_and_store(db, client_a, from_date=start, to_date=end)
    assert skipped == 0
    assert any(row.growth_action and row.growth_action.value == "conversion_path" for row in created)

    created_again, skipped_again = evaluate_and_store(db, client_a, from_date=start, to_date=end)
    assert len(created_again) == 0
    assert skipped_again >= 1


def test_evaluate_finds_high_impression_low_ctr_query(db, client_a):
    start, end = date_window(14)
    _watermark(db, client_a.id, "gsc_queries", end)
    db.add(
        FactGscQueryPage(
            id=uuid4(),
            client_id=client_a.id,
            date=end,
            query="carbon fiber tubes",
            raw_url="https://example.com/products",
            normalized_url="https://example.com/products",
            country="usa",
            device="DESKTOP",
            impressions=Decimal("500"),
            clicks=Decimal("1"),
            ctr=Decimal("0.002"),
            average_position=Decimal("4.5"),
        )
    )
    db.commit()

    created, _ = evaluate_and_store(db, client_a, from_date=start, to_date=end)
    matches = [row for row in created if row.query == "carbon fiber tubes"]
    assert len(matches) == 1
    assert matches[0].growth_action and matches[0].growth_action.value == "serp_ctr"


def test_decisions_api_evaluate_and_list(client, client_a, admin_user):
    start, end = date_window(7)
    headers = client_header(client_a.id, admin_user.email)

    evaluate = client.post(
        "/decisions/evaluate",
        headers=headers,
        json={"from": start.isoformat(), "to": end.isoformat()},
    )
    assert evaluate.status_code == 200
    body = evaluate.json()
    assert "created" in body
    assert "skipped" in body

    listed = client.get(
        f"/decisions?from={start.isoformat()}&to={end.isoformat()}",
        headers=headers,
    )
    assert listed.status_code == 200
    assert isinstance(listed.json(), list)


def test_decisions_are_client_isolated(db, client_a, client_b):
    start, end = date_window(7)
    evaluate_and_store(db, client_a, from_date=start, to_date=end)
    evaluate_and_store(db, client_b, from_date=start, to_date=end)

    a_rows = list_decisions(db, client_a.id, from_date=start, to_date=end)
    b_rows = list_decisions(db, client_b.id, from_date=start, to_date=end)
    assert all(row.client_id == client_a.id for row in a_rows)
    assert all(row.client_id == client_b.id for row in b_rows)
