from types import SimpleNamespace

import pytest

from app.core.settings import get_settings
from app.llm_visibility import analyze, platforms, report, runner
from app.models.client import Client
from app.models.llm_visibility import LlmResponse, LlmRun
from app.models.watchlist import WatchlistBucket, WatchlistKeyword

CONFIG = analyze.BrandConfig(
    "Absolutely Natural", ["absolutely natural"], "absolutelynatural.com", [("Rival", ["rival"]), ("Other Co", ["other co"])]
)


# ── analyze ──────────────────────────────────────────────────────────────────


def test_a_short_pattern_matches_whole_words_only():
    assert analyze.find_word("a small shop", "sma") == -1
    assert analyze.find_word("ask sma about it", "sma") == 4
    assert analyze.find_word("sma.", "sma") == 0


def test_brand_position_competitors_and_rank_are_read_from_the_answer():
    text = "Rival is popular. Absolutely Natural makes mineral sunscreen. Other Co too."
    a = analyze.analyze(text, [], CONFIG)
    assert a.brand_mentioned and a.brand_rank == 2
    assert a.all_brands_ordered == ["Rival", "Absolutely Natural", "Other Co"]
    assert a.competitors_mentioned == ["Rival", "Other Co"]
    assert analyze.visibility_type(a) == "Mentioned"


def test_a_domain_in_the_text_or_a_citation_counts_as_a_citation():
    text = "See https://absolutelynatural.com/collections/spf for details."
    a = analyze.analyze(text, [], CONFIG)
    assert a.url_cited and a.cited_urls == ["https://absolutelynatural.com/collections/spf"]
    cited = analyze.analyze("nothing", ["https://x.com", "https://absolutelynatural.com/a"], CONFIG)
    assert cited.url_cited and cited.position == "Source #2 of 2"
    assert analyze.visibility_type(cited) == "Cited"
    both = analyze.analyze("Absolutely Natural " + text, [], CONFIG)
    assert analyze.visibility_type(both) == "Cited + Mentioned"


def test_an_answer_that_names_nobody_is_not_visible():
    a = analyze.analyze("Use any mineral sunscreen.", [], CONFIG)
    assert analyze.visibility_type(a) == "Not visible" and a.brand_rank == 0 and a.position == "Not mentioned"


# ── report ───────────────────────────────────────────────────────────────────


def row(query, platform, vis, cluster="Sun", comps=(), rank=0, mentioned=None, cited=None, other=()):
    return SimpleNamespace(
        query_text=query, platform=platform, visibility_type=vis, topic_cluster=cluster, keyword=query,
        brand_mentioned=vis in ("Mentioned", "Cited + Mentioned") if mentioned is None else mentioned,
        url_cited=vis in ("Cited", "Cited + Mentioned") if cited is None else cited,
        competitors_mentioned=list(comps), brand_rank=rank, other_brands_mentioned=list(other),
    )


def test_errors_are_never_counted():
    rows = [row("q", "ChatGPT", "Mentioned"), row("q", "Gemini", "Error")]
    s = report.summary(rows, None)
    assert s["responses"] == 1 and s["visibility_rate"]["current"] == 1.0


def test_platform_deltas_compare_with_the_previous_run():
    cur = [row("q1", "ChatGPT", "Mentioned"), row("q2", "ChatGPT", "Not visible")]
    prev = [row("q1", "ChatGPT", "Not visible"), row("q2", "ChatGPT", "Not visible")]
    p = report.platform_deltas(cur, prev)[0]
    assert p["visibility_rate"] == {"current": 0.5, "previous": 0.0, "delta": 0.5}
    assert p["mentions"]["delta"] == 1
    assert report.platform_deltas(cur, None)[0]["visibility_rate"]["previous"] is None


def test_share_of_voice_is_per_topic_cluster_and_includes_competitors():
    cur = [row("q1", "ChatGPT", "Mentioned", comps=["Rival"]), row("q2", "ChatGPT", "Not visible", comps=["Rival"])]
    sov = {r["brand"]: r for r in report.share_of_voice(cur, None, "Absolutely Natural")}
    assert sov["Absolutely Natural"]["share"]["current"] == 0.5 and sov["Absolutely Natural"]["is_self"]
    assert sov["Rival"]["share"]["current"] == 1.0 and sov["Rival"]["mentions"]["previous"] is None


