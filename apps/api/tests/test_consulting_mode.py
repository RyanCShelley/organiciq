"""Consulting clients, and groups of clients (one company's sites)."""

from __future__ import annotations

from app.models.client import Client, ClientGroup, Tier
from tests.conftest import auth_header


def make(client, admin_user, **over):
    body = {"client_name": "Cato Corp", "domain": "cato.example", "service_mode": "consulting", **over}
    return client.post("/clients", json=body, headers=auth_header(admin_user.email))


def test_a_consulting_client_needs_no_tier_and_gets_the_consulting_one(client, db, admin_user):
    res = make(client, admin_user)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["service_mode"] == "consulting" and body["plan_label"] == "Consulting" and body["growth_action_allowance"] is None
    tier = db.query(Tier).filter(Tier.tier_name == "Consulting").one()
    assert str(tier.id) == body["tier_id"] and tier.growth_action_allowance == 0 and tier.tracked_keyword_limit == 100
    second = make(client, admin_user, client_name="Robinson", domain="robinson.example").json()
    assert second["tier_id"] == body["tier_id"] and db.query(Tier).filter(Tier.tier_name == "Consulting").count() == 1


def test_an_execution_client_still_needs_a_tier(client, db, admin_user):
    res = client.post("/clients", json={"client_name": "X", "domain": "x.example"}, headers=auth_header(admin_user.email))
    assert res.status_code == 422 and "tier_id" in res.text


def test_sites_of_one_company_share_a_group_made_on_first_use(client, db, admin_user):
    a = make(client, admin_user, client_name="Flint North", domain="flintnorth.example", group_name="Flint").json()
    b = make(client, admin_user, client_name="Flint South", domain="flintsouth.example", group_name="  flint ").json()
    assert a["group_name"] == "Flint" and a["group_slug"] == "flint" and b["group_slug"] == "flint"
    assert db.query(ClientGroup).count() == 1


def test_a_client_can_move_between_groups_and_modes(client, db, admin_user, client_a):
    h = auth_header(admin_user.email)
    out = client.patch(f"/clients/{client_a.id}", json={"service_mode": "consulting", "group_name": "Flint"}, headers=h).json()
    assert out["service_mode"] == "consulting" and out["group_name"] == "Flint"
    out = client.patch(f"/clients/{client_a.id}", json={"group_name": ""}, headers=h).json()
    assert out["group_name"] is None and out["service_mode"] == "consulting"
    assert db.get(Client, client_a.id).group_id is None


def test_an_execution_client_reads_as_before(client, db, admin_user, client_a):
    body = client.get("/clients", headers=auth_header(admin_user.email)).json()[0]
    assert body["service_mode"] == "execution" and body["group_name"] is None and body["plan_label"]


def test_a_consulting_client_has_no_monthly_cap_on_its_plan(client, db, admin_user, client_a):
    from tests.conftest import client_header

    client.patch(f"/clients/{client_a.id}", json={"service_mode": "consulting"}, headers=auth_header(admin_user.email))
    h = client_header(client_a.id, admin_user.email)
    for i in range(3):
        client.post("/v2/engine/tasks", json={"month": "2026-11", "kind": "suggestion", "rule_id": f"S-{i}", "search": "q", "page": f"https://clienta.example/p{i}", "title": "t", "steps": ["x"], "evidence": []}, headers=h)
    allowance = client.get("/v2/engine/tasks?month=2026-11", headers=h).json()["allowance"]
    assert allowance == {"monthly": None, "used": 3, "over": False}
