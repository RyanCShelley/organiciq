"""Unconfirmed suggestions: what each says, when it stays quiet, and that none is a prescription."""

from __future__ import annotations

from app.decisions.provisional import suggest
from app.ingestion.crawler.parse import parse_page
from app.services import page_diagnostic as pd

URL = "https://shop.example/products/spf-15-mineral-sunscreen"
ROW = {"position": 2.3, "impressions": 187, "clicks": 12, "expected_extra_clicks": 22.0}


def page(*, title="SPF 15 Mineral Sunscreen", body=""):
    html = f"<html><head><title>{title}</title><meta name='description' content='A sunscreen'></head><body><h1>SPF 15 Mineral Sunscreen</h1><h2>Ingredients</h2><p>Zinc.</p>{body}</body></html>"
    parsed = parse_page(url=URL, body=html, headers={})
    return parsed, pd.facts_from(URL, parsed)


def ids(result):
    return [s["id"] for s in result["suggestions"]]


def run(parsed, facts, evidence, row=ROW, search="spf 15 mineral sunscreen"):
    return suggest(search=search, url=URL, row=row, parsed=parsed, facts=facts, evidence=evidence)


def test_every_suggestion_is_unconfirmed_and_says_what_would_confirm_it():
    parsed, facts = page()
    evidence = {
        "page_queries": [{"query": "natural spf 15 mineral sunscreen", "impressions": 60, "clicks": 1, "position": 4.0}],
        "competing_pages": 2,
        "donors": [{"url": "https://shop.example/collections/spf", "query": "mineral sunscreen", "impressions": 900}],
    }
    out = run(parsed, facts, evidence)
    assert out["suggestions"] and all(s["confidence"] == "unconfirmed" and s["needs_to_confirm"] for s in out["suggestions"])


def test_phrasing_the_page_ranks_for_but_does_not_say_is_surfaced_without_inventing_copy():
    parsed, facts = page()
    evidence = {"page_queries": [{"query": "natural spf 15 mineral sunscreen", "impressions": 60, "clicks": 1, "position": 4.0}], "competing_pages": 1, "donors": []}
    s1 = next(s for s in run(parsed, facts, evidence)["suggestions"] if s["id"] == "S-1")
    text = " ".join(s1["steps"])
    assert "“natural spf 15 mineral sunscreen”: 60 impressions at position 4.0" in text
    assert "Today the title reads “SPF 15 Mineral Sunscreen”" in text
    assert "does not carry" in text  # the slug has no "natural"


def test_phrasing_already_in_the_title_is_not_suggested():
    parsed, facts = page(title="Natural SPF 15 Mineral Sunscreen")
    evidence = {"page_queries": [{"query": "natural spf 15 mineral sunscreen", "impressions": 60, "clicks": 1, "position": 4.0}], "competing_pages": 1, "donors": []}
    assert "S-1" not in ids(run(parsed, facts, evidence))


def test_several_pages_for_one_search_asks_for_an_owner_and_says_why_it_is_unconfirmed():
    parsed, facts = page()
    s6 = next(s for s in run(parsed, facts, {"page_queries": [], "competing_pages": 3, "donors": []})["suggestions"] if s["id"] == "S-6")
    assert "3 pages" in s6["why"] and "declared owner" in s6["needs_to_confirm"]


def test_a_top_three_page_with_weak_click_through_is_told_to_reread_its_snippet():
    parsed, facts = page()
    s5 = next(s for s in run(parsed, facts, {"page_queries": [], "competing_pages": 1, "donors": []})["suggestions"] if s["id"] == "S-5")
    assert "6.4% against" in s5["why"] and any("Title now: “SPF 15 Mineral Sunscreen”" in step for step in s5["steps"])
    healthy = {**ROW, "clicks": 40}
    assert "S-5" not in ids(run(parsed, facts, {"page_queries": [], "competing_pages": 1, "donors": []}, row=healthy))
    low = {**ROW, "position": 8.0}
    assert "S-5" not in ids(run(parsed, facts, {"page_queries": [], "competing_pages": 1, "donors": []}, row=low))


