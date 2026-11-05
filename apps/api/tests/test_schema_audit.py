"""Schema and knowledge graph: the audit by kind of page (Topic Hub's rules), the brand as an entity, and the on-demand page tools."""

from __future__ import annotations

import json
from datetime import date

import pytest

from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSchema, FactCrawlPageSnapshot
from app.schema_tools import llm, wikidata
from app.services import schema_pages
from app.services.page_diagnostic import Fetched
from tests.conftest import client_header

BASE = "https://shop.example"
CRAWL = date(2026, 10, 20)


def page(db, client, path, title="T"):
    url = BASE + path
    db.add(FactCrawlPageSnapshot(client_id=client.id, source=CRAWL_SOURCE_FIRST_PARTY, snapshot_date=CRAWL, raw_url=url, normalized_url=url, indexable=True, status_code=200, title=title))
    return url


def ld(db, client, path, raw, kind=None):
    db.add(FactCrawlPageSchema(client_id=client.id, snapshot_date=CRAWL, normalized_url=BASE + path, syntax="json_ld", schema_type=kind or raw.get("@type"), raw=raw, raw_text=json.dumps(raw)))


def seed(db, client):
    for path in ("/", "/products/a", "/products/b", "/products/c", "/blogs/news/post", "/collections/x", "/page/2", "/author/me/page/3"):
        page(db, client, path)
    ld(db, client, "/products/a", {"@context": "https://schema.org", "@type": "Product", "name": "A", "offers": {"@type": "Offer", "price": "5"}, "logo": "https://shop.example/l.png"})
    ld(db, client, "/products/b", {"@context": "https://schema.org", "@type": "Product", "name": "B"})
    ld(db, client, "/blogs/news/post", {"@context": "https://schema.org", "@type": "Article", "headline": "H", "publisher": {"@type": "Organization", "name": "Shop Example"}})
    ld(db, client, "/collections/x", {"@context": "https://schema.org", "@type": "CollectionPage", "name": "X"})
    db.commit()


def get(client, client_a, admin_user, path="/v2/schema", **params):
    return client.get(path, params=params, headers=client_header(client_a.id, admin_user.email))


def test_pages_are_grouped_by_kind_and_checked_against_the_markup_that_kind_needs(client, db, client_a, admin_user):
    seed(db, client_a)
    out = get(client, client_a, admin_user).json()["data"]
    assert out["pages"] == 6, "numbered list pages (/page/2) are not audited"
    by = {t["page_type"]: t for t in out["types"]}
    assert by["product"]["pages"] == 3 and by["product"]["expects"] == ["Product", "Offer", "WebPage"]
    texts = {i["url"]: i["text"] for i in by["product"]["items"]}
    assert "Missing Offer" in texts[BASE + "/products/b"] and BASE + "/products/c" in texts, "a product with no markup, and one with no offer, both need work"
    assert "cleanup" not in texts[BASE + "/products/a"], "a bare logo address is valid Schema.org (logo takes a URL), so it is no longer a cleanup"
    assert "Missing WebPage" in texts[BASE + "/products/a"], "the baseline expects every page to be a WebPage in the site's graph"
    assert "cleanup" in texts[BASE + "/products/b"] and "needs 'review|aggregateRating|offers'" in texts[BASE + "/products/b"], "a Product with no offer, rating or review is not eligible for Google's product snippet"
    assert by["editorial"]["affected"] == 1 and by["category"]["affected"] == 0, "the article has no WebPage"
    assert by["homepage"]["items"][0]["text"].startswith("Missing Organization, WebSite")
    assert 0 <= out["score"] <= 100 and out["with_markup"] == 4 and out["cleanups"] >= 1


def test_what_recurs_across_pages_is_listed_once_to_fix_in_the_template(client, db, client_a, admin_user):
    seed(db, client_a)
    out = get(client, client_a, admin_user).json()["data"]
    assert {"text": "Missing Offer on product pages", "pages": 2, "example": BASE + "/products/b"} in [{k: f[k] for k in ("text", "pages", "example")} for f in out["fixes"]]


