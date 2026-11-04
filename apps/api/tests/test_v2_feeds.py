"""Feed URLs on a client: add, list, remove, and keep clients apart."""

from __future__ import annotations

from app.models.client_feed import ClientFeed
from tests.conftest import client_header

FEED = "https://absolutely-natural.com/blogs/charley-s-corner.atom"


def test_add_then_list(client, db, client_a, admin_user):
    headers = client_header(client_a.id, admin_user.email)

    created = client.post("/v2/feeds", json={"url": FEED, "label": "Charley's Corner"}, headers=headers)
    assert created.status_code == 201
    assert created.json()["label"] == "Charley's Corner"

    listed = client.get("/v2/feeds", headers=headers).json()
    assert [f["url"] for f in listed] == [FEED]


def test_more_than_one_feed_is_allowed(client, db, client_a, admin_user):
    headers = client_header(client_a.id, admin_user.email)
    client.post("/v2/feeds", json={"url": FEED}, headers=headers)
    client.post("/v2/feeds", json={"url": "https://example.com/news.xml"}, headers=headers)
    assert len(client.get("/v2/feeds", headers=headers).json()) == 2


def test_the_same_feed_twice_is_refused_even_with_different_spelling(client, db, client_a, admin_user):
    headers = client_header(client_a.id, admin_user.email)
    client.post("/v2/feeds", json={"url": FEED}, headers=headers)
    again = client.post("/v2/feeds", json={"url": FEED.upper() + "/"}, headers=headers)
    assert again.status_code == 409
    assert db.query(ClientFeed).count() == 1


def test_a_value_that_is_not_a_web_address_is_refused(client, db, client_a, admin_user):
    headers = client_header(client_a.id, admin_user.email)
    for bad in ["", "   ", "absolutely-natural.com/feed", "ftp://x.com/feed", "https://", "https://a b.com"]:
        response = client.post("/v2/feeds", json={"url": bad}, headers=headers)
        assert response.status_code == 400, bad
    assert db.query(ClientFeed).count() == 0


def test_remove(client, db, client_a, admin_user):
    headers = client_header(client_a.id, admin_user.email)
    feed_id = client.post("/v2/feeds", json={"url": FEED}, headers=headers).json()["id"]

    assert client.delete(f"/v2/feeds/{feed_id}", headers=headers).status_code == 204
    assert client.get("/v2/feeds", headers=headers).json() == []
    assert client.delete(f"/v2/feeds/{feed_id}", headers=headers).status_code == 404


def test_one_clients_feed_cannot_be_removed_through_another(client, db, client_a, client_b, admin_user):
    feed_id = client.post(
        "/v2/feeds", json={"url": FEED}, headers=client_header(client_a.id, admin_user.email)
    ).json()["id"]

    other = client_header(client_b.id, admin_user.email)
    assert client.delete(f"/v2/feeds/{feed_id}", headers=other).status_code == 404
    assert client.get("/v2/feeds", headers=other).json() == []
    assert db.query(ClientFeed).count() == 1


def test_adding_needs_a_client(client, db, client_a, admin_user):
    from tests.conftest import auth_header

    response = client.post("/v2/feeds", json={"url": FEED}, headers=auth_header(admin_user.email))
    assert response.status_code == 400
