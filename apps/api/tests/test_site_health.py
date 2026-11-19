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
    assert by["missing_titles"]["affected"] == 0 and by["missing_titles"]["total"] == 7
    assert by["duplicate_titles"]["affected"] == 1 and by["duplicate_titles"]["urls"] == [BASE + "/dup1"] and by["duplicate_titles"]["total"] == 7
    assert by["duplicate_titles"]["duplicate_groups"] == [{"text": "Same", "urls": [BASE + "/dup1"], "count": 1}]
    assert by["missing_descriptions"]["affected"] == 1 and by["missing_descriptions"]["urls"] == [BASE + "/nodesc"] and by["missing_descriptions"]["total"] == 7
    assert by["duplicate_descriptions"]["affected"] == 0 and by["duplicate_descriptions"]["duplicate_groups"] == []
    assert by["indexation"]["score"] == 100
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
    dup_titles = next(c for c in november["changes"] if c["key"] == "duplicate_titles")
    assert dup_titles["fixed_count"] == 1 and dup_titles["new_count"] == 0 and dup_titles["fixed"] == [BASE + "/dup1"]
    missing_desc = next(c for c in november["changes"] if c["key"] == "missing_descriptions")
    assert missing_desc["fixed_count"] == 1 and missing_desc["new_count"] == 0 and missing_desc["fixed"] == [BASE + "/nodesc"]
    api = client.get("/v2/site-health", headers=h).json()
    assert api["month"] == "2026-11" and api["months"] == ["2026-11", "2026-10"]


def test_a_site_that_was_never_crawled_has_no_scores(client, db, client_a, admin_user):
    out = client.get("/v2/site-health", headers=client_header(client_a.id, admin_user.email)).json()
    assert out == {"month": None, "months": [], "crawls": [], "compare_to": None, "data": None}
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
    assert by["citation"]["affected"] == 1 and any("never named the brand" in i["text"] for i in by["graph"]["items"])
    assert by["depth"]["items"][0]["url"] == BASE + "/a"
    # A platform that gave no answer is listed too, so a score of 75 is never a mystery: the platform is named and the reason given.
    texts = [i["text"] for i in by["graph"]["items"]]
    assert any(t.startswith("Claude gave no usable answer") for t in texts) and any(t.startswith("ChatGPT answered 1 times") or t.startswith("Gemini answered 1 times") for t in texts)
    assert "Gemini: never names the brand" in by["graph"]["summary"] and "Claude: no usable answer" in by["graph"]["summary"]
    assert by["citation"]["summary"] == "0 of 2 answers carry the site's address."
    # Every item says what it is about, what is wrong and what to do, in plain words.
    assert cite["subject"] == "“What is the best natural SPF?”" and cite["problem"] == "None of 2 AI answers carry the site's address." and cite["fix"].startswith("Strengthen this page for “natural spf”")
    assert by["depth"]["items"][0]["problem"].startswith("The answers give little specific detail") and "numbers" in by["depth"]["items"][0]["fix"]
    assert by["faq"]["items"][0]["problem"] == "Shown 900 times in Google in 90 days, and the page has no FAQ markup." and "FAQPage" in by["faq"]["items"][0]["fix"]
    assert all(i["problem"] and i["fix"] for sig in by.values() for i in sig["items"])


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


def test_numbered_list_pages_are_not_judged_in_seo_health_but_broken_ones_still_count(db, client_a):
    seed(db, client_a)
    before = {c["key"]: c for c in sh.seo_health(db, client_a, CRAWL)["checks"]}
    for n in (2, 3):
        page(db, client_a, f"/author/ryan/page/{n}", desc="", title="")
    page(db, client_a, "/author/ryan/page/4", status=404, title="", desc="")
    db.commit()
    after = {c["key"]: c for c in sh.seo_health(db, client_a, CRAWL)["checks"]}
    for key in ("missing_titles", "duplicate_titles", "missing_descriptions", "duplicate_descriptions", "indexation", "schema"):
        assert after[key]["total"] == before[key]["total"] and after[key]["affected"] == before[key]["affected"], key
    assert after["errors"]["affected"] == before["errors"]["affected"] + 1, "a broken list page is still a broken page"