def test_the_brand_is_checked_as_an_entity_and_a_wikidata_item_can_be_approved(client, db, client_a, admin_user, monkeypatch):
    seed(db, client_a)
    checks = {c["key"]: c for c in get(client, client_a, admin_user).json()["data"]["entity"]["checks"]}
    assert checks["org"]["status"] == "warn", "the organization only appears as an article's publisher"
    assert checks["wikidata"]["status"] == "optional" and checks["same_as"]["status"] == "fail", "most brands have no Wikidata item, so the brand's own is optional"

    async def fake(names, **kw):
        return {n: [wikidata.QIDCandidate(qid="Q42", label=n, description="a brand", url="https://www.wikidata.org/wiki/Q42")] for n in names}

    monkeypatch.setattr(wikidata, "search_many", fake)
    h = client_header(client_a.id, admin_user.email)
    found = client.post("/v2/schema/concepts/search", json={"names": ["Shop Example"]}, headers=h).json()
    assert found["candidates"]["Shop Example"][0]["qid"] == "Q42"
    approved = client.post("/v2/schema/concepts", json={"name": client_a.client_name, "qid": "Q42", "label": "Shop", "description": "a brand"}, headers=h)
    assert approved.status_code == 200 and approved.json()["url"].endswith("/Q42")
    assert client.post("/v2/schema/concepts", json={"name": "x", "qid": "not-a-qid"}, headers=h).status_code == 422
    after = get(client, client_a, admin_user).json()["data"]
    assert next(c for c in after["entity"]["checks"] if c["key"] == "wikidata")["status"] == "pass" and len(after["concepts"]) == 1
    assert client.delete(f"/v2/schema/concepts/{approved.json()['id']}", headers=h).status_code == 200


def test_core_topics_are_checked_for_wikidata_ids_and_for_being_linked_from_the_markup(client, db, client_a, admin_user):
    from app.models.watchlist import WatchlistBucket

    seed(db, client_a)
    h = client_header(client_a.id, admin_user.email)

    def topics():
        return next(c for c in get(client, client_a, admin_user).json()["data"]["entity"]["checks"] if c["key"] == "topics")

    assert topics()["status"] == "warn" and "No core topics" in topics()["detail"]
    db.add(WatchlistBucket(client_id=client_a.id, name="Sunscreen", name_key="sunscreen", sort_order=0))
    db.commit()
    assert topics()["status"] == "fail" and topics()["items"][0]["kind"] == "missing"
    client.post("/v2/schema/concepts", json={"name": "Sunscreen", "qid": "Q10", "label": "sunscreen", "description": "lotion"}, headers=h)
    t = topics()
    assert t["status"] == "warn" and t["items"][0]["kind"] == "other" and "approved but not in the site's markup yet" in t["items"][0]["label"]
    ld(db, client_a, "/collections/x", {"@context": "https://schema.org", "@type": "CollectionPage", "name": "X", "about": {"@type": "Thing", "name": "Sunscreen", "sameAs": "https://www.wikidata.org/wiki/Q10"}})
    db.commit()
    t = topics()
    assert t["status"] == "pass" and t["detail"].startswith("1 of 1 topics are linked") and t["items"][0]["kind"] == "found"


def fetched(body="<html><body><nav>menu</nav><main><h1>Spf</h1><p>Natural sunscreen for daily use.</p></main></body></html>"):
    async def fetch(url):
        return Fetched(status=200, final_url=url, headers={}, body=body)

    return fetch


def test_the_model_audits_a_page_and_the_wikidata_lookup_not_the_model_supplies_the_item_numbers(client, db, client_a, admin_user, monkeypatch):
    from app.core.settings import get_settings

    client_a.domain = "shop.example"
    db.commit()
    seed(db, client_a)
    seen = {}
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "k")
    monkeypatch.setattr(schema_pages, "read_page", lambda url, domain: Fetched(status=200, final_url=url, headers={}, body="<html><body><nav>menu</nav><p>Natural sunscreen for daily use.</p></body></html>"))

    def call(depth, prompt, **kw):
        seen["prompt"] = prompt
        return json.dumps({"intent": "Product", "intent_explanation": "It sells one.", "diagnosis": ["No Offer."], "fix_plan": ["Add an Offer."], "suggested_concepts": ["Sunscreen"]}), 1000, 200

    async def fake(names, **kw):
        return {n: [wikidata.QIDCandidate(qid="Q1", label=n, description="d", url="u")] for n in names}

    monkeypatch.setattr(llm, "call", call)
    monkeypatch.setattr(wikidata, "search_many", fake)
    h = client_header(client_a.id, admin_user.email)
    url = BASE + "/products/b"
    made = client.post("/v2/schema/page/audit", json={"url": url, "depth": "quick"}, headers=h)
    assert made.status_code == 202
    out = client.get("/v2/schema/page", params={"url": url}, headers=h).json()
    audit = out["reports"]["audit"]
    assert audit["status"] == "done" and audit["intent"] == "Product" and audit["fix_plan"] == ["Add an Offer."]
    assert audit["concepts"][0]["candidates"][0]["qid"] == "Q1" and "Natural sunscreen" in seen["prompt"] and "menu" not in seen["prompt"]
    assert out["page_type"] == "product" and "Offer" in out["missing_required"] and audit["cost_usd"] > 0


