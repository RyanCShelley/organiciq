"""Phase 3 tests: Dedicated Page-Type Checklists & Plain Diagnose Screens (intent, page_type, fit)."""

from __future__ import annotations

from datetime import date

import pytest

from app.decisions import action_context as ac
from app.decisions import serp_intent
from app.decisions.checklists import CHECKLIST_PAGE_TYPES, checklist_for
from app.decisions.provisional import suggest as provisional_suggest
from app.ingestion.crawler.parse import parse_page
from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSnapshot
from app.models.gsc import FactGscQueryPage
from app.models.seranking import FactSerpFeature
from app.services import growth_action as ga
from app.services import page_diagnostic as pd
from tests.conftest import client_header
from tests.test_growth_action import PROD, SEP, crawled, gsc, reading, sug
from tests.test_growth_action_context import read


# ── Area 2: Dedicated Page-Type Checklists ───────────────────────────────────


def test_checklist_for_covers_four_page_types_and_returns_empty_for_others():
    assert CHECKLIST_PAGE_TYPES == frozenset({"service", "location", "category", "homepage"})

    required_keys = {"id", "title", "why", "steps", "action_type", "benefit", "status", "category"}
    seen_id_sets = {}
    for ptype in ("service", "location", "category", "homepage"):
        items = checklist_for(ptype)
        assert len(items) == 6
        for item in items:
            assert required_keys.issubset(item.keys())
            assert item["status"] in ("needed", "check", "done")
            assert isinstance(item["steps"], list) and len(item["steps"]) >= 1
        seen_id_sets[ptype] = {item["id"] for item in items}

    # All four checklists are distinct
    all_ids = [id_ for ids_set in seen_id_sets.values() for id_ in ids_set]
    assert len(all_ids) == 24

    for other in ("article", "product", "resource", "about", "contact", "utility", "unknown", ""):
        assert checklist_for(other) == []


def test_service_checklist_crawl_fact_awareness_and_focus_order():
    satisfied_facts = {
        "h1": "Commercial Roof Repair",
        "title": "Commercial Roof Repair | Acme",
        "description": "Fast commercial roof leak repairs across Dallas.",
        "word_count": 480,
        "schema_types": ["Service", "AggregateRating"],
        "has_faq": True,
        "conversion_elements": 3,
        "contact_only_in_footer": False,
        "sections": [{"heading": "Our Process", "has_list": True}],
    }
    svc_done = {c["id"]: c for c in checklist_for("service", satisfied_facts)}
    assert svc_done["CHK-SVC-2"]["status"] == "done"
    assert svc_done["CHK-SVC-3"]["status"] == "done"
    assert svc_done["CHK-SVC-4"]["status"] == "done"
    assert svc_done["CHK-SVC-5"]["status"] == "done"
    assert svc_done["CHK-SVC-6"]["status"] == "done"
    assert svc_done["CHK-SVC-1"]["status"] == "check"

    missing_facts = {
        "h1": "",
        "word_count": 80,
        "schema_types": [],
        "has_faq": False,
        "conversion_elements": 1,
        "contact_only_in_footer": True,
        "sections": [{"heading": "Overview"}],
    }
    svc_missing = {c["id"]: c for c in checklist_for("service", missing_facts)}
    assert svc_missing["CHK-SVC-1"]["status"] == "needed"
    assert svc_missing["CHK-SVC-2"]["status"] == "needed"
    assert svc_missing["CHK-SVC-3"]["status"] == "needed"
    assert svc_missing["CHK-SVC-5"]["status"] == "needed"
    assert svc_missing["CHK-SVC-6"]["status"] == "needed"

    # Focus sorting: leads puts conversion first; needed comes before check/done within category
    leads_ordered = checklist_for("service", missing_facts, focus="leads")
    assert leads_ordered[0]["category"] == "conversion"
    assert leads_ordered[0]["id"] == "CHK-SVC-2"  # needed beats check (CHK-SVC-4)