def test_a_saved_month_written_before_items_had_advice_is_rebuilt_from_the_same_crawl(db, client_a):
    seed(db, client_a)
    row = sh.record(db, client_a)
    first = sh.for_month(db, client_a, "2026-10", today=date(2026, 11, 3))
    payload = row.payload
    for sig in payload["geo"]["signals"]:
        for item in sig["items"]:
            item.pop("problem", None)
            item.pop("fix", None)
    row.payload = payload
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(row, "payload")
    db.commit()
    again = sh.for_month(db, client_a, "2026-10", today=date(2026, 11, 3))
    assert again["crawl_date"] == first["crawl_date"] and again["seo"]["score"] == first["seo"]["score"]
    assert all(i["problem"] for sig in again["geo"]["signals"] for i in sig["items"])


def test_duplicate_and_missing_meta_are_separated_and_grouped_by_shared_text(db, client_a, monkeypatch):
    page(db, client_a, "/missing-title", title="", desc="Unique desc")
    page(db, client_a, "/empty-flagged-dup", title="   ", dup_title=True, desc="   ", dup_desc=True)
    page(db, client_a, "/unflagged-same", title="Same Title", dup_title=False, desc="Same Desc", dup_desc=False)
    # 3 pages sharing "Shared Alpha" (case/whitespace differences) + 2 sharing "Beta Title"
    page(db, client_a, "/t-a1", title=" Shared Alpha ", dup_title=True)
    page(db, client_a, "/t-a2", title="shared alpha", dup_title=True)
    page(db, client_a, "/t-a3", title="SHARED ALPHA", dup_title=True)
    page(db, client_a, "/t-b1", title="Beta Title", dup_title=True)
    page(db, client_a, "/t-b2", title="Beta Title", dup_title=True)
    # 2 pages sharing a meta description
    page(db, client_a, "/d-1", desc="Repeated meta description text", dup_desc=True)
    page(db, client_a, "/d-2", desc="repeated meta description text ", dup_desc=True)
    db.commit()

    # Cap URLS_KEPT=2 to verify duplicate_groups and by_page are built BEFORE URLS_KEPT truncation.
    monkeypatch.setattr(sh, "URLS_KEPT", 2)
    built = sh.build(db, client_a)
    assert built is not None
    by = {c["key"]: c for c in built["seo"]["checks"]}

    assert sorted(by["missing_titles"]["urls"]) == [BASE + "/empty-flagged-dup", BASE + "/missing-title"]
    assert by["missing_titles"]["affected"] == 2
    assert by["duplicate_titles"]["affected"] == 5
    assert len(by["duplicate_titles"]["urls"]) == 2  # truncated to URLS_KEPT
    assert BASE + "/unflagged-same" not in [u for g in by["duplicate_titles"]["duplicate_groups"] for u in g["urls"]]
    assert by["duplicate_titles"]["duplicate_groups"] == [
        {
            "text": "Shared Alpha",
            "urls": [BASE + "/t-a1", BASE + "/t-a2", BASE + "/t-a3"],
            "count": 3,
        },
        {
            "text": "Beta Title",
            "urls": [BASE + "/t-b1", BASE + "/t-b2"],
            "count": 2,
        },
    ]

    assert sorted(by["missing_descriptions"]["urls"]) == [BASE + "/empty-flagged-dup"]
    assert by["duplicate_descriptions"]["affected"] == 2
    assert by["duplicate_descriptions"]["duplicate_groups"] == [
        {
            "text": "Repeated meta description text",
            "urls": [BASE + "/d-1", BASE + "/d-2"],
            "count": 2,
        }
    ]

    by_url = {p["url"]: p for p in built["by_page"]}
    for u in (BASE + "/t-a1", BASE + "/t-a2", BASE + "/t-a3"):
        dup_issue = next(i for i in by_url[u]["issues"] if i["source"] == "seo" and i["key"] == "duplicate_titles")
        assert dup_issue["subject"] == "Shared Alpha"
        assert "2 other pages" in dup_issue["problem"]


