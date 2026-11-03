"""A growth action is one page worked together for one topic, counted as one against the plan."""

from __future__ import annotations

from datetime import date

from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSnapshot
from app.models.engine_task import EngineTask
from app.models.gsc import FactGscQueryPage
from app.models.watchlist import WatchlistBucket, WatchlistKeyword
from app.services import growth_action as ga
from tests.conftest import client_header

SEP = "2026-09"
COLL = "https://shop.example/collections/spf"
PROD = "https://shop.example/products/spf-30"
BLOG = "https://shop.example/blogs/sun"


def gsc(db, client_a, query, url, impressions, clicks=1, position=8.0):
    db.add(
        FactGscQueryPage(
            client_id=client_a.id, date=date(2026, 8, 10), query=query, raw_url=url, normalized_url=url,
            country="usa", device="DESKTOP", impressions=impressions, clicks=clicks, ctr=0, average_position=position,
        )
    )


def crawled(db, client_a, url, title):
    db.add(FactCrawlPageSnapshot(client_id=client_a.id, source=CRAWL_SOURCE_FIRST_PARTY, snapshot_date=date(2026, 10, 1),
                                 raw_url=url, normalized_url=url, indexable=True, title=title))


def watch(db, client_a, keyword="natural sunscreen", prompt="Best natural sunscreen for sensitive skin?"):
    b = WatchlistBucket(client_id=client_a.id, name="Sunscreen", name_key="sunscreen", sort_order=0)
    db.add(b)
    db.flush()
    db.add(WatchlistKeyword(client_id=client_a.id, bucket_id=b.id, keyword=keyword, keyword_key=keyword, paired_ai_prompt=prompt))
    db.commit()


def data(db, client_a):
    gsc(db, client_a, "natural sunscreen", COLL, 3000, position=13)
    gsc(db, client_a, "all natural sunscreen", COLL, 600, position=19)
    gsc(db, client_a, "natural sunscreen spf 30", PROD, 160, position=9)
    gsc(db, client_a, "natural sunscreen reviews", BLOG, 4000, position=30)
    gsc(db, client_a, "tanning oil", "https://shop.example/oil", 9000)  # not the topic
    crawled(db, client_a, COLL, "Sunscreen | Natural Sunscreen | Shop")
    crawled(db, client_a, PROD, "SPF 30 Mineral Sunscreen")
    db.commit()


# ── choosing the page ────────────────────────────────────────────────────────


def test_a_low_impression_page_is_still_listed_and_can_be_chosen(db, client_a, monkeypatch):
    data(db, client_a)
    small = "https://shop.example/blogs/small"
    gsc(db, client_a, "natural sunscreen for pilots", small, 6, clicks=0, position=5.2)
    db.commit()
    monkeypatch.setattr(ga, "PAGES_SHOWN", 2)
    out = ga.topic_pages(db, client_a, SEP, "natural sunscreen", include=small)
    assert [p["url"] for p in out["pages"]][-1] == small and len(out["pages"]) == 3
    assert all(p["url"] != small for p in ga.topic_pages(db, client_a, SEP, "natural sunscreen")["pages"])


def test_the_page_with_the_most_impressions_is_recommended_and_a_title_that_says_the_topic_counts_extra(db, client_a):
    data(db, client_a)
    out = ga.topic_pages(db, client_a, SEP, "Natural  Sunscreen")
    assert out["keyword"] == "natural sunscreen" and out["total_pages"] == 3
    by = {p["url"]: p for p in out["pages"]}
    assert by[COLL]["impressions"] == 3600 and by[COLL]["searches"] == 2 and by[COLL]["top_search"] == "natural sunscreen"
    assert by[COLL]["title_says_topic"] is True and by[COLL]["score"] == 5400.0
    assert by[PROD]["title_says_topic"] is False
    # The blog has more raw impressions than the collection's 3,600 but not 1.5 times more... it is the larger, and its title is unknown.
    assert out["recommended"] == (BLOG if by[BLOG]["score"] > by[COLL]["score"] else COLL)
    assert "tanning oil" not in str(out)