def test_a_page_with_nothing_liftable_is_told_so_and_one_with_a_list_is_not():
    parsed, facts = page()
    assert "S-3" in ids(run(parsed, facts, {"page_queries": [], "competing_pages": 1, "donors": []}))
    parsed2, facts2 = page(body="<h2>Facts</h2><ul><li>SPF 15</li><li>Zinc</li></ul>")
    assert "S-3" not in ids(run(parsed2, facts2, {"page_queries": [], "competing_pages": 1, "donors": []}))


def test_an_faq_is_suggested_only_from_questions_people_really_type():
    parsed, facts = page()
    evidence = {"page_queries": [{"query": "is zinc oxide safe on skin", "impressions": 40, "clicks": 0, "position": 8.0}, {"query": "spf 15 mineral sunscreen", "impressions": 187, "clicks": 12, "position": 2.3}], "competing_pages": 1, "donors": []}
    out = run(parsed, facts, evidence)
    s2 = next(s for s in out["suggestions"] if s["id"] == "S-2")
    assert any("is zinc oxide safe on skin" in step for step in s2["steps"])
    none = run(parsed, facts, {"page_queries": [{"query": "spf 15 mineral sunscreen", "impressions": 187, "clicks": 12, "position": 2.3}], "competing_pages": 1, "donors": []})
    assert "S-2" not in ids(none)
    assert none["skipped"][0]["id"] == "S-2" and "no question-shaped search" in none["skipped"][0]["reason"].lower()


def test_a_page_that_already_has_an_faq_is_left_to_the_markup_rule():
    parsed, facts = page(body="<h2>Frequently asked questions</h2><p>Does it stain?</p>")
    evidence = {"page_queries": [{"query": "is zinc oxide safe on skin", "impressions": 40, "clicks": 0, "position": 8.0}], "competing_pages": 1, "donors": []}
    assert "S-2" not in ids(run(parsed, facts, evidence))


def test_link_sources_are_other_pages_on_the_topic_and_the_check_is_named():
    parsed, facts = page()
    evidence = {"page_queries": [], "competing_pages": 1, "donors": [{"url": "https://shop.example/collections/spf", "query": "mineral sunscreen", "impressions": 900}]}
    s4 = next(s for s in run(parsed, facts, evidence)["suggestions"] if s["id"] == "S-4")
    assert "https://shop.example/collections/spf" in s4["steps"][0] and "link crawl" in s4["needs_to_confirm"]
    assert run(parsed, facts, {"page_queries": [], "competing_pages": 1, "donors": []})["skipped"][-1]["id"] == "S-4"


def test_the_diagnosis_carries_suggestions_apart_from_prescriptions():
    parsed_html = "<html><head><title>x</title></head><body><h1>Spf 15 mineral sunscreen</h1></body></html>"

    async def fetch(url):
        return pd.Fetched(200, url, {}, parsed_html)

    out = pd.diagnose(
        search="spf 15 mineral sunscreen", url="https://shop.example/p", row=ROW, client_domain="shop.example", fetch=fetch,
        evidence={"page_queries": [], "competing_pages": 2, "donors": []},
    )
    assert out["prescriptions"] == [] and "S-6" in [s["id"] for s in out["suggestions"]]
    without = pd.diagnose(search="x", url="https://shop.example/p", row=ROW, client_domain="shop.example", fetch=fetch)
    assert without["suggestions"] == []


def test_phrasing_that_is_a_brand_search_is_never_suggested():
    parsed, facts = page()
    evidence = {
        "page_queries": [
            {"query": "natural spf 15 mineral sunscreen", "impressions": 60, "clicks": 1, "position": 4.0},
            {"query": "shop example spf 15 mineral sunscreen", "impressions": 300, "clicks": 20, "position": 1.2},
        ],
        "competing_pages": 1, "donors": [], "brand_keys": ["shop example"],
    }
    s1 = next(s for s in run(parsed, facts, evidence)["suggestions"] if s["id"] == "S-1")
    text = " ".join(s1["steps"])
    assert "natural spf 15 mineral sunscreen" in text and "shop example" not in text.split("Today the title")[0]
