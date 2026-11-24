"""Watchlist keyword & bucket CRUD (`POST`/`PATCH`/`DELETE`) + auth & cascade tests."""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.main import app
from app.models.client_focus import ClientFocus
from app.models.user import User, UserClient, UserRole
from app.models.watchlist import WatchlistBucket, WatchlistKeyword
from tests.conftest import auth_header, client_header


def _seed_client_user(db, client_obj, email: str, role: UserRole) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email,
        name=role.value,
        google_sub=f"sub-{email}",
        role=role,
    )
    db.add(user)
    db.flush()
    db.add(UserClient(user_id=user.id, client_id=client_obj.id, role=role))
    db.commit()
    return user


def test_add_keyword_with_full_metadata(client, db, client_a, admin_user):
    headers = client_header(client_a.id, admin_user.email)
    resp = client.post(
        "/v2/watchlist/keywords",
        json={
            "keyword": "  mineral   spf ",
            "bucket_name": "Sun Care",
            "volume": 2400,
            "difficulty": 35,
            "intent": "  commercial  ",
            "paired_ai_prompt": "  best mineral spf? ",
            "notes": " Top priority ",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["keyword"] == "mineral spf"
    assert body["keyword_key"] == "mineral spf"
    assert body["bucket_name"] == "Sun Care"
    assert body["created"] is True
    assert body["bucket_created"] is True

    wl = client.get("/v2/watchlist", headers=headers)
    assert wl.status_code == 200
    wl_body = wl.json()
    assert wl_body["keyword_count"] == 1
    assert len(wl_body["buckets"]) == 1
    kw_out = wl_body["buckets"][0]["keywords"][0]
    assert kw_out["id"] == body["id"]
    assert kw_out["keyword"] == "mineral spf"
    assert kw_out["volume"] == 2400
    assert kw_out["difficulty"] == 35
    assert kw_out["intent"] == "commercial"
    assert kw_out["paired_ai_prompt"] == "best mineral spf?"
    assert kw_out["notes"] == "Top priority"

    db_row = db.query(WatchlistKeyword).filter(WatchlistKeyword.id == body["id"]).one()
    assert db_row.source == "manual"


def test_add_keyword_validation_bounds(client, client_a, admin_user):
    headers = client_header(client_a.id, admin_user.email)
    bad_payloads = [
        {"keyword": "mineral spf", "volume": -1},
        {"keyword": "mineral spf", "difficulty": -1},
        {"keyword": "mineral spf", "difficulty": 101},
        {"keyword": "mineral spf", "intent": "x" * 121},
    ]
    for payload in bad_payloads:
        resp = client.post("/v2/watchlist/keywords", json=payload, headers=headers)
        assert resp.status_code == 422, f"Expected 422 for {payload}, got {resp.status_code}"


def test_bulk_add_keywords_deduplicates_and_creates_bucket(client, db, client_a, admin_user):
    headers = client_header(client_a.id, admin_user.email)
    existing_bucket = WatchlistBucket(
        client_id=client_a.id, name="Core", name_key="core", sort_order=0
    )
    db.add(existing_bucket)
    db.flush()
    db.add(
        WatchlistKeyword(
            client_id=client_a.id,
            bucket_id=existing_bucket.id,
            keyword="mineral spf",
            keyword_key="mineral spf",
            source="manual",
        )
    )
    db.commit()

    resp = client.post(
        "/v2/watchlist/keywords/bulk",
        json={
            "items": [
                {"keyword": "  MINERAL   SPF ", "bucket_name": "Sun Care"},
                {"keyword": "reef safe balm", "bucket_name": "Sun Care", "volume": 800},
                {"keyword": "zinc lotion", "bucket_name": "  sun   care ", "difficulty": 20},
                {"keyword": "  Reef   Safe Balm ", "bucket_name": "Sun Care"},
            ]
        },
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["created_count"] == 2
    assert body["existing_count"] == 2
    assert len(body["results"]) == 4
    assert body["results"][0]["created"] is False
    assert body["results"][1]["created"] is True
    assert body["results"][1]["bucket_created"] is True
    assert body["results"][2]["created"] is True
    assert body["results"][2]["bucket_created"] is False
    assert body["results"][3]["created"] is False

    wl = client.get("/v2/watchlist", headers=headers).json()
    assert wl["keyword_count"] == 3
    assert [b["name"] for b in wl["buckets"]] == ["Core", "Sun Care"]


def test_patch_keyword_updates_fields_and_normalizes_key(client, db, client_a, admin_user):
    headers = client_header(client_a.id, admin_user.email)
    b = WatchlistBucket(client_id=client_a.id, name="Core", name_key="core", sort_order=0)
    db.add(b)
    db.flush()
    kw = WatchlistKeyword(
        client_id=client_a.id,
        bucket_id=b.id,
        keyword="natural spf",
        keyword_key="natural spf",
        source="csv",
    )
    db.add(kw)
    db.commit()

    resp = client.patch(
        f"/v2/watchlist/keywords/{kw.id}",
        json={
            "keyword": "  Natural   Sunscreen ",
            "volume": 5000,
            "difficulty": 42,
            "intent": "transactional",
            "paired_ai_prompt": "top natural sunscreen",
            "notes": "Updated",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["keyword"] == "Natural Sunscreen"
    assert body["volume"] == 5000
    assert body["difficulty"] == 42
    assert body["intent"] == "transactional"
    assert body["paired_ai_prompt"] == "top natural sunscreen"
    assert body["notes"] == "Updated"
    assert body["bucket_id"] == str(b.id)
    assert body["bucket_name"] == "Core"
    assert body["source"] == "csv"

    db.refresh(kw)
    assert kw.keyword_key == "natural sunscreen"
    assert kw.source == "csv"

    wl = client.get("/v2/watchlist", headers=headers).json()
    assert wl["buckets"][0]["keywords"][0]["keyword"] == "Natural Sunscreen"


def test_patch_keyword_explicit_null_clears_optional_fields_without_touching_omitted(
    client, db, client_a, admin_user
):
    headers = client_header(client_a.id, admin_user.email)
    created = client.post(
        "/v2/watchlist/keywords",
        json={
            "keyword": "reef sunscreen",
            "volume": 1200,
            "difficulty": 28,
            "intent": "commercial",
            "paired_ai_prompt": "best reef sunscreen",
            "notes": "Initial note",
        },
        headers=headers,
    ).json()

    cleared = client.patch(
        f"/v2/watchlist/keywords/{created['id']}",
        json={"volume": None, "notes": None},
        headers=headers,
    )
    assert cleared.status_code == 200
    body = cleared.json()
    assert body["volume"] is None
    assert body["notes"] is None
    assert body["difficulty"] == 28
    assert body["intent"] == "commercial"
    assert body["paired_ai_prompt"] == "best reef sunscreen"

    # Whitespace-only optional string clears to None
    ws = client.patch(
        f"/v2/watchlist/keywords/{created['id']}",
        json={"intent": "   "},
        headers=headers,
    )
    assert ws.status_code == 200
    assert ws.json()["intent"] is None

    # Explicit null or blank on required keyword returns 422
    for bad in ({"keyword": None}, {"keyword": "   "}):
        resp = client.patch(
            f"/v2/watchlist/keywords/{created['id']}",
            json=bad,
            headers=headers,
        )
        assert resp.status_code == 422


def test_patch_keyword_moves_bucket_by_id_and_by_name(client, db, client_a, client_b, admin_user):
    headers = client_header(client_a.id, admin_user.email)
    b1 = WatchlistBucket(client_id=client_a.id, name="Core", name_key="core", sort_order=0)
    b2 = WatchlistBucket(client_id=client_a.id, name="Secondary", name_key="secondary", sort_order=1)
    foreign = WatchlistBucket(client_id=client_b.id, name="Other", name_key="other", sort_order=0)
    db.add_all([b1, b2, foreign])
    db.flush()
    kw = WatchlistKeyword(
        client_id=client_a.id,
        bucket_id=b1.id,
        keyword="mineral tint",
        keyword_key="mineral tint",
        source="manual",
    )
    db.add(kw)
    db.commit()

    move_id = client.patch(
        f"/v2/watchlist/keywords/{kw.id}",
        json={"bucket_id": str(b2.id)},
        headers=headers,
    )
    assert move_id.status_code == 200
    assert move_id.json()["bucket_id"] == str(b2.id)
    assert move_id.json()["bucket_name"] == "Secondary"

    move_name = client.patch(
        f"/v2/watchlist/keywords/{kw.id}",
        json={"bucket_name": "New Group"},
        headers=headers,
    )
    assert move_name.status_code == 200
    assert move_name.json()["bucket_name"] == "New Group"
    new_bucket = (
        db.query(WatchlistBucket)
        .filter(WatchlistBucket.client_id == client_a.id, WatchlistBucket.name_key == "new group")
        .one()
    )
    assert new_bucket.sort_order == 2

    both = client.patch(
        f"/v2/watchlist/keywords/{kw.id}",
        json={"bucket_id": str(b1.id), "bucket_name": "Core"},
        headers=headers,
    )
    assert both.status_code == 422

    null_bucket = client.patch(
        f"/v2/watchlist/keywords/{kw.id}",
        json={"bucket_id": None},
        headers=headers,
    )
    assert null_bucket.status_code == 422

    foreign_resp = client.patch(
        f"/v2/watchlist/keywords/{kw.id}",
        json={"bucket_id": str(foreign.id)},
        headers=headers,
    )
    assert foreign_resp.status_code == 404

    unknown_resp = client.patch(
        f"/v2/watchlist/keywords/{kw.id}",
        json={"bucket_id": str(uuid.uuid4())},
        headers=headers,
    )
    assert unknown_resp.status_code == 404


def test_patch_keyword_duplicate_keyword_key_returns_409(client, client_a, admin_user):
    headers = client_header(client_a.id, admin_user.email)
    k1 = client.post("/v2/watchlist/keywords", json={"keyword": "mineral spf"}, headers=headers).json()
    k2 = client.post("/v2/watchlist/keywords", json={"keyword": "zinc lotion"}, headers=headers).json()

    conflict = client.patch(
        f"/v2/watchlist/keywords/{k2['id']}",
        json={"keyword": "  MINERAL   SPF "},
        headers=headers,
    )
    assert conflict.status_code == 409

    same_row = client.patch(
        f"/v2/watchlist/keywords/{k1['id']}",
        json={"keyword": "Mineral  SPF"},
        headers=headers,
    )
    assert same_row.status_code == 200
    assert same_row.json()["keyword"] == "Mineral SPF"


def test_patch_and_delete_keyword_ownership_and_404(client, db, client_a, client_b, admin_user):
    h_a = client_header(client_a.id, admin_user.email)
    h_b = client_header(client_b.id, admin_user.email)

    kw_a = client.post("/v2/watchlist/keywords", json={"keyword": "alpha term"}, headers=h_a).json()
    kw_b = client.post("/v2/watchlist/keywords", json={"keyword": "beta term"}, headers=h_b).json()

    assert (
        client.patch(
            f"/v2/watchlist/keywords/{kw_b['id']}",
            json={"notes": "cross"},
            headers=h_a,
        ).status_code
        == 404
    )
    assert client.delete(f"/v2/watchlist/keywords/{kw_b['id']}", headers=h_a).status_code == 404

    del_resp = client.delete(f"/v2/watchlist/keywords/{kw_a['id']}", headers=h_a)
    assert del_resp.status_code == 204
    assert client.get("/v2/watchlist", headers=h_a).json()["keyword_count"] == 0
    assert client.delete(f"/v2/watchlist/keywords/{kw_a['id']}", headers=h_a).status_code == 404


def test_bucket_create_and_patch_rename_reorder_and_conflict(client, db, client_a, client_b, admin_user):
    h_a = client_header(client_a.id, admin_user.email)
    h_b = client_header(client_b.id, admin_user.email)

    c1 = client.post("/v2/watchlist/buckets", json={"name": "Core"}, headers=h_a)
    assert c1.status_code == 201
    b1 = c1.json()
    assert b1["sort_order"] == 0

    c2 = client.post("/v2/watchlist/buckets", json={"name": "Secondary"}, headers=h_a)
    assert c2.status_code == 201
    b2 = c2.json()
    assert b2["sort_order"] == 1

    dup = client.post("/v2/watchlist/buckets", json={"name": "  core "}, headers=h_a)
    assert dup.status_code == 409

    patched = client.patch(
        f"/v2/watchlist/buckets/{b2['id']}",
        json={"name": "  Growth  ", "sort_order": 5},
        headers=h_a,
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Growth"
    assert patched.json()["sort_order"] == 5
    assert db.get(WatchlistBucket, uuid.UUID(b2["id"])).name_key == "growth"

    rename_conflict = client.patch(
        f"/v2/watchlist/buckets/{b2['id']}",
        json={"name": "CORE"},
        headers=h_a,
    )
    assert rename_conflict.status_code == 409

    null_name = client.patch(
        f"/v2/watchlist/buckets/{b2['id']}",
        json={"name": None},
        headers=h_a,
    )
    assert null_name.status_code == 422

    other_b = client.post("/v2/watchlist/buckets", json={"name": "Client B"}, headers=h_b).json()
    assert (
        client.patch(
            f"/v2/watchlist/buckets/{other_b['id']}",
            json={"name": "Hijack"},
            headers=h_a,
        ).status_code
        == 404
    )


def test_delete_bucket_confirm_cascade_and_client_focus_set_null(client, db, client_a, admin_user):
    headers = client_header(client_a.id, admin_user.email)
    b = client.post("/v2/watchlist/buckets", json={"name": "Sunscreen"}, headers=headers).json()
    client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "mineral spf", "bucket_id": b["id"]},
        headers=headers,
    )
    client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "reef lotion", "bucket_id": b["id"]},
        headers=headers,
    )
    focus = ClientFocus(
        client_id=client_a.id,
        month=date(2026, 10, 1),
        focus="visibility",
        bucket_id=uuid.UUID(b["id"]),
    )
    db.add(focus)
    db.commit()

    unconfirmed = client.delete(f"/v2/watchlist/buckets/{b['id']}", headers=headers)
    assert unconfirmed.status_code == 409

    confirmed = client.delete(
        f"/v2/watchlist/buckets/{b['id']}",
        params={"confirm": "true"},
        headers=headers,
    )
    assert confirmed.status_code == 200
    body = confirmed.json()
    assert body["deleted"] is True
    assert body["deleted_keywords"] == 2
    assert body["cleared_focuses"] == 1

    assert db.query(WatchlistKeyword).filter(WatchlistKeyword.client_id == client_a.id).count() == 0
    db.expire_all()
    refreshed_focus = db.get(ClientFocus, focus.id)
    assert refreshed_focus is not None
    assert refreshed_focus.bucket_id is None

    focus_resp = client.get("/v2/focus", headers=headers)
    assert focus_resp.status_code == 200
    assert focus_resp.json()[0]["bucket_name"] is None

    # Empty bucket deletes without confirm=true
    empty_b = client.post("/v2/watchlist/buckets", json={"name": "Empty"}, headers=headers).json()
    del_empty = client.delete(f"/v2/watchlist/buckets/{empty_b['id']}", headers=headers)
    assert del_empty.status_code == 200
    assert del_empty.json()["deleted_keywords"] == 0


def test_watchlist_crud_auth_guards(client, db, client_a, client_b, team_user):
    viewer_user = _seed_client_user(db, client_a, "viewer@watchlist.example", UserRole.CLIENT_VIEWER)
    client_admin = _seed_client_user(
        db, client_a, "cadmin@watchlist.example", UserRole.CLIENT_ADMIN
    )

    h_team_a = client_header(client_a.id, team_user.email)
    h_team_b = client_header(client_b.id, team_user.email)

    bucket_resp = client.post("/v2/watchlist/buckets", json={"name": "Team Bucket"}, headers=h_team_a)
    assert bucket_resp.status_code == 201
    bucket_id = bucket_resp.json()["id"]

    kw_resp = client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "team term", "bucket_id": bucket_id},
        headers=h_team_a,
    )
    assert kw_resp.status_code == 200
    kw_id = kw_resp.json()["id"]

    # Unassigned client for team_user -> 403
    assert (
        client.post("/v2/watchlist/buckets", json={"name": "Forbidden"}, headers=h_team_b).status_code
        == 403
    )

    # Client-role users -> 403 across all new routes
    for user in (viewer_user, client_admin):
        hdr = client_header(client_a.id, user.email)
        assert client.post("/v2/watchlist/buckets", json={"name": "X"}, headers=hdr).status_code == 403
        assert (
            client.patch(f"/v2/watchlist/buckets/{bucket_id}", json={"name": "Y"}, headers=hdr).status_code
            == 403
        )
        assert client.delete(f"/v2/watchlist/buckets/{bucket_id}", headers=hdr).status_code == 403
        assert (
            client.post("/v2/watchlist/keywords/bulk", json={"items": [{"keyword": "z"}]}, headers=hdr).status_code
            == 403
        )
        assert (
            client.patch(f"/v2/watchlist/keywords/{kw_id}", json={"notes": "x"}, headers=hdr).status_code
            == 403
        )
        assert client.delete(f"/v2/watchlist/keywords/{kw_id}", headers=hdr).status_code == 403
        assert client.get("/v2/watchlist/suggestions", headers=hdr).status_code == 403

    # Missing X-OrganicIQ-Client-Id header -> 400
    assert (
        client.post(
            "/v2/watchlist/buckets",
            json={"name": "No Client"},
            headers=auth_header(team_user.email),
        ).status_code
        == 400
    )

    # Assigned team_user can delete their own keyword and bucket
    assert client.delete(f"/v2/watchlist/keywords/{kw_id}", headers=h_team_a).status_code == 204
    assert client.delete(f"/v2/watchlist/buckets/{bucket_id}", headers=h_team_a).status_code == 200


