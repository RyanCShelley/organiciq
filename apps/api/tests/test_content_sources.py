"""Content sources: /v2/feeds endpoints removed while client sitemap_url and crawler ingestion work."""

from __future__ import annotations

import asyncio
from datetime import date
from uuid import uuid4

import httpx
from sqlalchemy import inspect, text

from app import reset_client_data as rc
from app.ask import schema as ask_schema
from app.core.db import Base
from app.ingestion.crawler import fetch, pipeline
from app.main import app
from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSnapshot
from app.models.job import SyncJob, SyncJobStatus
from tests.conftest import auth_header, client_header


def test_v2_feeds_routes_return_404(client, client_a, admin_user):
    headers = client_header(client_a.id, admin_user.email)
    assert client.get("/v2/feeds", headers=headers).status_code == 404
    assert (
        client.post(
            "/v2/feeds",
            json={"url": "https://example.com/feed.xml", "label": "Blog"},
            headers=headers,
        ).status_code
        == 404
    )
    assert client.delete("/v2/feeds/1", headers=headers).status_code == 404
    assert client.delete(f"/v2/feeds/{uuid4()}", headers=headers).status_code == 404


def test_client_feed_table_and_routes_not_registered():
    assert "client_feeds" not in Base.metadata.tables
    paths = [getattr(r, "path", "") for r in app.routes]
    assert not any(p.startswith("/v2/feeds") for p in paths)


def test_patch_and_get_client_sitemap_url(client, client_a, team_user):
    headers = auth_header(team_user.email)

    initial = client.get(f"/clients/{client_a.id}", headers=headers)
    assert initial.status_code == 200
    assert initial.json()["sitemap_url"] is None

    sitemap = "https://clienta.example/custom-sitemap.xml"
    updated = client.patch(
        f"/clients/{client_a.id}",
        json={"sitemap_url": sitemap},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["sitemap_url"] == sitemap

    fetched = client.get(f"/clients/{client_a.id}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["sitemap_url"] == sitemap

    listed = client.get("/clients", headers=headers)
    assert listed.status_code == 200
    by_slug = {c["slug"]: c for c in listed.json()}
    assert by_slug[client_a.slug]["sitemap_url"] == sitemap

    cleared = client.patch(
        f"/clients/{client_a.id}",
        json={"sitemap_url": None},
        headers=headers,
    )
    assert cleared.status_code == 200
    assert cleared.json()["sitemap_url"] is None
    assert client.get(f"/clients/{client_a.id}", headers=headers).json()["sitemap_url"] is None


def test_patch_client_rejects_non_public_sitemap_url(client, client_a, admin_user):
    res = client.patch(
        f"/clients/{client_a.id}",
        json={"sitemap_url": "http://localhost/sitemap.xml"},
        headers=auth_header(admin_user.email),
    )
    assert res.status_code == 422


def _mock_site_handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if url == "https://example.com/robots.txt":
        return httpx.Response(404, text="Not found")
    if url == "https://example.com/custom-sitemap.xml":
        return httpx.Response(
            200,
            headers={"content-type": "application/xml"},
            text=(
                '<?xml version="1.0"?>'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                "<url><loc>https://example.com/</loc></url>"
                "<url><loc>https://example.com/unlinked-guide</loc>"
                "<lastmod>2026-10-01</lastmod></url>"
                "</urlset>"
            ),
        )
    if url == "https://example.com/":
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<html><head><title>Home</title></head><body><h1>Home</h1><p>Welcome home page content here.</p></body></html>",
        )
    if url == "https://example.com/unlinked-guide":
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<html><head><title>Guide</title></head><body><h1>Guide</h1><p>Content discovered only via sitemap.</p></body></html>",
        )
    return httpx.Response(404, text="Not found")


def test_crawl_site_ingests_declared_sitemap_urls(monkeypatch):
    monkeypatch.setattr(
        fetch, "PublicOnlyTransport", lambda **kwargs: httpx.MockTransport(_mock_site_handler)
    )
    monkeypatch.setattr(fetch, "DEFAULT_CRAWL_DELAY", 0.0)

    result = asyncio.run(
        fetch.crawl_site(
            "example.com",
            page_limit=10,
            sitemap_url="https://example.com/custom-sitemap.xml",
        )
    )
    assert result.sitemap_location == "https://example.com/custom-sitemap.xml"
    assert result.sitemap_failures == []
    assert result.sitemap_unreadable is False
    assert result.sitemap_urls == {
        "https://example.com/": None,
        "https://example.com/unlinked-guide": date(2026, 10, 1),
    }
    by_url = {p.normalized_url: p for p in result.pages}
    assert set(by_url) == {"https://example.com/", "https://example.com/unlinked-guide"}
    guide = by_url["https://example.com/unlinked-guide"]
    assert guide.in_sitemap is True
    assert guide.parsed is not None
    assert guide.parsed.content_updated_on == date(2026, 10, 1)
    assert guide.parsed.content_updated_source == "sitemap"


