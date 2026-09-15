from tests.conftest import auth_header, client_header


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


# --- Team access ------------------------------------------------------------
#
# SMA_TEAM users see nothing until assigned, and there was no way to assign
# without calling the API directly.


def test_client_team_includes_admins_who_need_no_assignment(client, db, client_a, admin_user):
    """
    Admins see every client without a row in user_clients. Omitting them would
    make the list read as "nobody has access" when several people do.
    """
    res = client.get(
        f"/admin/clients/{client_a.id}/team", headers=auth_header(admin_user.email)
    )
    body = res.json()

    assert res.status_code == 200
    admins = [m for m in body if m["via_admin"]]
    assert any(m["email"] == admin_user.email for m in admins)


def test_assign_then_unassign_a_team_member(client, db, client_a, admin_user, team_user):
    headers = auth_header(admin_user.email)

    assigned = client.post(
        "/admin/user-clients",
        headers=headers,
        json={"user_id": str(team_user.id), "client_id": str(client_a.id)},
    )
    assert assigned.status_code == 201

    team = client.get(f"/admin/clients/{client_a.id}/team", headers=headers).json()
    assert any(m["email"] == team_user.email and not m["via_admin"] for m in team)

    removed = client.request(
        "DELETE",
        "/admin/user-clients",
        headers=headers,
        json={"user_id": str(team_user.id), "client_id": str(client_a.id)},
    )
    assert removed.status_code == 204

    team = client.get(f"/admin/clients/{client_a.id}/team", headers=headers).json()
    assert not any(m["email"] == team_user.email and not m["via_admin"] for m in team)


def test_team_endpoints_require_admin(client, team_user, client_a):
    """A team member must not be able to grant themselves more access."""
    headers = auth_header(team_user.email)

    assert client.get("/admin/users", headers=headers).status_code == 403
    assert (
        client.get(f"/admin/clients/{client_a.id}/team", headers=headers).status_code == 403
    )
    assert (
        client.post(
            "/admin/user-clients",
            headers=headers,
            json={"user_id": str(team_user.id), "client_id": str(client_a.id)},
        ).status_code
        == 403
    )


def test_unassigning_a_missing_link_is_not_an_error(client, client_a, admin_user, team_user):
    res = client.request(
        "DELETE",
        "/admin/user-clients",
        headers=auth_header(admin_user.email),
        json={"user_id": str(team_user.id), "client_id": str(client_a.id)},
    )
    assert res.status_code == 204