def test_location_category_and_homepage_checklists_reflect_crawl_facts_and_parsed_page():
    # Location: LocalBusiness subtype + reviews + CTA + meta
    loc_done = {
        c["id"]: c["status"]
        for c in checklist_for(
            "location",
            {
                "title": "Austin Plumber | Acme",
                "description": "Licensed plumbers in Austin.",
                "word_count": 320,
                "schema_types": ["Plumber", "Review"],
                "conversion_elements": 2,
                "contact_only_in_footer": False,
                "sections": [{"heading": "Services Offered", "has_list": True}, {"heading": "Hours & Directions"}],
            },
        )
    }
    assert loc_done["CHK-LOC-2"] == "done"
    assert loc_done["CHK-LOC-3"] == "done"
    assert loc_done["CHK-LOC-5"] == "done"

    loc_needed = {
        c["id"]: c["status"]
        for c in checklist_for(
            "location",
            {"title": "", "description": "", "word_count": 50, "schema_types": [], "conversion_elements": 0, "contact_only_in_footer": True, "sections": []},
        )
    }
    assert loc_needed["CHK-LOC-1"] == "needed"
    assert loc_needed["CHK-LOC-2"] == "needed"
    assert loc_needed["CHK-LOC-3"] == "needed"
    assert loc_needed["CHK-LOC-4"] == "needed"
    assert loc_needed["CHK-LOC-6"] == "needed"

    # Category: CollectionPage / comparison table vs missing H1/meta
    cat_done = {
        c["id"]: c["status"]
        for c in checklist_for(
            "category",
            {
                "h1": "Mineral Sunscreens",
                "title": "Mineral Sunscreens | Shop",
                "description": "Shop mineral sunscreens.",
                "schema_types": ["CollectionPage"],
                "sections": [{"heading": "How to compare", "has_table": True}],
            },
        )
    }
    assert cat_done["CHK-CAT-3"] == "done"
    assert cat_done["CHK-CAT-5"] == "done"

    cat_needed = {
        c["id"]: c["status"]
        for c in checklist_for("category", {"h1": "", "title": "", "description": "", "schema_types": [], "sections": []})
    }
    assert cat_needed["CHK-CAT-1"] == "needed"
    assert cat_needed["CHK-CAT-3"] == "needed"
    assert cat_needed["CHK-CAT-5"] == "needed"
    assert cat_needed["CHK-CAT-6"] == "needed"

    # Homepage: accepts ParsedPage directly as well as dict
    home_html = (
        "<html><head><title>Acme Co</title><meta name='description' content='Trusted roofing.'></head>"
        "<body><h1>Acme Roofing</h1><a href='tel:5551234567'>Call us</a>"
        "<h2>Our Services</h2><p>Roof repair and replacement.</p>"
        "<h2>Trusted Reviews</h2><p>Five star rated.</p>"
        '<script type="application/ld+json">{"@context":"https://schema.org","@type":"Organization","name":"Acme"}</script>'
        "</body></html>"
    )
    parsed_home = parse_page(url="https://acme.example/", body=home_html, headers={})
    home_done = {c["id"]: c["status"] for c in checklist_for("homepage", parsed_home)}
    assert home_done["CHK-HOME-2"] == "done"
    assert home_done["CHK-HOME-4"] == "done"
    assert home_done["CHK-HOME-5"] == "done"


def test_growth_action_build_surfaces_checklist_for_eligible_page_types_and_clears_when_stopped(db, client_a):
    svc_url = "https://shop.example/services/skin-consult"
    gsc(db, client_a, "skin consultation", svc_url, 700, clicks=12, position=5.0)
    crawled(db, client_a, svc_url, "Skin Consultation Service")
    db.commit()

    out = ga.build(
        db,
        client_a,
        SEP,
        "skin consultation",
        page=svc_url,
        focus="leads",
        diagnose=read([sug("S-5")], facts={"h1": "Skin Consultation", "title": "Skin Consultation", "schema_types": ["Service"], "conversion_elements": 0}),
        evidence_for=lambda s, u: {},
        signals_for=lambda s: {"reading": reading("transactional")},
    )
    assert out["ok"] is True
    assert len(out["checklist"]) == 6
    assert out["context"]["checklist"] == out["checklist"]
    assert out["checklist"][0]["category"] == "conversion"
    assert {c["id"]: c["status"] for c in out["checklist"]}["CHK-SVC-5"] == "done"

    stopped = ga.build(
        db,
        client_a,
        SEP,
        "skin consultation",
        page=svc_url,
        diagnose=read(outcome="denied", blocked="HTTP 403"),
        evidence_for=lambda s, u: {},
        signals_for=lambda s: {"reading": reading("transactional")},
    )
    assert stopped["checklist"] == []