def test_generated_markup_links_only_to_approved_items_and_never_carries_breadcrumbs(client, db, client_a, admin_user, monkeypatch):
    from app.core.settings import get_settings

    client_a.domain = "shop.example"
    db.commit()
    seed(db, client_a)
    schema_pages.approve_concept(db, client_a, "Sunscreen", "Q7", "Sunscreen", "", "x@y.co")
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "k")
    monkeypatch.setattr(schema_pages, "read_page", lambda url, domain: Fetched(status=200, final_url=url, headers={}, body="<html><body><p>Sunscreen.</p></body></html>"))
    seen = {}

    def call(depth, prompt, **kw):
        seen["prompt"] = prompt
        graph = {"@context": "https://schema.org", "@graph": [{"@type": "WebPage", "@id": BASE + "/p#webpage", "name": "P", "breadcrumb": {"@id": "x"}},
                                                          {"@type": "Organization", "@id": BASE + "#organization", "name": "Shop", "sameAs": ["https://www.instagram.com/", "https://www.linkedin.com/company/shop-example"]},
                                                          {"@type": "BreadcrumbList", "@id": "x"}]}
        return json.dumps(graph), 800, 400

    monkeypatch.setattr(llm, "call", call)
    h = client_header(client_a.id, admin_user.email)
    client.post("/v2/schema/page/markup", json={"url": BASE + "/products/a", "depth": "deep"}, headers=h)
    markup = client.get("/v2/schema/page", params={"url": BASE + "/products/a"}, headers=h).json()["reports"]["markup"]
    assert markup["status"] == "done" and "BreadcrumbList" not in markup["json_ld"] and "breadcrumb" not in markup["json_ld"]
    assert "https://www.wikidata.org/wiki/Q7" in seen["prompt"] and markup["approved"] == [{"name": "Sunscreen", "qid": "Q7"}]
    assert any("Breadcrumb" in n for n in markup["post_corrections"]) and markup["depth"] == "deep"
    assert "linkedin.com/company/shop-example" in markup["json_ld"] and "instagram.com/\"" not in markup["json_ld"], "a link to a site's front page is not a profile"
    assert any("front page" in n for n in markup["post_corrections"])


def test_a_page_off_the_clients_site_is_not_read_and_a_failure_is_shown(client, db, client_a, admin_user, monkeypatch):
    from app.core.settings import get_settings

    seed(db, client_a)
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "k")
    monkeypatch.setattr(llm, "call", lambda *a, **k: ("{}", 1, 1))
    h = client_header(client_a.id, admin_user.email)
    client.post("/v2/schema/page/audit", json={"url": "https://elsewhere.example/page", "depth": "quick"}, headers=h)
    report = client.get("/v2/schema/page", params={"url": "https://elsewhere.example/page"}, headers=h).json()["reports"]["audit"]
    assert report["status"] == "failed" and "not on this client's website" in report["error"]


def ignore(client, client_a, admin_user, scope, key, label=""):
    return client.post("/v2/schema/ignores", json={"scope": scope, "key": key, "label": label}, headers=client_header(client_a.id, admin_user.email))