def test_a_title_that_says_the_topic_beats_a_slightly_bigger_page_that_does_not(db, client_a):
    gsc(db, client_a, "natural sunscreen", COLL, 1000)
    gsc(db, client_a, "natural sunscreen", PROD, 1300)
    crawled(db, client_a, COLL, "Natural Sunscreen")
    crawled(db, client_a, PROD, "SPF 30")
    db.commit()
    assert ga.topic_pages(db, client_a, SEP, "natural sunscreen")["recommended"] == COLL


def test_brand_searches_are_left_out_of_the_choice(db, client_a):
    client_a.client_name = "Shop Example"
    db.commit()
    gsc(db, client_a, "shop example natural sunscreen", PROD, 9000)
    gsc(db, client_a, "natural sunscreen", COLL, 100)
    db.commit()
    assert [p["url"] for p in ga.topic_pages(db, client_a, SEP, "natural sunscreen")["pages"]] == [COLL]


# ── the bundle ───────────────────────────────────────────────────────────────


def fake_diagnosis(suggestions, prescriptions=(), skipped=()):
    def diagnose(search, url, row, evidence):
        return {"read": {"ok": True}, "suggestions": list(suggestions), "prescriptions": list(prescriptions),
                "skipped_suggestions": list(skipped), "observations": [], "page_facts": {"h1": "SUN CARE"}}
    return diagnose


def sug(id_, title="t", steps=("do it",), evidence=()):
    return {"id": id_, "title": title, "why": "w", "steps": list(steps), "evidence": list(evidence), "confidence": "unconfirmed"}


def build(db, client_a, diagnosis, page=None):
    return ga.build(db, client_a, SEP, "natural sunscreen", page=page, diagnose=diagnosis, evidence_for=lambda s, u: {})


def test_the_bundle_holds_the_core_parts_that_apply_and_the_extras_the_page_read_found(db, client_a):
    data(db, client_a)
    watch(db, client_a)
    out = build(db, client_a, fake_diagnosis([sug("A-1"), sug("S-1"), sug("S-2"), sug("S-5"), sug("S-3"), sug("S-6")]), page=COLL)
    assert out["ok"] and out["page"] == COLL and out["search"] == "natural sunscreen"
    assert [p["id"] for p in out["parts"]] == ["A-1", "S-1", "S-2", "S-5"]
    assert [p["core"] for p in out["parts"]] == [True, True, True, False]
    assert [o["id"] for o in out["optional"]] == ["S-3"]  # offered to add; S-6 is answered by choosing the page


def test_a_core_part_with_nothing_to_do_is_named_and_not_padded_in(db, client_a):
    data(db, client_a)
    watch(db, client_a, prompt="")
    out = build(db, client_a, fake_diagnosis([sug("S-5")], skipped=[{"id": "S-2", "reason": "No question-shaped search."}]), page=COLL)
    assert [p["id"] for p in out["parts"]] == ["S-5"]
    assert {x["id"] for x in out["left_out"]} == {"A-1", "S-1", "S-2"}


def test_the_topics_paired_question_stands_in_for_a_core_part_the_page_read_could_not_make(db, client_a):
    data(db, client_a)
    watch(db, client_a)
    out = build(db, client_a, fake_diagnosis([sug("S-1")], skipped=[{"id": "A-1", "reason": "No LLM visibility run has been done."}]), page=COLL)
    by = {p["id"]: p for p in out["parts"]}
    assert by["A-1"]["title"] == "Answer “Best natural sunscreen for sensitive skin?” at the top of the page"
    assert "Best natural sunscreen for sensitive skin?" in " ".join(by["S-2"]["steps"])
    assert [p["id"] for p in out["parts"]] == ["A-1", "S-1", "S-2"]


