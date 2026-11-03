"""Site health: the SEO and GEO scores, kept per month."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlInternalLink, FactCrawlPageIssue, FactCrawlPageSchema, FactCrawlPageSnapshot
from app.models.llm_visibility import LlmResponse, LlmRun
from app.services import site_health as sh
from tests.conftest import client_header

CRAWL = date(2026, 10, 20)
BASE = "https://shop.example"


def page(db, client, path, *, status=200, title="T", desc="D", indexable=True, dup_title=False, dup_desc=False, redirects=0, soft=False, snap=CRAWL):
    url = BASE + path
    db.add(FactCrawlPageSnapshot(client_id=client.id, source=CRAWL_SOURCE_FIRST_PARTY, snapshot_date=snap, raw_url=url, normalized_url=url, indexable=indexable, status_code=status,
                                 title=title, description=desc, title_duplicate=dup_title, description_duplicate=dup_desc, redirect_count=redirects, soft_404=soft))
    return url


def schema(db, client, path, kind="Product", syntax="json_ld", raw_text=None):
    db.add(FactCrawlPageSchema(client_id=client.id, snapshot_date=CRAWL, normalized_url=BASE + path, syntax=syntax, schema_type=kind, raw_text=raw_text or kind))


def seed(db, client):
    for path in ("/", "/about-us", "/pages/contact", "/a", "/b"):
        page(db, client, path)
    page(db, client, "/dup1", title="Same", dup_title=True)
    page(db, client, "/nodesc", desc="")
    page(db, client, "/gone", status=404, title="", desc="")
    page(db, client, "/chain", status=301, redirects=2, title="", desc="")
    for path in ("/", "/a"):
        schema(db, client, path)
    db.add(FactCrawlInternalLink(client_id=client.id, source=CRAWL_SOURCE_FIRST_PARTY, snapshot_date=CRAWL, from_url=BASE + "/", to_url=BASE + "/gone", in_content=True, is_template=False, occurrences=1))
    db.add(FactCrawlInternalLink(client_id=client.id, source=CRAWL_SOURCE_FIRST_PARTY, snapshot_date=CRAWL, from_url=BASE + "/", to_url=BASE + "/a", in_content=True, is_template=False, occurrences=1))
    db.commit()


def test_seo_health_counts_what_is_wrong_and_weights_it(db, client_a):
    seed(db, client_a)
    out = sh.seo_health(db, client_a, CRAWL)
    by = {c["key"]: c for c in out["checks"]}
    assert by["titles"]["affected"] == 1 and by["titles"]["urls"] == [BASE + "/dup1"] and by["titles"]["total"] == 7
    assert by["descriptions"]["affected"] == 1 and by["indexation"]["score"] == 100
    assert by["errors"]["affected"] == 1 and by["errors"]["urls"] == [BASE + "/gone"]
    assert by["redirects"]["affected"] == 1 and by["links"]["affected"] == 1 and by["links"]["urls"] == [BASE + "/gone"]
    assert by["schema"]["affected"] == 5 and by["site_files"]["score"] == 100
    assert sum(sh.SEO_WEIGHTS.values()) == 100 and 0 < out["score"] < 100 and out["grade"] == sh.grade(out["score"])


def test_a_robots_and_sitemap_problem_costs_the_site_files_check(db, client_a):
    seed(db, client_a)
    for code in ("sitemap_missing", "no_robots"):
        db.add(FactCrawlPageIssue(client_id=client_a.id, source=CRAWL_SOURCE_FIRST_PARTY, snapshot_date=CRAWL, issue_code=code, normalized_url=None, raw={}))
    db.commit()
    check = next(c for c in sh.seo_health(db, client_a, CRAWL)["checks"] if c["key"] == "site_files")
    assert check["score"] == 30 and "no sitemap found" in check["detail"]


def test_geo_readiness_ports_the_graders_signals_and_says_what_it_could_not_measure(db, client_a):
    seed(db, client_a)
    schema(db, client_a, "/", "Organization", raw_text='{"@type":"Organization","telephone":"555","address":{"streetAddress":"1 Main"}}')
    schema(db, client_a, "/faq", "FAQPage")
    db.add(FactCrawlPageIssue(client_id=client_a.id, source=CRAWL_SOURCE_FIRST_PARTY, snapshot_date=CRAWL, issue_code="ai_crawlers_blocked", normalized_url=None, raw={"agents": ["GPTBot", "CCBot"]}))
    db.commit()
    geo = sh.geo_readiness(db, client_a)
    by = {s["key"]: s for s in geo["signals"]}
    assert by["schema"]["score"] == 70  # json-ld 40, plus 10 each for product, organization and faqpage
    assert by["faq"]["score"] == 0 and by["crawler"]["score"] == 60 and by["crawler"]["detail"]["blocked"] == ["gptbot", "ccbot"]
    assert by["entity"]["detail"]["about_page"] and by["entity"]["detail"]["contact_page"] and by["entity"]["detail"]["phone_in_markup"]
    assert by["citation"]["measured"] is False and geo["partial"] is True and sum(sh.GEO_WEIGHTS.values()) == 100


def test_geo_answer_signals_come_from_the_latest_ai_run(db, client_a):
    seed(db, client_a)
    run = LlmRun(client_id=client_a.id, status="completed")
    db.add(run)
    db.flush()
    domain = sh.bare_domain(client_a.domain)
    long_text = f"According to {domain}, the 2026 range costs $20. " + "x" * 700
    for platform, mentioned in (("openai", True), ("gemini", True), ("anthropic", False)):
        db.add(LlmResponse(run_id=run.id, client_id=client_a.id, query_text="q", platform=platform, visibility_type="Mentioned", brand_mentioned=mentioned, url_cited=False, full_response=long_text))
    db.commit()
    geo = sh.geo_readiness(db, client_a)
    by = {s["key"]: s for s in geo["signals"]}
    assert by["citation"]["score"] == 100 and by["attribution"]["score"] == 100 and by["graph"]["score"] == 50
    assert by["depth"]["score"] == 45 and geo["partial"] is False  # a year 20, over 300 characters 15, over 600 characters 10


def test_the_month_is_kept_locked_when_over_and_compared_with_the_month_before(client, db, client_a, admin_user):
    seed(db, client_a)
    h = client_header(client_a.id, admin_user.email)
    assert sh.record(db, client_a) is not None  # a crawl finishing writes its month
    first = sh.for_month(db, client_a, "2026-10", today=date(2026, 11, 3))
    assert first["locked"] is True and first["previous"] is None and first["crawl"]["pages"] == 9
    # A later crawl (a page fixed) in November writes November and leaves October as it was.
    db.query(FactCrawlPageSnapshot).delete()
    for path in ("/", "/a", "/b"):
        page(db, client_a, path, snap=date(2026, 11, 2))
    db.commit()
    sh.record(db, client_a)
    october = sh.for_month(db, client_a, "2026-10", today=date(2026, 11, 3))
    assert october["seo"]["score"] == first["seo"]["score"] and october["crawl_date"] == "2026-10-20"
    november = sh.for_month(db, client_a, "2026-11", today=date(2026, 11, 3))
    assert november["locked"] is False and november["previous"]["seo"] == first["seo"]["score"]
    titles = next(c for c in november["changes"] if c["key"] == "titles")
    assert titles["fixed_count"] == 1 and titles["new_count"] == 0 and titles["fixed"] == [BASE + "/dup1"]
    api = client.get("/v2/site-health", headers=h).json()
    assert api["month"] == "2026-11" and api["months"] == ["2026-11", "2026-10"]


def test_a_site_that_was_never_crawled_has_no_scores(client, db, client_a, admin_user):
    out = client.get("/v2/site-health", headers=client_header(client_a.id, admin_user.email)).json()
    assert out == {"month": None, "months": [], "data": None}
    assert client.get("/v2/site-health", params={"month": "nope"}, headers=client_header(client_a.id, admin_user.email)).status_code == 400


def test_each_geo_signal_lists_what_to_fix(db, client_a):
    from app.models.gsc import FactGscQueryPage
    from app.models.watchlist import WatchlistBucket, WatchlistKeyword

    seed(db, client_a)  # pages /, /about-us, /pages/contact, /a, /b, /dup1, /nodesc; JSON-LD Product on / and /a
    db.add(FactCrawlPageIssue(client_id=client_a.id, source=CRAWL_SOURCE_FIRST_PARTY, snapshot_date=CRAWL, issue_code="ai_crawlers_blocked", normalized_url=None, raw={"agents": ["GPTBot"]}))
    for url, imp in ((BASE + "/a", 900), (BASE + "/b", 300)):
        db.add(FactGscQueryPage(client_id=client_a.id, date=date(2026, 10, 10), query="natural spf", raw_url=url, normalized_url=url, country="usa", device="DESKTOP",
                                impressions=Decimal(imp), clicks=Decimal(1), ctr=Decimal(0), average_position=Decimal(5)))
    b = WatchlistBucket(client_id=client_a.id, name="SPF", name_key="spf", sort_order=0)
    db.add(b)
    db.flush()
    db.add(WatchlistKeyword(client_id=client_a.id, bucket_id=b.id, keyword="natural spf", keyword_key="natural spf", paired_ai_prompt="What is the best natural SPF?"))
    run = LlmRun(client_id=client_a.id, status="completed")
    db.add(run)
    db.flush()
    for platform in ("openai", "gemini"):
        db.add(LlmResponse(run_id=run.id, client_id=client_a.id, query_text="What is the best natural SPF?", platform=platform, visibility_type="Not visible", brand_mentioned=False, url_cited=False, full_response="Try Badger."))
    db.commit()
    by = {s["key"]: s for s in sh.geo_readiness(db, client_a)["signals"]}
    schema_urls = [i["url"] for i in by["schema"]["items"]]
    assert BASE + "/" not in schema_urls[1:] and BASE + "/b" in schema_urls and by["schema"]["items"][0]["text"].startswith("No Organization markup")
    assert [i["url"] for i in by["faq"]["items"]] == [BASE + "/a", BASE + "/b"] and "900" in by["faq"]["items"][0]["text"]
    assert any("No phone number" in i["text"] for i in by["entity"]["items"]) and any(i["url"] == BASE + "/nodesc" for i in by["entity"]["items"])
    assert by["crawler"]["items"][0]["text"].startswith("GPTBot is blocked") and by["crawler"]["items"][0]["url"].endswith("/robots.txt")
    cite = by["citation"]["items"][0]
    assert "none of 2 answers" in cite["text"] and cite["url"] == BASE + "/a", "the page to strengthen is the one that shows most for the keyword"
    assert by["citation"]["affected"] == 1 and any("does not name the brand" in i["text"] for i in by["graph"]["items"])
    assert by["depth"]["items"][0]["url"] == BASE + "/a"


def test_faq_is_scored_page_by_page_on_the_pages_google_shows_most(db, client_a):
    from app.models.gsc import FactGscQueryPage

    seed(db, client_a)
    for url, imp in ((BASE + "/a", 900), (BASE + "/b", 300), (BASE + "/", 100), (BASE + "/not-crawled", 5000)):
        db.add(FactGscQueryPage(client_id=client_a.id, date=date(2026, 10, 10), query="q", raw_url=url, normalized_url=url, country="usa", device="DESKTOP",
                                impressions=Decimal(imp), clicks=Decimal(1), ctr=Decimal(0), average_position=Decimal(5)))
    schema(db, client_a, "/a", "FAQPage")
    db.commit()
    faq = next(s for s in sh.geo_readiness(db, client_a)["signals"] if s["key"] == "faq")
    assert faq["score"] == 33 and faq["detail"] == {"pages": 3, "with_markup": 1}  # /a has it; /b and / do not; an uncrawled page is not judged
    assert [i["url"] for i in faq["items"]] == [BASE + "/b", BASE + "/"] and faq["affected"] == 2


def test_numbered_list_pages_are_not_judged_in_geo_readiness(db, client_a):
    seed(db, client_a)
    for n in (2, 3, 11):
        page(db, client_a, f"/author/ryan/page/{n}", desc="")
    page(db, client_a, "/blog?page=4", desc="")
    db.commit()
    for url in ("/author/ryan/page/2", "/author/ryan/page/11", "/blog?page=4", "/a/p/7"):
        assert sh.is_pagination(BASE + url)
    for url in ("/author/ryan", "/pages/page-builder", "/collections/spf", "/products/pager"):
        assert not sh.is_pagination(BASE + url)
    by = {s["key"]: s for s in sh.geo_readiness(db, client_a)["signals"]}
    listed = [i["url"] for s in by.values() for i in s["items"]]
    assert not any("/page/" in (u or "") or "page=" in (u or "") for u in listed)
    assert by["entity"]["detail"]["description_share"] == 0.86  # 6 of the 7 real pages have a description; the four list pages are left out
