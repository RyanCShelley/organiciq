from tests.conftest import client_header


def test_platform_overview_lists_clients(db, client, client_a, admin_user):
    res = client.get("/admin/platform/overview", headers=client_header(client_a.id, admin_user.email))
    assert res.status_code == 200
    body = res.json()
    assert any(row["client_name"] == "Client A" for row in body)


def test_ga4_events_for_conversions(db, client, client_a, admin_user):
    from datetime import date
    from uuid import uuid4

    from app.models.config import OrganicChannel
    from app.models.ga4 import FactGa4Event

    db.add(
        FactGa4Event(
            id=uuid4(),
            client_id=client_a.id,
            date=date.today(),
            raw_url="https://example.com/",
            normalized_url="https://example.com/",
            session_source="google",
            session_medium="organic",
            channel=OrganicChannel.ORGANIC_SEARCH,
            event_name="generate_lead",
            event_count=5,
        )
    )
    db.commit()

    res = client.get(
        "/admin/conversion-definitions/ga4-events",
        headers=client_header(client_a.id, admin_user.email),
    )
    assert res.status_code == 200
    body = res.json()
    assert body[0]["event_name"] == "generate_lead"
    assert body[0]["event_count"] == 5
