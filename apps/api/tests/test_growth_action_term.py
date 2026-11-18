"""One term, one page. The term the person selects is the term read, and the page they select is the page worked on.

Selecting “natural sunscreen for face” on the collection page used to be swapped for the watchlist keyword
“natural sunscreen” to pick a "best page" (a blog post), then swapped again for that post's top search
(“natural sunscreen zinc oxide”) to read intent. Neither was the search selected, and the page was not the page selected.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import httpx

from app.decisions import action_context as ac
from app.models.llm_visibility import LlmResponse, LlmRun
from app.services import growth_action as ga
from app.services import winners
from tests.test_growth_action import BLOG, COLL, PROD, SEP, gsc, reading, sug, watch
from tests.test_growth_action_context import ids, ranked, read

FACE, SPF30, ZINC = "natural sunscreen for face", "natural sunscreen spf 30", "natural sunscreen zinc oxide"
SPLIT = ranked("transactional", {"product page": 4, "article or blog post": 4}, secondary="informational",
               evidence=["4 of 8 organic results are product pages with price", "A popular products feature appears"])


OUTLINE = {"title": "SPF", "h1": "SPF", "word_count": 300, "sections": [], "schema_types": [], "faq_questions": 0, "conversion_elements": 3}


def site(db, client_a):
    client_a.domain = "shop.example"
    gsc(db, client_a, FACE, COLL, 135, clicks=0, position=14.2)
    gsc(db, client_a, FACE, BLOG, 20, position=40)
    gsc(db, client_a, SPF30, PROD, 160, position=9)
    gsc(db, client_a, "natural sunscreen", BLOG, 9000, position=12)
    gsc(db, client_a, ZINC, BLOG, 7000, position=6)
    watch(db, client_a)


def build(db, client_a, search, page, found=SPLIT, asked=None, **kw):
    def signals(term):
        if asked is not None:
            asked.append(term)
        return {"reading": {**found, "search": term}}
    return ga.build(db, client_a, SEP, "natural sunscreen", search=search, page=page, diagnose=read([sug("A-1"), sug("S-1"), sug("S-5")], facts={"outline": OUTLINE, "schema_types": ["CollectionPage"] if page == COLL else ["Product"] if page == PROD else ["Article"]}),
                    evidence_for=lambda s, u: {}, signals_for=signals, **kw)


def test_the_search_selected_is_the_only_search_read_and_the_page_selected_is_the_page_worked_on(db, client_a):
    site(db, client_a)
    for term, page in ((FACE, COLL), (SPF30, PROD)):
        asked: list[str] = []
        out = build(db, client_a, term, page, asked=asked)
        assert set(asked) == {term}, "no other search's results page is read: not the watchlist keyword, not the page's top search"
        assert out["ok"] and out["search"] == term and out["page"] == page and out["search_source"] == "the search you selected"
        assert out["keyword"] == "natural sunscreen", "the watchlist keyword is a label"
        d = ga.draft(out, "2026-12")
        assert d["page"] == page and "natural sunscreen zinc oxide" not in json.dumps(out)


def test_a_split_results_page_is_settled_by_what_the_searcher_is_there_to_do(db, client_a):
    """Four product pages and four articles, read as transactional: the page that sells suits; the article only partly."""
    site(db, client_a)
    coll, blog = ac.compatibility(SPLIT, ac.classify_page(COLL)), ac.compatibility(SPLIT, ac.classify_page(BLOG))
    assert coll["level"] == "high" and coll["leads"] == "selling" and blog["level"] == "medium"
    assert "level with" in blog["why"] and "transactional" in blog["why"]
    out = build(db, client_a, FACE, COLL)
    assert out["context"]["fit"]["level"] == "high" and out["context"]["mismatch"] is False
    assert out["parts"][0]["title"] == "Help the searcher find, compare and buy from the range" and out["better_page"] is None
    learn = ranked("informational", {"product page": 4, "article or blog post": 4})
    assert ac.compatibility(learn, ac.classify_page(BLOG))["level"] == "high" and ac.compatibility(learn, ac.classify_page(COLL))["level"] == "medium"


def test_advice_written_for_another_intent_is_not_borrowed(db, client_a):
    """A blog post under a transactional search was told to "help them understand the topic", from the secondary intent."""
    site(db, client_a)
    out = build(db, client_a, FACE, BLOG)
    assert "IM-1" not in ids(out["parts"]) and "understand the topic" not in json.dumps(out)
    assert out["better_page"]["url"] == COLL and out["page"] == BLOG, "the better page is named; the page worked on is still the one selected"


def test_a_reading_of_a_different_search_is_refused(db, client_a):
    site(db, client_a)
    out = ga.build(db, client_a, SEP, "natural sunscreen", search=FACE, page=COLL, diagnose=read([sug("S-1"), sug("S-5")]), evidence_for=lambda s, u: {},
                   signals_for=lambda term: {"reading": {**SPLIT, "search": ZINC}})
    intent = out["context"]["intent"]
    assert intent["read"] is False and "was for “natural sunscreen zinc oxide”, not “natural sunscreen for face”" in intent["uncertainty"]
    assert ids(out["parts"]) == ["S-5"], "nothing intent-dependent is built on someone else's results page"


def test_a_page_that_does_not_show_for_the_search_selected_is_not_worked_on_for_it(db, client_a):
    site(db, client_a)
    assert "does not show for “natural sunscreen spf 30”" in build(db, client_a, SPF30, COLL)["error"]


def test_a_page_with_no_search_selected_uses_its_top_search_and_says_so(db, client_a):
    site(db, client_a)
    out = ga.build(db, client_a, SEP, "natural sunscreen", page=BLOG, diagnose=read([sug("S-5")], facts={"schema_types": ["Article"]}), evidence_for=lambda s, u: {},
                   signals_for=lambda term: {"reading": {**reading("informational"), "search": term}})
    assert out["search"] == "natural sunscreen" and "top search" in out["search_source"] and "no search was selected" in out["search_source"]


# ── who is winning ───────────────────────────────────────────────────────────

W1, W2, W3 = "https://rival-a.example/natural-sunscreen", "https://rival-b.example/collections/mineral", "https://guide.example/best-natural-sunscreen"
WINNING = {**ranked("transactional", {"category or collection page": 6, "article or blog post": 2}), "ranked": [
    {"rank": 1, "url": W1, "domain": "rival-a.example", "title": "Natural Sunscreen", "content_type": "category or collection page", "content_style": "product listing"},
    {"rank": 2, "url": "https://shop.example/collections/spf", "domain": "shop.example", "title": "SPF", "content_type": "category or collection page", "content_style": "product listing"},
    {"rank": 3, "url": W2, "domain": "rival-b.example", "title": "Mineral", "content_type": "category or collection page", "content_style": "product listing"},
]}


def page(url, **kw):
    return {"url": url, "read": True, "title": "Natural Sunscreen", "h1": "Natural Sunscreen", "word_count": 900, "schema_types": ["ItemList", "Product"], "faq_questions": 4, "conversion_elements": 20,
            "sections": [{"heading": "Shop by SPF", "text": "SPF 30 and 50, reef-safe.", "has_table": True, "has_list": False}], **kw}


async def reader(urls):
    return [page(u) if "rival-b" not in u else {"url": u, "read": False, "reason": "Its robots.txt disallows our reader, so it was not fetched."} for u in urls]


def llm_run(db, client_a):
    run = LlmRun(client_id=client_a.id, status="completed", platforms=["chatgpt", "perplexity"], started_at=datetime(2026, 11, 1, 12, tzinfo=timezone.utc))
    db.add(run)
    db.flush()
    prompt = "Best natural sunscreen for sensitive skin?"
    db.add(LlmResponse(run_id=run.id, client_id=client_a.id, query_text=prompt, platform="chatgpt", visibility_type="Not visible", brand_mentioned=False, url_cited=False,
                       cited_urls=[W3, "https://rival-a.example/natural-sunscreen"], all_brands_ordered=["Rival A", "Badger"], total_brands=2))
    db.add(LlmResponse(run_id=run.id, client_id=client_a.id, query_text=prompt, platform="perplexity", visibility_type="Mentioned", brand_mentioned=True, url_cited=True, brand_rank=2, total_brands=3,
                       cited_urls=[W3, "https://shop.example/collections/spf"], all_brands_ordered=["Rival A", "Shop", "Badger"]))
    db.commit()


def answer(gaps):
    return lambda prompt: json.dumps({"best_page": {"verdict": "yes", "why": "Two of the three winners read are collection pages like this one."}, "gaps": gaps})


GAP = {"issue": "The page does not state SPF, size or price in its product list.", "evidence": "rival-a.example lists SPF and price beside each product in a table.",
       "seen_on": [W1], "change": "Show SPF, size and price beside each product in the list. Keep the layout.", "expected_outcome": "A shopper can compare without opening each product, and the attributes can be extracted.",
       "validation": "View the page source and confirm each product's SPF and price are in the HTML.", "serves": "both", "basis": "observed"}


def test_the_ai_platforms_winners_come_from_the_trackers_own_run(db, client_a):
    site(db, client_a)
    llm_run(db, client_a)
    found = winners.llm_winners(db, client_a, FACE)
    assert found["ok"] and found["prompt"] == "Best natural sunscreen for sensitive skin?" and found["run_date"] == "2026-11-01"
    by = {p["platform"]: p for p in found["platforms"]}
    assert by["chatgpt"]["brands"] == ["Rival A", "Badger"] and by["chatgpt"]["client_cited"] is False and by["perplexity"]["brand_rank"] == 2
    assert found["cited_pages"][0] == {"url": W3, "domain": "guide.example", "platforms": ["chatgpt", "perplexity"], "own": False, "page_type": "Not established"}
    assert found["client_cited_on"] == ["perplexity"] and any(p["own"] for p in found["cited_pages"])
    assert winners.llm_winners(db, client_a, "garden hose")["ok"] is False


def test_the_winners_pages_are_read_and_only_gaps_that_point_at_them_are_kept(db, client_a):
    site(db, client_a)
    llm_run(db, client_a)
    loose = {**GAP, "seen_on": ["https://never-shown.example/"], "issue": "Invented."}
    bare = {**GAP, "evidence": ""}
    found = winners.gather(db, client_a, search=FACE, intent=WINNING, page_url="https://shop.example/collections/spf", page_type="Category or collection page",
                           own={"title": "SPF", "sections": []}, reader=reader, ask=answer([GAP, loose, bare]))
    assert [p["url"] for p in found["search"]["pages"]] == [W1, W2], "the top ranking pages that are not this site's"
    assert found["search"]["client_ranks"][0]["rank"] == 2 and [p["url"] for p in found["llm"]["pages"]] == [W3]
    assert found["search"]["pages"][1]["read"] is False and "robots.txt" in found["search"]["pages"][1]["reason"]
    assert [g["issue"] for g in found["comparison"]["gaps"]] == [GAP["issue"]], "a gap naming a page it was not shown, or giving no evidence, is dropped"
    assert found["comparison"]["best_page"]["verdict"] == "yes"


def test_each_gap_becomes_a_part_with_its_issue_evidence_change_outcome_and_check(db, client_a):
    site(db, client_a)
    llm_run(db, client_a)
    out = build(db, client_a, FACE, COLL, found=WINNING,
                winners_for=lambda s, i, u, t, own, asked: winners.gather(db, client_a, search=s, intent=i, page_url=u, page_type=t, own=own, reader=reader, ask=answer([GAP])))
    part = next(p for p in out["parts"] if p["id"] == "W-1")
    assert part["why"] == GAP["issue"] and part["steps"][0] == GAP["change"]
    assert part["steps"][1].startswith("Expected: A shopper can compare") and part["steps"][2].startswith("Check afterwards: View the page source")
    assert part["evidence"] == ["Observed from the winning pages: " + GAP["evidence"], "Seen on: " + W1] and part["benefit"] == "SEO and AI visibility"
    assert ids(out["parts"])[0] == "IM-1" and out["context"]["winners"]["llm"]["ok"] is True


def test_with_no_winner_readable_nothing_is_compared_and_it_says_so(db, client_a):
    async def none(urls):
        return [{"url": u, "read": False, "reason": "It answered our reader with HTTP 403, and was not asked again under another name."} for u in urls]

    found = winners.gather(db, client_a, search=FACE, intent=WINNING, page_url="https://shop.example/collections/spf", page_type="Category", own={}, reader=none, ask=answer([GAP]))
    assert found["comparison"]["ok"] is False and found["comparison"]["gaps"] == [] and "could be read" in found["comparison"]["reason"]


def test_a_winner_is_read_under_our_own_name_once_and_robots_is_obeyed():
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, request.headers["user-agent"]))
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private/\n")
        if request.url.path == "/refused":
            return httpx.Response(403, text="<title>403 Forbidden</title>")
        return httpx.Response(200, text="<html><head><title>Natural Sunscreen</title></head><body><h1>Natural Sunscreen</h1><h2>Shop by SPF</h2><p>SPF 30 and 50.</p></body></html>", headers={"content-type": "text/html"})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), headers={"User-Agent": winners.USER_AGENT}) as client:
            robots: dict = {}
            return [await winners._read_one(client, f"https://rival.example{path}", robots) for path in ("/shop", "/private/x", "/refused")]

    ok, disallowed, refused = asyncio.run(go())
    assert ok["read"] and ok["title"] == "Natural Sunscreen" and ok["sections"][0]["heading"] in ("Natural Sunscreen", "Shop by SPF")
    assert disallowed["read"] is False and "robots.txt disallows" in disallowed["reason"]
    assert refused["read"] is False and "not asked again under another name" in refused["reason"]
    assert [p for p, _ in seen] == ["/robots.txt", "/shop", "/refused"] and {ua for _, ua in seen} == {winners.USER_AGENT}
