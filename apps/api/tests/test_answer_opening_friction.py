"""Answer injection (A-1), page-opening rewrite (P-1) and friction removal (F-1): when each fires and what it quotes."""

from __future__ import annotations

from datetime import datetime, timezone

from app.decisions.provisional import suggest, suggest_leads
from app.ingestion.crawler.parse import parse_page
from app.models.llm_visibility import LlmResponse, LlmRun
from app.models.watchlist import WatchlistBucket, WatchlistKeyword
from app.services import llm_evidence
from app.services import page_diagnostic as pd

URL = "https://shop.example/products/spf-30"
NOUN = {"singular": "order", "plural": "orders"}
SITE = {"median_engagement_rate": 70.0, "median_conversion_rate": 4.0}
WEAK = {"conversion_rate": 1.0, "engagement_rate": 30.0, "conversions": 3, "sessions": 300}


def page(body="", head_extra="", footer=""):
    html = (
        f"<html><head><title>SPF 30</title>{head_extra}</head><body><h1>SPF 30 Mineral Sunscreen</h1>"
        f"<h2>About</h2><p>Our story begins in 1998 with a small kitchen.</p>{body}<footer>{footer}</footer></body></html>"
    )
    return parse_page(url=URL, body=html, headers={})


# ── parser signals ───────────────────────────────────────────────────────────


def test_the_longest_content_form_is_counted_and_search_and_footer_forms_are_not():
    long_form = "<form>" + "".join(f"<input type='text' name='f{i}'>" for i in range(7)) + "<input type='submit'></form>"
    search = "<form role='search'><input type='search'><input type='text'></form>"
    in_footer = "<form>" + "".join(f"<input type='text' name='n{i}'>" for i in range(9)) + "</form>"
    assert page(body=long_form + search, footer=in_footer).form_fields == 7


def test_contact_links_only_in_the_footer_are_noticed():
    assert page(footer="<a href='tel:5551234'>Call</a>").contact_only_in_footer is True
    assert page(body="<a href='mailto:a@b.co'>Mail</a>", footer="<a href='tel:5551234'>Call</a>").contact_only_in_footer is False
    assert page().contact_only_in_footer is False


# ── A-1 answer injection ─────────────────────────────────────────────────────

ROW = {"position": 2.0, "impressions": 50, "clicks": 5}


def run(parsed, llm, row=ROW):
    facts = pd.facts_from(URL, parsed)
    return suggest(search="mineral sunscreen", url=URL, row=row, parsed=parsed, facts=facts, evidence={"page_queries": [], "competing_pages": 1, "donors": [], "llm": llm})


LLM = {
    "ok": True, "run_date": "2026-10-30", "prompt": "Which mineral sunscreen is gentle for a toddler?", "keyword": "mineral sunscreen",
    "platforms": [{"platform": "ChatGPT", "cited": False, "mentioned": False}, {"platform": "Perplexity", "cited": True, "mentioned": True}],
    "named": ["Blue Lizard", "Aveeno"],
}


def test_answer_injection_quotes_the_prompt_the_platforms_and_the_current_opening_and_writes_no_copy():
    a1 = next(s for s in run(page(), LLM)["suggestions"] if s["id"] == "A-1")
    assert "ChatGPT answered" in a1["why"] and "(Perplexity did cite it)" in a1["why"] and "Blue Lizard, Aveeno" in a1["why"]
    text = " ".join(a1["steps"])
    assert "Which mineral sunscreen is gentle for a toddler?" in text
    assert "Main heading: “SPF 30 Mineral Sunscreen”" in text and "Our story begins in 1998" in text
    assert a1["confidence"] == "unconfirmed" and a1["needs_to_confirm"]


def test_answer_injection_says_why_it_stays_quiet():
    cited = {**LLM, "platforms": [{"platform": "ChatGPT", "cited": True, "mentioned": True}]}
    out = run(page(), cited)
    assert "A-1" not in [s["id"] for s in out["suggestions"]]
    assert "cited this site" in next(k for k in out["skipped"] if k["id"] == "A-1")["reason"]
    none = run(page(), {"ok": False, "reason": "No LLM visibility run has been done for this client yet."})
    assert "No LLM visibility run" in next(k for k in none["skipped"] if k["id"] == "A-1")["reason"]