# ── Area 3: Plain Diagnose Screens (intent, page_type, fit cleanly applied) ──


def _parsed_and_facts(url: str, html: str):
    parsed = parse_page(url=url, body=html, headers={})
    facts = pd.facts_from(url, parsed)
    return parsed, facts


def test_provisional_suggest_gates_by_intent_page_type_and_fit():
    svc_url = "https://shop.example/services/roof-repair"
    svc_html = (
        "<html><head><title>Roof Repair</title><meta name='description' content='Licensed roof repair.'></head>"
        "<body><h1>Roof Repair</h1><h2>Overview</h2><p>We fix roofs fast.</p></body></html>"
    )
    parsed_svc, facts_svc = _parsed_and_facts(svc_url, svc_html)
    base_ev = {
        "llm": {"ok": True, "run_date": "2026-10-01", "prompt": "How to fix a roof leak?", "keyword": "roof leak", "platforms": [{"platform": "ChatGPT", "cited": False}], "named": ["Rival"]},
        "page_queries": [
            {"query": "how to fix a roof leak fast", "impressions": 200, "position": 6.0},
            {"query": "how do I patch a roof leak?", "impressions": 150, "position": 7.0},
        ],
        "competing_pages": 1,
        "donors": [{"url": "https://shop.example/blog/roofing", "query": "roof leak", "impressions": 100}],
    }
    row = {"position": 7.0, "impressions": 800, "clicks": 3}

    # 1. Low-fit (informational query on service page) suppresses A-1, P-1, S-1, S-3, S-2 into skipped, keeps MC-1 & S-4
    low_fit_res = provisional_suggest(
        search="how to fix roof leak",
        url=svc_url,
        row=row,
        parsed=parsed_svc,
        facts=facts_svc,
        evidence=base_ev,
        intent=reading("informational"),
        page_type={"type": ac.SERVICE, "name": "Service page"},
        fit={"level": ac.LOW, "why": "0 of 8 results are selling pages."},
        serp_questions=["Can I patch a roof in the rain?"],
    )
    assert {s["id"] for s in low_fit_res["suggestions"]} == {"MC-1", "S-4"}
    skipped_low = {s["id"]: s["reason"] for s in low_fit_res["skipped"]}
    assert {"A-1", "P-1", "S-1", "S-3", "S-2"}.issubset(skipped_low.keys())
    assert all(skipped_low[k].startswith("Not recommended here:") for k in ("A-1", "P-1", "S-1", "S-3", "S-2"))

    # 2. High-fit transactional query on service page suppresses A-1 and P-1, keeps S-1/S-3/S-2/MC-1/S-4
    tx_res = provisional_suggest(
        search="roof repair service",
        url=svc_url,
        row=row,
        parsed=parsed_svc,
        facts=facts_svc,
        evidence={
            **base_ev,
            "page_queries": [
                {"query": "roof repair service near me", "impressions": 200, "position": 6.0},
                {"query": "how much does roof repair service cost?", "impressions": 150, "position": 7.0},
            ],
        },
        intent=reading("transactional"),
        page_type={"type": ac.SERVICE, "name": "Service page"},
        fit={"level": ac.HIGH, "why": "7 of 8 results are service pages."},
    )
    tx_ids = {s["id"] for s in tx_res["suggestions"]}
    assert "A-1" not in tx_ids and "P-1" not in tx_ids
    assert {"S-1", "MC-1", "S-3", "S-2", "S-4"}.issubset(tx_ids)
    assert {s["id"] for s in tx_res["skipped"]} >= {"A-1", "P-1"}

    # 3. Product/category page suppresses A-1 even on commercial SERP ("opens with what is for sale")
    cat_res = provisional_suggest(
        search="best mineral sunscreen",
        url="https://shop.example/collections/mineral-sunscreen",
        row=row,
        parsed=parsed_svc,
        facts=facts_svc,
        evidence=base_ev,
        intent=reading("commercial"),
        page_type={"type": ac.CATEGORY, "name": "Category or collection page"},
        fit={"level": ac.HIGH, "why": "Commercial query matches collection page."},
    )
    assert "A-1" not in {s["id"] for s in cat_res["suggestions"]}
    assert "opens with what is for sale" in next(s["reason"] for s in cat_res["skipped"] if s["id"] == "A-1")

    # 4. Matching informational SERP on an article page keeps A-1, P-1, S-1, S-2, S-3 cleanly
    blog_url = "https://shop.example/blog/how-to-fix-roof-leak"
    parsed_blog, facts_blog = _parsed_and_facts(blog_url, svc_html)
    info_res = provisional_suggest(
        search="how to fix roof leak",
        url=blog_url,
        row=row,
        parsed=parsed_blog,
        facts=facts_blog,
        evidence=base_ev,
        intent=reading("informational"),
        page_type={"type": ac.ARTICLE, "name": "Blog or article"},
        fit={"level": ac.HIGH, "why": "8 of 8 results are articles."},
        serp_questions=["Can I patch a roof in the rain?"],
    )
    info_ids = {s["id"] for s in info_res["suggestions"]}
    assert {"A-1", "P-1", "S-1", "S-2", "S-3", "MC-1", "S-4"}.issubset(info_ids)


