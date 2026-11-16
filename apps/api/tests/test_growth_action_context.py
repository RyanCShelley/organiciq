"""The right action for the right search on the right page, on evidence that was really seen.

Intent comes from the search's results page, read by `serp_intent`. Scenarios A to H are the regression cases from
the Growth Actions refinement brief; the rest are the intent rules: no results page means no intent-dependent advice,
and the advice changes when the results page does.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from app.decisions import action_context as ac
from app.decisions import serp_intent
from app.integrations import dataforseo
from app.models.engine_task import EngineTask
from app.models.seranking import FactSerpFeature
from app.services import growth_action as ga
from app.services import search_signals
from tests.test_growth_action import BLOG, COLL, PROD, SEP, crawled, gsc, reading, sug, watch

ASK = "what is the difference between tanning oil and sunscreen"
TOPIC = "difference between tanning oil and sunscreen"
INFO, BUY = reading("informational"), reading("transactional")


def read(suggestions=(), prescriptions=(), *, facts=None, outcome="read", source="live", blocked=None, ok=True, error=None, crawl_date=None):
    def diagnose(search, url, row, evidence):
        r = {"ok": ok, "outcome": outcome, "evidence_source": source, "crawl_date": crawl_date}
        if blocked:
            r["blocked"] = blocked
            r["received"] = {"status": 403}
        if error:
            r["error"] = error
        return {"read": r, "suggestions": list(suggestions), "prescriptions": list(prescriptions), "skipped_suggestions": [], "observations": [],
                "page_facts": {"h1": "SPF 30", "title": "SPF 30 Mineral Sunscreen", "schema_types": ["Product"], **(facts or {})}}
    return diagnose


def build(db, client_a, diagnosis, keyword, page=None, intent=INFO, **kw):
    """`intent` is the results-page reading for every search in the test; None means no results page is held."""
    signals = (lambda s: {"reading": intent}) if intent is not None else None
    return ga.build(db, client_a, SEP, keyword, page=page, diagnose=diagnosis, evidence_for=lambda s, u: {}, signals_for=signals, **kw)


def ids(parts):
    return [p["id"] for p in parts]


# ── A: an informational search on a product page ─────────────────────────────


def test_a_an_informational_search_on_a_high_impression_product_page_is_routed_to_supporting_content(db, client_a):
    gsc(db, client_a, ASK, PROD, 5000)
    crawled(db, client_a, PROD, "SPF 30 Mineral Sunscreen")
    watch(db, client_a, keyword=TOPIC, prompt="What is the difference between tanning oil and sunscreen?")
    out = build(db, client_a, read([sug("A-1"), sug("S-1"), sug("P-1"), sug("S-5")]), TOPIC, page=PROD)
    ctx = out["context"]
    assert ctx["intent"]["intent"] == "informational" and ctx["page_type"]["type"] == "product" and ctx["fit"]["level"] == "low"
    assert ctx["intent"]["serp_date"] == "2026-10-01", "the intent is the one read from the results page"
    assert ctx["rerouted"] is True and ids(out["parts"])[0] == "SC-1"
    assert not {"A-1", "S-1", "P-1", "S-2"} & set(ids(out["parts"])), "no explanation is put at the top of the product page"
    assert out["parts"][0]["scope"] == "new supporting content" and "Write a supporting article" in out["parts"][0]["title"]
    assert "displaces" not in out["parts"][0]["why"] and {"A-1", "S-1"} <= {x["id"] for x in out["left_out"]}
    d = ga.draft(out, "2026-10")
    assert "supporting content" in d["title"] and "layout is unchanged" in d["done_when"]


# ── B: a buying search on a product page ─────────────────────────────────────


def test_b_a_buying_search_on_a_product_page_gets_work_on_the_product_page(db, client_a):
    gsc(db, client_a, "buy spf 30 sunscreen", PROD, 900)
    crawled(db, client_a, PROD, "SPF 30 Mineral Sunscreen")
    db.commit()
    out = build(db, client_a, read([sug("A-1"), sug("S-1"), sug("P-1"), sug("S-5")]), "spf 30 sunscreen", page=PROD, intent=BUY)
    ctx = out["context"]
    assert ctx["intent"]["intent"] == "transactional" and ctx["fit"]["level"] == "high" and ctx["rerouted"] is False
    assert ids(out["parts"]) == ["IM-1", "S-1", "S-5"], "work on the product page, led by what a buyer needs; no answer or rewritten opening for a reader"
    assert out["parts"][0]["title"] == "Help the searcher decide on and buy this product"
    assert ctx["validation"]["verdict"] != "reject"


# ── C: a product page on a shared template ───────────────────────────────────


def test_c_a_page_on_a_shared_template_keeps_the_change_in_its_own_content_and_flags_markup(db, client_a):
    gsc(db, client_a, "buy spf 30 sunscreen", PROD, 900)
    crawled(db, client_a, PROD, "SPF 30 Mineral Sunscreen")
    for n in range(6):
        crawled(db, client_a, f"https://shop.example/products/other-{n}", f"Product {n}")
    db.commit()
    v7 = {"action_id": "V-7", "title": "Mark up the FAQ", "why": "It has one", "steps": ["Add FAQPage"], "evidence": []}
    out = build(db, client_a, read([sug("P-1")], prescriptions=[v7]), "spf 30 sunscreen", page=PROD, intent=reading("commercial"))
    tpl = out["context"]["template"]
    assert tpl["shared"] is True and tpl["peers"] == 6 and tpl["pattern"] == "/products/" and tpl["basis"] == "inferred"
    by = {p["id"]: p for p in out["parts"]}
    assert by["P-1"]["scope"] == "page-specific" and "Do not change the template" in by["P-1"]["note"]
    assert by["V-7"]["scope"] == "template-wide" and "6 pages" in by["V-7"]["note"]
    assert any("Do not change the template" in line for line in ga.draft(out, "2026-10")["evidence"])


def test_c_without_a_site_crawl_the_template_is_unverified_not_assumed_free():
    tpl = ac.template_of("https://shop.example/products/spf-30", "product", None)
    assert tpl["shared"] is None and "unverified" in tpl["note"]
    assert "Template constraint unverified" in ac.scope_of("S-2", tpl)["note"]


# ── D: a page our reader was refused ─────────────────────────────────────────


def test_d_a_refused_page_gets_an_investigation_and_no_statement_about_its_content(db, client_a):
    gsc(db, client_a, "natural sunscreen", PROD, 900)
    watch(db, client_a)  # a paired question that used to be turned into "answer at the top" and "add an FAQ" on a page nobody read
    out = build(db, client_a, read(outcome="denied", blocked="The site refused our reader (HTTP 403)."), "natural sunscreen", page=PROD)
    assert out["ok"] and ids(out["parts"]) == ["TI-1"] and out["optional"] == []
    ctx = out["context"]
    assert ctx["evidence"]["crawl_status"] == "denied" and ctx["evidence"]["source"] == "none" and ctx["evidence"]["sufficient"] is False
    assert ctx["validation"]["verdict"] == "needs_verification"
    text = " ".join(out["parts"][0]["steps"] + [out["parts"][0]["why"]])
    assert "has not been read" in text and "does not contain" not in text and "no FAQ" not in text
    d = ga.draft(out, "2026-10")
    assert d["title"].startswith("Investigate crawler access") and any("Crawl status: Access denied" in e for e in d["evidence"])


def test_d_a_page_read_from_an_earlier_crawl_is_worked_on_and_says_how_old_its_facts_are(db, client_a):
    gsc(db, client_a, "buy spf 30 sunscreen", PROD, 900)
    db.commit()
    out = build(db, client_a, read([sug("S-5")], outcome="denied", source="crawl", crawl_date="2026-08-01"), "spf 30 sunscreen", page=PROD, intent=BUY)
    ev = out["context"]["evidence"]
    assert ids(out["parts"]) == ["IM-1", "S-5"] and ev["source"] == "crawl" and ev["confidence"] == "medium"
    assert any("site crawl of 2026-08-01" in u for u in ev["unverified"])


def test_d_every_way_a_read_can_end_has_one_name():
    assert ac.crawl_outcome(status=200) == "read" and ac.crawl_outcome(status=403) == "denied" and ac.crawl_outcome(status=429) == "rate_limited"
    assert ac.crawl_outcome(status=503) == "server_error" and ac.crawl_outcome(status=200, challenged=True) == "challenge"
    assert ac.crawl_outcome(status=200, empty=True) == "rendering" and ac.crawl_outcome(status=None, robots=True) == "robots"
    assert ac.crawl_outcome(status=None, error="The page took too long to answer.") == "network" and ac.crawl_outcome(status=None, error="odd") == "other"


# ── E: our reader is blocked, Google is not ──────────────────────────────────


def test_e_a_block_on_our_reader_is_not_called_a_block_on_search_engines(db, client_a):
    gsc(db, client_a, "natural sunscreen", PROD, 900)
    db.commit()
    out = build(db, client_a, read(outcome="denied", blocked="The site refused our reader (HTTP 403)."), "natural sunscreen", page=PROD)
    part = out["parts"][0]
    assert part["classification"] == "Tool-specific crawl limitation"
    assert "Search engine impact has not been established" in part["why"] and any("Google was showing it" in e for e in part["evidence"])
    assert "cannot index" not in " ".join(part["steps"] + [part["why"]]).lower()
    assert ac.technical_finding("denied", impressions=0, window_to="2026-09-30")["classification"] == "Insufficient evidence"
    assert ac.technical_finding("server_error", impressions=50, window_to="2026-09-30")["classification"] == "Potential technical issue requiring verification"


# ── F: weak candidates are not used to make up the number ────────────────────


def test_f_two_of_three_candidates_with_poor_fit_are_excluded_with_the_reason():
    picked = ac.select([
        {"url": "a", "score": 9000, "fit": "low", "evidence_ok": True},
        {"url": "b", "score": 300, "fit": "high", "evidence_ok": True},
        {"url": "c", "score": 7000, "fit": "low", "evidence_ok": True},
    ], limit=3)
    assert [c["url"] for c in picked["chosen"]] == ["b"], "one strong action, not three"
    assert {c["url"] for c in picked["excluded"]} == {"a", "c"} and all("does not suit" in c["excluded_because"] for c in picked["excluded"])


def test_f_the_page_with_the_most_impressions_does_not_win_when_it_does_not_suit_the_search(db, client_a):
    gsc(db, client_a, ASK, PROD, 9000)
    gsc(db, client_a, ASK, BLOG, 120)
    db.commit()
    out = ga.topic_pages(db, client_a, SEP, TOPIC, signals={"reading": INFO})
    assert out["recommended"] == BLOG and out["unsuitable"] == 1
    by = {p["url"]: p for p in out["pages"]}
    assert by[PROD]["fit"] == "low" and by[BLOG]["fit"] == "high" and by[PROD]["score"] > by[BLOG]["score"]


def test_f_an_action_already_planned_for_the_page_and_topic_is_not_offered_twice(db, client_a):
    gsc(db, client_a, "buy spf 30 sunscreen", PROD, 900)
    db.add(EngineTask(client_id=client_a.id, month="2026-10", kind="growth_action", rule_id="GA", search="spf 30 sunscreen", page_url=PROD, title="Growth action: /products/spf-30", confirmed_by="a@b.c"))
    db.commit()
    out = build(db, client_a, read([sug("S-5")]), "spf 30 sunscreen", page=PROD, planned_month="2026-10", intent=BUY)
    assert out["ok"] is False and "already planned" in out["error"] and out["context"]["validation"]["verdict"] == "reject"


# ── G: an article already covers it ──────────────────────────────────────────


def test_g_an_existing_article_is_improved_and_linked_before_anything_new_is_written(db, client_a):
    gsc(db, client_a, ASK, PROD, 5000)
    gsc(db, client_a, ASK, BLOG, 80)
    db.commit()
    out = build(db, client_a, read([sug("A-1")]), TOPIC, page=PROD)
    part = out["parts"][0]
    assert part["id"] == "SC-1" and "existing article" in part["title"] and part["action_type"] == "Optimize existing page"
    assert any(BLOG in s for s in part["steps"]) and any(PROD in s for s in part["steps"])
    assert "Write a supporting article" not in part["title"]


def test_g_an_article_found_only_by_its_title_in_the_crawl_counts(db, client_a):
    gsc(db, client_a, ASK, PROD, 5000)
    crawled(db, client_a, "https://shop.example/blogs/guide", "The Difference Between Tanning Oil and Sunscreen")
    db.commit()
    part = build(db, client_a, read(), TOPIC, page=PROD)["parts"][0]
    assert "existing article" in part["title"] and "its title says the topic" in part["why"]


# ── H: the search wants something the product is not ─────────────────────────


def test_h_wording_the_page_never_uses_is_not_copied_onto_a_product_page(db, client_a):
    gsc(db, client_a, "tanning oil with spf", PROD, 2000)
    db.commit()
    out = build(db, client_a, read([sug("S-1"), sug("S-5")], facts={"search_terms_missing": ["oil", "tanning"]}), "tanning oil with spf", page=PROD, intent=BUY)
    assert ids(out["parts"]) == ["IM-1", "S-5"], "the phrasing part would have put “tanning oil” on a sunscreen page"
    reason = next(x["reason"] for x in out["left_out"] if x["id"] == "S-1")
    assert "“oil”" in reason and "“tanning”" in reason and "only if it is true" in reason
    assert any("has not been checked" in u for u in out["context"]["evidence"]["unverified"])


# ── intent comes from the results page, and the advice follows it ────────────

PAGE = {
    "item_types": ["organic", "popular_products", "shopping", "people_also_ask", "ai_overview"],
    "results": [{"rank": n, "url": f"https://shop{n}.example/collections/natural-sunscreen", "domain": f"shop{n}.example", "title": f"Natural Sunscreen | Shop {n}", "snippet": "Mineral, reef-safe SPF."} for n in range(1, 11)],
}
ANSWER = {
    "primary": "transactional", "secondary": "commercial", "mixed": False, "confidence": "high",
    "searcher_goal": "The searcher wants to find and buy a natural sunscreen.",
    "results": [{"rank": n, "content_type": "category or collection page" if n < 8 else "article or blog post", "content_style": "product listing" if n < 8 else "list"} for n in range(1, 11)],
    "evidence": ["7 of 10 results are product or collection pages", "A popular products carousel and shopping results show"],
    "uncertainty": None, "label_disagreement": "The keyword tool says informational; the page is product listings.",
    "consumer_need": {"need": "reassure", "basis": "observed", "evidence": "Ranking titles lead with mineral, reef-safe and non-toxic."},
    "content_to_match": "Collection pages listing products with their SPF, size and price.",
}


def model(answer=ANSWER, calls=None):
    def ask(prompt):
        if calls is not None:
            calls.append(prompt)
        return "Here is the reading:\n```json\n" + json.dumps(answer) + "\n```"
    return ask


def test_natural_sunscreen_is_read_as_shopping_from_what_ranks_and_the_collection_page_is_told_to_serve_a_buyer(db, client_a):
    """The case that started this: a collection page, a results page of product listings, and advice to answer a question at the top."""
    found = serp_intent.read("natural sunscreen", item_types=PAGE["item_types"], results=PAGE["results"], serp_date="2026-11-12", labels=["informational"], ask=model())
    assert found["intent"] == "transactional" and found["secondary"] == "commercial" and found["read"] is True
    assert found["content_types"] == {"category or collection page": 7, "article or blog post": 3} and found["features"] == ["popular_products", "shopping", "people_also_ask"]
    assert found["label_disagreement"] and found["labels"] == ["informational"], "the tool's label is shown as disagreeing; it decided nothing"

    gsc(db, client_a, "natural sunscreen", COLL, 3000, position=13)
    crawled(db, client_a, COLL, "Natural Sunscreen | Shop")
    watch(db, client_a)
    out = build(db, client_a, read([sug("A-1"), sug("S-1"), sug("P-1"), sug("S-5")], facts={"schema_types": ["CollectionPage"], "title": "Natural Sunscreen | Shop"}), "natural sunscreen", page=COLL, intent=found)
    lead = out["parts"][0]
    assert out["context"]["fit"]["level"] == "high" and ids(out["parts"]) == ["IM-1", "S-1", "S-2", "S-5"]
    assert lead["title"] == "Help the searcher find, compare and buy from the range"
    steps = " ".join(lead["steps"])
    assert "price and availability" in steps and "Message (Reassure me, observed)" in steps and "What ranks for this search: Collection pages" in steps
    assert any("7 of 10 results" in e for e in lead["evidence"]) and any("Ranking content types: 7 category" in e for e in lead["evidence"])
    assert "A-1" in {x["id"] for x in out["left_out"]} and not {"A-1", "P-1"} & set(ids(out["parts"] + out["optional"]))
    assert any("Search intent: Transactional, secondary commercial" in e for e in ga.draft(out, "2026-12")["evidence"])


def test_with_no_results_page_the_intent_is_not_read_and_nothing_that_depends_on_it_is_recommended(db, client_a):
    gsc(db, client_a, "natural sunscreen", COLL, 3000, position=13)
    watch(db, client_a)
    v4 = {"action_id": "V-4", "title": "Add internal links", "why": "0 links", "steps": ["Link from the donors"], "evidence": ["0 editorial inbound"]}
    out = build(db, client_a, read([sug("A-1"), sug("S-1"), sug("P-1"), sug("S-2"), sug("S-5")], prescriptions=[v4]), "natural sunscreen", page=COLL, intent=None)
    ctx = out["context"]
    assert ctx["intent"]["name"] == "Intent not read — No SERP available" and ctx["fit"]["level"] == "unverified"
    assert ids(out["parts"]) == ["V-4", "S-5"], "what stands on other evidence carries on: the crawl's link count and the click-through against the benchmark"
    held = {x["id"]: x["reason"] for x in out["left_out"]}
    assert {"A-1", "S-1", "S-2"} <= set(held) and all(r.startswith("Held: Intent not read — No SERP available") for r in held.values())
    assert out["optional"] == [] and any("Intent not read" in u for u in ctx["evidence"]["unverified"])


def test_the_same_page_and_search_get_different_advice_when_the_results_page_differs(db, client_a):
    gsc(db, client_a, "closet organizers", "https://shop.example/services/closets", 900)
    db.commit()
    page = "https://shop.example/services/closets"
    seen = {}
    for name, found in (("buy", BUY), ("compare", reading("commercial")), ("local", reading("local")), ("learn", INFO)):
        out = build(db, client_a, read([sug("S-5")], facts={"schema_types": ["Service"], "title": "Closet Organizing"}), "closet organizers", page=page, intent=found)
        seen[name] = (ids(out["parts"]), out["parts"][0]["title"])
    assert seen["buy"][1] == "Help the searcher book or enquire about the service"
    assert seen["compare"][1] == "Help the searcher judge this provider against the alternatives"
    assert seen["local"][1] == "Help the searcher find this service nearby"
    assert seen["learn"][0][0] == "SC-1", "a service page is not rewritten to explain; the work goes to an article"
    assert len({v[1] for v in seen.values()}) == 4


def test_a_mixed_results_page_names_both_intents_and_the_page_is_judged_on_each(db, client_a):
    mixed = reading("commercial", "informational", mixed=True, evidence=["5 results are comparison lists", "5 are how-to guides"])
    assert mixed["intent"] == "mixed" and (mixed["primary"], mixed["secondary"]) == ("commercial", "informational")
    assert reading("commercial", None, mixed=True)["intent"] == "commercial", "mixed needs two named intents"
    fit = ac.compatibility(mixed, ac.classify_page("https://x/blog/best-closet-systems"))
    assert fit["level"] == "medium" and "commercial side" in fit["why"] and "informational side" in fit["why"]
    assert "Mixed (commercial and informational)" in serp_intent.describe(mixed)


def test_the_model_is_not_made_to_choose_and_what_it_returns_is_held_to_what_is_allowed():
    kw = dict(item_types=PAGE["item_types"], results=PAGE["results"], serp_date="2026-11-12")
    unsure = serp_intent.read("jaguar", ask=model({"primary": "insufficient", "evidence": [], "uncertainty": "Results split between the animal, the car and the team."}), **kw)
    assert unsure["intent"] == "insufficient" and unsure["read"] is False and "split between" in unsure["uncertainty"]
    assert serp_intent.read("x", ask=model({**ANSWER, "evidence": []}), **kw)["read"] is False, "an intent with nothing seen to support it is a guess"
    assert serp_intent.read("x", ask=model({**ANSWER, "primary": "shopping"}), **kw)["intent"] == "insufficient"
    assert serp_intent.read("x", ask=model({**ANSWER, "consumer_need": {"need": "reassure", "basis": "observed", "evidence": ""}}), **kw)["consumer_need"] is None
    assert serp_intent.read("x", ask=model({**ANSWER, "consumer_need": {"need": "delight", "basis": "observed", "evidence": "x"}}), **kw)["consumer_need"] is None

    def down(prompt):
        raise RuntimeError("The model did not answer (529).")

    failed = serp_intent.read("x", ask=down, **kw)
    assert failed["intent"] == "insufficient" and "could not be read" in failed["uncertainty"]
    assert serp_intent.read("x", item_types=None, results=None)["intent"] == "not_read"
    assert serp_intent.read("x", item_types=["organic"], results=[])["intent"] == "not_read", "a pull kept without its ranking results cannot be read"


def test_the_prompt_shows_the_model_the_results_and_tells_it_labels_do_not_decide():
    calls: list[str] = []
    serp_intent.read("natural sunscreen", item_types=PAGE["item_types"], results=PAGE["results"], labels=["informational"], ask=model(calls=calls))
    assert "Natural Sunscreen | Shop 1" in calls[0] and "popular_products" in calls[0] and "for reference only" in calls[0] and "Do not force an answer" in calls[0]


def test_a_pull_keeps_the_top_ten_ranking_results():
    items = [{"type": "organic", "rank_group": n, "url": f"https://a{n}.example/p", "domain": f"www.a{n}.example", "title": f"T {n}", "description": "d"} for n in range(1, 13)]
    found = dataforseo.parse({"keyword": "k", "item_types": ["organic", "shopping"], "items": [{"type": "shopping", "items": []}, *items]})
    assert len(found.organic) == 10 and found.organic[0] == {"rank": 1, "url": "https://a1.example/p", "domain": "a1.example", "title": "T 1", "snippet": "d"}


def test_the_results_page_is_pulled_and_read_once_when_an_action_is_built_and_never_when_pages_are_listed(db, client_a, monkeypatch):
    monkeypatch.setattr(search_signals.dataforseo, "configured", lambda: True)
    pulls, asks = [], []

    def fetch(keyword):
        pulls.append(keyword)
        return dataforseo.SerpFeatures(keyword=keyword, item_types=tuple(PAGE["item_types"]), organic=tuple(PAGE["results"]))

    none = lambda keywords, source="us": [{"keyword": keywords[0], "intents": ["informational"], "is_data_found": True}]
    kw = dict(overview=none, fetch=fetch, ask=model(calls=asks))
    assert search_signals.for_search(db, client_a, "natural sunscreen", pull=False, **kw)["reading"]["intent"] == "not_read" and pulls == []
    first = search_signals.for_search(db, client_a, "Natural  Sunscreen", **kw)
    again = search_signals.for_search(db, client_a, "natural sunscreen", **kw)
    listed = search_signals.for_search(db, client_a, "natural sunscreen", pull=False, **kw)
    assert first["reading"]["intent"] == "transactional" == again["reading"]["intent"] == listed["reading"]["intent"]
    assert pulls == ["natural sunscreen"] and len(asks) == 1, "one pull and one reading, however often it is asked for"
    assert first["labels"] == ["informational"] and first["reading"]["labels"] == ["informational"]
    row = db.query(FactSerpFeature).filter(FactSerpFeature.client_id == client_a.id).one()
    assert len(row.results) == 10 and row.reading["intent"] == "transactional"
    row.pulled_on = date.today() - timedelta(days=45)
    db.commit()
    search_signals.for_search(db, client_a, "natural sunscreen", **kw)
    assert len(pulls) == 2 and len(asks) == 2, "a results page over a month old is pulled and read again"


def test_without_dataforseo_or_with_a_failed_pull_the_intent_is_not_read_and_says_why(db, client_a, monkeypatch):
    monkeypatch.setattr(search_signals.dataforseo, "configured", lambda: False)
    off = search_signals.for_search(db, client_a, "natural sunscreen")["reading"]
    assert off["intent"] == "not_read" and "not configured" in off["uncertainty"]
    monkeypatch.setattr(search_signals.dataforseo, "configured", lambda: True)

    def broken(keyword):
        raise dataforseo.DataForSeoError("no SERP")

    failed = search_signals.for_search(db, client_a, "natural sunscreen", overview=lambda k, source="us": [], fetch=broken)["reading"]
    assert failed["intent"] == "not_read" and "could not be pulled" in failed["uncertainty"]


def test_a_page_type_from_markup_is_trusted_more_than_one_from_the_address_and_unknown_stays_unknown():
    assert ac.classify_page("https://x/item-9", schema_types=["Product"])["confidence"] == "high"
    by_address = ac.classify_page("https://x/blog/closets")
    assert by_address["type"] == "article" and by_address["confidence"] == "medium"
    assert ac.classify_page("https://x/collections/spf")["type"] == "category"
    assert ac.classify_page("https://x/collections/spf/products/spf-30")["type"] == "product"
    assert ac.classify_page("https://x/locations/nashville")["type"] == "location"
    unknown = ac.classify_page("https://x/zx81")
    assert unknown["type"] == "unknown" and ac.compatibility(INFO, unknown)["level"] == "unverified"


# ── fit is judged against what ranks ─────────────────────────────────────────


def ranked(primary, types, styles=None, **kw):
    """A reading whose ranking results are of the given types: `{"article or blog post": 8}`."""
    rows = [{"rank": i, "content_type": t, "content_style": (styles or ["none"])[min(i, len(styles or ["none"]) - 1)]} for i, t in enumerate(t for t, n in types.items() for _ in range(n))]
    return reading(primary, results=rows, **kw)


ROUNDUPS = ranked("commercial", {"article or blog post": 8}, ["list"], secondary="informational",
                  evidence=["6 of 8 organic results are 'best' or 'top' roundups", "None of the 8 organic results is a product or collection page"],
                  content_to_match="Roundup lists of the best natural sunscreens.")


def test_a_collection_page_does_not_suit_a_search_where_only_articles_rank_whatever_the_intent_is_called(db, client_a):
    """Read as commercial, “natural sunscreen” was said to suit the collection page while all eight ranking results were articles."""
    fit = ac.compatibility(ROUNDUPS, ac.classify_page(COLL))
    assert fit["level"] == "low" and fit["basis"] == "what ranks" and fit["leads"] == "explaining" and (fit["matched"], fit["total"]) == (0, 8)
    assert "0 of the 8 ranking results are product, collection or service pages" in fit["why"]

    gsc(db, client_a, "natural sunscreen", COLL, 3000, position=13)
    crawled(db, client_a, COLL, "Natural Sunscreen | Shop")
    watch(db, client_a)
    out = build(db, client_a, read([sug("A-1"), sug("S-1"), sug("S-5")], facts={"schema_types": ["CollectionPage"], "title": "Natural Sunscreen | Shop"}), "natural sunscreen", page=COLL, intent=ROUNDUPS)
    lead = out["parts"][0]
    assert out["context"]["rerouted"] is True and lead["id"] == "SC-1" and "IM-1" not in ids(out["parts"])
    assert lead["title"] == "Write a “best of” list for “natural sunscreen”", "no article exists, so a new page in the style that ranks"
    assert any("What ranks for this search: Roundup lists" in s for s in lead["steps"]) and any("None of the 8 organic results" in e for e in lead["evidence"])
    assert not {"A-1", "S-1"} & set(ids(out["parts"] + out["optional"])), "no work is proposed on the collection page's own copy"


def test_an_existing_blog_post_is_used_before_a_new_page_and_is_listed_first(db, client_a):
    gsc(db, client_a, "natural sunscreen", COLL, 3000, position=13)
    gsc(db, client_a, "natural sunscreen", BLOG, 150, position=30)
    db.commit()
    pages = ga.topic_pages(db, client_a, SEP, "natural sunscreen", signals={"reading": ROUNDUPS})
    assert pages["recommended"] == BLOG and [p["fit"] for p in pages["pages"]] == ["high", "low"], "the blog post leads although the collection page has twenty times the impressions"
    lead = build(db, client_a, read(facts={"schema_types": ["CollectionPage"]}), "natural sunscreen", page=COLL, intent=ROUNDUPS)["parts"][0]
    assert "existing article" in lead["title"] and any(BLOG in s for s in lead["steps"]) and any("“best of” list" in s for s in lead["steps"])


def test_the_cut_offs_none_is_low_half_is_high_between_is_partly_and_under_five_results_falls_back():
    coll = ac.classify_page(COLL)
    assert ac.compatibility(ranked("commercial", {"category or collection page": 5, "article or blog post": 5}), coll)["level"] == "high"
    assert ac.compatibility(ranked("commercial", {"product page": 2, "article or blog post": 8}), coll)["level"] == "medium", "a product page ranking counts for a collection page: both sell"
    assert ac.compatibility(ranked("commercial", {"article or blog post": 10}), coll)["level"] == "low"
    few = ac.compatibility(ranked("commercial", {"article or blog post": 4}), coll)
    assert few["basis"] == "intent" and few["level"] == "high" and "Too few ranking results" in few["why"]


def test_an_article_is_not_worked_on_for_a_search_where_selling_pages_rank(db, client_a):
    gsc(db, client_a, "spf 30 sunscreen", BLOG, 800)
    gsc(db, client_a, "spf 30 sunscreen", PROD, 90)
    db.commit()
    shop = ranked("transactional", {"product page": 6, "category or collection page": 3})
    out = build(db, client_a, read([sug("A-1"), sug("S-1"), sug("S-5")], facts={"schema_types": ["Article"], "title": "Sun"}), "spf 30 sunscreen", page=BLOG, intent=shop)
    lead = out["parts"][0]
    assert lead["id"] == "RT-1" and PROD in lead["title"] and not {"A-1", "S-1"} & set(ids(out["parts"] + out["optional"]))
    assert ga.draft(out, "2026-12")["title"].startswith("Growth action: the selling page for")