def test_the_brand_is_listed_in_every_topic_even_when_no_answer_named_it():
    cur = [row("q1", "ChatGPT", "Not visible", comps=["Rival"])]
    sov = {r["brand"]: r for r in report.share_of_voice(cur, None, "Absolutely Natural")}
    assert sov["Absolutely Natural"]["share"]["current"] == 0.0 and sov["Absolutely Natural"]["is_self"]
    assert sov["Rival"]["share"]["current"] == 1.0


def test_query_movers_rank_the_biggest_changes():
    cur = [row("up", "ChatGPT", "Cited + Mentioned"), row("down", "ChatGPT", "Not visible"), row("same", "ChatGPT", "Mentioned")]
    prev = [row("up", "ChatGPT", "Not visible"), row("down", "ChatGPT", "Mentioned"), row("same", "ChatGPT", "Mentioned")]
    m = report.movers(report.query_summary(cur, prev))
    assert [r["query"] for r in m["improved"]] == ["up"] and m["improved"][0]["change"] == 2
    assert [r["query"] for r in m["declined"]] == ["down"] and m["declined"][0]["change"] == -1


def test_a_first_run_has_no_movers():
    assert report.movers(report.query_summary([row("q", "ChatGPT", "Mentioned")], None)) == {"improved": [], "declined": []}


# ── runner ───────────────────────────────────────────────────────────────────


def _watch(db, client: Client, pairs):
    b = WatchlistBucket(client_id=client.id, name="Sunscreen", name_key="sunscreen", sort_order=0)
    db.add(b)
    db.flush()
    for kw, prompt in pairs:
        db.add(WatchlistKeyword(client_id=client.id, bucket_id=b.id, keyword=kw, keyword_key=kw, paired_ai_prompt=prompt))
    db.commit()


def test_prompts_come_from_the_watchlist_and_blank_or_repeated_ones_are_dropped(db, client_a):
    _watch(db, client_a, [("a", "Best  mineral sunscreen?"), ("b", "  "), ("c", None), ("d", "best mineral sunscreen?")])
    items = runner.prompts_for(db, client_a)
    assert [i["prompt"] for i in items] == ["Best mineral sunscreen?"] and items[0]["cluster"] == "Sunscreen"


def test_a_brand_is_spotted_by_its_name_and_domain_and_competitors_by_theirs(db, client_a):
    client_a.client_name = "Absolutely Natural"
    client_a.domain = "absolutelynatural.com"
    client_a.competitor_domains = ["https://www.mineralfusion.com/shop"]
    db.commit()
    config = runner.brand_config(db, client_a)
    assert config.brand_patterns == ["absolutely natural", "absolutelynatural", "absolutelynatural.com"]
    assert config.competitors == [("Mineralfusion", ["mineralfusion", "mineralfusion.com"])]


@pytest.fixture
def keys(monkeypatch):
    s = get_settings()
    for name in ("openai_api_key", "perplexity_api_key"):
        monkeypatch.setattr(s, name, "k")
    monkeypatch.setattr(s, "gemini_api_key", "")
    monkeypatch.setattr(s, "anthropic_api_key", "")


def test_a_run_asks_each_prompt_on_each_keyed_platform_and_keeps_every_answer(db, client_a, keys, monkeypatch):
    client_a.client_name, client_a.domain = "Absolutely Natural", "absolutelynatural.com"
    db.commit()
    _watch(db, client_a, [("a", "p1"), ("b", "p2")])

    def fake(platform, prompt):
        if platform == "perplexity" and prompt == "p2":
            raise platforms.PlatformError("boom")
        return platforms.PlatformAnswer(text="Absolutely Natural is good.", input_tokens=100, output_tokens=50)

    monkeypatch.setattr(platforms, "ask", fake)
    run = runner.run_for_client(db, client_a, triggered_by="test")
    assert run.status == "completed" and run.total_calls == 4 and run.total_errors == 1
    rows = db.query(LlmResponse).filter(LlmResponse.run_id == run.id).all()
    assert len(rows) == 4
    assert {r.platform for r in rows} == {"ChatGPT", "Perplexity"}
    bad = next(r for r in rows if r.visibility_type == "Error")
    assert bad.platform == "Perplexity" and "boom" in bad.error
    good = next(r for r in rows if r.visibility_type == "Mentioned")
    assert good.topic_cluster == "Sunscreen" and good.full_response == "Absolutely Natural is good."
    assert float(run.estimated_cost_usd) > 0