def test_unicode_case_folding_length_and_int4_bounds_return_422(client, client_a, admin_user):
    headers = client_header(client_a.id, admin_user.email)

    bad_creates = [
        ("/v2/watchlist/keywords", {"keyword": "\u0130" * 400}),
        ("/v2/watchlist/keywords", {"keyword": "valid", "bucket_name": "\u0130" * 160}),
        ("/v2/watchlist/keywords", {"keyword": "big vol", "volume": 3_000_000_000}),
        ("/v2/watchlist/buckets", {"name": "\u0130" * 160}),
        ("/v2/watchlist/buckets", {"name": "BigSort", "sort_order": 3_000_000_000}),
    ]
    for path, payload in bad_creates:
        resp = client.post(path, json=payload, headers=headers)
        assert resp.status_code == 422, f"Expected 422 for POST {path}, got {resp.status_code}"

    bucket = client.post("/v2/watchlist/buckets", json={"name": "Valid Bucket"}, headers=headers).json()
    kw = client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "valid term", "bucket_id": bucket["id"]},
        headers=headers,
    ).json()

    bad_patches = [
        (f"/v2/watchlist/keywords/{kw['id']}", {"keyword": "\u0130" * 400}),
        (f"/v2/watchlist/keywords/{kw['id']}", {"bucket_name": "\u0130" * 160}),
        (f"/v2/watchlist/keywords/{kw['id']}", {"volume": 3_000_000_000}),
        (f"/v2/watchlist/buckets/{bucket['id']}", {"name": "\u0130" * 160}),
        (f"/v2/watchlist/buckets/{bucket['id']}", {"sort_order": 3_000_000_000}),
    ]
    for path, payload in bad_patches:
        resp = client.patch(path, json=payload, headers=headers)
        assert resp.status_code == 422, f"Expected 422 for PATCH {path}, got {resp.status_code}"


