"""A host that blocks our reader: the page is read from the site crawl, and everything says so."""

from __future__ import annotations

from datetime import date

from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSnapshot
from app.services import crawl_fallback as cf
from app.services import page_diagnostic as pd

URL = "https://shop.example/services/panel-upgrade"
ROW = {"position": 12.2, "impressions": 1891, "clicks": 3, "expected_extra_clicks": 11.7}
CAPTCHA = "<html><head><meta http-equiv='refresh' content='0;/.well-known/sgcaptcha/?r=%2F'></head></html>"
GOOD = "<html><head><title>Panel Upgrade</title></head><body><h1>Panel upgrade</h1><p>Words about the work here.</p></body></html>"


def reader(body, headers=None, status=202):
    async def fetch(url):
        return pd.Fetched(status=status, final_url=url, headers=headers or {}, body=body, requested_url=url, user_agent=pd.USER_AGENT, fetched_at="2026-11-06T17:27:00+00:00", size=len(body))

    return fetch


def snap(db, client):
    db.add(FactCrawlPageSnapshot(
        client_id=client.id, source=CRAWL_SOURCE_FIRST_PARTY, snapshot_date=date(2026, 11, 3), raw_url=URL, normalized_url=URL, status_code=200, title="Panel Upgrade | Shop",
        description="Electrical panel upgrades.", word_count=640, conversion_elements=2, indexable=True,
        sections=[{"level": 1, "heading": "Electrical panel upgrade", "first_paragraph": "We replace old fuse boxes with modern breaker panels."}, {"level": 2, "heading": "How much does it cost?", "first_paragraph": "Most upgrades are quoted on site."}],
        faq_questions=["How much does it cost?"],
    ))
    db.commit()


def test_a_blocked_page_is_read_from_the_crawl_and_says_so(db, client_a):
    snap(db, client_a)
    out = pd.diagnose(search="panel upgrade", url=URL, row=ROW, client_domain="shop.example", fetch=cf.with_crawl(db, client_a, reader(CAPTCHA, {"sg-captcha": "challenge"})))
    assert out["read"]["ok"] is True and out["read"]["source"] == "crawl" and "blocked" not in out["read"]
    assert "site crawl of Nov 03, 2026" in out["read"]["source_note"] and "SiteGround's captcha" in out["read"]["source_note"]
    assert any(o["text"] for o in out["observations"]) and all("crawl" in o["how"] for o in out["observations"] if o["level"] in ("problem", "ok"))
    assert out["page_facts"]["title"] == "Panel Upgrade | Shop" and out["page_facts"]["word_count"] == 640


def test_a_page_that_reads_fine_is_never_replaced(db, client_a):
    snap(db, client_a)
    out = pd.diagnose(search="panel upgrade", url=URL, row=ROW, client_domain="shop.example", fetch=cf.with_crawl(db, client_a, reader(GOOD, status=200)))
    assert out["read"].get("source") is None and out["page_facts"]["title"] == "Panel Upgrade"


def test_no_crawl_of_the_page_keeps_the_blocked_note(db, client_a):
    out = pd.diagnose(search="panel upgrade", url=URL, row=ROW, client_domain="shop.example", fetch=cf.with_crawl(db, client_a, reader(CAPTCHA, {"sg-captcha": "challenge"})))
    assert out["read"]["blocked"] == "The site answered our reader with SiteGround's captcha instead of the page." and out["prescriptions"] == []


def test_a_page_that_cannot_be_fetched_is_also_read_from_the_crawl(db, client_a):
    import httpx

    async def down(url):
        raise httpx.ConnectTimeout("slow")

    snap(db, client_a)
    out = pd.diagnose(search="panel upgrade", url=URL, row=ROW, client_domain="shop.example", fetch=cf.with_crawl(db, client_a, down))
    assert out["read"]["source"] == "crawl" and "could not be fetched" in out["read"]["source_note"]