def test_a_run_with_no_prompts_or_no_keys_says_so(db, client_a, monkeypatch):
    with pytest.raises(runner.NothingToRun, match="no paired AI prompts"):
        runner.run_for_client(db, client_a)
    _watch(db, client_a, [("a", "p1")])
    for name in ("openai_api_key", "perplexity_api_key", "gemini_api_key", "anthropic_api_key"):
        monkeypatch.setattr(get_settings(), name, "")
    with pytest.raises(runner.NothingToRun, match="No AI platform"):
        runner.run_for_client(db, client_a)
    assert db.query(LlmRun).count() == 0


# ── routes and schedule ──────────────────────────────────────────────────────

from tests.conftest import client_header  # noqa: E402


def test_settings_show_what_a_run_will_use_and_can_be_saved(client, db, client_a, admin_user, keys):
    client_a.client_name, client_a.domain = "Absolutely Natural", "absolutelynatural.com"
    client_a.competitor_domains = ["mineralfusion.com"]
    db.commit()
    _watch(db, client_a, [("a", "p1")])
    h = client_header(client_a.id, admin_user.email)
    got = client.get("/v2/llm/settings", headers=h).json()
    assert got["prompts"] == 1 and got["clusters"] == ["Sunscreen"] and got["calls_per_run"] == 2
    assert [p["name"] for p in got["platforms"] if p["enabled"]] == ["ChatGPT", "Perplexity"]

    saved = client.put(
        "/v2/llm/settings",
        json={"brand_name": "Absolutely Natural", "brand_patterns": ["Absolutely Natural", "AN Skincare"],
              "competitors": [{"domain": "mineralfusion.com", "name": "Mineral Fusion", "patterns": ["Mineral Fusion"]}]},
        headers=h,
    )
    assert saved.status_code == 200
    assert saved.json()["brand_patterns"] == ["absolutely natural", "an skincare"]
    assert saved.json()["competitors"][0]["name"] == "Mineral Fusion"
    refused = client.put(
        "/v2/llm/settings",
        json={"brand_name": "x", "brand_patterns": ["x"], "competitors": [{"domain": "other.com", "name": "O", "patterns": ["o"]}]},
        headers=h,
    )
    assert refused.status_code == 400


def test_a_run_is_queued_once_and_refused_with_nothing_to_ask(client, db, client_a, admin_user, keys):
    h = client_header(client_a.id, admin_user.email)
    assert client.post("/v2/llm/run", headers=h).status_code == 400
    _watch(db, client_a, [("a", "p1")])
    assert client.post("/v2/llm/run", headers=h).status_code == 202
    assert client.post("/v2/llm/run", headers=h).status_code == 409


def test_the_overview_is_empty_before_a_run_and_a_run_is_not_readable_from_another_client(client, db, client_a, client_b, admin_user, keys, monkeypatch):
    h = client_header(client_a.id, admin_user.email)
    assert client.get("/v2/llm/overview", headers=h).json()["run"] is None
    _watch(db, client_a, [("a", "p1")])
    monkeypatch.setattr(platforms, "ask", lambda platform, prompt: platforms.PlatformAnswer(text="nothing", input_tokens=1, output_tokens=1))
    run = runner.run_for_client(db, client_a)
    out = client.get("/v2/llm/overview", headers=h).json()
    assert out["run"]["id"] == str(run.id) and out["summary"]["responses"] == 2 and out["previous_run"] is None
    assert len(client.get(f"/v2/llm/runs/{run.id}/responses", headers=h).json()) == 2
    other = client_header(client_b.id, admin_user.email)
    assert client.get(f"/v2/llm/runs/{run.id}/responses", headers=other).status_code == 404


def test_the_schedule_queues_clients_with_prompts_and_not_twice(db, client_a, keys, monkeypatch):
    from app.services import daily_sync

    assert daily_sync.enqueue_due_llm_runs(db)["due"] == 0  # no prompts yet
    _watch(db, client_a, [("a", "p1")])
    assert daily_sync.enqueue_due_llm_runs(db)["enqueued"] == 1
    assert daily_sync.enqueue_due_llm_runs(db)["enqueued"] == 0
    for name in ("openai_api_key", "perplexity_api_key"):
        monkeypatch.setattr(get_settings(), name, "")
    assert daily_sync.enqueue_due_llm_runs(db)["due"] == 0


