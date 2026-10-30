"""Diagnosing a page picked from the Traffic or Leads list."""

from __future__ import annotations

from datetime import date

from app.decisions import leads_candidates as lc
from app.decisions import traffic_candidates as tc
from app.decisions.provisional import suggest_leads, suggest_traffic
from app.ingestion.crawler.parse import parse_page
from app.models.config import ClientConversionPage, ConversionDefinition
from app.models.gsc import FactGscQueryPage
from app.services import page_diagnostic as pd
from tests.conftest import client_header

URL = "https://shop.example/products/spf-15"
NOUN = {"singular": "order", "plural": "orders"}


def parsed(body="", head=""):
    html = f"<html><head><title>SPF 15</title>{head}</head><body><h1>SPF 15</h1><h2>Ingredients</h2><p>Zinc.</p>{body}</body></html>"
    return parse_page(url=URL, body=html, headers={})


def lost(query, prev_imp, cur_imp, prev_clk, cur_clk, prev_pos, cur_pos):
    return {
        "query": query,
        "impressions": {"previous": prev_imp, "current": cur_imp},
        "clicks": {"previous": prev_clk, "current": cur_clk},
        "position": {"previous": prev_pos, "current": cur_pos},
        "clicks_lost": prev_clk - cur_clk,
        "impressions_lost": prev_imp - cur_imp,
    }


def ids(found):
    return [s["id"] for s in found["suggestions"]]


# ── traffic ──────────────────────────────────────────────────────────────────


def test_traffic_lists_the_searches_that_lost_the_most_and_is_unconfirmed():
    found = suggest_traffic(lost=[lost("mineral sunscreen", 900, 300, 20, 4, 6.0, 9.0)], unit=None)
    t1 = found["suggestions"][0]
    assert t1["id"] == "T-S1" and t1["confidence"] == "unconfirmed"
    assert "“mineral sunscreen”: 900 to 300 impressions, 20 to 4 clicks, position 6.0 to 9.0" in t1["steps"][0]
    assert "lists what fell, not why" in t1["needs_to_confirm"]


def test_traffic_tells_lost_rankings_from_lost_demand():
    slipped = [lost(f"q{i}", 100, 40, 10, 2, 5.0, 9.0) for i in range(3)]
    assert next(s for s in suggest_traffic(lost=slipped, unit=None)["suggestions"] if s["id"] == "T-S2")["title"] == "Rankings fell, not just demand"
    steady = [lost(f"q{i}", 100, 40, 10, 2, 5.0, 5.2) for i in range(3)]
    assert next(s for s in suggest_traffic(lost=steady, unit=None)["suggestions"] if s["id"] == "T-S2")["title"] == "Demand fell more than rankings"
    dropped_out = [lost("gone", 100, 0, 10, 0, 5.0, None), lost("gone2", 100, 0, 10, 0, 5.0, None)]
    assert next(s for s in suggest_traffic(lost=dropped_out, unit=None)["suggestions"] if s["id"] == "T-S2")["title"] == "Rankings fell, not just demand"


def test_traffic_with_nothing_lost_says_where_the_drop_is_not():
    found = suggest_traffic(lost=[], unit=None)
    assert found["suggestions"] == [] and found["skipped"][0]["id"] == "T-S1"


def gsc(db, client_a, day, query, url, impressions, clicks, position):
    db.add(
        FactGscQueryPage(
            client_id=client_a.id, date=day, query=query, raw_url=url, normalized_url=url, country="usa",
            device="DESKTOP", impressions=impressions, clicks=clicks, ctr=0, average_position=position,
        )
    )


def test_queries_lost_compares_three_months_with_the_three_before(db, client_a):
    gsc(db, client_a, date(2026, 5, 10), "mineral sunscreen", URL, 900, 20, 6.0)
    gsc(db, client_a, date(2026, 8, 10), "mineral sunscreen", URL, 300, 4, 9.0)
    gsc(db, client_a, date(2026, 5, 11), "tiny", URL, 10, 5, 3.0)      # under 20 impressions before: ignored
    gsc(db, client_a, date(2026, 5, 12), "stable", URL, 100, 5, 4.0)
    gsc(db, client_a, date(2026, 8, 12), "stable", URL, 100, 5, 4.0)    # nothing lost
    db.commit()
    rows = tc.queries_lost(db, client_a, "2026-09", URL)
    assert [r["query"] for r in rows] == ["mineral sunscreen"]
    assert rows[0]["clicks_lost"] == 16 and rows[0]["impressions_lost"] == 600
    assert rows[0]["position"] == {"current": 9.0, "previous": 6.0}


# ── leads ────────────────────────────────────────────────────────────────────

SITE = {"median_engagement_rate": 70.0, "median_conversion_rate": 4.0}
WEAK = {"page": URL, "sessions": 400, "conversions": 4, "conversion_rate": 1.0, "engagement_rate": 30.0}
STRONG = {"page": URL, "sessions": 400, "conversions": 24, "conversion_rate": 6.0, "engagement_rate": 80.0}


def test_leads_says_visitors_leave_when_engagement_is_well_under_the_sites_median():
    found = suggest_leads(row=WEAK, site=SITE, path={"declared": 0, "crawl": True, "linked_to": []}, parsed=parsed(), noun=NOUN)
    l1 = next(s for s in found["suggestions"] if s["id"] == "L-S1")
    assert "30.0% against a site median of 70.0%" in l1["why"]


