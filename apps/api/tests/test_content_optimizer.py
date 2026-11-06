"""The content optimizer: what it reads from a page, and what it keeps of what the model returns."""

from __future__ import annotations

import json

from app.services import content_optimizer as co

PAGE = """<html><body><nav>menu</nav><h1>Slab leak detection</h1>
<p>We find leaks under your slab with electronic listening gear and thermal imaging, without breaking floors first.</p>
<p>Our crews are licensed and insured and cover the whole metro area every day of the week.</p>
<h2>How it works</h2><p>A tech walks the house and listens at each fixture.</p></body></html>"""
FAQ_PAGE = PAGE.replace("</body>", "<h2>Frequently asked questions</h2><h3>Does it damage floors?</h3><p>No.</p><h3>How long does it take?</h3><p>Hours.</p></body>")


def test_the_spot_is_the_heading_the_opening_and_whether_an_faq_exists():
    spot = co.read_spot(PAGE)
    assert spot["h1"] == "Slab leak detection" and spot["opening"].startswith("We find leaks under your slab") and "menu" not in spot["opening"]
    assert spot["has_faq"] is False
    faq = co.read_spot(FAQ_PAGE)
    assert faq["has_faq"] is True and faq["faq_questions"] == ["Does it damage floors?", "How long does it take?"]


def test_terms_the_page_does_not_say_are_the_ones_to_work_in():
    detail = {"searches": [{"query": "slab leak detection"}, {"query": "leak under foundation"}]}
    assert co.missing_terms(detail, "Slab leak detection by licensed crews") == ["leak under foundation"]


def test_an_edit_is_kept_only_if_its_sentence_is_on_the_page():
    spot, text = co.read_spot(PAGE), "A tech walks the house and listens at each fixture. Other words."
    parsed = {"edits": [
        {"before": "A tech walks the house and listens at each fixture.", "after": "A tech walks the house and listens at each fixture to find a leak under the foundation.", "terms": ["leak under foundation"]},
        {"before": "A sentence the page never had.", "after": "Whatever."},
    ], "left_out": ["x: no place"]}
    out = co.clean("terms", parsed, spot=spot, text=text)
    assert [e["before"] for e in out["edits"]] == ["A tech walks the house and listens at each fixture."] and out["left_out"] == ["x: no place"]


def test_an_opening_the_same_as_now_is_not_an_option():
    spot = co.read_spot(PAGE)
    out = co.clean("opening", {"diagnosis": "d", "options": [{"text": spot["opening"]}, {"text": "New opening.", "serves": ["a"], "why": "w"}]}, spot=spot, text="")
    assert [o["text"] for o in out["options"]] == ["New opening."] and out["before"] == spot["opening"]


def test_the_faq_markup_is_built_from_the_same_questions_and_answers():
    out = co.clean("faq", {"items": [{"question": "Does it damage floors", "answer": "No, we listen first.", "from_search": "slab leak"}, {"question": "", "answer": "x"}]}, spot=co.read_spot(PAGE), text="")
    assert [i["question"] for i in out["items"]] == ["Does it damage floors?"]
    marked = json.loads(out["markup"])
    assert marked["@type"] == "FAQPage" and marked["mainEntity"][0]["name"] == "Does it damage floors?" and marked["mainEntity"][0]["acceptedAnswer"]["text"] == "No, we listen first."


def test_the_prompt_for_a_page_with_an_faq_asks_only_for_new_questions():
    spot = co.read_spot(FAQ_PAGE)
    prompt = co.build_prompt("faq", url="https://x.example/a", brand="X", detail={"title": "T", "searches": []}, spot=spot, text="t", start="2026-08-01", end="2026-11-01", terms=[])
    assert "already has an FAQ" in prompt and "Does it damage floors?" in prompt
