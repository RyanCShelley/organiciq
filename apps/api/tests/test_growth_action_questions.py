"""The FAQ part is built from questions people ask about the term, checked against the page.

A page that already had an FAQ used to get no FAQ advice at all, and a page without one got a single generic
question. Now the questions come from the results page's "People also ask", the question-shaped searches the page
shows for, the winners' own FAQs and the paired AI prompt, and only the ones the page does not answer are suggested.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from app.integrations import dataforseo
from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlInternalLink
from app.models.seranking import FactSerpFeature
from app.services import growth_action as ga
from app.services import search_signals, winners
from tests.test_growth_action import COLL, SEP, crawled, sug
from tests.test_growth_action_context import ids, read
from tests.test_growth_action_term import FACE, OUTLINE, W1, WINNING, page, site

PAA = ["Is natural sunscreen safe for the face?", "Does mineral sunscreen clog pores?"]
FAQ_PAGE = "https://shop.example/pages/faq"


def answer(missing, gaps=()):
    return lambda prompt: json.dumps({"best_page": {"verdict": "yes", "why": "It is a collection page like the winners."}, "gaps": list(gaps), "missing_questions": missing})


async def reader(urls):
    return [page(u, faq_list=["How often should I reapply?"]) for u in urls]


def build(db, client_a, missing, *, has_faq, asked=None, suggestions=(sug("S-5"),)):
    def winners_for(s, i, u, t, own, questions):
        if asked is not None:
            asked.extend(questions)
        return winners.gather(db, client_a, search=s, intent=i, page_url=u, page_type=t, own=own, reader=reader, ask=answer(missing), questions=questions)

    return ga.build(
        db, client_a, SEP, "natural sunscreen", search=FACE, page=COLL,
        diagnose=read(list(suggestions), facts={"outline": OUTLINE, "schema_types": ["CollectionPage"], "has_faq": has_faq}),
        evidence_for=lambda s, u: {"page_queries": [{"query": "is natural sunscreen good for face", "impressions": 40}, {"query": "natural sunscreen for face", "impressions": 135}]},
        signals_for=lambda term: {"reading": {**WINNING, "search": term}, "questions": PAA}, winners_for=winners_for,
    )


def test_a_pull_keeps_the_people_also_ask_questions():
    found = dataforseo.parse({"keyword": "k", "item_types": ["organic", "people_also_ask"], "items": [
        {"type": "people_also_ask", "items": [{"type": "people_also_ask_element", "title": q} for q in [*PAA, PAA[0], ""]]},
    ]})
    assert found.questions == tuple(PAA), "each question once, in order, blanks dropped"
    assert dataforseo.parse({"keyword": "k", "item_types": ["organic"], "items": []}).questions == ()


def test_a_page_that_showed_people_also_ask_before_its_questions_were_kept_is_pulled_once_more(db, client_a, monkeypatch):
    monkeypatch.setattr(search_signals.dataforseo, "configured", lambda: True)
    results = [{"rank": n, "url": f"https://a{n}.example/p", "domain": f"a{n}.example", "title": "T", "snippet": "d"} for n in range(1, 9)]
    db.add(FactSerpFeature(client_id=client_a.id, pulled_on=date.today() - timedelta(days=2), keyword=FACE, item_types=["organic", "people_also_ask"], results=results,
                           reading={**WINNING, "read": True}))
    db.commit()
    pulls = []

    def fetch(keyword):
        pulls.append(keyword)
        return dataforseo.SerpFeatures(keyword=keyword, item_types=("organic", "people_also_ask"), organic=tuple(results), questions=tuple(PAA))

    kw = dict(overview=lambda keywords, source="us": [], fetch=fetch, ask=lambda prompt: json.dumps({"primary": "transactional", "confidence": "high", "evidence": ["6 of 8 are product pages"]}))
    assert search_signals.for_search(db, client_a, FACE, pull=False, **kw)["questions"] == [] and pulls == [], "listing pages spends nothing"
    assert search_signals.for_search(db, client_a, FACE, **kw)["questions"] == PAA
    assert search_signals.for_search(db, client_a, FACE, **kw)["questions"] == PAA and pulls == [FACE], "pulled once, then held"


def test_only_questions_that_were_on_the_list_come_back_and_each_says_where_it_was_seen():
    asked = [{"question": PAA[0], "source": "people_also_ask", "detail": None}, {"question": PAA[0].lower(), "source": "search_console", "detail": "40 impressions"},
             {"question": "Made up source?", "source": "a hunch", "detail": None}]
    found = winners.compare(search=FACE, intent=WINNING, page_url=COLL, page_type="Category", own=OUTLINE, search_pages=[page(W1, faq_list=["How often should I reapply?"])], llm_pages=[], llm={},
                            questions=asked, ask=answer([{"id": "Q2", "why": "Shoppers ask it."}, {"id": "Q9", "why": "Invented."}, {"id": "Q2", "why": "Twice."}]))
    assert found["questions"]["checked"] == 2, "one of each wording, known sources only, plus the winner's own FAQ question"
    assert found["questions"]["missing"] == [{"question": "How often should I reapply?", "source": "winner", "detail": W1, "source_name": "answered on a winning page", "why": "Shoppers ask it."}]


def test_with_no_winner_readable_the_questions_are_still_checked():
    asked = [{"question": PAA[0], "source": "people_also_ask", "detail": None}]
    found = winners.compare(search=FACE, intent=WINNING, page_url=COLL, page_type="Category", own=OUTLINE, search_pages=[{"url": W1, "read": False}], llm_pages=[], llm={}, questions=asked,
                            ask=answer([{"id": "Q1", "why": "Not answered."}]))
    assert found["ok"] is False and found["best_page"] is None and found["gaps"] == [] and [q["question"] for q in found["questions"]["missing"]] == [PAA[0]]
    assert winners.compare(search=FACE, intent=WINNING, page_url=COLL, page_type="Category", own=OUTLINE, search_pages=[], llm_pages=[], llm={}, ask=answer([]))["questions"] is None


def test_a_page_with_an_faq_is_told_which_questions_it_is_missing(db, client_a):
    site(db, client_a)
    asked: list = []
    out = build(db, client_a, [{"id": "Q1", "why": "It is the first thing asked."}, {"id": "Q3", "why": "People search it."}], has_faq=True, asked=asked)
    assert [(q["question"], q["source"]) for q in asked] == [(PAA[0], "people_also_ask"), (PAA[1], "people_also_ask"), ("is natural sunscreen good for face", "search_console"),
                                                             ("Best natural sunscreen for sensitive skin?", "prompt")], "the search itself is not a question and is not asked"
    part = next(p for p in out["parts"] if p["id"] == "S-2")
    assert part["title"] == "Add 2 missing questions to the page's FAQ" and part["name"] == "Add the missing questions to the FAQ"
    assert part["steps"][0] == f"“{PAA[0]}” Seen in: People also ask, on the results page. It is the first thing asked."
    assert part["steps"][1] == "“is natural sunscreen good for face” Seen in: a search this page shows for (40 impressions). People search it."
    assert part["steps"][-1].startswith("Add them to the page's existing FAQ") and "5 questions checked, 2 not answered on the page" in part["evidence"]
    assert "model's reading" in part["why"]


def test_a_page_without_an_faq_gets_one_built_from_the_missing_questions_not_a_generic_one(db, client_a):
    site(db, client_a)
    out = build(db, client_a, [{"id": "Q2", "why": "Asked on the results page."}], has_faq=False, suggestions=(sug("S-5"), sug("S-2", title="Add a short FAQ from real questions")))
    parts = [p for p in out["parts"] if p["id"] == "S-2"]
    assert len(parts) == 1 and parts[0]["title"] == "Add a short FAQ with 1 question people ask" and parts[0]["steps"][0].startswith(f"“{PAA[1]}”")
    assert parts[0]["steps"][-1] == "Put them in a short FAQ section on the page." and "FAQPage" not in " ".join(parts[0]["steps"]), "markup is not a default step"


def test_an_faq_that_already_answers_everything_found_gets_no_faq_part_and_says_so(db, client_a):
    site(db, client_a)
    out = build(db, client_a, [], has_faq=True)
    assert "S-2" not in ids(out["parts"])
    assert next(p for p in out["left_out"] if p["id"] == "S-2")["reason"] == "The page already has an FAQ, and it answers all 5 of the questions found for this search."


def test_the_sites_faq_page_is_linked_from_the_faq_work_unless_the_page_already_links_to_it(db, client_a):
    site(db, client_a)
    crawled(db, client_a, FAQ_PAGE, "FAQ")
    crawled(db, client_a, "https://shop.example/blogs/news/sunscreen-faq-myths", "Sunscreen myths")
    db.commit()
    out = build(db, client_a, [{"id": "Q1", "why": "Asked."}], has_faq=True)
    assert ids(out["parts"])[ids(out["parts"]).index("S-2") + 1] == "FQ-1", "with FAQ work in the action the link is part of it"
    link = next(p for p in out["parts"] if p["id"] == "FQ-1")
    assert link["steps"][0] == f"The FAQ page: {FAQ_PAGE}" and link["action_type"] == "Improve internal linking"
    offered = build(db, client_a, [], has_faq=True)
    assert "FQ-1" not in ids(offered["parts"]) and "FQ-1" in ids(offered["optional"]), "with no FAQ work it is offered, not added"
    db.add(FactCrawlInternalLink(client_id=client_a.id, source=CRAWL_SOURCE_FIRST_PARTY, snapshot_date=date(2026, 10, 1), from_url=COLL, to_url=FAQ_PAGE, in_content=True))
    db.commit()
    linked = build(db, client_a, [{"id": "Q1", "why": "Asked."}], has_faq=True)
    assert "FQ-1" not in ids(linked["parts"]) + ids(linked["optional"])