def test_plain_diagnose_and_diagnose_page_endpoints_return_context_checklist_history_and_template(
    client, db, client_a, admin_user, monkeypatch
):
    domain = client_a.domain
    cat_url = f"https://{domain}/collections/spf"
    for i in range(5):
        db.add(
            FactCrawlPageSnapshot(
                client_id=client_a.id,
                source=CRAWL_SOURCE_FIRST_PARTY,
                snapshot_date=date(2026, 8, 25),
                raw_url=f"https://{domain}/collections/col-{i}",
                normalized_url=f"https://{domain}/collections/col-{i}",
                indexable=True,
                title=f"Collection {i}",
            )
        )
    db.add(
        FactCrawlPageSnapshot(
            client_id=client_a.id,
            source=CRAWL_SOURCE_FIRST_PARTY,
            snapshot_date=date(2026, 8, 25),
            raw_url=cat_url,
            normalized_url=cat_url,
            indexable=True,
            title="SPF Collection",
        )
    )
    db.add(
        FactGscQueryPage(
            client_id=client_a.id,
            date=date(2026, 8, 10),
            query="mineral sunscreen collection",
            raw_url=cat_url,
            normalized_url=cat_url,
            country="usa",
            device="DESKTOP",
            impressions=900,
            clicks=1,
            ctr=0,
            average_position=7.5,
        )
    )
    db.add(
        FactSerpFeature(
            client_id=client_a.id,
            pulled_on=date.today(),
            keyword="mineral sunscreen collection",
            item_types=["organic", "people_also_ask"],
            holders={},
            results=[{"rank": 1, "url": "https://r.example/c", "domain": "r.example", "title": "Collection", "snippet": "..."}],
            questions=["What SPF is best for daily wear?"],
            reading=reading("commercial"),
        )
    )
    db.commit()

    html = (
        "<html><head><title>SPF Collection</title><meta name='description' content='Mineral SPF range.'>"
        '<script type="application/ld+json">{"@context":"https://schema.org","@type":"CollectionPage"}</script>'
        "</head><body><h1>Mineral Sunscreens</h1><p>Browse our reef-safe mineral SPF products.</p></body></html>"
    )

    async def fetch(u):
        return pd.Fetched(200, u, {}, html)

    monkeypatch.setattr(pd, "_fetch", fetch)
    h = client_header(client_a.id, admin_user.email)

    diag = client.post(
        "/v2/engine/diagnose",
        json={"month": "2026-09", "focus": "traffic", "selections": [{"search": "mineral sunscreen collection", "page": cat_url}]},
        headers=h,
    )
    assert diag.status_code == 200, diag.text
    res0 = diag.json()["results"][0]
    ctx = res0["context"]
    assert ctx["page_type"]["type"] == "category"
    assert ctx["intent"]["intent"] == "commercial"
    assert ctx["fit"]["level"] in ("high", "medium")
    assert ctx["template"]["shared"] is True and ctx["template"]["peers"] == 5
    assert len(ctx["checklist"]) == 6
    assert {c["id"]: c["status"] for c in ctx["checklist"]}["CHK-CAT-3"] == "done"
    assert res0["page_history"]["page"] == cat_url
    assert res0["page_facts"]["schema_types"] == ["CollectionPage"]

    # diagnose-page with focus="traffic"
    dp_traffic = client.post(
        "/v2/engine/diagnose-page",
        json={"month": "2026-09", "focus": "traffic", "pages": [cat_url]},
        headers=h,
    )
    assert dp_traffic.status_code == 200
    dpt0 = dp_traffic.json()["results"][0]
    assert dpt0["focus"] == "traffic"
    assert dpt0["context"]["page_type"]["type"] == "category"
    assert dpt0["context"]["intent"]["intent"] == "commercial"
    assert len(dpt0["context"]["checklist"]) == 6
    assert {c["id"]: c["status"] for c in dpt0["context"]["checklist"]}["CHK-CAT-3"] == "done"
    assert dpt0["context"]["checklist"][0]["category"] == "ctr"
    assert "MC-1" in [s["id"] for s in dpt0["suggestions"]]