def _watch_and_run(db, client_a, prompt_in_run=True):
    b = WatchlistBucket(client_id=client_a.id, name="Sunscreen", name_key="sunscreen", sort_order=0)
    db.add(b)
    db.flush()
    db.add(WatchlistKeyword(client_id=client_a.id, bucket_id=b.id, keyword="mineral sunscreen", keyword_key="mineral sunscreen", paired_ai_prompt="Best mineral sunscreen?"))
    db.add(WatchlistKeyword(client_id=client_a.id, bucket_id=b.id, keyword="sunscreen", keyword_key="sunscreen", paired_ai_prompt="Best sunscreen?"))
    run_ = LlmRun(client_id=client_a.id, status="completed", started_at=datetime(2026, 10, 30, tzinfo=timezone.utc), platforms=["openai"])
    db.add(run_)
    db.flush()
    if prompt_in_run:
        db.add(LlmResponse(run_id=run_.id, client_id=client_a.id, query_text="Best mineral sunscreen?", platform="ChatGPT", visibility_type="Not visible",
                           brand_mentioned=False, url_cited=False, competitors_mentioned=["Badger"], other_brands_mentioned=["EltaMD"]))
    db.commit()


def test_the_evidence_picks_the_longest_matching_keyword_and_reads_the_latest_run(db, client_a):
    _watch_and_run(db, client_a)
    got = llm_evidence.for_search(db, client_a, "best mineral sunscreen for kids")
    assert got["ok"] and got["prompt"] == "Best mineral sunscreen?" and got["keyword"] == "mineral sunscreen"
    assert got["platforms"] == [{"platform": "ChatGPT", "cited": False, "mentioned": False}] and got["named"] == ["Badger", "EltaMD"]


def test_the_evidence_says_what_is_missing(db, client_a):
    assert "No watchlist keyword" in llm_evidence.for_search(db, client_a, "mineral sunscreen")["reason"]
    _watch_and_run(db, client_a, prompt_in_run=False)
    assert "did not ask" in llm_evidence.for_search(db, client_a, "mineral sunscreen")["reason"]
    assert "No watchlist keyword" in llm_evidence.for_search(db, client_a, "tanning oil")["reason"]


# ── P-1 page-opening rewrite ─────────────────────────────────────────────────


def test_a_first_page_ranking_with_weak_click_through_gets_an_opening_rewrite_and_a_top_three_page_gets_the_snippet_rule():
    weak = {"position": 6.0, "impressions": 400, "clicks": 1}  # 0.25% against 0.73% expected at position 6
    ids = [s["id"] for s in run(page(), {"ok": False, "reason": "x"}, row=weak)["suggestions"]]
    assert "P-1" in ids and "S-5" not in ids
    top = {"position": 2.0, "impressions": 400, "clicks": 6}
    ids = [s["id"] for s in run(page(), {"ok": False, "reason": "x"}, row=top)["suggestions"]]
    assert "S-5" in ids and "P-1" not in ids
    healthy = {"position": 6.0, "impressions": 400, "clicks": 8}
    assert "P-1" not in [s["id"] for s in run(page(), {"ok": False, "reason": "x"}, row=healthy)["suggestions"]]


def test_a_leads_page_with_weak_engagement_gets_the_opening_rewrite_quoting_its_opening():
    found = suggest_leads(row=WEAK, site=SITE, path={"declared": 0, "crawl": True, "linked_to": []}, parsed=page(), noun=NOUN)
    p1 = next(s for s in found["suggestions"] if s["id"] == "P-1")
    assert "30.0% against a site median of 70.0%" in p1["why"] and "Our story begins in 1998" in " ".join(p1["steps"])


# ── F-1 friction removal ─────────────────────────────────────────────────────


def test_friction_lists_only_what_the_page_read_found():
    long_form = "<form>" + "".join(f"<input type='text' name='f{i}'>" for i in range(8)) + "</form>"
    parsed = page(body=long_form, footer="<a href='tel:555'>Call</a>")
    found = suggest_leads(row=WEAK, site=SITE, path={"declared": 2, "crawl": True, "linked_to": []}, parsed=parsed, noun=NOUN)
    f1 = next(s for s in found["suggestions"] if s["id"] == "F-1")
    text = " ".join(f1["steps"])
    assert "asks for 8 fields" in text and "only phone number or email link is in the footer" in text
    assert "does not link in its content to any of the 2 declared conversion pages" in text
    assert "no form, phone or email" not in text  # it has a form


def test_a_page_with_a_clear_way_forward_reports_no_friction():
    parsed = page(body="<a href='/cart'>Buy now</a>")
    found = suggest_leads(row=WEAK, site=SITE, path={"declared": 2, "crawl": True, "linked_to": ["https://shop.example/cart"]}, parsed=parsed, noun=NOUN)
    assert "F-1" not in [s["id"] for s in found["suggestions"]]
    assert "none of the known frictions" in next(k for k in found["skipped"] if k["id"] == "F-1")["reason"]


def test_a_page_above_the_conversion_median_is_not_checked_for_friction():
    strong = {"conversion_rate": 6.0, "engagement_rate": 80.0, "conversions": 18, "sessions": 300}
    found = suggest_leads(row=strong, site=SITE, path={"declared": 0, "crawl": False, "linked_to": []}, parsed=page(), noun=NOUN)
    assert [s["id"] for s in found["suggestions"]] == []