def test_leads_without_declared_conversion_pages_says_the_path_cannot_be_checked():
    found = suggest_leads(row=WEAK, site=SITE, path={"declared": 0, "crawl": True, "linked_to": []}, parsed=parsed(), noun=NOUN)
    l2 = next(s for s in found["suggestions"] if s["id"] == "L-S2")
    assert "No conversion pages are declared" in " ".join(l2["steps"])


def test_leads_with_conversion_pages_but_no_link_to_any_of_them_is_stated_as_a_fact():
    found = suggest_leads(row=WEAK, site=SITE, path={"declared": 3, "crawl": True, "linked_to": []}, parsed=parsed(), noun=NOUN)
    l2 = next(s for s in found["suggestions"] if s["id"] == "L-S2")
    assert l2["title"] == "This page does not link to a conversion page" and "no in-content link" in l2["why"]
    assert "1.0% of sessions end in an order here, against a site median of 4.0%" in l2["why"]
    assert "the crawl has already checked" in l2["needs_to_confirm"]


def test_leads_with_a_link_in_place_asks_whether_visitors_act_on_it():
    found = suggest_leads(row=WEAK, site=SITE, path={"declared": 3, "crawl": True, "linked_to": ["https://shop.example/contact"]}, parsed=parsed(), noun=NOUN)
    l2 = next(s for s in found["suggestions"] if s["id"] == "L-S2")
    assert "links to 1 of 3 declared conversion pages" in l2["why"]


def test_a_page_at_or_above_the_site_median_has_no_gap_to_explain():
    found = suggest_leads(row=STRONG, site=SITE, path={"declared": 0, "crawl": False, "linked_to": []}, parsed=parsed(), noun=NOUN)
    assert found["suggestions"] == [] and "no gap to explain" in found["skipped"][0]["reason"]


def test_a_page_outside_the_sites_norm_says_why():
    found = suggest_leads(row=None, site=SITE, path={"declared": 0, "crawl": False, "linked_to": []}, parsed=parsed(), noun=NOUN)
    assert "needs 50 organic sessions" in found["skipped"][0]["reason"]


def test_conversion_path_counts_only_in_content_links_to_declared_pages(db, client_a):
    from uuid import uuid4

    from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlInternalLink, FactCrawlPageSnapshot

    contact, pricing = "https://shop.example/contact", "https://shop.example/pricing"
    for page in (contact, pricing):
        db.add(ClientConversionPage(client_id=client_a.id, normalized_url=page, label=page.rsplit("/", 1)[-1]))
    db.add(
        FactCrawlPageSnapshot(
            id=uuid4(), client_id=client_a.id, source=CRAWL_SOURCE_FIRST_PARTY, snapshot_date=date(2026, 10, 29), raw_url=URL,
            normalized_url=URL, indexable=True, status_code=200, inbound_internal_links=0, word_count=1, in_sitemap=True, redirect_count=0,
        )
    )
    # Contact is reached only by the site-wide navigation; pricing by a link in the page's own content.
    for to, template in ((contact, True), (pricing, False)):
        db.add(
            FactCrawlInternalLink(
                id=uuid4(), client_id=client_a.id, source=CRAWL_SOURCE_FIRST_PARTY, snapshot_date=date(2026, 10, 29),
                from_url=URL, to_url=to, anchor_text="x", in_content=not template, is_template=template, occurrences=1,
            )
        )
    db.commit()
    out = lc.conversion_path(db, client_a, URL)
    assert out["declared"] == 2 and out["crawl"] is True and out["linked_to"] == [pricing]


# ── the route ────────────────────────────────────────────────────────────────


async def html(url):
    return pd.Fetched(200, url, {}, "<html><head><title>x</title></head><body><h1>x</h1></body></html>")


def test_the_page_route_reads_each_page_and_never_a_foreign_one(client, db, client_a, admin_user, monkeypatch):
    fetched = []

    async def fetch(url):
        fetched.append(url)
        return await html(url)

    monkeypatch.setattr(pd, "_fetch", fetch)
    h = client_header(client_a.id, admin_user.email)
    ok = f"https://{client_a.domain}/p"
    res = client.post("/v2/engine/diagnose-page", json={"focus": "traffic", "pages": [ok, "https://evil.example/x"]}, headers=h)
    assert res.status_code == 200
    results = res.json()["results"]
    assert results[0]["read"]["ok"] is True and results[0]["search"] == "(page)"
    assert results[1]["read"]["ok"] is False and "not on this client's website" in results[1]["read"]["error"]
    assert fetched == [ok]


def test_the_page_route_checks_focus_and_count(client, db, client_a, admin_user):
    h = client_header(client_a.id, admin_user.email)
    assert client.post("/v2/engine/diagnose-page", json={"focus": "visibility", "pages": ["x"]}, headers=h).status_code == 422
    assert client.post("/v2/engine/diagnose-page", json={"focus": "leads", "pages": [f"https://a/{i}" for i in range(6)]}, headers=h).status_code == 422
    assert client.post("/v2/engine/diagnose-page", json={"focus": "leads", "pages": []}, headers=h).status_code == 422