# ── Iteration 2 Regression Tests ─────────────────────────────────────────────


def test_diagnose_and_diagnose_page_checklist_parity_with_has_stat_across_all_four_page_types():
    async def _make_fetch(html: str):
        async def _f(u: str) -> pd.Fetched:
            return pd.Fetched(200, u, {}, html)

        return _f

    cases = [
        (
            "service",
            "https://shop.example/services/roof-repair",
            "roof repair service",
            (
                "<html><head><title>Roof Repair | Acme</title><meta name='description' content='Fast roof repair.'>"
                '<script type="application/ld+json">{"@context":"https://schema.org","@type":"Service"}</script></head>'
                "<body><h1>Roof Repair Service</h1><a href='tel:5551234567'>Call Now</a>"
                "<p>We fix residential and commercial roof leaks with certified technicians and clear warranties for every project we take on across the metro region.</p>"
                "<h2>Key Numbers</h2><p>We resolve 98% of roof leaks in a single visit across 1,200 homes each year.</p>"
                "</body></html>"
            ),
            "CHK-SVC-3",
            "done",
        ),
        (
            "location",
            "https://shop.example/locations/austin",
            "austin plumber",
            (
                "<html><head><title>Austin Plumber | Acme</title><meta name='description' content='Plumbing in Austin.'>"
                '<script type="application/ld+json">{"@context":"https://schema.org","@type":"Plumber"}</script></head>'
                "<body><h1>Austin Plumbing</h1><a href='tel:5551234567'>Call Austin</a>"
                "<p>Licensed plumbers serving Austin neighborhoods with fast emergency response and transparent flat-rate estimates for residential and commercial properties.</p>"
                "<h2>Local Metrics</h2><p>99% on-time arrival across 1,500 Austin jobs.</p>"
                "<h2>Neighborhood Coverage</h2><p>Serving North, Central, and South Austin daily.</p>"
                "</body></html>"
            ),
            "CHK-LOC-4",
            "check",
        ),
        (
            "category",
            "https://shop.example/collections/mineral-sunscreen",
            "mineral sunscreen",
            (
                "<html><head><title>Mineral Sunscreens | Shop</title><meta name='description' content='Compare SPF options.'>"
                '<script type="application/ld+json">{"@context":"https://schema.org","@type":"CollectionPage"}</script></head>'
                "<body><h1>Mineral Sunscreens</h1>"
                "<h2>Range Overview</h2><p>Formulas feature 20% non-nano zinc oxide with 95% reef-safe customer satisfaction across 1,200 verified buyers.</p>"
                "</body></html>"
            ),
            "CHK-CAT-5",
            "done",
        ),
        (
            "homepage",
            "https://shop.example/",
            "acme shop",
            (
                "<html><head><title>Acme Shop | Mineral Care</title><meta name='description' content='Mineral skincare.'>"
                '<script type="application/ld+json">{"@context":"https://schema.org","@type":"Organization","name":"Acme"}</script></head>'
                "<body><h1>Acme Mineral Care</h1><a href='tel:5551234567'>Contact Us</a>"
                "<p>Clean mineral skincare formulated for daily sun protection and sensitive skin types across North America.</p>"
                "<h2>Why Customers Switch</h2><p>97% of customers reorder within 60 days.</p>"
                "<h2>Core Collections</h2><p>Explore daily SPF lotions, sticks, and lip balms.</p>"
                "</body></html>"
            ),
            "CHK-HOME-3",
            "check",
        ),
    ]

    for expected_type, url, search, html, key_id, expected_status in cases:
        parsed = parse_page(url=url, body=html, headers={})
        expected_checklist = checklist_for(expected_type, parsed, focus="visibility")

        async def fetch_fn(u: str, _html: str = html) -> pd.Fetched:
            return pd.Fetched(200, u, {}, _html)

        diag = pd.diagnose(
            search=search,
            url=url,
            row={"position": 6.0, "impressions": 400, "clicks": 4},
            client_domain="shop.example",
            fetch=fetch_fn,
            evidence={"page_queries": [], "competing_pages": 1, "donors": []},
            focus="visibility",
        )
        diag_page = pd.diagnose_page(
            focus="visibility",
            url=url,
            client_domain="shop.example",
            fetch=fetch_fn,
            evidence={"search": search},
        )

        assert diag["context"]["page_type"]["type"] == expected_type
        assert diag_page["context"]["page_type"]["type"] == expected_type
        assert any(s.get("has_stat") is True for s in diag["page_facts"]["outline"]["sections"])
        assert any(s.get("has_stat") is True for s in diag_page["page_facts"]["sections"])
        assert any(s.get("has_stat") is True for s in diag_page["page_facts"]["outline"]["sections"])

        assert diag["context"]["checklist"] == expected_checklist
        assert diag_page["context"]["checklist"] == expected_checklist
        assert {c["id"]: c["status"] for c in diag_page["context"]["checklist"]}[key_id] == expected_status