def test_integrity_error_on_concurrent_writes_returns_409_or_idempotent(
    client, db, client_a, admin_user, monkeypatch
):
    headers = client_header(client_a.id, admin_user.email)
    bucket = client.post("/v2/watchlist/buckets", json={"name": "Core"}, headers=headers).json()
    kw = client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "alpha term", "bucket_id": bucket["id"]},
        headers=headers,
    ).json()

    real_commit = Session.commit

    # Simulate concurrent POST /keywords winning the unique-key race before commit
    def commit_with_raced_keyword(self):
        self.rollback()
        winner = WatchlistKeyword(
            client_id=client_a.id,
            bucket_id=uuid.UUID(bucket["id"]),
            keyword="race term",
            keyword_key="race term",
            source="manual",
        )
        self.add(winner)
        real_commit(self)
        raise IntegrityError("INSERT", {}, Exception("uq_watchlist_keyword"))

    monkeypatch.setattr(Session, "commit", commit_with_raced_keyword)
    race_add = client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "race term", "bucket_id": bucket["id"]},
        headers=headers,
    )
    assert race_add.status_code == 200
    assert race_add.json()["created"] is False
    assert race_add.json()["keyword_key"] == "race term"

    # Simulate IntegrityError on PATCH keyword, POST bucket, PATCH bucket -> 409 Conflict
    def commit_raises_integrity(self):
        raise IntegrityError("INSERT/UPDATE", {}, Exception("uq_conflict"))

    monkeypatch.setattr(Session, "commit", commit_raises_integrity)
    assert (
        client.patch(
            f"/v2/watchlist/keywords/{kw['id']}",
            json={"keyword": "beta term"},
            headers=headers,
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/v2/watchlist/buckets",
            json={"name": "Raced Bucket"},
            headers=headers,
        ).status_code
        == 409
    )
    assert (
        client.patch(
            f"/v2/watchlist/buckets/{bucket['id']}",
            json={"name": "Raced Rename"},
            headers=headers,
        ).status_code
        == 409
    )
    monkeypatch.undo()


