"""The consulting portal: who may open which client's portal, and that no internal route is open to a client user."""

from __future__ import annotations

import uuid

import pytest
from fastapi.routing import APIRoute

from app.main import app
from app.models.client import Client, ClientGroup
from app.models.user import User, UserClient, UserRole
from tests.conftest import auth_header, client_header

#: Routes that are meant to be reachable without staff rights: health, the sign-in hand-off (guarded by a shared secret), the OAuth return (guarded by a
#: state token), and the portal itself (guarded by its own access rule, tested below).
OPEN = {
    ("GET", "/health"), ("POST", "/auth/upsert"), ("GET", "/oauth/google/callback"),
    ("GET", "/v2/consulting/clients"), ("GET", "/v2/consulting/portal"), ("GET", "/v2/consulting/portal/overview"), ("GET", "/v2/consulting/portal/recommendations"),
    ("GET", "/v2/consulting/portal/recommendations/{rec_id}"), ("POST", "/v2/consulting/portal/recommendations/{rec_id}/progress"),
}


def viewer(db, client: Client, email: str, role=UserRole.CLIENT_VIEWER) -> User:
    user = User(id=uuid.uuid4(), email=email, name="Viewer", google_sub=f"sub-{email}", role=role)
    db.add(user)
    db.flush()
    db.add(UserClient(user_id=user.id, client_id=client.id, role=role))
    db.commit()
    return user


def consult(db, client: Client, group: str | None = None) -> Client:
    client.service_mode = "consulting"
    if group:
        g = db.query(ClientGroup).filter(ClientGroup.name == group).first() or ClientGroup(name=group, slug=group.lower())
        db.add(g)
        db.flush()
        client.group_id = g.id
    db.commit()
    return client


def internal_routes():
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            if (method, route.path) not in OPEN:
                yield method, route.path


@pytest.mark.parametrize("method,path", list(internal_routes()))
def test_no_internal_route_is_open_to_a_client_user(client, db, client_a, method, path):
    """Every route outside the portal refuses a client-role user who is assigned to the client, so a new route that forgets its gate fails here."""
    consult(db, client_a)
    viewer(db, client_a, "viewer@cato.example")
    filled = path
    for part in [p for p in path.split("/") if p.startswith("{")]:
        filled = filled.replace(part, str(uuid.uuid4()) if "id" in part else "2026-10")
    res = client.request(method, filled, headers=client_header(client_a.id, "viewer@cato.example"), json={})
    assert res.status_code in (401, 403), f"{method} {path} answered {res.status_code} to a client user"


def test_a_client_user_opens_only_their_own_consulting_portal(client, db, client_a, client_b):
    consult(db, client_a)
    consult(db, client_b)
    viewer(db, client_a, "viewer@cato.example")
    own = client.get("/v2/consulting/portal", headers=client_header(client_a.id, "viewer@cato.example"))
    assert own.status_code == 200 and own.json()["client"]["slug"] == client_a.slug and own.json()["previewing"] is False
    other = client.get("/v2/consulting/portal", headers=client_header(client_b.id, "viewer@cato.example"))
    assert other.status_code == 403


def test_a_client_without_a_portal_is_closed_to_its_own_user_and_not_found_for_staff(client, db, client_a, admin_user):
    viewer(db, client_a, "viewer@cato.example")
    assert client.get("/v2/consulting/portal", headers=client_header(client_a.id, "viewer@cato.example")).status_code == 403
    assert client.get("/v2/consulting/portal", headers=client_header(client_a.id, admin_user.email)).status_code == 404


def test_one_company_group_opens_all_its_sites_and_no_one_elses(client, db, client_a, client_b, tier):
    from tests.conftest import _make_client

    third = _make_client(db, tier, "Client C")
    consult(db, client_a, "Flint")
    consult(db, client_b, "Flint")
    consult(db, third, "Other")
    viewer(db, client_a, "viewer@flint.example")
    h = lambda c: client_header(c.id, "viewer@flint.example")  # noqa: E731
    sites = client.get("/v2/consulting/clients", headers=auth_header("viewer@flint.example")).json()["clients"]
    assert {s["slug"] for s in sites} == {client_a.slug, client_b.slug}
    assert client.get("/v2/consulting/portal", headers=h(client_b)).json()["sites"][0]["slug"] == client_a.slug
    assert client.get("/v2/consulting/portal", headers=h(third)).status_code == 403


def test_the_portal_shows_the_client_and_brand_but_no_plan_or_connections(client, db, client_a, admin_user):
    consult(db, client_a)
    body = client.get("/v2/consulting/portal", headers=client_header(client_a.id, admin_user.email)).json()
    assert body["previewing"] is True and body["brand"] == {"name": "SMA Marketing", "powered_by": "Organic IQ"}
    assert set(body["client"]) == {"id", "slug", "name", "domain", "group"}
    text = str(body).lower()
    assert "tier" not in text and "allowance" not in text and "teamwork" not in text and "integration" not in text


def test_a_staff_member_not_assigned_to_a_client_cannot_open_its_portal(client, db, client_b, team_user):
    consult(db, client_b)
    assert client.get("/v2/consulting/portal", headers=client_header(client_b.id, team_user.email)).status_code == 403


def test_the_workspace_profile_is_staff_only_and_saves(client, db, client_a, admin_user):
    consult(db, client_a)
    viewer(db, client_a, "viewer@cato.example")
    assert client.get("/v2/consulting/profile", headers=client_header(client_a.id, "viewer@cato.example")).status_code == 403
    assert client.put("/v2/consulting/profile", json={"goals": "More booked jobs"}, headers=client_header(client_a.id, "viewer@cato.example")).status_code == 403
    h = client_header(client_a.id, admin_user.email)
    saved = client.put("/v2/consulting/profile", json={"goals": " More booked jobs ", "internal_notes": "Owner is sensitive about pricing."}, headers=h).json()
    assert saved["goals"] == "More booked jobs" and saved["updated_by"] == admin_user.email
    assert client.get("/v2/consulting/profile", headers=h).json()["internal_notes"].startswith("Owner")