def test_run_site_crawl_job_uses_client_sitemap_url(client, db, client_a, admin_user, monkeypatch):
    res = client.patch(
        f"/clients/{client_a.id}",
        json={"domain": "example.com", "sitemap_url": "https://example.com/custom-sitemap.xml"},
        headers=auth_header(admin_user.email),
    )
    assert res.status_code == 200

    monkeypatch.setattr(
        fetch, "PublicOnlyTransport", lambda **kwargs: httpx.MockTransport(_mock_site_handler)
    )
    monkeypatch.setattr(fetch, "DEFAULT_CRAWL_DELAY", 0.0)

    job = SyncJob(
        id=uuid4(),
        client_id=client_a.id,
        source="site_crawl",
        start_date=date.today(),
        end_date=date.today(),
        status=SyncJobStatus.QUEUED,
    )
    db.add(job)
    db.commit()

    pipeline.run_site_crawl_job(db, job)
    db.refresh(job)

    assert job.status == SyncJobStatus.SUCCESSFUL
    assert "sitemap 2 URLs via https://example.com/custom-sitemap.xml" in (job.error_message or "")

    snaps = {
        s.normalized_url: s
        for s in db.query(FactCrawlPageSnapshot)
        .filter(
            FactCrawlPageSnapshot.client_id == client_a.id,
            FactCrawlPageSnapshot.source == CRAWL_SOURCE_FIRST_PARTY,
        )
        .all()
    }
    assert set(snaps) == {"https://example.com/", "https://example.com/unlinked-guide"}
    assert snaps["https://example.com/unlinked-guide"].in_sitemap is True
    assert snaps["https://example.com/unlinked-guide"].content_updated_on == date(2026, 10, 1)
    assert snaps["https://example.com/unlinked-guide"].content_updated_source == "sitemap"


def test_reset_client_data_succeeds_without_client_feeds_table(db, client_a):
    existing_before = set(inspect(db.get_bind()).get_table_names())
    had_ask_scope_state = "ask_scope_state" in existing_before
    if had_ask_scope_state:
        db.execute(text("DROP TABLE IF EXISTS ask_scope_state"))
        db.commit()
    try:
        existing = set(inspect(db.get_bind()).get_table_names())
        assert "client_feeds" not in existing
        assert "ask_scope_state" not in existing

        p = rc.plan(db, client_a)
        assert "client_feeds" not in p["clear_setup"]
        assert p["kept"]["ask_scope_state"] == 0

        rc.apply(db, client_a)
        db.commit()

        purged = rc.purge(db, client_a)
        db.commit()
        assert purged["clients"] == 1
        assert "ask_scope_state" not in set(inspect(db.get_bind()).get_table_names())
    finally:
        if had_ask_scope_state:
            db.rollback()
            ask_schema._ready = False
            ask_schema.ensure(db)


def test_reset_client_data_plan_and_apply_skip_absent_synced_and_setup_tables(
    db, client_a, monkeypatch
):
    monkeypatch.setattr(rc, "SYNCED", rc.SYNCED + ("missing_runtime_synced",))
    monkeypatch.setattr(rc, "SETUP", rc.SETUP + ("missing_runtime_setup",))
    monkeypatch.setattr(rc, "KEPT", rc.KEPT + ("missing_runtime_kept",))

    p = rc.plan(db, client_a)
    assert p["clear_synced"]["missing_runtime_synced"] == 0
    assert p["clear_setup"]["missing_runtime_setup"] == 0
    assert p["kept"]["missing_runtime_kept"] == 0

    deleted = rc.apply(db, client_a)
    db.commit()
    assert "missing_runtime_synced" not in deleted
    assert "missing_runtime_setup" not in deleted


def test_reset_client_data_clears_legacy_client_feeds_table_when_present(db, client_a, client_b):
    try:
        db.execute(
            text(
                """
                CREATE TABLE client_feeds (
                    id UUID PRIMARY KEY,
                    client_id UUID NOT NULL REFERENCES clients(id),
                    url VARCHAR(512) NOT NULL,
                    url_key VARCHAR(512) NOT NULL
                )
                """
            )
        )
        db.execute(
            text(
                """
                INSERT INTO client_feeds (id, client_id, url, url_key)
                VALUES (:id1, :c1, 'https://a.example/feed.xml', 'a.example/feed.xml'),
                       (:id2, :c2, 'https://b.example/feed.xml', 'b.example/feed.xml')
                """
            ),
            {"id1": str(uuid4()), "c1": str(client_a.id), "id2": str(uuid4()), "c2": str(client_b.id)},
        )
        db.commit()

        p = rc.plan(db, client_a)
        assert p["clear_setup"]["client_feeds"] == 1

        deleted = rc.apply(db, client_a)
        db.commit()
        assert deleted["client_feeds"] == 1
        assert rc.count(db, "client_feeds", client_b.id) == 1

        db.execute(
            text(
                """
                INSERT INTO client_feeds (id, client_id, url, url_key)
                VALUES (:id3, :c1, 'https://a.example/news.xml', 'a.example/news.xml')
                """
            ),
            {"id3": str(uuid4()), "c1": str(client_a.id)},
        )
        db.commit()

        purged = rc.purge(db, client_a)
        db.commit()
        assert purged["client_feeds"] == 1
        assert purged["clients"] == 1
        assert rc.count(db, "client_feeds", client_b.id) == 1
    finally:
        db.rollback()
        db.execute(text("DROP TABLE IF EXISTS client_feeds"))
        db.commit()
