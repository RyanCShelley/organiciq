"""The content optimizer: what it reads from a page, and what it keeps of what the model returns."""

from __future__ import annotations

import json
from datetime import date, timedelta
from uuid import UUID

import pytest

from app.api.routers.v2_optimizer import DraftIn
from app.core.settings import get_settings
from app.models.gsc import FactGscQueryPage
from app.models.schema_tools import ContentModelRun
from app.schema_tools import llm
from app.services import content_optimizer as co
from app.services.page_diagnostic import Fetched
from tests.conftest import client_header

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


def test_pasted_text_is_read_the_same_way():
    spot = co.spot_from_text("Slab leak detection\n\nWe find leaks under your slab with listening gear and thermal imaging, no digging first.\n\nHow long does it take?\n\nDoes it damage floors?\n\nNo.")
    assert spot["h1"] == "Slab leak detection" and spot["opening"].startswith("We find leaks") and spot["has_faq"] is True and len(spot["faq_questions"]) == 2


def _enable_optimizer(monkeypatch, reply_or_fn, seen: dict, *, body: str = PAGE):
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "k")
    monkeypatch.setattr(co, "read_page", lambda url, domain, *_: Fetched(status=200, final_url=url, headers={}, body=body))

    def call(depth, prompt, **kw):
        seen["prompt"] = prompt
        seen["depth"] = depth
        seen["calls"] = seen.get("calls", 0) + 1
        reply = reply_or_fn(depth, prompt) if callable(reply_or_fn) else reply_or_fn
        return reply, 1200, 300

    monkeypatch.setattr(llm, "call", call)


def _valid_reply(kind: str, keyword: str) -> str:
    if kind == "opening":
        return json.dumps({
            "diagnosis": f"The opening does not mention {keyword}.",
            "options": [{"text": f"New opening targeting {keyword} for local homeowners.", "serves": [keyword], "why": "Answers the target search immediately."}],
        })
    if kind == "terms":
        return json.dumps({
            "edits": [{
                "before": "A tech walks the house and listens at each fixture.",
                "after": f"A tech walks the house and listens at each fixture for {keyword}.",
                "terms": [keyword],
                "why": "Fits the existing sentence naturally.",
            }],
            "left_out": [],
        })
    return json.dumps({
        "items": [{"question": f"What does {keyword} involve", "answer": "Our licensed crew inspects with electronic listening gear and thermal imaging.", "from_search": keyword}],
    })


def test_draft_keyword_validation_trims_treats_whitespace_as_none_and_rejects_over_max(client, db, client_a, admin_user, monkeypatch):
    seen: dict = {}
    _enable_optimizer(monkeypatch, lambda _d, _p: _valid_reply("opening", "foundation crack repair"), seen)
    hd = client_header(client_a.id, admin_user.email)
    url = f"https://{client_a.domain}/validation-page"

    # (a) Trims and collapses internal whitespace
    res_ok = client.post("/v2/optimizer/draft", json={"url": url, "kind": "opening", "depth": "quick", "keyword": "  foundation   crack   repair  "}, headers=hd)
    assert res_ok.status_code == 202
    run_id = UUID(res_ok.json()["id"])
    db.expire_all()
    row = db.get(ContentModelRun, run_id)
    assert row is not None and row.status == "done"
    assert row.payload["keyword"] == "foundation crack repair"

    # (b) Whitespace-only keyword collapses to None -> zero-GSC page fails cleanly
    res_blank = client.post("/v2/optimizer/draft", json={"url": f"https://{client_a.domain}/blank-kw", "kind": "opening", "depth": "quick", "keyword": "   \t\n  "}, headers=hd)
    assert res_blank.status_code == 202
    db.expire_all()
    blank_row = db.get(ContentModelRun, UUID(res_blank.json()["id"]))
    assert blank_row is not None and blank_row.status == "failed"
    assert "no searches with enough data" in (blank_row.error or "")

    # (c) Over-max keyword length returns 422
    max_len = DraftIn.model_fields["keyword"].metadata[0].max_length
    res_long = client.post("/v2/optimizer/draft", json={"url": url, "kind": "opening", "depth": "quick", "keyword": "k" * (max_len + 1)}, headers=hd)
    assert res_long.status_code == 422


