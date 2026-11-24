"""GSC keyword suggestions endpoint (`GET /v2/watchlist/suggestions`) and `SvTerm.id` tests."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSnapshot
from app.models.gsc import FactGscQueryPage
from app.models.integration import ConnectionStatus, Integration, IntegrationProvider
from app.models.user import User, UserClient, UserRole
from app.models.watchlist import WatchlistBucket, WatchlistKeyword
from tests.conftest import client_header


def _connect_gsc(db, client_obj, property_id: str = "sc-domain:clienta.example") -> None:
    integ = (
        db.query(Integration)
        .filter(
            Integration.client_id == client_obj.id,
            Integration.provider == IntegrationProvider.GSC,
        )
        .one()
    )
    integ.connection_status = ConnectionStatus.CONNECTED
    integ.external_property_id = property_id
    db.commit()


def _seed_gsc(
    db,
    client_obj,
    day: date,
    query: str,
    impressions: int,
    position: float,
    *,
    clicks: int = 1,
    url: str = "https://clienta.example/spf",
) -> None:
    db.add(
        FactGscQueryPage(
            client_id=client_obj.id,
            date=day,
            query=query,
            raw_url=url,
            normalized_url=url,
            country="usa",
            device="DESKTOP",
            impressions=Decimal(impressions),
            clicks=Decimal(clicks),
            ctr=Decimal(0),
            average_position=Decimal(str(position)),
        )
    )


def test_suggestions_when_gsc_disconnected_returns_200_empty(client, client_a, admin_user):
    resp = client.get(
        "/v2/watchlist/suggestions",
        headers=client_header(client_a.id, admin_user.email),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "gsc_connected": False,
        "has_gsc_data": False,
        "google_through": None,
        "days": 90,
        "suggestions": [],
    }


def test_suggestions_when_gsc_connected_but_no_data_returns_200_empty(
    client, db, client_a, admin_user
):
    _connect_gsc(db, client_a)
    resp = client.get(
        "/v2/watchlist/suggestions",
        headers=client_header(client_a.id, admin_user.email),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "gsc_connected": True,
        "has_gsc_data": False,
        "google_through": None,
        "days": 90,
        "suggestions": [],
    }


def test_suggestions_aggregates_multipages_filters_brand_and_watchlist_and_computes_signals(
    client, db, client_a, client_b, admin_user
):
    _connect_gsc(db, client_a)
    client_a.brand_aliases = ["acme"]
    db.flush()

    bucket = WatchlistBucket(client_id=client_a.id, name="Core", name_key="core", sort_order=0)
    db.add(bucket)
    db.flush()
    db.add(
        WatchlistKeyword(
            client_id=client_a.id,
            bucket_id=bucket.id,
            keyword="Natural  Sunscreen",
            keyword_key="natural sunscreen",
            source="manual",
        )
    )
    db.add(
        FactCrawlPageSnapshot(
            client_id=client_a.id,
            source=CRAWL_SOURCE_FIRST_PARTY,
            snapshot_date=date(2026, 10, 10),
            raw_url="https://clienta.example/p1",
            normalized_url="https://clienta.example/p1",
            indexable=True,
            title="Mineral Sunscreen Guide",
            sections=[{"heading": "Reef Safe Lotion"}],
        )
    )

    # Anchor google_through at 2026-10-28, default days=90 -> [2026-07-31 .. 2026-10-28], prior [2026-05-02 .. 2026-07-30]
    _seed_gsc(
        db,
        client_a,
        date(2026, 10, 28),
        "mineral face sunscreen",
        200,
        6.0,
        clicks=12,
        url="https://clienta.example/p1",
    )
    _seed_gsc(
        db,
        client_a,
        date(2026, 10, 20),
        "mineral face sunscreen",
        100,
        12.0,
        clicks=3,
        url="https://clienta.example/p2",
    )

    _seed_gsc(db, client_a, date(2026, 7, 15), "reef safe lotion", 20, 15.0, clicks=1)
    _seed_gsc(db, client_a, date(2026, 10, 25), "reef safe lotion", 80, 7.0, clicks=6)

    # Tracked with different casing & extra spaces -> excluded
    _seed_gsc(db, client_a, date(2026, 10, 22), "  NATURAL   Sunscreen ", 500, 3.0, clicks=40)
    # Brand queries -> excluded
    _seed_gsc(db, client_a, date(2026, 10, 22), "client a sunscreen", 500, 1.0, clicks=100)
    _seed_gsc(db, client_a, date(2026, 10, 22), "acme balm", 500, 2.0, clicks=80)
    # Low-impression noise -> excluded in strict mode
    _seed_gsc(db, client_a, date(2026, 10, 22), "tiny noise", 5, 10.0, clicks=0)
    # Other client data -> isolated
    _seed_gsc(db, client_b, date(2026, 10, 22), "client b secret", 900, 2.0, clicks=50)
    db.commit()

    resp = client.get(
        "/v2/watchlist/suggestions",
        headers=client_header(client_a.id, admin_user.email),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["gsc_connected"] is True
    assert body["has_gsc_data"] is True
    assert body["google_through"] == "2026-10-28"
    assert body["days"] == 90

    by_key = {s["key"]: s for s in body["suggestions"]}
    assert "mineral face sunscreen" in by_key
    mfs = by_key["mineral face sunscreen"]
    assert mfs["impressions"] == 300
    assert mfs["clicks"] == 15
    assert mfs["ctr"] == 5.0
    assert mfs["position"] == 8.0
    assert mfs["page"] == "https://clienta.example/p1"
    assert "high_impressions" in mfs["signals"]
    assert "relevant" in mfs["signals"]

    assert "reef safe lotion" in by_key
    rsl = by_key["reef safe lotion"]
    assert "rising" in rsl["signals"]
    assert rsl["impressions_before"] == 20
    assert rsl["impressions_change_pct"] == 300.0
    assert rsl["move"] == 8.0

    assert "natural sunscreen" not in by_key
    assert "client a sunscreen" not in by_key
    assert "acme balm" not in by_key
    assert "tiny noise" not in by_key
    assert "client b secret" not in by_key


def test_suggestions_search_filter_surfaces_lower_impression_matching_queries_and_still_excludes_brand_and_watchlist(
    client, db, client_a, admin_user
):
    _connect_gsc(db, client_a)
    bucket = WatchlistBucket(client_id=client_a.id, name="Core", name_key="core", sort_order=0)
    db.add(bucket)
    db.flush()
    db.add(
        WatchlistKeyword(
            client_id=client_a.id,
            bucket_id=bucket.id,
            keyword="natural sunscreen",
            keyword_key="natural sunscreen",
            source="manual",
        )
    )

    _seed_gsc(db, client_a, date(2026, 10, 20), "travel size mineral mist", 15, 11.0, clicks=2)
    _seed_gsc(db, client_a, date(2026, 10, 20), "natural sunscreen", 300, 4.0, clicks=20)
    _seed_gsc(db, client_a, date(2026, 10, 20), "client a mist", 300, 2.0, clicks=40)
    _seed_gsc(db, client_a, date(2026, 10, 20), "lip balm", 400, 5.0, clicks=18)
    _seed_gsc(db, client_a, date(2026, 10, 20), "100% mineral spray", 40, 8.0, clicks=3)
    db.commit()

    headers = client_header(client_a.id, admin_user.email)
    resp = client.get("/v2/watchlist/suggestions", params={"search": "mist"}, headers=headers)
    assert resp.status_code == 200
    keys = [s["key"] for s in resp.json()["suggestions"]]
    assert keys == ["travel size mineral mist"]
    row = resp.json()["suggestions"][0]
    assert row["impressions"] == 15
    assert row["clicks"] == 2
    assert row["position"] == 11.0

    # Watchlist term remains excluded even when search matches it
    resp_watch = client.get(
        "/v2/watchlist/suggestions", params={"search": "sunscreen"}, headers=headers
    )
    assert resp_watch.status_code == 200
    assert [s["key"] for s in resp_watch.json()["suggestions"]] == []

    # Wildcards % and _ in search are escaped literally
    resp_wild = client.get("/v2/watchlist/suggestions", params={"search": "%"}, headers=headers)
    assert resp_wild.status_code == 200
    assert [s["key"] for s in resp_wild.json()["suggestions"]] == ["100% mineral spray"]

    resp_under = client.get("/v2/watchlist/suggestions", params={"search": "_"}, headers=headers)
    assert resp_under.status_code == 200
    assert resp_under.json()["suggestions"] == []


def test_suggestions_limit_and_days_window_bounds(client, db, client_a, admin_user):
    _connect_gsc(db, client_a)
    end = date(2026, 10, 28)
    for idx in range(5):
        _seed_gsc(
            db,
            client_a,
            end - timedelta(days=idx),
            f"sunscreen guide {idx}",
            150 + idx * 20,
            5.0,
            clicks=5 + idx,
        )
    # 60 days old (outside days=30 window)
    _seed_gsc(
        db,
        client_a,
        end - timedelta(days=60),
        "old summer sunscreen",
        900,
        3.0,
        clicks=50,
    )
    db.commit()

    headers = client_header(client_a.id, admin_user.email)
    resp = client.get(
        "/v2/watchlist/suggestions",
        params={"days": 30, "limit": 2},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["days"] == 30
    assert len(body["suggestions"]) == 2
    returned_keys = [s["key"] for s in body["suggestions"]]
    assert "old summer sunscreen" not in returned_keys
    assert returned_keys == ["sunscreen guide 4", "sunscreen guide 3"]

    assert (
        client.get("/v2/watchlist/suggestions", params={"days": 0}, headers=headers).status_code
        == 422
    )
    assert (
        client.get("/v2/watchlist/suggestions", params={"limit": 101}, headers=headers).status_code
        == 422
    )


def test_suggestions_auth_guard_and_svterm_id(client, db, client_a, admin_user):
    viewer = User(
        id=uuid.uuid4(),
        email="viewer@suggestions.example",
        name="Viewer",
        google_sub="sub-viewer-sugg",
        role=UserRole.CLIENT_VIEWER,
    )
    db.add(viewer)
    db.flush()
    db.add(UserClient(user_id=viewer.id, client_id=client_a.id, role=UserRole.CLIENT_VIEWER))

    bucket = WatchlistBucket(client_id=client_a.id, name="Core", name_key="core", sort_order=0)
    db.add(bucket)
    db.flush()
    kw = WatchlistKeyword(
        client_id=client_a.id,
        bucket_id=bucket.id,
        keyword="mineral spf",
        keyword_key="mineral spf",
        source="manual",
    )
    db.add(kw)
    db.commit()

    assert (
        client.get(
            "/v2/watchlist/suggestions",
            headers=client_header(client_a.id, viewer.email),
        ).status_code
        == 403
    )

    sv = client.get(
        "/v2/search-visibility",
        params={"from": "2026-10-01", "to": "2026-10-28"},
        headers=client_header(client_a.id, admin_user.email),
    )
    assert sv.status_code == 200
    terms = sv.json()["terms"]
    assert len(terms) == 1
    assert terms[0]["id"] == str(kw.id)


def test_suggestions_normalizes_tabs_and_newlines_across_current_and_prior_periods(
    client, db, client_a, admin_user
):
    _connect_gsc(db, client_a)
    end = date(2026, 10, 28)

    _seed_gsc(
        db,
        client_a,
        end,
        "organic lotion",
        200,
        6.0,
        clicks=10,
        url="https://clienta.example/lotion",
    )
    _seed_gsc(
        db,
        client_a,
        end - timedelta(days=1),
        "\torganic\n lotion ",
        150,
        8.0,
        clicks=8,
        url="https://clienta.example/lotion-alt",
    )

    # Prior period has tab/newline whitespace while current period is plain text
    _seed_gsc(
        db,
        client_a,
        date(2026, 7, 15),
        "\tmineral balm\n",
        120,
        14.0,
        clicks=5,
        url="https://clienta.example/balm",
    )
    _seed_gsc(
        db,
        client_a,
        end - timedelta(days=3),
        "mineral balm",
        180,
        9.0,
        clicks=9,
        url="https://clienta.example/balm",
    )
    db.commit()

    resp = client.get(
        "/v2/watchlist/suggestions",
        headers=client_header(client_a.id, admin_user.email),
    )
    assert resp.status_code == 200
    by_key = {s["key"]: s for s in resp.json()["suggestions"]}

    assert "organic lotion" in by_key
    ol = by_key["organic lotion"]
    assert ol["impressions"] == 350
    assert ol["clicks"] == 18
    assert ol["query"] == "organic lotion"
    assert ol["page"] == "https://clienta.example/lotion"

    assert "mineral balm" in by_key
    mb = by_key["mineral balm"]
    assert mb["impressions"] == 180
    assert mb["impressions_before"] == 120
    assert mb["impressions_change_pct"] == 50.0
    assert mb["position"] == 9.0
    assert mb["position_before"] == 14.0
    assert mb["move"] == 5.0
    assert "new" not in mb["signals"]
    assert "rising" in mb["signals"]