def test_gemini_is_asked_without_thinking_so_the_answer_is_not_cut_off(monkeypatch):
    sent = {}

    def fake_post(url, *, headers, body, label):
        sent.update(body)
        return {"candidates": [{"content": {"parts": [{"text": "ok"}]}}], "usageMetadata": {}}

    monkeypatch.setattr(platforms, "_post", fake_post)
    assert platforms._gemini("hi", "k").text == "ok"
    assert sent["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 0}


def test_extra_prompts_join_the_run_under_their_own_topic_and_are_never_asked_twice(client, db, client_a, admin_user, keys):
    _watch(db, client_a, [("a", "Best mineral sunscreen?")])
    h = client_header(client_a.id, admin_user.email)
    added = client.post(
        "/v2/llm/prompts",
        json={"prompts": [
            {"prompt": "Is Absolutely  Natural any good?", "topic_cluster": "Brand check"},
            {"prompt": "best mineral sunscreen?", "topic_cluster": "Niche"},  # already a watchlist prompt
            {"prompt": "is absolutely natural any good?", "topic_cluster": "Niche"},  # same as the first
        ]},
        headers=h,
    ).json()
    assert added["added"] == 1 and added["skipped"] == 2
    items = runner.prompts_for(db, client_a)
    assert [(i["prompt"], i["cluster"], i["extra"]) for i in items] == [
        ("Best mineral sunscreen?", "Sunscreen", False),
        ("Is Absolutely Natural any good?", "Brand check", True),
    ]
    assert added["settings"]["prompts"] == 2 and added["settings"]["extra_prompts"][0]["topic_cluster"] == "Brand check"


def test_an_extra_prompt_can_be_removed_but_not_by_another_client(client, db, client_a, client_b, admin_user, keys):
    h = client_header(client_a.id, admin_user.email)
    client.post("/v2/llm/prompts", json={"prompts": [{"prompt": "A question?", "topic_cluster": "Niche"}]}, headers=h)
    pid = client.get("/v2/llm/settings", headers=h).json()["extra_prompts"][0]["id"]
    assert client.delete(f"/v2/llm/prompts/{pid}", headers=client_header(client_b.id, admin_user.email)).status_code == 404
    assert client.delete(f"/v2/llm/prompts/{pid}", headers=h).json()["extra_prompts"] == []


# ── prompts that name the brand ──────────────────────────────────────────────


def test_a_prompt_that_says_the_brand_is_asked_by_name_and_only_a_citation_counts():
    assert analyze.names_brand("Is Absolutely Natural sunscreen any good?", CONFIG)
    assert not analyze.names_brand("Which mineral sunscreen is gentle for a toddler?", CONFIG)
    echoed = analyze.analyze("Absolutely Natural? I have no information on that brand.", [], CONFIG)
    assert echoed.brand_mentioned
    assert analyze.visibility_type(echoed, asked_by_name=True) == "Named in prompt"
    cited = analyze.analyze("See https://absolutelynatural.com/p", [], CONFIG)
    assert analyze.visibility_type(cited, asked_by_name=True) == "Cited"


def named(query, platform, vis, cited):
    r = row(query, platform, vis, cited=cited)
    r.asked_by_name = True
    return r


def test_named_prompts_stay_out_of_the_visibility_numbers_and_get_their_own_check():
    rows = [
        row("category q", "ChatGPT", "Not visible"),
        named("Is Absolutely Natural good?", "ChatGPT", "Named in prompt", False),
        named("Is Absolutely Natural good?", "Perplexity", "Cited", True),
        named("Is Absolutely Natural good?", "Gemini", "Error", None),
    ]
    assert report.summary(rows, None)["responses"] == 1 and report.summary(rows, None)["mentions"]["current"] == 0
    assert [r["query"] for r in report.query_summary(rows, None)] == ["category q"]
    check = report.brand_check(rows)
    assert check["platforms"] == [{"platform": "ChatGPT", "answers": 1, "site_cited": 0}, {"platform": "Perplexity", "answers": 1, "site_cited": 1}]
    assert check["prompts"][0]["by_platform"] == {"ChatGPT": "Not cited", "Perplexity": "Cited"}


def test_a_run_marks_prompts_that_name_the_brand(db, client_a, keys, monkeypatch):
    client_a.client_name, client_a.domain = "Absolutely Natural", "absolutelynatural.com"
    db.commit()
    _watch(db, client_a, [("a", "Is Absolutely Natural any good?"), ("b", "Best mineral sunscreen?")])
    monkeypatch.setattr(platforms, "ask", lambda platform, prompt: platforms.PlatformAnswer(text="Absolutely Natural, I know little.", input_tokens=1, output_tokens=1))
    run = runner.run_for_client(db, client_a)
    rows = {(r.query_text, r.platform): r for r in db.query(LlmResponse).filter(LlmResponse.run_id == run.id)}
    asked = rows[("Is Absolutely Natural any good?", "ChatGPT")]
    assert asked.asked_by_name is True and asked.visibility_type == "Named in prompt"
    plain = rows[("Best mineral sunscreen?", "ChatGPT")]
    assert plain.asked_by_name is False and plain.visibility_type == "Mentioned"


def test_a_run_is_due_a_week_after_the_last_one_and_not_before(db, client_a, keys):
    from datetime import datetime, timedelta, timezone

    from app.services import daily_sync

    _watch(db, client_a, [("a", "p1")])
    last = LlmRun(client_id=client_a.id, status="completed", started_at=datetime.now(timezone.utc) - timedelta(days=5))
    db.add(last)
    db.commit()
    assert daily_sync.enqueue_due_llm_runs(db)["due"] == 0, "five days is too soon"
    last.started_at = datetime.now(timezone.utc) - timedelta(days=8)
    db.commit()
    assert daily_sync.enqueue_due_llm_runs(db)["enqueued"] == 1, "eight days is a week and more"


def _month_run(db, client, when, answers):
    """A completed run on a date, with answers as (cluster, brand named by us, competitors)."""
    from datetime import datetime, timezone

    run = LlmRun(client_id=client.id, status="completed", started_at=datetime(*when, 12, tzinfo=timezone.utc))
    db.add(run)
    db.flush()
    for i, (cluster, named, rivals) in enumerate(answers):
        db.add(LlmResponse(run_id=run.id, client_id=client.id, query_text=f"q{i}", topic_cluster=cluster, platform="openai", visibility_type="Mentioned" if named else "Not visible",
                           brand_mentioned=named, url_cited=False, competitors_mentioned=rivals, full_response=f"answer {i}"))
    return run


def test_share_of_voice_over_a_month_pools_every_run_and_shows_how_each_run_differed(client, db, client_a, admin_user):
    h = client_header(client_a.id, admin_user.email)
    brand = client.get("/v2/llm/overview", headers=h).json()["brand"]
    _month_run(db, client_a, (2026, 9, 20), [("SPF", False, ["Badger"]), ("SPF", False, ["Badger"])])                     # September: not named at all
    _month_run(db, client_a, (2026, 10, 2), [("SPF", True, ["Badger"]), ("SPF", False, ["Badger"])])                      # 1 of 2
    _month_run(db, client_a, (2026, 10, 9), [("SPF", True, []), ("SPF", True, ["Badger"]), ("SPF", False, ["Badger"]), ("SPF", False, [])])  # 2 of 4
    db.commit()
    out = client.get("/v2/llm/share-of-voice", headers=h).json()
    assert out["month"] == "2026-10" and out["months"] == ["2026-10", "2026-09"] and len(out["runs"]) == 2 and out["previous_runs"] == 1 and out["answers"] == 6
    rows = {r["brand"]: r for r in out["share_of_voice"]}
    assert rows[brand]["share"]["current"] == 0.5 and rows[brand]["mentions"]["current"] == 3 and rows[brand]["responses"] == 6, "3 of the month's 6 answers"
    assert rows[brand]["share"]["previous"] == 0.0 and rows[brand]["share"]["delta"] == 0.5
    assert rows[brand]["by_run"] == [0.5, 0.5] and rows["Badger"]["by_run"] == [1.0, 0.5] and round(rows["Badger"]["share"]["current"], 4) == 0.6667
    september = client.get("/v2/llm/share-of-voice", params={"month": "2026-09"}, headers=h).json()
    assert september["answers"] == 2 and september["previous_runs"] == 0 and next(r for r in september["share_of_voice"] if r["brand"] == brand)["share"]["previous"] is None
    answers = client.get("/v2/llm/share-of-voice/responses", params={"month": "2026-10"}, headers=h).json()
    assert len(answers) == 6 and answers[0]["run_started_at"].startswith("2026-10-09") and answers[-1]["run_started_at"].startswith("2026-10-02")
    assert client.get("/v2/llm/share-of-voice", params={"month": "October"}, headers=h).status_code == 400


def test_a_client_with_no_runs_has_an_empty_month_view(client, db, client_a, admin_user):
    out = client.get("/v2/llm/share-of-voice", headers=client_header(client_a.id, admin_user.email)).json()
    assert out["month"] is None and out["months"] == [] and out["share_of_voice"] == []
