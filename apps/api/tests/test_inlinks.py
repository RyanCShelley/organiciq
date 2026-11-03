"""Inlink suggester: who should link to whom, with the anchor text, and whether a link is live."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import numpy as np
import pytest

from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlInternalLink, FactCrawlPageSnapshot
from app.models.gsc import FactGscQueryPage
from app.services import inlinks
from app.services.page_diagnostic import Fetched
from tests.conftest import client_header

BASE = "https://shop.example"
CRAWL = date(2026, 10, 20)


def page(db, client, path, title, words=400, canonical=None):
    url = BASE + path
    db.add(FactCrawlPageSnapshot(client_id=client.id, source=CRAWL_SOURCE_FIRST_PARTY, snapshot_date=CRAWL, raw_url=url, normalized_url=url, indexable=True, status_code=200,
                                 title=title, word_count=words, canonical_url=canonical))
    return url


def link(db, client, a, b, template=False):
    db.add(FactCrawlInternalLink(client_id=client.id, source=CRAWL_SOURCE_FIRST_PARTY, snapshot_date=CRAWL, from_url=BASE + a, to_url=BASE + b, in_content=not template, is_template=template, occurrences=1))


def gsc(db, client, query, path, impressions, clicks, position=6.0):
    db.add(FactGscQueryPage(client_id=client.id, date=date(2026, 10, 10), query=query, raw_url=BASE + path, normalized_url=BASE + path, country="usa", device="DESKTOP",
                            impressions=Decimal(impressions), clicks=Decimal(clicks), ctr=Decimal(0), average_position=Decimal(position)))


@pytest.fixture(autouse=True)
def fake_vectors(monkeypatch):
    """Pages about sunscreen are alike, pages about soap are alike, the two groups are not: no model is loaded."""
    inlinks._VECTORS.clear()

    def embed(pages):
        out = []
        for p in pages:
            t = (p.title or "").lower()
            out.append(np.array([1.0, 0.1] if "sunscreen" in t else [0.1, 1.0] if "soap" in t else [0.7, 0.7], dtype="float32"))
        m = np.array(out)
        return m / np.linalg.norm(m, axis=1, keepdims=True)

    monkeypatch.setattr(inlinks.keyword_matcher, "embed_pages", embed)
    monkeypatch.setattr(inlinks.keyword_matcher, "page_text", lambda p: p.title or "")


def seed(db, client):
    page(db, client, "/products/spf-30", "SPF 30 Mineral Sunscreen | Shop Example")             # the target: under-linked, earns impressions
    page(db, client, "/blog/best-sunscreen", "The Best Natural Sunscreen for Kids | Shop Example")   # a strong, alike source
    page(db, client, "/blog/soap-guide", "A Guide to Natural Soap | Shop Example")                  # strong but about something else
    page(db, client, "/products/spf-50", "SPF 50 Sunscreen | Shop Example")                         # alike, but already links
    page(db, client, "/products/spf-30-dup", "SPF 30 Mineral Sunscreen | Shop Example", canonical=BASE + "/products/spf-30")
    page(db, client, "/cart", "Cart")
    gsc(db, client, "spf 30 sunscreen", "/products/spf-30", 900, 12, 6.0)
    gsc(db, client, "best natural sunscreen", "/blog/best-sunscreen", 3000, 200, 2.0)
    gsc(db, client, "natural soap guide", "/blog/soap-guide", 2000, 150, 2.0)
    gsc(db, client, "spf 50", "/products/spf-50", 800, 60, 3.0)
    link(db, client, "/products/spf-50", "/products/spf-30")
    db.commit()


def get(client, client_a, admin_user):
    return client.get("/v2/inlinks", headers=client_header(client_a.id, admin_user.email))


def test_the_under_linked_page_gets_alike_sources_that_do_not_link_yet_with_an_anchor(client, db, client_a, admin_user):
    seed(db, client_a)
    out = get(client, client_a, admin_user).json()["data"]
    by = {t["target_url"]: t for t in out["targets"]}
    target = by[BASE + "/products/spf-30"]
    assert [s["source_url"] for s in target["suggestions"]] == [BASE + "/blog/best-sunscreen"], "soap is not alike; spf-50 already links; the duplicate and the cart are not pages"
    sug = target["suggestions"][0]
    assert sug["similarity"] > 0.9 and sug["reasons"][0].startswith("Similar subject") and "clicks" in sug["reasons"][-1]
    assert sug["suggested_anchor"] and not sug["suggested_anchor"].lower().startswith("http")
    assert target["queries"] == ["spf 30 sunscreen"] and target["impressions"] == 900 and target["inbound"] == 1
    assert not any("dup" in u for u in by), "a canonical duplicate is not a target"


def test_a_link_to_a_duplicate_counts_as_a_link_to_the_real_page(client, db, client_a, admin_user):
    seed(db, client_a)
    link(db, client_a, "/blog/best-sunscreen", "/products/spf-30-dup")  # the duplicate's canonical is /products/spf-30
    db.commit()
    out = get(client, client_a, admin_user).json()["data"]
    target = next((t for t in out["targets"] if t["target_url"] == BASE + "/products/spf-30"), None)
    assert target is None or BASE + "/blog/best-sunscreen" not in [s["source_url"] for s in target["suggestions"]]


def test_ignoring_a_pair_or_a_page_removes_it_and_restoring_brings_it_back(client, db, client_a, admin_user):
    seed(db, client_a)
    h = client_header(client_a.id, admin_user.email)
    t, s = BASE + "/products/spf-30", BASE + "/blog/best-sunscreen"
    made = client.post("/v2/inlinks/ignore", json={"target": t, "source": s}, headers=h)
    assert made.status_code == 200
    data = get(client, client_a, admin_user).json()["data"]
    assert all(x["target_url"] != t for x in data["targets"]) and data["summary"]["ignored"] == 1
    assert client.delete(f"/v2/inlinks/ignore/{made.json()['id']}", headers=h).status_code == 200
    assert any(x["target_url"] == t for x in get(client, client_a, admin_user).json()["data"]["targets"])
    whole = client.post("/v2/inlinks/ignore", json={"target": t}, headers=h).json()["id"]
    assert all(x["target_url"] != t for x in get(client, client_a, admin_user).json()["data"]["targets"])
    client.delete(f"/v2/inlinks/ignore/{whole}", headers=h)


def test_checking_a_link_finds_it_live_records_it_and_stops_suggesting_it(client, db, client_a, admin_user, monkeypatch):
    seed(db, client_a)
    h = client_header(client_a.id, admin_user.email)
    t, s = BASE + "/products/spf-30", BASE + "/blog/best-sunscreen"
    html = f'<html><body><nav><a href="/">Home</a></nav><p>Read about <a href="https://www.shop.example/products/spf-30/">our SPF 30 mineral sunscreen</a>.</p></body></html>'
    monkeypatch.setattr(inlinks, "read_page", lambda url, domain: Fetched(status=200, final_url=url, headers={}, body=html))
    out = client.post("/v2/inlinks/verify", json={"source": s, "target": t}, headers=h).json()
    assert out["found"] is True and out["anchor"] == "our SPF 30 mineral sunscreen" and out["checked"] is True
    data = get(client, client_a, admin_user).json()["data"]
    assert data["summary"]["live"] == 1 and all(t != x["target_url"] for x in data["targets"]), "it is live now, so there is nothing left to suggest for this page"
    monkeypatch.setattr(inlinks, "read_page", lambda url, domain: Fetched(status=200, final_url=url, headers={}, body="<html><body><a href='/other'>x</a></body></html>"))
    assert client.post("/v2/inlinks/verify", json={"source": BASE + "/blog/soap-guide", "target": t}, headers=h).json()["found"] is False
    monkeypatch.setattr(inlinks, "read_page", lambda url, domain: Fetched(status=404, final_url=url, headers={}, body=""))
    missing = client.post("/v2/inlinks/verify", json={"source": s, "target": t}, headers=h).json()
    assert missing["checked"] is False and "404" in missing["error"]


def test_a_site_that_was_not_crawled_has_no_suggestions(client, db, client_a, admin_user):
    assert get(client, client_a, admin_user).json() == {"data": None}


def test_any_page_can_be_looked_up_even_one_with_enough_links(client, db, client_a, admin_user):
    seed(db, client_a)
    for i in range(6):  # spf-50 now has plenty of editorial links, so it is not on the main list
        page(db, client_a, f"/blog/post-{i}", f"Sunscreen note {i}")
        link(db, client_a, f"/blog/post-{i}", "/products/spf-50")
    db.commit()
    h = client_header(client_a.id, admin_user.email)
    main = client.get("/v2/inlinks", headers=h).json()["data"]
    assert BASE + "/products/spf-50" not in [t["target_url"] for t in main["targets"]]
    found = client.get("/v2/inlinks", params={"q": "SPF-50"}, headers=h).json()["data"]
    assert [t["target_url"] for t in found["targets"]] == [BASE + "/products/spf-50"] and found["q"] == "spf-50" and found["targets"][0]["inbound"] >= 6
    by_search = client.get("/v2/inlinks", params={"q": "spf 30 sunscreen"}, headers=h).json()["data"]
    assert BASE + "/products/spf-30" in [t["target_url"] for t in by_search["targets"]]