def test_bulk_add_toctou_integrity_error_on_bucket_and_keyword_resolves_or_409(
    client, db, engine, client_a, admin_user, monkeypatch
):
    headers = client_header(client_a.id, admin_user.email)
    core_bucket = client.post("/v2/watchlist/buckets", json={"name": "Core"}, headers=headers).json()
    core_bucket_id = uuid.UUID(core_bucket["id"])

    real_flush = Session.flush
    raced_bucket = False
    raced_keyword = False

    def flush_with_toctou_race(self, objects=None):
        nonlocal raced_bucket, raced_keyword
        if self is db:
            for obj in list(self.new):
                if (
                    not raced_bucket
                    and isinstance(obj, WatchlistBucket)
                    and obj.name_key == "toctou bucket"
                ):
                    raced_bucket = True
                    with Session(bind=engine) as concurrent_db:
                        concurrent_db.add(
                            WatchlistBucket(
                                client_id=client_a.id,
                                name="TOCTOU Bucket",
                                name_key="toctou bucket",
                                sort_order=1,
                            )
                        )
                        concurrent_db.commit()
                elif (
                    not raced_keyword
                    and isinstance(obj, WatchlistKeyword)
                    and obj.keyword_key == "toctou raced kw"
                ):
                    raced_keyword = True
                    with Session(bind=engine) as concurrent_db:
                        concurrent_db.add(
                            WatchlistKeyword(
                                client_id=client_a.id,
                                bucket_id=core_bucket_id,
                                keyword="toctou raced kw",
                                keyword_key="toctou raced kw",
                                source="manual",
                            )
                        )
                        concurrent_db.commit()
        return real_flush(self, objects=objects)

    monkeypatch.setattr(Session, "flush", flush_with_toctou_race)
    resp = client.post(
        "/v2/watchlist/keywords/bulk",
        json={
            "items": [
                {"keyword": "raced bucket kw1", "bucket_name": "TOCTOU Bucket"},
                {"keyword": "raced bucket kw2", "bucket_name": "  toctou   bucket "},
                {"keyword": "toctou raced kw", "bucket_name": "TOCTOU Bucket"},
                {"keyword": "clean bulk kw", "bucket_name": "Clean Bucket"},
            ]
        },
        headers=headers,
    )
    monkeypatch.undo()

    assert raced_bucket is True
    assert raced_keyword is True
    assert resp.status_code == 200
    body = resp.json()
    assert body["created_count"] == 3
    assert body["existing_count"] == 1
    assert body["results"][0]["created"] is True
    assert body["results"][0]["bucket_created"] is False
    assert body["results"][0]["bucket_name"] == "TOCTOU Bucket"
    assert body["results"][1]["created"] is True
    assert body["results"][1]["bucket_created"] is False
    assert body["results"][1]["bucket_name"] == "TOCTOU Bucket"
    assert body["results"][2]["created"] is False
    assert body["results"][2]["bucket_created"] is False
    assert body["results"][2]["bucket_name"] == "Core"
    assert body["results"][3]["created"] is True
    assert body["results"][3]["bucket_created"] is True
    assert body["results"][3]["bucket_name"] == "Clean Bucket"

    # Real concurrent threads calling POST /v2/watchlist/keywords/bulk
    previous_override = app.dependency_overrides.get(get_db)

    def thread_safe_get_db():
        with Session(bind=engine) as s:
            yield s

    app.dependency_overrides[get_db] = thread_safe_get_db
    try:
        barrier = threading.Barrier(2)

        def call_bulk():
            with TestClient(app) as tc:
                barrier.wait(timeout=5)
                return tc.post(
                    "/v2/watchlist/keywords/bulk",
                    json={
                        "items": [
                            {
                                "keyword": "barrier bulk kw",
                                "bucket_name": "Barrier Bulk Bucket",
                            }
                        ]
                    },
                    headers=headers,
                )

        with ThreadPoolExecutor(max_workers=2) as pool:
            r1, r2 = [f.result() for f in (pool.submit(call_bulk), pool.submit(call_bulk))]
    finally:
        if previous_override is not None:
            app.dependency_overrides[get_db] = previous_override
        else:
            app.dependency_overrides.pop(get_db, None)

    assert r1.status_code == 200
    assert r2.status_code == 200
    created_counts = sorted([r1.json()["created_count"], r2.json()["created_count"]])
    existing_counts = sorted([r1.json()["existing_count"], r2.json()["existing_count"]])
    assert created_counts == [0, 1]
    assert existing_counts == [0, 1]

    # Unresolvable IntegrityError during flush or commit -> 409 Conflict (never 500)
    def flush_raises_unresolvable(self, objects=None):
        if self is db and any(isinstance(o, WatchlistKeyword) for o in self.new):
            raise IntegrityError("INSERT", {}, Exception("unresolvable_fk"))
        return real_flush(self, objects=objects)

    monkeypatch.setattr(Session, "flush", flush_raises_unresolvable)
    unresolvable_resp = client.post(
        "/v2/watchlist/keywords/bulk",
        json={"items": [{"keyword": "unresolvable kw", "bucket_id": core_bucket["id"]}]},
        headers=headers,
    )
    assert unresolvable_resp.status_code == 409
    monkeypatch.undo()

    def commit_raises_integrity(self):
        raise IntegrityError("COMMIT", {}, Exception("deferred_uq"))

    monkeypatch.setattr(Session, "commit", commit_raises_integrity)
    commit_conflict_resp = client.post(
        "/v2/watchlist/keywords/bulk",
        json={"items": [{"keyword": "commit conflict kw", "bucket_id": core_bucket["id"]}]},
        headers=headers,
    )
    assert commit_conflict_resp.status_code == 409
    monkeypatch.undo()


