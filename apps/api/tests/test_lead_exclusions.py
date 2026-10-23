"""Lead exclusions flow into the baseline and the API rejects empty rules."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.config import ConversionDefinition, LeadExclusion, OrganicChannel
from app.models.ga4 import FactGa4Event
from app.services.dashboard import _sum_leads


def test_sum_leads_ignores_excluded_events(db: Session, client_a: Client):
    for url, count in (("/real", 4), ("/test", 7)):
        db.add(
            FactGa4Event(
                client_id=client_a.id,
                date=date(2026, 9, 10),
                raw_url=url,
                normalized_url=url,
                channel=OrganicChannel.ORGANIC_SEARCH,
                event_name="generate_lead",
                event_count=count,
            )
        )
    db.commit()
    period = (date(2026, 9, 1), date(2026, 9, 30))
    assert _sum_leads(db, client_a.id, ["generate_lead"], period) == 11
    db.add(LeadExclusion(client_id=client_a.id, url_pattern="/test", reason="tests"))
    db.commit()
    assert _sum_leads(db, client_a.id, ["generate_lead"], period) == 4


def test_api_round_trips_and_refuses_a_rule_that_matches_everything(client, client_a, admin_user):
    from tests.conftest import client_header

    headers = client_header(client_a.id, admin_user.email)
    empty = client.put("/admin/lead-exclusions", headers=headers, json=[{"reason": "oops"}])
    assert empty.status_code == 422
    no_reason = client.put(
        "/admin/lead-exclusions", headers=headers, json=[{"url_pattern": "/t", "reason": " "}]
    )
    assert no_reason.status_code == 422
    saved = client.put(
        "/admin/lead-exclusions",
        headers=headers,
        json=[{"date_from": "2026-09-01", "date_to": "2026-09-30", "reason": "September tests"}],
    )
    assert saved.status_code == 200
    assert saved.json()[0]["date_from"] == "2026-09-01"
    assert len(client.get("/admin/lead-exclusions", headers=headers).json()) == 1
