"""The monthly focus: save, read back per month, one per month, clients kept apart."""

from __future__ import annotations

from app.models.client_focus import ClientFocus
from app.models.watchlist import WatchlistBucket
from tests.conftest import client_header


def _bucket(db, client, name="Natural & Mineral Sunscreen"):
    bucket = WatchlistBucket(client_id=client.id, name=name, name_key=name.lower(), sort_order=0)
    db.add(bucket)
    db.commit()
    return bucket


def test_a_focus_is_saved_and_read_back_for_its_month(client, db, client_a, admin_user):
    headers = client_header(client_a.id, admin_user.email)
    bucket = _bucket(db, client_a)

    saved = client.put(
        "/v2/focus/2026-10", json={"focus": "traffic", "bucket_id": str(bucket.id)}, headers=headers
    )
    assert saved.status_code == 200

    read = client.get("/v2/focus/2026-10", headers=headers).json()
    assert read == {
        "month": "2026-10",
        "focus": "traffic",
        "bucket_id": str(bucket.id),
        "bucket_name": "Natural & Mineral Sunscreen",
    }


def test_a_month_with_no_focus_reads_as_null(client, db, client_a, admin_user):
    response = client.get("/v2/focus/2026-11", headers=client_header(client_a.id, admin_user.email))
    assert response.status_code == 200 and response.json() is None


def test_setting_a_month_again_replaces_it(client, db, client_a, admin_user):
    headers = client_header(client_a.id, admin_user.email)
    client.put("/v2/focus/2026-10", json={"focus": "traffic"}, headers=headers)
    client.put("/v2/focus/2026-10", json={"focus": "leads"}, headers=headers)

    assert db.query(ClientFocus).count() == 1
    assert client.get("/v2/focus/2026-10", headers=headers).json()["focus"] == "leads"


def test_months_are_kept_separately_and_listed_newest_first(client, db, client_a, admin_user):
    headers = client_header(client_a.id, admin_user.email)
    client.put("/v2/focus/2026-09", json={"focus": "visibility"}, headers=headers)
    client.put("/v2/focus/2026-10", json={"focus": "traffic"}, headers=headers)

    listed = client.get("/v2/focus", headers=headers).json()
    assert [(f["month"], f["focus"]) for f in listed] == [("2026-10", "traffic"), ("2026-09", "visibility")]


def test_only_the_three_focuses_are_accepted(client, db, client_a, admin_user):
    headers = client_header(client_a.id, admin_user.email)
    response = client.put("/v2/focus/2026-10", json={"focus": "backlinks"}, headers=headers)
    assert response.status_code == 422
    assert db.query(ClientFocus).count() == 0


def test_a_bad_month_is_refused(client, db, client_a, admin_user):
    headers = client_header(client_a.id, admin_user.email)
    for bad in ["2026-13", "2026-1", "October", "2026-00"]:
        assert client.put(f"/v2/focus/{bad}", json={"focus": "traffic"}, headers=headers).status_code == 400, bad


def test_another_clients_bucket_is_refused(client, db, client_a, client_b, admin_user):
    other = _bucket(db, client_b, "Not mine")
    response = client.put(
        "/v2/focus/2026-10",
        json={"focus": "traffic", "bucket_id": str(other.id)},
        headers=client_header(client_a.id, admin_user.email),
    )
    assert response.status_code == 400
    assert db.query(ClientFocus).count() == 0


def test_one_clients_focus_is_not_visible_to_another(client, db, client_a, client_b, admin_user):
    client.put("/v2/focus/2026-10", json={"focus": "traffic"}, headers=client_header(client_a.id, admin_user.email))
    assert client.get("/v2/focus/2026-10", headers=client_header(client_b.id, admin_user.email)).json() is None


def test_clear(client, db, client_a, admin_user):
    headers = client_header(client_a.id, admin_user.email)
    client.put("/v2/focus/2026-10", json={"focus": "traffic"}, headers=headers)
    assert client.delete("/v2/focus/2026-10", headers=headers).status_code == 204
    assert client.get("/v2/focus/2026-10", headers=headers).json() is None


def test_deleting_the_bucket_keeps_the_focus(client, db, client_a, admin_user):
    headers = client_header(client_a.id, admin_user.email)
    bucket = _bucket(db, client_a)
    client.put("/v2/focus/2026-10", json={"focus": "traffic", "bucket_id": str(bucket.id)}, headers=headers)

    db.delete(bucket)
    db.commit()

    read = client.get("/v2/focus/2026-10", headers=headers).json()
    assert read["focus"] == "traffic" and read["bucket_id"] is None