def test_a_rules_own_faq_markup_prescription_counts_as_the_faq_part(db, client_a):
    data(db, client_a)
    watch(db, client_a)
    v7 = {"action_id": "V-7", "title": "Mark up the FAQ", "why": "It has one", "steps": ["Add FAQPage"], "evidence": []}
    out = build(db, client_a, fake_diagnosis([sug("A-1"), sug("S-1")], prescriptions=[v7]), page=COLL)
    assert [p["id"] for p in out["parts"]] == ["A-1", "S-1", "V-7"] and out["parts"][2]["confirmed_by_rule"] is True


def test_a_page_that_does_not_show_for_the_topic_or_cannot_be_read_is_refused(db, client_a):
    data(db, client_a)
    watch(db, client_a)
    assert "does not show for this topic" in build(db, client_a, fake_diagnosis([]), page="https://shop.example/other")["error"]
    unreadable = lambda s, u, r, e: {"read": {"ok": False, "error": "timed out"}}
    assert "could not be read: timed out" in build(db, client_a, unreadable)["error"]
    assert "No page shows" in ga.build(db, client_a, SEP, "nothing here", page=None, diagnose=unreadable, evidence_for=lambda s, u: {})["error"]


def test_the_draft_is_one_task_with_every_part_as_a_headed_checklist(db, client_a):
    data(db, client_a)
    watch(db, client_a, prompt="")
    bundle = build(db, client_a, fake_diagnosis([sug("A-1", steps=("Write the answer",), evidence=("quoted",)), sug("S-1", steps=("Say it",))]), page=COLL)
    d = ga.draft(bundle, "2026-10")
    assert d["kind"] == "growth_action" and d["rule_id"] == "GA" and d["search"] == "natural sunscreen" and d["page"] == COLL
    assert d["title"] == "Growth action: /collections/spf for “natural sunscreen”"
    assert d["steps"] == ["# 1. Answer the question at the top", "Write the answer", "# 2. Use the phrasing people search", "Say it"]
    assert "2 parts" in d["why"] and "Answer the question at the top: quoted" in d["evidence"]


# ── the plan counts pages ────────────────────────────────────────────────────


def test_a_growth_action_and_other_tasks_on_one_page_are_one_against_the_allowance(client, db, client_a, admin_user):
    h = client_header(client_a.id, admin_user.email)
    base = {"month": "2026-10", "search": "natural sunscreen", "title": "t"}
    r1 = client.post("/v2/engine/tasks", json={**base, "kind": "growth_action", "rule_id": "GA", "page": COLL, "steps": ["# 1. Answer", "Write it"]}, headers=h)
    r2 = client.post("/v2/engine/tasks", json={**base, "kind": "suggestion", "rule_id": "S-5", "page": COLL}, headers=h)
    r3 = client.post("/v2/engine/tasks", json={**base, "kind": "growth_action", "rule_id": "GA", "page": PROD}, headers=h)
    assert r1.json()["allowance"]["used"] == 1 and r2.json()["allowance"]["used"] == 1 and r3.json()["allowance"]["used"] == 2
    assert client.get("/v2/engine/tasks?month=2026-10", headers=h).json()["allowance"]["used"] == 2
    # Dropping every task on a page gives it back.
    for t in client.get("/v2/engine/tasks?month=2026-10", headers=h).json()["tasks"]:
        if t["page"] == PROD:
            client.patch(f"/v2/engine/tasks/{t['id']}", json={"status": "dropped"}, headers=h)
    assert client.get("/v2/engine/tasks?month=2026-10", headers=h).json()["allowance"]["used"] == 1


def test_the_teamwork_text_of_a_growth_action_lists_each_part_with_its_checklist(client, db, client_a, admin_user):
    h = client_header(client_a.id, admin_user.email)
    task = client.post(
        "/v2/engine/tasks",
        json={"month": "2026-10", "search": "natural sunscreen", "title": "Growth action: /collections/spf", "kind": "growth_action",
              "rule_id": "GA", "page": COLL, "steps": ["# 1. Answer the question at the top", "Write it", "# 2. Add a short FAQ", "Add three"]},
        headers=h,
    ).json()["task"]
    text = client.get(f"/v2/engine/tasks/{task['id']}/text", headers=h).json()["text"]
    assert "1. Answer the question at the top\n  [ ] Write it" in text and "2. Add a short FAQ\n  [ ] Add three" in text
    assert "A growth action from the Decision engine" in text


