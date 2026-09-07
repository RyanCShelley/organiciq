from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.models.config import OrganicChannel
from app.models.crawl import FactCrawlPageSnapshot
from app.models.ga4 import FactGa4Traffic
from app.models.crawl import FactCrawlPageSnapshot
from app.models.gsc import FactGscPage
from app.models.job import DataWatermark, ValidationStatus
from app.services.decisions import evaluate_and_store, run_diagnose
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

    res = client.get(
        f"/decisions/diagnose?from={start.isoformat()}&to={end.isoformat()}",
        headers=client_header(client_a.id, admin_user.email),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ready"] is True
    assert len(body["levers"]) == 5
    assert "findings_count" in body
    assert "recommended_actions" in body
    assert "formula" in body


def test_evaluate_persists_scored_decisions(db, client_a):
    start, end = date_window(14)
    page = "https://example.com/services/sem"
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
            clicks=Decimal("2"),
            ctr=Decimal("0.0013"),
            average_position=Decimal("5"),
        )
    )
    db.add(
        FactCrawlPageSnapshot(
            id=uuid4(),
            client_id=client_a.id,
            snapshot_date=end,
            raw_url=page,
            normalized_url=page,
            indexable=False,
            status_code=200,
            inbound_internal_links=0,
            word_count=1200,
        )
    )
    db.commit()

    created, skipped, result = evaluate_and_store(db, client_a, from_date=start, to_date=end)
    assert result.ready is True
    assert len(created) >= 1
    assert created[0].priority_score is not None
    assert created[0].impact is not None

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

    res = client.post(
        "/decisions/evaluate",
        headers=headers,
        json={"from": start.isoformat(), "to": end.isoformat()},
    )
    assert res.status_code == 200
    body = res.json()
    assert "diagnose" in body
    assert body["diagnose"]["ready"] is True
