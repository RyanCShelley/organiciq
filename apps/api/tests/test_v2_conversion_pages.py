"""The pages GA4 says a conversion event fired on, folded into one row per page."""

from __future__ import annotations

from app.models.config import ClientConversionPage
from app.models.integration import ConnectionStatus, Integration, IntegrationProvider
from app.services import ga4_conversion_pages as svc
from tests.conftest import client_header


def _row(path, event, count):
    return {
        "dimensionValues": [{"value": path}, {"value": event}],
        "metricValues": [{"value": str(count)}],
    }


def _ga4(db, client_a, monkeypatch, rows):
    row = (
        db.query(Integration)
        .filter(Integration.client_id == client_a.id, Integration.provider == IntegrationProvider.GA4)
        .one_or_none()
    )
    if row is None:
        row = Integration(client_id=client_a.id, provider=IntegrationProvider.GA4)
        db.add(row)
    row.external_property_id = "properties/1"
    row.connection_status = ConnectionStatus.CONNECTED
    db.commit()
    seen = {}

    def fake_report(**kwargs):
        seen.update(kwargs)
        return rows

    monkeypatch.setattr(svc, "run_report", fake_report)
    monkeypatch.setattr(svc, "access_token_for_client", lambda db, cid: "token")
    monkeypatch.setattr(svc, "client_has_google_credentials", lambda db, cid: True)
    return seen


def test_pages_are_folded_summed_and_sorted(client, db, client_a, admin_user, monkeypatch):
    seen = _ga4(
        db, client_a, monkeypatch,
        [
            _row("/contact", "form_submit", 30),
            _row("/contact", "phone_click", 5),
            _row("/thanks", "form_submit", 12),
            _row("/blog/post", "form_submit", 3),
        ],
    )
    response = client.get(
        "/v2/conversions/pages?event=form_submit&event=phone_click",
        headers=client_header(client_a.id, admin_user.email),
    )
    assert response.status_code == 200
    pages = response.json()
    assert [p["path"] for p in pages] == ["/contact", "/thanks", "/blog/post"]
    assert pages[0]["total"] == 35 and pages[0]["events"] == {"form_submit": 30, "phone_click": 5}
    assert pages[0]["url"].endswith("/contact") and pages[0]["url"].startswith("https://")
    assert seen["dimension_filter"]["filter"]["inListFilter"]["values"] == ["form_submit", "phone_click"]
    assert seen["dimensions"] == ["pagePath", "eventName"]


def test_a_page_already_declared_is_marked(client, db, client_a, admin_user, monkeypatch):
    _ga4(db, client_a, monkeypatch, [_row("/contact", "form_submit", 9)])
    page_url = svc.normalize_landing_page("/contact", client_a.domain)
    db.add(ClientConversionPage(client_id=client_a.id, normalized_url=page_url, label="Contact"))
    db.commit()

    pages = client.get(
        "/v2/conversions/pages?event=form_submit", headers=client_header(client_a.id, admin_user.email)
    ).json()
    assert pages[0]["declared"] is True


def test_without_ga4_it_says_what_to_do(client, db, client_a, admin_user):
    response = client.get(
        "/v2/conversions/pages?event=form_submit", headers=client_header(client_a.id, admin_user.email)
    )
    assert response.status_code == 400 and "Connections" in response.json()["detail"]


def test_it_needs_at_least_one_event(client, db, client_a, admin_user):
    response = client.get("/v2/conversions/pages", headers=client_header(client_a.id, admin_user.email))
    assert response.status_code == 422


def test_ga4_failing_is_reported_not_a_crash(client, db, client_a, admin_user, monkeypatch):
    _ga4(db, client_a, monkeypatch, [])

    def broken(**kwargs):
        raise RuntimeError("quota exhausted")

    monkeypatch.setattr(svc, "run_report", broken)
    response = client.get(
        "/v2/conversions/pages?event=form_submit", headers=client_header(client_a.id, admin_user.email)
    )
    assert response.status_code == 502 and "quota exhausted" in response.json()["detail"]
