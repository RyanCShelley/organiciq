"""The executive summary: topics (Google beside AI answers), competitors, share of voice, clicks by month, and publishing it beside the monthly report."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from app.models.gsc import FactGscDaily, FactGscQueryPage
from app.models.llm_visibility import ClientLlmSettings, LlmResponse, LlmRun
from app.models.seranking import FactSerCompetitor, FactSerRanking, FactSerSiteSummary
from app.models.watchlist import WatchlistBucket, WatchlistKeyword
from app.services import consulting_exec as ce
from tests.conftest import client_header
from tests.test_portal_access import consult, viewer

SASE_Q = "Who are the best SASE vendors?"
AI_Q = "How do I secure AI use at work?"


def seed(db, client):
    db.add(ClientLlmSettings(client_id=client.id, brand_name="Acme"))
    sase = WatchlistBucket(client_id=client.id, name="SASE", name_key="sase", sort_order=0)
    ai = WatchlistBucket(client_id=client.id, name="AI Security", name_key="ai security", sort_order=1)
    db.add_all([sase, ai])
    db.flush()
    db.add_all([
        WatchlistKeyword(client_id=client.id, bucket_id=sase.id, keyword="sase", keyword_key="sase", volume=8000, paired_ai_prompt=SASE_Q),
        WatchlistKeyword(client_id=client.id, bucket_id=sase.id, keyword="what is sase", keyword_key="what is sase", volume=2000),
        WatchlistKeyword(client_id=client.id, bucket_id=ai.id, keyword="ai security", keyword_key="ai security", volume=5000, paired_ai_prompt=AI_Q),
    ])
    for kw, pos in (("sase", 2), ("what is sase", 40), ("ai security", 60)):
        db.add(FactSerRanking(client_id=client.id, date=date(2026, 10, 30), site_engine_id="s", keyword_id=kw, keyword=kw, position=pos, volume=1))
    run = LlmRun(id=uuid.uuid4(), client_id=client.id, status="completed", platforms=["openai", "gemini"], started_at=datetime(2026, 10, 20, tzinfo=timezone.utc))
    db.add(run)
    db.flush()
    for platform, q, named, comps in (("openai", SASE_Q, True, ["Fortinet"]), ("gemini", SASE_Q, True, ["Fortinet", "Cisco"]), ("openai", AI_Q, False, ["Palo Alto"]), ("gemini", AI_Q, False, ["Palo Alto", "Cisco"])):
        db.add(LlmResponse(run_id=run.id, client_id=client.id, query_text=q, topic_cluster="x", platform=platform, visibility_type="Mentioned" if named else "Not visible", brand_mentioned=named, url_cited=False, competitors_mentioned=comps))
    for m, clicks in ((date(2025, 10, 5), 1000), (date(2026, 9, 5), 820), (date(2026, 10, 5), 800)):
        db.add(FactGscDaily(client_id=client.id, date=m, impressions=10000, clicks=clicks, ctr=0.05, average_position=8))
    db.add_all([
        FactGscQueryPage(client_id=client.id, date=date(2026, 10, 5), query="sase", raw_url="https://x/", normalized_url="https://x/", country="usa", device="DESKTOP", impressions=900, clicks=200, ctr=0, average_position=2),
        FactGscQueryPage(client_id=client.id, date=date(2025, 10, 5), query="sase", raw_url="https://x/", normalized_url="https://x/", country="usa", device="DESKTOP", impressions=900, clicks=300, ctr=0, average_position=2),
        FactGscQueryPage(client_id=client.id, date=date(2026, 10, 5), query="acme sase pricing", raw_url="https://x/", normalized_url="https://x/", country="usa", device="DESKTOP", impressions=90, clicks=77, ctr=0, average_position=1),
    ])
    db.add_all([FactSerSiteSummary(client_id=client.id, metric_date=date(2026, 7, 30), visibility_percent=10), FactSerSiteSummary(client_id=client.id, metric_date=date(2026, 10, 30), visibility_percent=12.3)])
    for cid, name, now in (("1", "Fortinet", 38), ("2", "Cisco", 30)):
        db.add(FactSerCompetitor(client_id=client.id, site_engine_id="s", competitor_id=cid, name=name, visibility=now, metric_date=date(2026, 10, 30)))
    db.commit()


def topic(out, name):
    return next(t for t in out["topics"] if t["name"] == name)


def test_a_topic_shows_google_top_10_share_of_demand_beside_ai_share_and_leader(db, client_a):
    client_a.client_name = "Acme"
    seed(db, client_a)
    out = ce.build(db, client_a, "2026-10")
    sase, ai = topic(out, "SASE"), topic(out, "AI Security")
    assert (sase["keywords"], sase["searches_per_month"], sase["google_top10_pct"], sase["google_heat"]) == (2, 10000, 80.0, "green")
    assert sase["ai_share_pct"] == 100.0 and sase["ai_heat"] == "green" and sase["ai_leader"]["is_self"] is True
    assert ai["google_top10_pct"] == 0.0 and ai["google_heat"] == "red" and ai["ai_share_pct"] == 0.0 and ai["ai_leader"] == {"name": "Palo Alto", "share_pct": 100.0, "is_self": False}
    assert ai["read_out"] == "A gap in both Google and AI answers. Palo Alto appears in 100% of AI answers."
    assert sase["read_out"] == "Strong in Google and in AI answers."


def test_topic_clicks_come_from_tracked_non_brand_terms_against_last_year(db, client_a):
    client_a.client_name = "Acme"
    seed(db, client_a)
    out = ce.build(db, client_a, "2026-10")
    assert topic(out, "SASE")["clicks"] == {"value": 200.0, "last_year": 300.0, "change": -100}
    assert topic(out, "AI Security")["clicks"]["value"] is None


def test_competitors_show_current_visibility_and_the_client_shows_its_three_month_change(db, client_a):
    client_a.client_name = "Acme"
    seed(db, client_a)
    rows = {c["name"]: c for c in ce.build(db, client_a, "2026-10")["competitors"]}
    assert rows["Acme"]["is_self"] is True and rows["Acme"]["change_pct"] == 23.0
    assert rows["Cisco"]["visibility"] == 30.0 and rows["Cisco"]["change_pct"] is None and rows["Fortinet"]["ai_share_pct"] == 50.0


def test_ai_share_of_voice_by_vendor_counts_answers_naming_each(db, client_a):
    client_a.client_name = "Acme"
    seed(db, client_a)
    v = {x["name"]: x["share_pct"] for x in ce.build(db, client_a, "2026-10")["ai_vendors"]}
    assert v == {"Acme": 50.0, "Fortinet": 50.0, "Cisco": 50.0, "Palo Alto": 50.0}


def test_the_headline_strip_and_clicks_by_month(db, client_a):
    client_a.client_name = "Acme"
    seed(db, client_a)
    out = ce.build(db, client_a, "2026-10")
    k = {x["label"]: x for x in out["kpis"]}
    assert k["Google clicks, Oct 2026"]["value"] == 800.0 and "-20% vs Oct 2025" in k["Google clicks, Oct 2026"]["sub"] and k["Google clicks, Oct 2026"]["tone"] == "bad"
    assert k["Google visibility vs peers"]["value"] == 12.3 and "+23% over three months" in k["Google visibility vs peers"]["sub"] and "30% to 38%" in k["Google visibility vs peers"]["sub"]
    assert k["AI share of voice"]["sub"].startswith("#1 of 4")
    assert k["Strongest topic"]["value"] == "SASE" and "Biggest gap: AI Security" in k["Strongest topic"]["sub"]
    assert len(out["clicks_by_month"]) == 13 and out["clicks_by_month"][-1] == {"month": "2026-10", "value": 800.0}


def test_nothing_synced_gives_empty_parts_and_no_invented_figures(db, client_a):
    out = ce.build(db, client_a, "2026-10")
    assert out["topics"] == [] and out["competitors"] == [] and out["ai_vendors"] == [] and out["priorities"] == []
    assert all(k["value"] is None for k in out["kpis"])


def test_both_reports_are_published_separately_and_the_client_sees_both(client, db, client_a, admin_user):
    consult(db, client_a)
    h = client_header(client_a.id, admin_user.email)
    viewer(db, client_a, "viewer@cato.example")
    v = client_header(client_a.id, "viewer@cato.example")
    for kind, words in (("monthly", "Monthly words."), ("executive", "Leadership words.")):
        client.put("/v2/consulting/report", json={"month": "2026-10", "kind": kind, "analysis": words, "notes": {"topics": "  A note under the topics. "}}, headers=h)
        assert client.post("/v2/consulting/report/state", json={"month": "2026-10", "kind": kind, "to": "published"}, headers=h).status_code == 200
    both = client.get("/v2/consulting/portal/reports", headers=v).json()
    assert both["monthly"]["analysis"] == "Monthly words." and both["executive"]["analysis"] == "Leadership words." and both["executive"]["kind"] == "executive"
    assert both["executive"]["notes"] == {"topics": "A note under the topics."} and {"topics", "kpis"} <= set(both["executive"]["data"])
    client.post("/v2/consulting/report/state", json={"month": "2026-10", "kind": "executive", "to": "draft"}, headers=h)
    assert client.get("/v2/consulting/portal/reports", headers=v).json()["executive"] is None
    assert client.get("/v2/consulting/report?month=2026-10&kind=executive", headers=h).json()["report"]["review_state"] == "draft"
    assert client.get("/v2/consulting/report?month=2026-10&kind=deck", headers=h).status_code == 400


def test_the_executive_summary_lists_published_recommendations_as_priorities(client, db, client_a, admin_user):
    from tests.test_consulting_recs import FULL, move

    consult(db, client_a)
    h = client_header(client_a.id, admin_user.email)
    rec = client.post("/v2/consulting/recommendations", json=FULL, headers=h).json()
    move(client, h, rec, "approved")
    move(client, h, rec, "published")
    assert ce.build(db, client_a, "2026-10")["priorities"] == [{"title": FULL["title"], "action": FULL["action"]}]