def test_by_page_and_site_wide_merge_seo_and_geo_with_prescribed_fixes(db, client_a):
    from app.models.gsc import FactGscQueryPage
    from app.models.watchlist import WatchlistBucket, WatchlistKeyword

    # Omit /about and /contact so entity signal produces url=None site-wide items.
    page(db, client_a, "/", title="", desc="")
    page(db, client_a, "/hub", title="Hub", desc="Hub desc")
    page(db, client_a, "/noindex-page", title="Hidden", desc="Hidden desc", indexable=False)
    page(db, client_a, "/soft", title="Soft", desc="Soft desc", status=200, soft=True)
    page(db, client_a, "/server-err", title="", desc="", status=503)
    page(db, client_a, "/chain3", title="Chain", desc="Chain desc", status=301, redirects=3)
    schema(db, client_a, "/hub", "Product")
    db.add(FactCrawlInternalLink(client_id=client_a.id, source=CRAWL_SOURCE_FIRST_PARTY, snapshot_date=CRAWL, from_url=BASE + "/hub", to_url=BASE + "/server-err", in_content=True, is_template=False, occurrences=1))
    db.add(FactCrawlPageIssue(client_id=client_a.id, source=CRAWL_SOURCE_FIRST_PARTY, snapshot_date=CRAWL, issue_code="no_robots", normalized_url=None, raw={}))
    db.add(FactCrawlPageIssue(client_id=client_a.id, source=CRAWL_SOURCE_FIRST_PARTY, snapshot_date=CRAWL, issue_code="sitemap_missing", normalized_url=None, raw={}))
    db.add(FactCrawlPageIssue(client_id=client_a.id, source=CRAWL_SOURCE_FIRST_PARTY, snapshot_date=CRAWL, issue_code="ai_crawlers_blocked", normalized_url=None, raw={"agents": ["GPTBot"]}))

    db.add(FactGscQueryPage(client_id=client_a.id, date=date(2026, 10, 10), query="best widget", raw_url=BASE + "/", normalized_url=BASE + "/", country="usa", device="DESKTOP",
                            impressions=Decimal(500), clicks=Decimal(10), ctr=Decimal(0), average_position=Decimal(4)))
    b = WatchlistBucket(client_id=client_a.id, name="Core", name_key="core", sort_order=0)
    db.add(b)
    db.flush()
    db.add(WatchlistKeyword(client_id=client_a.id, bucket_id=b.id, keyword="best widget", keyword_key="best widget", paired_ai_prompt="What is the best widget?"))
    run = LlmRun(client_id=client_a.id, status="completed")
    db.add(run)
    db.flush()
    db.add(LlmResponse(run_id=run.id, client_id=client_a.id, query_text="What is the best widget?", platform="openai", visibility_type="Not visible", brand_mentioned=False, url_cited=False, full_response="Short answer."))
    db.add(LlmResponse(run_id=run.id, client_id=client_a.id, query_text="Unmapped prompt?", platform="gemini", visibility_type="Not visible", brand_mentioned=False, url_cited=False, full_response="Another short answer."))
    db.commit()

    built = sh.build(db, client_a)
    assert built is not None
    by_url = {p["url"]: p for p in built["by_page"]}

    # Verify ordering: (-issue_count, -severity_rank, url)
    sort_keys = [(-p["issue_count"], -sh.SEVERITY_RANK[p["highest_severity"]], p["url"]) for p in built["by_page"]]
    assert sort_keys == sorted(sort_keys)

    # Homepage merges SEO + GEO findings on the same URL
    home = by_url[BASE + "/"]
    assert home["seo_count"] > 0 and home["geo_count"] > 0
    assert home["issue_count"] == home["seo_count"] + home["geo_count"] == len(home["issues"])
    assert {i["source"] for i in home["issues"]} == {"seo", "geo"}
    assert home["highest_severity"] == "high"

    # Links attributed to from_url (/hub) in by_page, while seo.checks.links still lists broken target (/server-err)
    links_check = next(c for c in built["seo"]["checks"] if c["key"] == "links")
    assert links_check["urls"] == [BASE + "/server-err"]
    hub_links = [i for i in by_url[BASE + "/hub"]["issues"] if i["key"] == "links"]
    assert len(hub_links) == 1
    assert "/server-err" in hub_links[0]["problem"]
    assert "Edit links on this page" in hub_links[0]["fix"]
    assert not any(i["key"] == "links" for i in by_url[BASE + "/server-err"]["issues"])

    # Errors distinguish soft_404 vs >=500; redirects include redirect_count; indexation is high severity
    soft_err = next(i for i in by_url[BASE + "/soft"]["issues"] if i["key"] == "errors")
    assert soft_err["subject"] == "Soft 404" and "soft 404" in soft_err["problem"].lower()
    srv_err = next(i for i in by_url[BASE + "/server-err"]["issues"] if i["key"] == "errors")
    assert srv_err["subject"] == "HTTP 503" and "503" in srv_err["problem"]
    redir = next(i for i in by_url[BASE + "/chain3"]["issues"] if i["key"] == "redirects")
    assert "3 redirects" in redir["problem"]
    idx = next(i for i in by_url[BASE + "/noindex-page"]["issues"] if i["key"] == "indexation")
    assert idx["severity"] == "high"

    # AI crawler block is on /robots.txt in by_page, NOT duplicated in site_wide
    robots_url = f"https://{sh.bare_domain(client_a.domain)}/robots.txt"
    assert any(i["source"] == "geo" and i["key"] == "crawler" for i in by_url[robots_url]["issues"])

    # site_files and url=None GEO items (about/contact, graph, unmapped prompt) live exclusively in site_wide
    site_wide = built["site_wide"]
    assert any(i["source"] == "seo" and i["key"] == "site_files" and i["subject"] == "/robots.txt" for i in site_wide)
    assert any(i["source"] == "seo" and i["key"] == "site_files" and i["subject"] == "XML Sitemap" for i in site_wide)
    assert not any(i["key"] == "site_files" for p in built["by_page"] for i in p["issues"])
    assert not any(i["key"] == "crawler" for i in site_wide)
    assert any(i["source"] == "geo" and i["key"] == "entity" and i["subject"] == "The site" for i in site_wide)
    assert any(i["source"] == "geo" and i["key"] == "graph" for i in site_wide)
    assert any(i["source"] == "geo" and i["key"] == "citation" and "Unmapped prompt?" in (i["subject"] or "") for i in site_wide)

    # Every issue carries valid deterministic metadata
    for issue in [i for p in built["by_page"] for i in p["issues"]] + site_wide:
        assert issue["source"] in ("seo", "geo")
        assert issue["severity"] in ("high", "medium", "low")
        assert issue["label"] and issue["problem"] and issue["fix"]


