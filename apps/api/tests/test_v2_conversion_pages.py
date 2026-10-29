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
    pages = response.json()["pages"]
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
    ).json()["pages"]
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


THANK_YOU = [
    _row("/checkouts/cn/hWNDwk8QovDYD002QtjLhfYA/en-us/thank-you", "purchase", 1),
    _row("/checkouts/cn/hWNE3HWu0fT6peGS4kLFYlMn/en-us/thank-you", "purchase", 1),
    _row("/checkouts/cn/hWNEJpf11zInXmVofRNPw0af/en-us/thank-you", "purchase", 1),
    _row("(not set)", "purchase", 16),
    _row("/pages/contact", "form_submit", 4),
]


def test_unique_order_addresses_suggest_one_thank_you_pattern(client, db, client_a, admin_user, monkeypatch):
    _ga4(db, client_a, monkeypatch, THANK_YOU)
    body = client.get(
        "/v2/conversions/pages?event=purchase&event=form_submit",
        headers=client_header(client_a.id, admin_user.email),
    ).json()
    assert body["suggested"] == [{"pattern": "/thank-you", "total": 3, "pages": 3}]


def test_a_tracked_pattern_marks_every_matching_page(client, db, client_a, admin_user, monkeypatch):
    _ga4(db, client_a, monkeypatch, THANK_YOU)
    headers = client_header(client_a.id, admin_user.email)
    saved = client.put(
        "/v2/conversions/completion-patterns",
        json=[{"pattern": "Thank-You", "label": "Order complete"}, {"pattern": "/thank-you"}],
        headers=headers,
    )
    assert saved.status_code == 200
    assert saved.json() == [{"pattern": "/thank-you", "label": "Order complete"}]

    body = client.get("/v2/conversions/pages?event=purchase", headers=headers).json()
    pages = body["pages"]
    assert body["tracked"] == [{"pattern": "/thank-you", "total": 3, "pages": 3}]
    assert body["suggested"] == []
    # Every thank-you address is folded into `tracked`; the rest stay, busiest first.
    assert [p["path"] for p in pages] == ["(not set)", "/pages/contact"]


def test_patterns_are_checked_and_kept_per_client(client, db, client_a, client_b, admin_user):
    a = client_header(client_a.id, admin_user.email)
    assert client.put("/v2/conversions/completion-patterns", json=[{"pattern": "has space"}], headers=a).status_code == 400
    assert client.put("/v2/conversions/completion-patterns", json=[{"pattern": "   "}], headers=a).status_code == 400
    too_many = [{"pattern": f"/p{i}"} for i in range(21)]
    assert client.put("/v2/conversions/completion-patterns", json=too_many, headers=a).status_code == 400

    client.put("/v2/conversions/completion-patterns", json=[{"pattern": "/thank-you"}], headers=a)
    other = client.get("/v2/conversions/completion-patterns", headers=client_header(client_b.id, admin_user.email))
    assert other.json() == []


def test_patterns_do_not_touch_the_offer_pages(client, db, client_a, admin_user):
    from app.models.config import ClientConversionPage

    client.put(
        "/v2/conversions/completion-patterns",
        json=[{"pattern": "/thank-you"}],
        headers=client_header(client_a.id, admin_user.email),
    )
    assert db.query(ClientConversionPage).count() == 0


def test_counts_cover_every_page_even_when_the_list_is_trimmed(db, client_a, monkeypatch):
    rows = [_row(f"/checkouts/cn/{i:04d}/en-us/thank-you", "purchase", 1) for i in range(350)]
    rows.append(_row("/pages/contact", "form_submit", 4))
    _ga4(db, client_a, monkeypatch, rows)

    pages = svc.pages_for_events(db, client_a, ["purchase", "form_submit"])
    summary = svc.summarise(pages, limit=200)

    assert summary["suggested"] == [{"pattern": "/thank-you", "total": 350, "pages": 350}]
    assert len(summary["pages"]) == 200 and summary["pages_not_shown"] == 151