def test_what_does_not_apply_can_be_ignored_and_restored(client, db, client_a, admin_user):
    seed(db, client_a)
    base = get(client, client_a, admin_user).json()["data"]
    by = {t["page_type"]: t for t in base["types"]}
    assert "WebSite" in by["homepage"]["expects"] and by["homepage"]["affected"] == 1 and by["product"]["affected"] == 3

    # A markup type not expected of a kind of page: the home page then needs only an Organization.
    made = ignore(client, client_a, admin_user, "expect", "homepage:WebSite", "Home page: WebSite is not expected")
    assert made.status_code == 200
    after = {t["page_type"]: t for t in get(client, client_a, admin_user).json()["data"]["types"]}
    assert "WebSite" not in after["homepage"]["expects"] and "Missing Organization" in after["homepage"]["items"][0]["text"] and "WebSite" not in after["homepage"]["items"][0]["text"]

    # A whole kind of page, and one page.
    ignore(client, client_a, admin_user, "page_type", "homepage")
    ignore(client, client_a, admin_user, "page", BASE + "/products/c")
    data = get(client, client_a, admin_user).json()["data"]
    types = {t["page_type"]: t for t in data["types"]}
    assert "homepage" not in types and types["product"]["pages"] == 2 and types["product"]["affected"] == 2
    assert {i["scope"] for i in data["ignored"]} == {"expect", "page_type", "page"}

    # An entity check that cannot apply (this brand has no Wikidata item) stops counting against the brand.
    ignore(client, client_a, admin_user, "check", "wikidata", "Linked to its Wikidata item")
    checks = {c["key"]: c for c in get(client, client_a, admin_user).json()["data"]["entity"]["checks"]}
    assert checks["wikidata"]["status"] == "ignored" and checks["wikidata"]["fix"] is None and checks["same_as"]["status"] == "fail"

    # Restoring brings it back.
    for i in get(client, client_a, admin_user).json()["data"]["ignored"]:
        assert client.delete(f"/v2/schema/ignores/{i['id']}", headers=client_header(client_a.id, admin_user.email)).status_code == 200
    restored = get(client, client_a, admin_user).json()["data"]
    assert restored["ignored"] == [] and {t["page_type"]: t for t in restored["types"]}["homepage"]["affected"] == 1
    assert ignore(client, client_a, admin_user, "bogus", "x").status_code == 422


def test_a_recurring_cleanup_can_be_ignored_everywhere(client, db, client_a, admin_user):
    seed(db, client_a)
    first = get(client, client_a, admin_user).json()["data"]
    cleanup = next(t for t in next(x for x in first["types"] if x["page_type"] == "product")["items"] if "cleanup" in t["text"])
    assert cleanup["url"] == BASE + "/products/b"
    detail = "Google's Product snippet result needs 'review|aggregateRating|offers' on Product"
    ignore(client, client_a, admin_user, "cleanup", detail)
    after = get(client, client_a, admin_user).json()["data"]
    assert after["cleanups"] == first["cleanups"] - 1
    assert BASE + "/products/b" not in [i["url"] for i in next(x for x in after["types"] if x["page_type"] == "product")["items"] if "cleanup" in i["text"]]


def test_only_the_brands_own_organization_is_judged_and_other_organizations_are_listed_apart(client, db, client_a, admin_user):
    """A page that names a client, a partner or a publisher is not the brand under another name, and their profiles are not the brand's."""
    client_a.domain, brand = "shop.example", client_a.client_name
    db.commit()
    seed(db, client_a)
    ld(db, client_a, "/", {"@context": "https://schema.org", "@type": "Organization", "name": brand, "url": BASE, "sameAs": ["https://www.facebook.com/shop"], "logo": "https://shop.example/l.png", "telephone": "555"})
    ld(db, client_a, "/blogs/news/post", {"@context": "https://schema.org", "@type": "Article", "headline": "H", "about": {"@type": "Organization", "name": "OpenAI", "url": "https://openai.com", "sameAs": ["https://openai.com/about"]}})
    db.commit()
    entity = get(client, client_a, admin_user).json()["data"]["entity"]
    checks = {c["key"]: c for c in entity["checks"]}
    assert checks["names"]["status"] == "pass", "OpenAI is another organization, not a second name for the brand"
    assert [r["label"] for r in checks["names"]["items"] if r["kind"] == "found"] == [brand]
    assert any(r["label"] == "Another organization: OpenAI" for r in checks["names"]["items"])
    assert entity["same_as"] == ["https://www.facebook.com/shop"], "the other organization's profile is not the brand's"
    assert checks["same_as"]["items"][0]["pages"] == [BASE + "/"], "each link says which pages carry it"
    assert checks["logo"]["items"][0]["label"].startswith("logo: https://shop.example/l.png")


def test_a_brand_named_two_ways_lists_each_name_with_its_pages(client, db, client_a, admin_user):
    client_a.domain, brand = "shop.example", client_a.client_name
    db.commit()
    seed(db, client_a)
    ld(db, client_a, "/", {"@context": "https://schema.org", "@type": "Organization", "name": brand, "url": BASE})
    ld(db, client_a, "/products/a", {"@context": "https://schema.org", "@type": "Organization", "name": "Shop Ex.", "url": BASE})
    db.commit()
    names = next(c for c in get(client, client_a, admin_user).json()["data"]["entity"]["checks"] if c["key"] == "names")
    assert names["status"] == "fail"
    assert {r["label"]: r["pages"] for r in names["items"] if r["kind"] == "found"} == {brand: [BASE + "/"], "Shop Ex.": [BASE + "/products/a"]}
