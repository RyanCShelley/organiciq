"""Adding a client through POST /clients, then editing the fields v2's Settings screens send."""

from __future__ import annotations

from tests.conftest import auth_header


def test_a_client_can_be_added_then_edited(client, db, tier, admin_user):
    headers = auth_header(admin_user.email)

    created = client.post(
        "/clients",
        json={
            "service_reporting": {"organiciq": True, "ad_accelerator": False},
            "client_name": "ZZ Test Co",
            "domain": "zztest.example",
            "tier_id": str(tier.id),
            "start_date": "2026-09-01",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["slug"] == "zz-test-co"
    assert body["plan_label"] == f"{tier.tier_name} plan"
    assert body["service_reporting"] == {"organiciq": True, "ad_accelerator": False}

    edited = client.patch(
        f"/clients/{body['id']}",
        json={
            "service_reporting": {"organiciq": True, "ad_accelerator": True},
            "status": "active",
            "sitemap_url": "https://zztest.example/sitemap.xml",
            "path_prefix": "/unmanned",
            "primary_market": "Canada",
            "competitor_domains": ["a.com", "ZZTEST.example", "b.com"],
            "brand_aliases": ["Zz Testing Co"],
        },
        headers=headers,
    )
    assert edited.status_code == 200, edited.text
    out = edited.json()
    assert out["service_reporting"] == {"organiciq": True, "ad_accelerator": True}
    assert out["status"] == "active" and out["path_prefix"] == "/unmanned"
    assert out["competitor_domains"] == ["a.com", "b.com"]
    assert out["brand_aliases"] == ["zz testing co"]


def test_a_client_can_be_tagged_ecommerce_and_the_tag_is_checked(client, db, tier, admin_user):
    headers = auth_header(admin_user.email)
    created = client.post(
        "/clients",
        json={"client_name": "Shop Co", "domain": "shop.example", "tier_id": str(tier.id), "business_model": "ecommerce"},
        headers=headers,
    )
    assert created.status_code == 201 and created.json()["business_model"] == "ecommerce"

    cid = created.json()["id"]
    both = client.patch(f"/clients/{cid}", json={"business_model": "both"}, headers=headers)
    assert both.json()["business_model"] == "both"

    assert client.patch(f"/clients/{cid}", json={"business_model": "saas"}, headers=headers).status_code == 422
    # A save that does not mention it leaves it alone.
    assert client.patch(f"/clients/{cid}", json={"status": "active"}, headers=headers).json()["business_model"] == "both"


def test_an_untagged_client_reads_as_not_said(client, db, tier, admin_user):
    created = client.post(
        "/clients",
        json={"client_name": "Plain Co", "domain": "plain.example", "tier_id": str(tier.id)},
        headers=auth_header(admin_user.email),
    )
    assert created.json()["business_model"] is None
