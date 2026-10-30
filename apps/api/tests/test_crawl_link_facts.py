"""Link facts from the crawl: counted in-content only, and used to judge V-4 and S-4."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlInternalLink, FactCrawlPageSnapshot
from app.services import crawl_link_facts as clf
from app.services import page_diagnostic as pd

PAGE = "https://shop.example/products/spf-15"
HUB = "https://shop.example/collections/spf"
BLOG = "https://shop.example/blogs/zinc"
OTHER = "https://shop.example/pages/about"


def _page(db, client_a, url, inbound):
    db.add(
        FactCrawlPageSnapshot(
            id=uuid4(), client_id=client_a.id, source=CRAWL_SOURCE_FIRST_PARTY, snapshot_date=date(2026, 10, 29),
            raw_url=url, normalized_url=url, indexable=True, status_code=200, inbound_internal_links=inbound,
            inbound_editorial_links=inbound, word_count=100, in_sitemap=True, redirect_count=0,
        )
    )


def _link(db, client_a, src, dst, *, in_content=True, template=False):
    db.add(
        FactCrawlInternalLink(
            id=uuid4(), client_id=client_a.id, source=CRAWL_SOURCE_FIRST_PARTY, snapshot_date=date(2026, 10, 29),
            from_url=src, to_url=dst, anchor_text="spf", in_content=in_content, is_template=template, occurrences=1,
        )
    )


def _site(db, client_a, *, inbound_to_page, median_pages=(1, 1, 3)):
    _page(db, client_a, PAGE, inbound_to_page)
    for i, n in enumerate(median_pages):
        _page(db, client_a, f"https://shop.example/p{i}", n)
    db.commit()


CANDIDATES = [
    {"url": HUB, "query": "mineral sunscreen", "impressions": 900},
    {"url": BLOG, "query": "is zinc safe", "impressions": 200},
]


def test_no_crawl_means_none_so_the_caller_says_it_could_not_check(db, client_a):
    assert clf.link_facts(db, client_a, PAGE, CANDIDATES) is None


def test_in_content_links_are_counted_and_navigation_is_not(db, client_a):
    _site(db, client_a, inbound_to_page=2)
    _link(db, client_a, HUB, PAGE)                          # a real link
    _link(db, client_a, OTHER, PAGE, template=True)         # site-wide navigation
    _link(db, client_a, BLOG, PAGE, in_content=False)       # not in the content area
    db.commit()

    out = clf.link_facts(db, client_a, PAGE, CANDIDATES)
    assert out["inbound"] == 2 and out["median"] == 1.5
    assert out["linked_from"] == [HUB]
    assert [c["url"] for c in out["sources_without_link"]] == [BLOG]
    assert [c["url"] for c in out["sources_already_linking"]] == [HUB]


async def _html(url):
    return pd.Fetched(200, url, {}, "<html><head><title>x</title></head><body><h1>Spf 15</h1></body></html>")


ROW = {"position": 9.0, "impressions": 500, "clicks": 4, "expected_extra_clicks": 3.0}


def _diag(links):
    return pd.diagnose(
        search="spf 15", url=PAGE.replace("shop.example", "shop.example"), row=ROW, client_domain="shop.example",
        fetch=_html, evidence={"page_queries": [], "competing_pages": 1, "donors": [], "crawl": links},
    )


def test_an_under_linked_page_with_sources_fires_the_catalogs_own_link_rule():
    links = {
        "date": "2026-10-29", "in_crawl": True, "pages": 50, "inbound": 0, "median": 3.0, "linked_from": [],
        "sources_without_link": [{"url": HUB, "query": "mineral sunscreen", "impressions": 900}],
        "sources_already_linking": [],
    }
    out = _diag(links)
    fired = [p["action_id"] for p in out["prescriptions"]]
    assert "V-4" in fired
    v4 = next(p for p in out["prescriptions"] if p["action_id"] == "V-4")
    assert "0 in-content links point here, against a site median of 3" in v4["why"]
    assert any(HUB in step for step in v4["steps"])
    # The unconfirmed version of the same advice is not repeated beside the real prescription.
    assert "S-4" not in [s["id"] for s in out["suggestions"]]


def test_a_page_not_under_linked_says_so_as_a_fact_and_s4_is_optional():
    links = {
        "date": "2026-10-29", "in_crawl": True, "pages": 50, "inbound": 1, "median": 1.0, "linked_from": [HUB],
        "sources_without_link": [{"url": BLOG, "query": "is zinc safe", "impressions": 200}],
        "sources_already_linking": [{"url": HUB, "query": "mineral sunscreen", "impressions": 900}],
    }
    out = _diag(links)
    reasons = {n["action_id"]: n["reason"] for n in out["not_judged"]}
    assert "1 in-content link points here, against a site median of 1" in reasons["V-4"]
    assert "not under-linked by the site's own measure" in reasons["V-4"]
    s4 = next(s for s in out["suggestions"] if s["id"] == "S-4")
    assert "optional, not a fix for a gap" in s4["why"] and BLOG in s4["steps"][0]
    assert "the crawl has already checked" in s4["needs_to_confirm"]


def test_when_every_topical_page_already_links_it_says_so():
    links = {
        "date": "2026-10-29", "in_crawl": True, "pages": 50, "inbound": 4, "median": 1.0, "linked_from": [HUB],
        "sources_without_link": [], "sources_already_linking": [{"url": HUB, "query": "x", "impressions": 9}],
    }
    out = _diag(links)
    skipped = next(k for k in out["skipped_suggestions"] if k["id"] == "S-4")
    assert "already links here (1 checked against the crawl of 2026-10-29)" in skipped["reason"]


def test_without_a_crawl_the_old_honest_message_stands():
    out = _diag(None)
    reasons = {n["action_id"]: n["reason"] for n in out["not_judged"]}
    assert "link crawl" in reasons["V-4"]