def test_the_routes_choose_pages_and_refuse_a_bad_month(client, db, client_a, admin_user):
    data(db, client_a)
    watch(db, client_a)
    h = client_header(client_a.id, admin_user.email)
    assert client.get("/v2/engine/topic-pages?keyword=natural sunscreen&month=2026-09", headers=h).json()["recommended"]
    assert client.get("/v2/engine/topic-pages?keyword=x&month=bad", headers=h).status_code == 400


# ── a candidate's topic ──────────────────────────────────────────────────────


def test_a_search_takes_the_longest_watchlist_keyword_it_contains_else_it_is_its_own_topic(db, client_a):
    watch(db, client_a, keyword="natural sunscreen")
    got = ga.resolve_topic(db, client_a, SEP, "best natural sunscreen spf 30", PROD)
    assert got == {"keyword": "natural sunscreen", "source": "the watchlist keyword it contains"}
    assert ga.resolve_topic(db, client_a, SEP, "natural self tanner", PROD) == {"keyword": "natural self tanner", "source": "the search itself"}


def test_a_page_from_the_traffic_or_leads_list_takes_its_top_non_brand_search(db, client_a):
    client_a.client_name = "Shop Example"
    db.commit()
    watch(db, client_a, keyword="natural sunscreen")
    gsc(db, client_a, "shop example spf 30", PROD, 9000)  # brand: ignored
    gsc(db, client_a, "natural sunscreen spf 30", PROD, 400)
    gsc(db, client_a, "mineral sunscreen", PROD, 100)
    db.commit()
    got = ga.resolve_topic(db, client_a, SEP, "(page)", PROD)
    assert got["keyword"] == "natural sunscreen" and "top search" in got["source"]
    assert ga.resolve_topic(db, client_a, SEP, "(page)", "https://shop.example/none")["keyword"] is None


def test_the_route_returns_the_topic_and_its_pages(client, db, client_a, admin_user):
    data(db, client_a)
    watch(db, client_a)
    h = client_header(client_a.id, admin_user.email)
    out = client.get(f"/v2/engine/topic-for?search=natural sunscreen spf 30&page={PROD}&month=2026-09", headers=h).json()
    assert out["keyword"] == "natural sunscreen" and out["pages"]["recommended"]
    none = client.get("/v2/engine/topic-for?search=(page)&page=https://shop.example/none&month=2026-09", headers=h).json()
    assert none["keyword"] is None and none["pages"] is None


def test_every_rule_that_fired_is_in_the_action_and_replaces_its_unconfirmed_twin(db, client_a):
    data(db, client_a)
    watch(db, client_a, prompt="")
    v4 = {"action_id": "V-4", "title": "Add internal links to the page that owns “natural sunscreen”", "why": "0 links", "steps": ["Link from the donors"], "evidence": ["0 editorial inbound"]}
    out = build(db, client_a, fake_diagnosis([sug("S-1")], prescriptions=[v4]), page=COLL)
    assert [p["id"] for p in out["parts"]] == ["S-1", "V-4"]
    v4_part = out["parts"][1]
    assert v4_part["confirmed_by_rule"] is True and v4_part["name"] == "Add internal links"


def test_a_page_level_suggestion_from_traffic_or_leads_joins_the_action_when_it_is_the_candidates_page(db, client_a):
    data(db, client_a)
    watch(db, client_a, prompt="")
    leads_s = sug("L-S2", title="Check the way to an order", steps=("Look at the next step",))
    out = ga.build(db, client_a, SEP, "natural sunscreen", page=COLL, diagnose=fake_diagnosis([sug("S-1")]), evidence_for=lambda s, u: {}, extra_suggestions=[leads_s])
    assert [p["id"] for p in out["parts"]] == ["S-1", "L-S2"] and out["parts"][1]["name"] == "Check the way to an order"