def test_checklist_for_focus_is_case_insensitive_and_unknown_page_type_copy_reads_naturally(db, client_a):
    facts = {
        "h1": "Roof Repair",
        "title": "Roof Repair",
        "description": "Fast roof repair.",
        "word_count": 300,
        "schema_types": ["Service"],
        "has_faq": True,
        "conversion_elements": 0,
        "contact_only_in_footer": True,
        "sections": [{"heading": "Our Process", "has_list": True}],
    }
    assert checklist_for("service", facts, focus="Leads") == checklist_for("service", facts, focus="leads")
    assert checklist_for("service", facts, focus="Leads")[0]["category"] == "conversion"
    assert checklist_for("service", facts, focus=" TRAFFIC ") == checklist_for("service", facts, focus="traffic")

    # Unknown page type (ac.OTHER) + transactional intent should not produce "at the top of a not established"
    unknown_url = "https://shop.example/custom-landing"
    parsed = parse_page(
        url=unknown_url,
        body="<html><head><title>Custom Landing</title></head><body><h1>Custom</h1><p>Short copy.</p></body></html>",
        headers={},
    )
    sug_out = provisional_suggest(
        search="buy custom kit",
        url=unknown_url,
        row={"position": 7.0, "impressions": 500, "clicks": 3},
        parsed=parsed,
        facts=pd.facts_from(unknown_url, parsed),
        evidence={
            "llm": {"ok": True, "run_date": "2026-10-01", "prompt": "What is custom kit?", "keyword": "custom kit", "platforms": [{"platform": "ChatGPT", "cited": False}], "named": []},
            "page_queries": [],
            "competing_pages": 1,
            "donors": [],
        },
        intent=reading("transactional"),
        page_type={"type": ac.OTHER, "name": "Not established"},
        fit={"level": ac.HIGH, "why": "Match"},
    )
    a1_skip = next(s for s in sug_out["skipped"] if s["id"] == "A-1")
    assert "page whose type is not established" in a1_skip["reason"]
    assert "a not established" not in a1_skip["reason"]

    gsc(db, client_a, "buy custom kit", unknown_url, 500)
    db.commit()
    ga_out = ga.build(
        db,
        client_a,
        SEP,
        "buy custom kit",
        page=unknown_url,
        diagnose=read([sug("A-1"), sug("P-1")], facts={"h1": "Custom", "title": "Custom", "schema_types": []}),
        evidence_for=lambda s, u: {},
        signals_for=lambda s: {"reading": reading("transactional")},
    )
    assert ga_out["context"]["page_type"]["type"] == ac.OTHER
    left_out = {item["id"]: item["reason"] for item in ga_out["left_out"]}
    assert "page whose type is not established" in left_out["A-1"]
    assert "page whose type is not established" in left_out["P-1"]
    assert "a not established" not in left_out["A-1"]