@pytest.mark.parametrize("kind", ["opening", "terms", "faq"])
def test_adhoc_keyword_runs_end_to_end_with_zero_gsc_and_no_watchlist(client, db, client_a, admin_user, monkeypatch, kind):
    seen: dict = {}
    keyword = "foundation crack repair"
    _enable_optimizer(monkeypatch, _valid_reply(kind, keyword), seen)
    hd = client_header(client_a.id, admin_user.email)
    raw_url = f"https://www.{client_a.domain}/one-off-page/"
    norm_url = f"https://{client_a.domain}/one-off-page"

    # Verify start() + latest() expose keyword while status is "running"
    running_row = co.start(db, client_a, kind, norm_url, "quick", admin_user.email, keyword=f"  {keyword}  ")
    running_latest = co.latest(db, client_a, kind, norm_url)
    assert running_latest is not None and running_latest["status"] == "running" and running_latest["keyword"] == keyword
    db.delete(running_row)
    db.commit()

    res = client.post("/v2/optimizer/draft", json={"url": raw_url, "kind": kind, "depth": "quick", "keyword": f"  {keyword}  "}, headers=hd)
    assert res.status_code == 202
    run_id = UUID(res.json()["id"])

    db.expire_all()
    row = db.get(ContentModelRun, run_id)
    assert row is not None
    assert row.status == "done"
    assert row.error is None
    assert row.key == norm_url
    assert row.payload["keyword"] == keyword
    assert row.payload["searches_used"] == 1

    page_res = client.get("/v2/optimizer/page", params={"url": norm_url}, headers=hd)
    assert page_res.status_code == 200
    body = page_res.json()
    assert body["searches"] == [] and body["searches_total"] == 0
    draft = body["drafts"][kind]
    assert draft["status"] == "done" and draft["keyword"] == keyword
    if kind == "opening":
        assert len(draft["options"]) == 1
    elif kind == "terms":
        assert len(draft["edits"]) == 1
        assert f"- {keyword}" in seen["prompt"]
    else:
        assert len(draft["items"]) == 1 and draft["markup"]

    assert keyword in seen["prompt"]
    assert "position None" not in seen["prompt"]
    assert "no Search Console data" in seen["prompt"]


def test_adhoc_keyword_with_pasted_text_and_zero_gsc_skips_live_read(client, db, client_a, admin_user, monkeypatch):
    seen: dict = {}
    keyword = "crawl space leak"
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "k")
    monkeypatch.setattr(co, "read_page", lambda *args: (_ for _ in ()).throw(AssertionError("should not fetch live page")))
    monkeypatch.setattr(
        llm,
        "call",
        lambda depth, prompt, **kw: (
            seen.update({"prompt": prompt, "depth": depth}),
            _valid_reply("opening", keyword),
            900,
            200,
        )[1:],
    )
    hd = client_header(client_a.id, admin_user.email)
    url = f"https://{client_a.domain}/pasted-one-off"
    pasted = "Crawl Space Inspections\n\nOur licensed technicians inspect damp crawl spaces and pinpoint active foundation moisture before damage spreads."

    res = client.post("/v2/optimizer/draft", json={"url": url, "kind": "opening", "depth": "deep", "text": pasted, "keyword": keyword}, headers=hd)
    assert res.status_code == 202

    page_res = client.get("/v2/optimizer/page", params={"url": url}, headers=hd)
    assert page_res.status_code == 200
    draft = page_res.json()["drafts"]["opening"]
    assert draft["status"] == "done"
    assert draft["source"]["kind"] == "pasted"
    assert draft["keyword"] == keyword
    assert keyword in seen["prompt"]
    assert "position None" not in seen["prompt"]


def test_adhoc_keyword_combines_with_existing_gsc_queries_without_crashing(client, db, client_a, admin_user, monkeypatch):
    url = f"https://{client_a.domain}/combo"
    db.add(
        FactGscQueryPage(
            client_id=client_a.id,
            date=date.today() - timedelta(days=3),
            query="slab leak repair",
            raw_url=url,
            normalized_url=url,
            country="usa",
            device="DESKTOP",
            impressions=400,
            clicks=12,
            ctr=0.03,
            average_position=7.0,
        )
    )
    db.commit()
    hd = client_header(client_a.id, admin_user.email)

    # Subcase A: Distinct ad-hoc keyword prepended alongside existing GSC query
    seen_a: dict = {}
    _enable_optimizer(monkeypatch, _valid_reply("opening", "foundation crack repair"), seen_a)
    res_a = client.post("/v2/optimizer/draft", json={"url": url, "kind": "opening", "depth": "quick", "keyword": "foundation crack repair"}, headers=hd)
    assert res_a.status_code == 202
    draft_a = client.get("/v2/optimizer/page", params={"url": url}, headers=hd).json()["drafts"]["opening"]
    assert draft_a["status"] == "done"
    assert draft_a["keyword"] == "foundation crack repair"
    assert draft_a["searches_used"] == 2
    assert "foundation crack repair" in seen_a["prompt"]
    assert "slab leak repair" in seen_a["prompt"] and "400 impressions" in seen_a["prompt"]
    assert seen_a["prompt"].index("foundation crack repair") < seen_a["prompt"].index("slab leak repair")
    assert "position None" not in seen_a["prompt"]

    # Subcase B: Case-insensitive duplicate matches existing GSC query and keeps its real metrics
    seen_b: dict = {}
    _enable_optimizer(monkeypatch, _valid_reply("faq", "Slab Leak Repair"), seen_b)
    res_b = client.post("/v2/optimizer/draft", json={"url": url, "kind": "faq", "depth": "quick", "keyword": "Slab   Leak Repair"}, headers=hd)
    assert res_b.status_code == 202
    draft_b = client.get("/v2/optimizer/page", params={"url": url}, headers=hd).json()["drafts"]["faq"]
    assert draft_b["status"] == "done"
    assert draft_b["keyword"] == "Slab Leak Repair"
    assert draft_b["searches_used"] == 1
    assert seen_b["prompt"].lower().count("slab leak repair") >= 1
    assert "no Search Console ranking data yet" not in seen_b["prompt"]
    assert "400 impressions" in seen_b["prompt"]


