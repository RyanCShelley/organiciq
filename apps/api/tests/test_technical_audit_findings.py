from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.models.crawl import FactCrawlPageIssue, FactCrawlPageSnapshot
from app.models.gsc import FactGscPage
from app.models.job import DataWatermark, ValidationStatus
from app.services.lever_engine import detect_technical_signal, diagnose
from tests.conftest import date_window


def _crawl(**overrides) -> FactCrawlPageSnapshot:
    base = dict(
        id=uuid4(),
        client_id=uuid4(),
        snapshot_date=date(2026, 9, 1),
        raw_url="https://example.com/page",
        normalized_url="https://example.com/page",
        indexable=True,
        status_code=200,
        inbound_internal_links=10,
        word_count=800,
        title="Title",
        description="Description",
        title_duplicate=False,
        description_duplicate=False,
        redirect_count=0,
    )
    base.update(overrides)
    return FactCrawlPageSnapshot(**base)


def test_detect_missing_meta_from_empty_title():
    crawl = _crawl(title="", description="Has description")
    detected = detect_technical_signal(crawl.normalized_url, crawl)
    assert detected is not None
    assert detected.audit_signal == "missing_meta"
    assert detected.issue_code == "title_missing"


def test_detect_missing_meta_ignores_unenriched_null_title():
    crawl = _crawl(title=None, description=None)
    detected = detect_technical_signal(crawl.normalized_url, crawl)
    assert detected is None


def test_detect_redirect_chain_from_count_and_issue_code():
    crawl = _crawl(redirect_count=3)
    detected = detect_technical_signal(crawl.normalized_url, crawl)
    assert detected is not None
    assert detected.audit_signal == "redirect_chain"

    crawl2 = _crawl(redirect_count=0)
    detected2 = detect_technical_signal(
        crawl2.normalized_url,
        crawl2,
        page_issue_codes={"redirect_chain"},
    )
    assert detected2 is not None
    assert detected2.audit_signal == "redirect_chain"
    assert detected2.issue_code == "redirect_chain"


def test_detect_broken_redirect_from_issue_code():
    crawl = _crawl(status_code=301, redirect_url="https://example.com/gone")
    detected = detect_technical_signal(
        crawl.normalized_url,
        crawl,
        page_issue_codes={"redirect45xx"},
    )
    assert detected is not None
    assert detected.audit_signal == "broken_redirect"


def test_detect_priority_prefers_status_error_over_meta():
    crawl = _crawl(status_code=404, title="")
    detected = detect_technical_signal(crawl.normalized_url, crawl)
    assert detected is not None
    assert detected.audit_signal == "status_error"


def test_diagnose_emits_missing_meta_and_site_sitemap(db, client_a):
    start, end = date_window(14)
    page = "https://example.com/blog/useful-meta-gap"
    db.add(
        DataWatermark(
            id=uuid4(),
            client_id=client_a.id,
            source="gsc_pages",
            fact_through_date=end,
            validation_status=ValidationStatus.PASSED,
        )
    )
    db.add(
        FactGscPage(
            id=uuid4(),
            client_id=client_a.id,
            date=end,
            raw_url=page,
            normalized_url=page,
            country="usa",
            device="DESKTOP",
            impressions=Decimal("400"),
            clicks=Decimal("2"),
            ctr=Decimal("0.005"),
            average_position=Decimal("12"),
        )
    )
    db.add(
        FactCrawlPageSnapshot(
            id=uuid4(),
            client_id=client_a.id,
            snapshot_date=end,
            raw_url=page,
            normalized_url=page,
            indexable=True,
            status_code=200,
            inbound_internal_links=20,
            word_count=1200,
            title="",
            description="ok",
        )
    )
    db.add(
        FactCrawlPageIssue(
            id=uuid4(),
            client_id=client_a.id,
            snapshot_date=end,
            issue_code="sitemap_missing",
            normalized_url=None,
            severity=None,
            raw={"code": "sitemap_missing"},
        )
    )
    db.commit()

    result = diagnose(db, client_a, from_date=start, to_date=end)
    technical = [row for row in result.findings if row.lever == "technical_seo"]
    signals = {row.evidence_json.get("audit_signal") for row in technical}
    assert "missing_meta" in signals
    assert "sitemap_missing" in signals
    sitemap = next(row for row in technical if row.evidence_json.get("audit_signal") == "sitemap_missing")
    assert sitemap.promotion_blocked_reason == "advisory_audit_signal"
    meta = next(row for row in technical if row.evidence_json.get("audit_signal") == "missing_meta")
    assert meta.evidence_json.get("issue_code") == "title_missing"
    assert meta.promotion_blocked_reason == "advisory_audit_signal"