def test_auto_created_buckets_clamp_at_int4_max(client, client_a, admin_user):
    headers = client_header(client_a.id, admin_user.email)
    int4_max = 2_147_483_647

    seed_max = client.post(
        "/v2/watchlist/buckets",
        json={"name": "Max Bucket", "sort_order": int4_max},
        headers=headers,
    )
    assert seed_max.status_code == 201
    assert seed_max.json()["sort_order"] == int4_max

    auto_bucket = client.post(
        "/v2/watchlist/buckets",
        json={"name": "Auto Bucket 1"},
        headers=headers,
    )
    assert auto_bucket.status_code == 201
    assert auto_bucket.json()["sort_order"] == int4_max

    add_kw = client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "kw max 1", "bucket_name": "Auto Bucket 2"},
        headers=headers,
    )
    assert add_kw.status_code == 200
    assert add_kw.json()["bucket_created"] is True

    bulk_kw = client.post(
        "/v2/watchlist/keywords/bulk",
        json={
            "items": [
                {"keyword": "kw max 2", "bucket_name": "Auto Bucket 3"},
                {"keyword": "kw max 3", "bucket_name": "Auto Bucket 4"},
            ]
        },
        headers=headers,
    )
    assert bulk_kw.status_code == 200
    assert bulk_kw.json()["created_count"] == 2

    patch_kw = client.patch(
        f"/v2/watchlist/keywords/{add_kw.json()['id']}",
        json={"bucket_name": "Auto Bucket 5"},
        headers=headers,
    )
    assert patch_kw.status_code == 200
    assert patch_kw.json()["bucket_name"] == "Auto Bucket 5"

    wl = client.get("/v2/watchlist", headers=headers)
    assert wl.status_code == 200
    buckets = wl.json()["buckets"]
    assert len(buckets) == 6
    assert all(b["sort_order"] == int4_max for b in buckets)