def test_zero_gsc_without_adhoc_keyword_still_fails_cleanly(client, db, client_a, admin_user, monkeypatch):
    seen: dict = {}
    _enable_optimizer(monkeypatch, _valid_reply("opening", "unused"), seen)
    hd = client_header(client_a.id, admin_user.email)
    url = f"https://{client_a.domain}/no-gsc-no-kw"

    res = client.post("/v2/optimizer/draft", json={"url": url, "kind": "opening", "depth": "quick"}, headers=hd)
    assert res.status_code == 202
    run_id = UUID(res.json()["id"])

    db.expire_all()
    row = db.get(ContentModelRun, run_id)
    assert row is not None and row.status == "failed"
    assert "no searches with enough data in the last 90 days" in (row.error or "")

    draft = client.get("/v2/optimizer/page", params={"url": url}, headers=hd).json()["drafts"]["opening"]
    assert draft["status"] == "failed"
    assert "no searches with enough data in the last 90 days" in draft["error"]
    assert seen == {}


def test_optimizer_rows_page_block_and_missing_terms_handle_adhoc_keyword_unit():
    detail = {
        "title": "Foundation Repair",
        "searches": [
            {"query": "foundation crack repair", "impressions": 0, "clicks": 0, "position": None, "ad_hoc": True, "target": True},
            {"query": "slab leak detection", "impressions": None, "clicks": None, "position": 5.2},
        ],
    }
    rows_out = co._rows(detail)
    assert "position None" not in rows_out
    assert "no Search Console ranking data yet" in rows_out
    assert "slab leak detection" in rows_out and "0 impressions, 0 clicks" in rows_out

    assert co.missing_terms(detail, "Slab leak detection for homes") == ["foundation crack repair"]
    assert co.missing_terms(detail, "Foundation crack repair and slab leak detection") == []

    spot = co.read_spot(PAGE)
    terms_prompt = co.build_prompt(
        "terms",
        url="https://x.example/p",
        brand="X",
        detail={"title": "T", "searches": [detail["searches"][0]]},
        spot=spot,
        text="Foundation crack repair by licensed crews.",
        start="2026-08-01",
        end="2026-11-01",
        terms=[],
        keyword="foundation crack repair",
    )
    assert "Target keyword: foundation crack repair" in terms_prompt
    assert "already in page text; strengthen natural placement if helpful" in terms_prompt
    assert "TARGET KEYWORD (no Search Console data" in terms_prompt


def test_draft_keyword_strips_null_bytes_and_persists_cleanly(client, db, client_a, admin_user, monkeypatch):
    seen: dict = {}
    _enable_optimizer(monkeypatch, lambda _d, _p: _valid_reply("opening", "foobar"), seen)
    hd = client_header(client_a.id, admin_user.email)

    url_sanitized = f"https://{client_a.domain}/null-byte-sanitized"
    res_ok = client.post("/v2/optimizer/draft", json={"url": url_sanitized, "kind": "opening", "depth": "quick", "keyword": "foo\x00bar"}, headers=hd)
    assert res_ok.status_code == 202
    db.expire_all()
    row_ok = db.get(ContentModelRun, UUID(res_ok.json()["id"]))
    assert row_ok is not None and row_ok.status == "done"
    assert row_ok.payload["keyword"] == "foobar"

    page_res = client.get("/v2/optimizer/page", params={"url": url_sanitized}, headers=hd)
    assert page_res.status_code == 200
    assert page_res.json()["drafts"]["opening"]["keyword"] == "foobar"

    url_only_null = f"https://{client_a.domain}/null-byte-empty"
    res_empty = client.post("/v2/optimizer/draft", json={"url": url_only_null, "kind": "opening", "depth": "quick", "keyword": "\x00"}, headers=hd)
    assert res_empty.status_code == 202
    db.expire_all()
    row_empty = db.get(ContentModelRun, UUID(res_empty.json()["id"]))
    assert row_empty is not None and row_empty.status == "failed"
    assert "keyword" not in (row_empty.payload or {})
    assert "no searches with enough data" in (row_empty.error or "")

    direct_row = co.start(db, client_a, "opening", f"https://{client_a.domain}/direct-start", "quick", admin_user.email, keyword=("a" * 299) + " " + ("b" * 10) + "\x00")
    assert direct_row.payload["keyword"] == "a" * 299


def test_rows_without_position_or_adhoc_does_not_mislabel_target_keyword():
    non_adhoc = co._rows({"searches": [{"query": "weird gsc", "impressions": None, "clicks": None, "position": None}]})
    assert "weird gsc" in non_adhoc
    assert "no Search Console ranking data yet" in non_adhoc
    assert "(target keyword)" not in non_adhoc

    adhoc_only = co._rows({"searches": [{"query": "kw odd", "impressions": None, "clicks": None, "position": None, "ad_hoc": True}]})
    assert "“kw odd” (target keyword): no Search Console ranking data yet" in adhoc_only
