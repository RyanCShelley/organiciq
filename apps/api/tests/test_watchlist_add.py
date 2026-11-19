"""Quick watchlist keyword addition (`POST /v2/watchlist/keywords`) with default/named bucket handling."""

from __future__ import annotations

import uuid

from app.models.watchlist import WatchlistBucket, WatchlistKeyword
from tests.conftest import client_header


def test_add_keyword_creates_default_general_bucket_when_none_exist(client, db, client_a, admin_user):
    headers = client_header(client_a.id, admin_user.email)
    resp = client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "  Mineral   SPF "},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["keyword"] == "Mineral SPF"
    assert body["keyword_key"] == "mineral spf"
    assert body["bucket_name"] == "General"
    assert body["created"] is True
    assert body["bucket_created"] is True

    bucket = db.query(WatchlistBucket).filter(WatchlistBucket.id == body["bucket_id"]).one()
    assert bucket.name_key == "general"
    assert bucket.sort_order == 0
    kw = db.query(WatchlistKeyword).filter(WatchlistKeyword.id == body["id"]).one()
    assert kw.source == "manual"


def test_add_keyword_uses_existing_bucket_by_id_and_creates_named_bucket(client, db, client_a, admin_user):
    headers = client_header(client_a.id, admin_user.email)
    existing_bucket = WatchlistBucket(
        client_id=client_a.id, name="Core", name_key="core", sort_order=0
    )
    db.add(existing_bucket)
    db.commit()

    first = client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "reef safe sunscreen", "bucket_id": str(existing_bucket.id)},
        headers=headers,
    )
    assert first.status_code == 200
    b1 = first.json()
    assert b1["bucket_id"] == str(existing_bucket.id)
    assert b1["bucket_name"] == "Core"
    assert b1["created"] is True
    assert b1["bucket_created"] is False

    # Idempotent repeat on same normalized keyword_key
    repeat = client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "  REEF   SAFE SUNSCREEN "},
        headers=headers,
    )
    assert repeat.status_code == 200
    b_repeat = repeat.json()
    assert b_repeat["id"] == b1["id"]
    assert b_repeat["created"] is False
    assert b_repeat["bucket_created"] is False

    # Named bucket auto-creation
    named = client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "zinc oxide lotion", "bucket_name": "Product Lines"},
        headers=headers,
    )
    assert named.status_code == 200
    b_named = named.json()
    assert b_named["bucket_name"] == "Product Lines"
    assert b_named["created"] is True
    assert b_named["bucket_created"] is True


def test_add_keyword_validation_and_not_found(client, db, client_a, client_b, admin_user):
    headers = client_header(client_a.id, admin_user.email)
    blank = client.post("/v2/watchlist/keywords", json={"keyword": "   "}, headers=headers)
    assert blank.status_code == 422

    foreign_bucket = WatchlistBucket(
        client_id=client_b.id, name="Other", name_key="other", sort_order=0
    )
    db.add(foreign_bucket)
    db.commit()

    bad = client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "valid term", "bucket_id": str(foreign_bucket.id)},
        headers=headers,
    )
    assert bad.status_code == 404

    missing = client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "valid term", "bucket_id": str(uuid.uuid4())},
        headers=headers,
    )
    assert missing.status_code == 404
