from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.models.gsc import FactGscPage
from app.models.job import DataWatermark, ValidationStatus
from app.services.decisions import evaluate_and_store
from tests.conftest import client_header, date_window, seed_required_sources


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


def test_diagnose_api(db, client, client_a, admin_user):
    start, end = date_window(7)
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
    db.commit()

    seed_required_sources(db, client_a.id, end)
    res = client.get(
        f"/decisions/diagnose?from={start.isoformat()}&to={end.isoformat()}",
        headers=client_header(client_a.id, admin_user.email),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ready"] is True
    assert len(body["levers"]) == 5
    assert "findings_count" in body
    assert "growth_actions" in body
    assert "formula" in body


def test_evaluate_persists_scored_decisions(db, client_a):
    """A decision is stored per growth action, once.

    This used to seed a noindexed page with no inbound links, which makes
    technical findings and no action at all — the CTR finding on a
    noindexed page is suppressed, correctly. It stored rows anyway, because
    it was storing the legacy impact promotion, which included report-only
    work nobody had been asked to do.
    """
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
    # A site lead rate, or the valuer has no honest way to turn recoverable
    # clicks into leads and records `no_lead_rate` instead of a value.
    from app.models.config import ConversionDefinition, OrganicChannel
    from app.models.ga4 import FactGa4Event, FactGa4Traffic

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
        FactGa4Traffic(
            id=uuid4(),
            client_id=client_a.id,
            date=end,
            raw_url=page,
            normalized_url=page,
            session_source="google",
            session_medium="organic",
            channel=OrganicChannel.ORGANIC_SEARCH,
            sessions=Decimal("500"),
            active_users=Decimal("500"),
            views=Decimal("500"),
            engaged_sessions=Decimal("400"),
        )
    )
    db.add(
        FactGa4Event(
            id=uuid4(),
            client_id=client_a.id,
            date=end,
            raw_url=page,
            normalized_url=page,
            session_source="google",
            session_medium="organic",
            channel=OrganicChannel.ORGANIC_SEARCH,
            event_name="generate_lead",
            event_count=10,
        )
    )
    db.commit()

    seed_required_sources(db, client_a.id, end)
    created, skipped, result = evaluate_and_store(db, client_a, from_date=start, to_date=end)
    assert result.ready is True
    assert len(result.growth_actions) >= 1, "the fixture has to produce an action"
    assert len(created) == len(result.growth_actions)
    assert all(
        row.evidence_json.get("demand") is not None
        or row.evidence_json.get("precondition")
        for row in result.growth_actions
    )

    created_again, skipped_again, _ = evaluate_and_store(db, client_a, from_date=start, to_date=end)
    assert len(created_again) == 0
    assert skipped_again >= 1


def test_decisions_api_evaluate_includes_diagnose(db, client, client_a, admin_user):
    start, end = date_window(7)
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
    db.commit()
    headers = client_header(client_a.id, admin_user.email)

    seed_required_sources(db, client_a.id, end)
    res = client.post(
        "/decisions/evaluate",
        headers=headers,
        json={"from": start.isoformat(), "to": end.isoformat()},
    )
    assert res.status_code == 200
    body = res.json()
    assert "diagnose" in body
    assert body["diagnose"]["ready"] is True
