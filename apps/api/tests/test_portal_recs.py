"""What a client sees of the recommendations, and what a client can change."""

from __future__ import annotations

from app.models.user import UserRole
from tests.conftest import client_header
from tests.test_consulting_recs import FULL, move
from tests.test_portal_access import consult, viewer

SECRET = "Owner is sensitive about pricing."


def publish(client, db, client_a, admin_user, **over):
    consult(db, client_a)
    h = client_header(client_a.id, admin_user.email)
    rec = client.post("/v2/consulting/recommendations", json={**FULL, "internal_notes": SECRET, "confidence_reasons": ["only one source"], **over}, headers=h).json()
    move(client, h, rec, "approved")
    move(client, h, rec, "published")
    return h, rec


def test_a_client_sees_only_published_briefs_most_urgent_first(client, db, client_a, admin_user):
    h, high = publish(client, db, client_a, admin_user)
    _, low = publish(client, db, client_a, admin_user, title="Low one", priority="low")
    client.post("/v2/consulting/recommendations", json={**FULL, "title": "Still a draft"}, headers=h)
    viewer(db, client_a, "viewer@cato.example")
    res = client.get("/v2/consulting/portal/recommendations", headers=client_header(client_a.id, "viewer@cato.example")).json()
    assert [r["title"] for r in res["recommendations"]] == [FULL["title"], "Low one"] and res["can_update"] is False


def test_nothing_internal_reaches_a_client(client, db, client_a, admin_user):
    h, rec = publish(client, db, client_a, admin_user)
    viewer(db, client_a, "viewer@cato.example")
    v = client_header(client_a.id, "viewer@cato.example")
    one = client.get(f"/v2/consulting/portal/recommendations/{rec['id']}", headers=v).json()
    body = (client.get("/v2/consulting/portal/recommendations", headers=v).text + client.get(f"/v2/consulting/portal/recommendations/{rec['id']}", headers=v).text + client.get("/v2/consulting/portal/overview", headers=v).text)
    for secret in (SECRET, "only one source", "internal_notes", "confidence_reasons", "source_ref", "created_by", "approved_by", "published_by", "revision", "events", admin_user.email):
        assert secret not in body, secret
    assert set(one) == {*__import__("app.services.consulting_recs", fromlist=["x"]).CLIENT_FIELDS, "id", "measure_on", "implemented_on", "published_at", "verified_at", "reported", "target_urls", "can_update"}


def test_an_unpublished_or_other_clients_brief_is_not_found(client, db, client_a, client_b, admin_user):
    h, rec = publish(client, db, client_a, admin_user)
    draft = client.post("/v2/consulting/recommendations", json=FULL, headers=h).json()
    viewer(db, client_a, "viewer@cato.example")
    v = client_header(client_a.id, "viewer@cato.example")
    assert client.get(f"/v2/consulting/portal/recommendations/{draft['id']}", headers=v).status_code == 404
    consult(db, client_b)
    other = client_header(client_b.id, admin_user.email)
    assert client.get(f"/v2/consulting/portal/recommendations/{rec['id']}", headers=other).status_code == 404
    assert client.get(f"/v2/consulting/portal/recommendations/{rec['id']}", headers=client_header(client_b.id, "viewer@cato.example")).status_code == 403
    move(client, h, rec, "approved")  # unpublish
    assert client.get(f"/v2/consulting/portal/recommendations/{rec['id']}", headers=v).status_code == 404


def test_a_client_admin_updates_status_recorded_as_the_clients_and_never_verified(client, db, client_a, admin_user):
    h, rec = publish(client, db, client_a, admin_user)
    viewer(db, client_a, "boss@cato.example", UserRole.CLIENT_ADMIN)
    b = client_header(client_a.id, "boss@cato.example")
    out = client.post(f"/v2/consulting/portal/recommendations/{rec['id']}/progress", json={"status": "completed", "implemented_on": "2026-11-05", "notes": "Done by Sam."}, headers=b).json()
    assert out["impl_status"] == "completed" and out["client_notes"] == "Done by Sam." and out["verification"] == "unverified" and out["reported"] is True
    staff = client.get(f"/v2/consulting/recommendations/{rec['id']}", headers=h).json()
    assert staff["impl_status_source"] == "client" and staff["events"][0]["by"] == "boss@cato.example"


def test_a_read_only_client_cannot_update_and_no_one_can_change_the_text_or_verify(client, db, client_a, admin_user):
    h, rec = publish(client, db, client_a, admin_user)
    viewer(db, client_a, "viewer@cato.example")
    viewer(db, client_a, "boss@cato.example", UserRole.CLIENT_ADMIN)
    url = f"/v2/consulting/portal/recommendations/{rec['id']}/progress"
    assert client.post(url, json={"status": "planned"}, headers=client_header(client_a.id, "viewer@cato.example")).status_code == 403
    b = client_header(client_a.id, "boss@cato.example")
    assert client.post(url, json={"title": "Hacked"}, headers=b).status_code == 422
    assert client.post(url, json={"verification": "verified"}, headers=b).status_code == 422
    assert client.post(url, json={"status": "done"}, headers=b).status_code == 400
    assert client.get(f"/v2/consulting/recommendations/{rec['id']}", headers=h).json()["title"] == FULL["title"]


def test_staff_previewing_update_on_the_clients_behalf_recorded_as_the_consultants(client, db, client_a, admin_user):
    h, rec = publish(client, db, client_a, admin_user)
    out = client.post(f"/v2/consulting/portal/recommendations/{rec['id']}/progress", json={"status": "planned"}, headers=h).json()
    assert out["impl_status"] == "planned"
    assert client.get(f"/v2/consulting/recommendations/{rec['id']}", headers=h).json()["impl_status_source"] == "consultant"


def test_the_overview_counts_status_and_lists_the_most_important_open_briefs(client, db, client_a, admin_user):
    h, a = publish(client, db, client_a, admin_user)
    _, b = publish(client, db, client_a, admin_user, title="B", priority="low")
    client.post(f"/v2/consulting/recommendations/{b['id']}/progress", json={"status": "completed"}, headers=h)
    viewer(db, client_a, "viewer@cato.example")
    ov = client.get("/v2/consulting/portal/overview", headers=client_header(client_a.id, "viewer@cato.example")).json()
    assert ov["total"] == 2 and ov["counts"]["completed"] == 1 and ov["counts"]["recommended"] == 1 and ov["not_reported"] == 1 and [t["title"] for t in ov["top"]] == [FULL["title"]]
