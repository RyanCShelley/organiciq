from datetime import date
from uuid import uuid4

import pytest

from app.ingestion.seranking.audit_pages import parse_audit_page, resolve_latest_finished_audit
from app.ingestion.seranking.pipeline_audit import run_seranking_audit_job
from app.models.crawl import FactCrawlPageSnapshot
from app.models.integration import ConnectionStatus, Integration, IntegrationProvider
from app.models.job import DataWatermark, SyncJob, SyncJobStatus, ValidationStatus
from tests.conftest import date_window


def test_parse_audit_page_maps_fields():
    parsed = parse_audit_page(
        {
            "url": "https://www.example.com/blog/post/",
            "status": "404",
            "canonical_url": "https://example.com/other",
            "inlinks": "6",
            "words_count": "2500",
            "sitemap": "1",
            "indexable_status": "non-indexable",
            "noindex": "0",
        }
    )
    assert parsed["normalized_url"] == "https://example.com/blog/post"
    assert parsed["status_code"] == 404
    assert parsed["indexable"] is False
    assert parsed["inbound_internal_links"] == 6
    assert parsed["word_count"] == 2500
    assert parsed["in_sitemap"] is True
    assert parsed["canonical_url"] == "https://example.com/other"


def test_resolve_latest_finished_audit_prefers_site_id(monkeypatch):
    audits = {
        "items": [
            {
                "id": 100,
                "site_id": 42,
                "url": "https://old.example.com",
                "status": "finished",
                "last_update": "2026-08-01",
            },
            {
                "id": 200,
                "site_id": 42,
                "url": "https://example.com",
                "status": "finished",
                "last_update": "2026-08-15",
            },
            {
                "id": 300,
                "site_id": 99,
                "url": "https://example.com",
                "status": "finished",
                "last_update": "2026-09-01",
            },
        ],
        "total": 3,
    }

    monkeypatch.setattr(
        "app.ingestion.seranking.audit_pages.ser_client.list_site_audits",
        lambda **kwargs: audits,
    )
    audit_id, snapshot_date = resolve_latest_finished_audit(
        api_key="test-key",
        site_id="42",
        client_domain="example.com",
    )
    assert audit_id == 200
    assert snapshot_date == date(2026, 8, 15)


def test_resolve_latest_finished_audit_falls_back_to_domain(monkeypatch):
    audits = {
        "items": [
            {
                "id": 500,
                "url": "https://www.smamarketing.net",
                "status": "finished",
                "last_update": "2026-08-20",
            }
        ],
        "total": 1,
    }

    monkeypatch.setattr(
        "app.ingestion.seranking.audit_pages.ser_client.list_site_audits",
        lambda **kwargs: audits,
    )
    audit_id, snapshot_date = resolve_latest_finished_audit(
        api_key="test-key",
        site_id="12345",
        client_domain="smamarketing.net",
    )
    assert audit_id == 500
    assert snapshot_date == date(2026, 8, 20)


def test_resolve_latest_finished_audit_requires_finished(monkeypatch):
    audits = {
        "items": [
            {
                "id": 1,
                "site_id": 42,
                "url": "https://example.com",
                "status": "processing",
                "last_update": "2026-08-20",
            }
        ],
        "total": 1,
    }
    monkeypatch.setattr(
        "app.ingestion.seranking.audit_pages.ser_client.list_site_audits",
        lambda **kwargs: audits,
    )
    with pytest.raises(RuntimeError, match="No finished SE Ranking Website Audit"):
        resolve_latest_finished_audit(api_key="test-key", site_id="42", client_domain="example.com")


def test_seranking_audit_pipeline_with_mocked_api(db, client_a, monkeypatch):
    monkeypatch.setenv("SE_RANKING_API_KEY", "test-key")
    start, end = date_window(1)

    integration = (
        db.query(Integration)
        .filter(
            Integration.client_id == client_a.id,
            Integration.provider == IntegrationProvider.SE_RANKING,
        )
        .one_or_none()
    )
    if integration is None:
        integration = Integration(
            id=uuid4(),
            client_id=client_a.id,
            provider=IntegrationProvider.SE_RANKING,
            connection_status=ConnectionStatus.CONNECTED,
        )
        db.add(integration)
    integration.external_property_id = "10113599"
    integration.connection_status = ConnectionStatus.CONNECTED
    db.commit()

    job = SyncJob(
        id=uuid4(),
        client_id=client_a.id,
        source="se_ranking_audit",
        start_date=start,
        end_date=end,
        status=SyncJobStatus.QUEUED,
    )
    db.add(job)
    db.commit()

    pages_payload = [
        {
            "url": "https://example.com/page-a",
            "status": "200",
            "inlinks": "3",
            "words_count": "900",
            "indexable_status": "ok",
            "noindex": "0",
            "sitemap": "0",
        },
        {
            "url": "https://example.com/page-b",
            "status": "404",
            "inlinks": "1",
            "words_count": "100",
            "indexable_status": "non-indexable",
            "noindex": "1",
            "sitemap": "0",
        },
    ]

    monkeypatch.setattr(
        "app.ingestion.seranking.audit_pages.ser_client.list_site_audits",
        lambda **kwargs: {
            "items": [
                {
                    "id": 700183831,
                    "site_id": 10113599,
                    "url": "https://example.com",
                    "status": "finished",
                    "last_update": end.isoformat(),
                }
            ],
            "total": 1,
        },
    )
    monkeypatch.setattr(
        "app.ingestion.seranking.fetch_audit.ser_client.get_audit_status",
        lambda **kwargs: {"status": "finished"},
    )
    monkeypatch.setattr(
        "app.ingestion.seranking.fetch_audit.ser_client.list_audit_pages_paginated",
        lambda **kwargs: pages_payload,
    )

    result = run_seranking_audit_job(db, job)
    assert result.status == SyncJobStatus.SUCCESSFUL
    assert result.records_written == 2

    facts = db.query(FactCrawlPageSnapshot).filter(FactCrawlPageSnapshot.client_id == client_a.id).all()
    assert len(facts) == 2
    broken = next(row for row in facts if row.status_code == 404)
    assert broken.indexable is False

    watermark = (
        db.query(DataWatermark)
        .filter(DataWatermark.client_id == client_a.id, DataWatermark.source == "se_ranking_audit")
        .one()
    )
    assert watermark.fact_through_date == end
    assert watermark.validation_status == ValidationStatus.PASSED