def test_legacy_snapshots_upgrade_on_current_crawl_and_synthesize_by_page_when_locked(client, db, client_a, admin_user):
    from app.models.site_health import SiteHealthSnapshot

    seed(db, client_a)
    h = client_header(client_a.id, admin_user.email)

    # 1) Legacy locked historical snapshots (2026-08 and 2026-09) while active crawl is 2026-10
    legacy_sep = {
        "crawl": {"date": "2026-09-25", "pages": 10, "limit": 500, "hit_limit": False},
        "seo": {
            "score": 81,
            "grade": "B-",
            "pages": 10,
            "checks": [
                {"key": "titles", "label": "Page titles", "weight": 15, "score": 80, "affected": 1, "total": 10, "detail": "1 dup", "urls": [BASE + "/dup1"]},
                {"key": "descriptions", "label": "Meta descriptions", "weight": 10, "score": 90, "affected": 1, "total": 10, "detail": "1 missing", "urls": [BASE + "/nodesc"]},
                {"key": "links", "label": "Internal links to broken pages", "weight": 15, "score": 90, "affected": 1, "total": 10, "detail": "1 broken", "urls": [BASE + "/gone"]},
                {"key": "site_files", "label": "robots.txt and sitemap", "weight": 10, "score": 60, "affected": 1, "total": 2, "detail": "no robots.txt", "urls": ["no robots.txt"]},
            ],
        },
        "geo": {
            "score": 62,
            "grade": "D-",
            "partial": True,
            "answers": None,
            "signals": [
                {
                    "key": "schema",
                    "label": "Structured data",
                    "weight": 15,
                    "score": 40,
                    "measured": True,
                    "detail": {},
                    "note": "x",
                    "summary": None,
                    "items": [{"text": "No structured data", "url": BASE + "/dup1", "subject": None, "problem": "No structured data.", "fix": "Add JSON-LD."}],
                    "affected": 1,
                },
                {
                    "key": "entity",
                    "label": "Entity clarity",
                    "weight": 10,
                    "score": 50,
                    "measured": True,
                    "detail": {},
                    "note": "x",
                    "summary": None,
                    "items": [{"text": "No about page", "url": None, "subject": "The site", "problem": "No about page.", "fix": "Add About page."}],
                    "affected": 1,
                },
            ],
        },
        "weights": {},
    }
    legacy_aug = {
        "crawl": {"date": "2026-08-25", "pages": 10, "limit": 500, "hit_limit": False},
        "seo": {"score": 78, "grade": "C+", "pages": 10, "checks": [
            {"key": "links", "label": "Internal links to broken pages", "weight": 15, "score": 90, "affected": 1, "total": 10, "detail": "1 broken", "urls": [BASE + "/old-gone"]},
        ]},
        "geo": {"score": 60, "grade": "D-", "partial": True, "answers": None, "signals": []},
        "weights": {},
    }
    db.add_all([
        SiteHealthSnapshot(client_id=client_a.id, month="2026-08", crawl_date=date(2026, 8, 25), payload=legacy_aug),
        SiteHealthSnapshot(client_id=client_a.id, month="2026-09", crawl_date=date(2026, 9, 25), payload=legacy_sep),
    ])
    db.commit()

    # Reading locked 2026-09 via API preserves scores & legacy checks, while synthesizing by_page & site_wide on read
    resp_sep = client.get("/v2/site-health", params={"month": "2026-09"}, headers=h)
    assert resp_sep.status_code == 200
    data_sep = resp_sep.json()["data"]
    assert data_sep["seo"]["score"] == 81 and data_sep["geo"]["score"] == 62
    assert [c["key"] for c in data_sep["seo"]["checks"]] == ["titles", "descriptions", "links", "site_files"]
    by_url_sep = {p["url"]: p for p in data_sep["by_page"]}
    assert {i["source"] for i in by_url_sep[BASE + "/dup1"]["issues"]} == {"seo", "geo"}
    assert by_url_sep[BASE + "/gone"]["issues"][0]["key"] == "links"
    assert "point to this broken URL" in by_url_sep[BASE + "/gone"]["issues"][0]["problem"]
    assert any(i["key"] == "site_files" and i["subject"] == "/robots.txt" for i in data_sep["site_wide"])
    assert any(i["source"] == "geo" and i["key"] == "entity" for i in data_sep["site_wide"])
    # Locked DB row remains untouched
    db.expire_all()
    sep_row = db.query(SiteHealthSnapshot).filter(SiteHealthSnapshot.client_id == client_a.id, SiteHealthSnapshot.month == "2026-09").one()
    assert "by_page" not in sep_row.payload

    # 2) Current-crawl month (2026-10) saved with legacy schema upgrades automatically via _payload_needs_upgrade
    db.add(SiteHealthSnapshot(client_id=client_a.id, month="2026-10", crawl_date=CRAWL, payload=legacy_sep))
    db.commit()
    oct_data = sh.for_month(db, client_a, "2026-10", today=date(2026, 11, 5))
    assert oct_data is not None
    oct_keys = {c["key"] for c in oct_data["seo"]["checks"]}
    assert {"missing_titles", "duplicate_titles", "missing_descriptions", "duplicate_descriptions"} <= oct_keys
    assert "titles" not in oct_keys and "descriptions" not in oct_keys
    assert "by_page" in oct_data and "site_wide" in oct_data
    # Month-over-month comparison skips new split keys absent from legacy 2026-09 instead of reporting false positives
    change_keys = {c["key"] for c in oct_data["changes"]}
    assert not (change_keys & {"missing_titles", "duplicate_titles", "missing_descriptions", "duplicate_descriptions"})
    # Verify DB row for current crawl was upgraded
    db.expire_all()
    oct_row = db.query(SiteHealthSnapshot).filter(SiteHealthSnapshot.client_id == client_a.id, SiteHealthSnapshot.month == "2026-10").one()
    assert "by_page" in oct_row.payload and "site_wide" in oct_row.payload
