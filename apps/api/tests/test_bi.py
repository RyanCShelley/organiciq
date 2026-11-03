"""Business Intelligence: channels, landing pages, keyword movement and the change log, for any date range."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.models.annotation import Annotation, AnnotationType
from app.models.config import ConversionDefinition, OrganicChannel
from app.models.ga4 import FactGa4Event, FactGa4Traffic
from app.models.seranking import FactSerRanking
from tests.conftest import client_header

START, END = date(2026, 10, 1), date(2026, 10, 31)
HOME, SPF = "https://shop.example/", "https://shop.example/collections/spf"


def traffic(db, client, day, url, channel, sessions, engaged, seconds=None):
    db.add(FactGa4Traffic(client_id=client.id, date=day, raw_url=url, normalized_url=url, session_source="s", session_medium="m", channel=channel,
                          sessions=Decimal(sessions), active_users=Decimal(sessions), views=Decimal(sessions), engaged_sessions=Decimal(engaged),
                          engagement_seconds=None if seconds is None else Decimal(seconds)))


def event(db, client, day, url, channel, name, n):
    db.add(FactGa4Event(client_id=client.id, date=day, raw_url=url, normalized_url=url, session_source="s", session_medium="m", channel=channel, event_name=name, event_count=n))


def h(client_a, admin_user):
    return client_header(client_a.id, admin_user.email)


def seed(db, client_a):
    db.add(ConversionDefinition(client_id=client_a.id, event_name="purchase", conversion_name="Purchase", conversion_type="ecommerce", is_primary=True))
    traffic(db, client_a, date(2026, 10, 5), HOME, OrganicChannel.ORGANIC_SEARCH, 100, 40, seconds=4000)
    traffic(db, client_a, date(2026, 10, 6), SPF, OrganicChannel.ORGANIC_SEARCH, 50, 10, seconds=500)
    traffic(db, client_a, date(2026, 10, 6), SPF, OrganicChannel.DIRECT_UNATTRIBUTED, 200, 20, seconds=1000)
    traffic(db, client_a, date(2026, 9, 10), HOME, OrganicChannel.ORGANIC_SEARCH, 80, 30, seconds=2400)  # the period before
    event(db, client_a, date(2026, 10, 6), SPF, OrganicChannel.ORGANIC_SEARCH, "purchase", 5)
    event(db, client_a, date(2026, 10, 6), SPF, OrganicChannel.DIRECT_UNATTRIBUTED, "purchase", 2)
    event(db, client_a, date(2026, 10, 6), SPF, OrganicChannel.DIRECT_UNATTRIBUTED, "add_to_cart", 50)  # not a chosen conversion
    db.commit()


def test_channels_show_visits_engagement_time_and_conversions_beside_the_previous_period(client, db, client_a, admin_user):
    seed(db, client_a)
    out = client.get("/v2/bi", params={"from": START.isoformat(), "to": END.isoformat()}, headers=h(client_a, admin_user)).json()
    by = {c["channel"]: c for c in out["channels"]}
    organic, direct = by["organic_search"], by["direct_unattributed"]
    assert organic["sessions"] == 150 and organic["sessions_before"] == 80
    assert organic["engagement_rate"] == 33.33 and organic["avg_seconds"] == 30.0  # 4,500 seconds over 150 sessions
    assert organic["conversions"] == 5 and organic["conversion_rate"] == 3.33
    assert direct["conversions"] == 2, "add_to_cart is not a chosen conversion"
    assert [c["channel"] for c in out["channels"]][0] == "direct_unattributed"  # busiest first
    assert out["has_engagement_time"] is True and out["key_events"][0]["event"] == "purchase"


def test_landing_pages_can_be_narrowed_to_one_channel(client, db, client_a, admin_user):
    seed(db, client_a)
    p = {"from": START.isoformat(), "to": END.isoformat()}
    allp = {r["url"]: r for r in client.get("/v2/bi", params=p, headers=h(client_a, admin_user)).json()["pages"]}
    assert allp[SPF]["sessions"] == 250 and allp[SPF]["conversions"] == 7 and allp[HOME]["sessions"] == 100
    only = client.get("/v2/bi", params={**p, "channel": "organic_search"}, headers=h(client_a, admin_user)).json()["pages"]
    assert {r["url"]: r["sessions"] for r in only} == {HOME: 100, SPF: 50}
    assert {r["url"]: r["conversions"] for r in only}[SPF] == 5


def test_time_on_site_is_none_until_the_pull_that_includes_it(client, db, client_a, admin_user):
    traffic(db, client_a, date(2026, 10, 5), HOME, OrganicChannel.ORGANIC_SEARCH, 100, 40)
    db.commit()
    out = client.get("/v2/bi", params={"from": START.isoformat(), "to": END.isoformat()}, headers=h(client_a, admin_user)).json()
    assert out["has_engagement_time"] is False and out["channels"][0]["avg_seconds"] is None and out["pages"][0]["avg_seconds"] is None


def test_keywords_show_where_they_were_and_where_they_are(client, db, client_a, admin_user):
    def rank(day, keyword, position, volume=500):
        db.add(FactSerRanking(client_id=client_a.id, date=day, site_engine_id="1", keyword_id=keyword, keyword=keyword, position=Decimal(position), volume=Decimal(volume)))

    for kw, a, b in (("up kw", 20, 8), ("down kw", 5, 12), ("lost kw", 9, 0), ("new kw", 0, 30)):
        rank(date(2026, 10, 2), kw, a)
        rank(date(2026, 10, 30), kw, b)
    db.commit()
    out = client.get("/v2/bi", params={"from": START.isoformat(), "to": END.isoformat()}, headers=h(client_a, admin_user)).json()["keywords"]
    assert out["from"] == "2026-10-02" and out["to"] == "2026-10-30"
    by = {k["keyword"]: k for k in out["keywords"]}
    assert (by["up kw"]["state"], by["up kw"]["change"]) == ("up", 12.0)
    assert by["down kw"]["state"] == "down" and by["lost kw"]["state"] == "lost" and by["new kw"]["state"] == "new"


def test_the_change_log_takes_a_note_and_will_not_remove_one_from_a_shipped_task(client, db, client_a, admin_user):
    hd = h(client_a, admin_user)
    made = client.post("/v2/bi/changes", json={"date": "2026-10-12", "description": "Moved the SPF collection to a new template", "page": SPF}, headers=hd)
    assert made.status_code == 201
    db.add(Annotation(client_id=client_a.id, date=date(2026, 10, 20), annotation_type=AnnotationType.GROWTH_ACTION, description="Shipped", engine_uid="t1", baseline_metrics_json={}))
    db.commit()
    log = client.get("/v2/bi", params={"from": START.isoformat(), "to": END.isoformat()}, headers=hd).json()["changes"]
    assert [c["date"] for c in log] == ["2026-10-20", "2026-10-12"] and [c["from_task"] for c in log] == [True, False]
    shipped = next(c for c in log if c["from_task"])
    assert client.delete(f"/v2/bi/changes/{shipped['id']}", headers=hd).status_code == 400
    assert client.delete(f"/v2/bi/changes/{made.json()['id']}", headers=hd).status_code == 200


def test_a_bad_range_or_channel_is_refused(client, db, client_a, admin_user):
    hd = h(client_a, admin_user)
    assert client.get("/v2/bi", params={"from": "2026-10-31", "to": "2026-10-01"}, headers=hd).status_code == 400
    assert client.get("/v2/bi", params={"from": "2026-10-01", "to": "2026-10-31", "channel": "nope"}, headers=hd).status_code == 400


def test_totals_daily_coverage_and_ai_mentions_feed_the_overview(client, db, client_a, admin_user):
    from app.models.llm_visibility import LlmResponse, LlmRun

    seed(db, client_a)
    for kw, a, b in (("a", 2, 3), ("b", 9, 25), ("c", 0, 0)):
        for day, pos in ((date(2026, 10, 2), a), (date(2026, 10, 30), b)):
            db.add(FactSerRanking(client_id=client_a.id, date=day, site_engine_id="1", keyword_id=kw, keyword=kw, position=Decimal(pos), volume=Decimal(10)))
    old = LlmRun(client_id=client_a.id, status="completed")
    new = LlmRun(client_id=client_a.id, status="completed")
    db.add_all([old, new])
    db.flush()
    db.execute(__import__("sqlalchemy").text("update llm_runs set started_at='2026-09-20' where id=:i"), {"i": old.id})
    db.execute(__import__("sqlalchemy").text("update llm_runs set started_at='2026-10-20' where id=:i"), {"i": new.id})
    for run, mentioned in ((old, 0), (new, 1)):
        for i in range(2):
            db.add(LlmResponse(run_id=run.id, client_id=client_a.id, query_text=f"q{i}", platform="openai", visibility_type="Mentioned", brand_mentioned=bool(mentioned and i == 0), url_cited=False))
    db.commit()
    out = client.get("/v2/bi", params={"from": START.isoformat(), "to": END.isoformat()}, headers=h(client_a, admin_user)).json()
    assert out["totals"]["sessions"] == 350 and out["totals_before"]["sessions"] == 80
    assert out["totals"]["avg_seconds"] == 15.7 and out["totals"]["conversions"] == 7
    assert len(out["daily"]) == 31 and out["daily"][4]["sessions"] == 100 and out["daily"][5]["conversions"] == 7
    cov = out["keywords"]["coverage"]
    assert cov["start"] == {"top3": 1, "top10": 1, "top20": 0, "top100": 0, "outside": 1} and cov["end"] == {"top3": 1, "top10": 0, "top20": 0, "top100": 1, "outside": 1}
    ai = out["ai"]
    assert ai["date"] == "2026-10-20" and ai["mention_rate"] == 50.0 and ai["mention_rate_before"] == 0.0 and ai["platforms"][0]["checks"] == 2


def test_keyword_movement_carries_the_volume_the_paired_prompt_and_how_the_ai_answered_it(client, db, client_a, admin_user):
    from app.models.llm_visibility import LlmResponse, LlmRun
    from app.models.watchlist import WatchlistBucket, WatchlistKeyword

    for day, pos in ((date(2026, 10, 2), 20), (date(2026, 10, 30), 8)):
        db.add(FactSerRanking(client_id=client_a.id, date=day, site_engine_id="1", keyword_id="k", keyword="natural sunscreen", position=Decimal(pos)))
    b = WatchlistBucket(client_id=client_a.id, name="Sunscreen", name_key="sunscreen", sort_order=0)
    db.add(b)
    db.flush()
    db.add(WatchlistKeyword(client_id=client_a.id, bucket_id=b.id, keyword="Natural Sunscreen", keyword_key="natural sunscreen", volume=3200, paired_ai_prompt="What is the best natural sunscreen?"))
    old = LlmRun(client_id=client_a.id, status="completed")
    new = LlmRun(client_id=client_a.id, status="completed")
    db.add_all([old, new])
    db.flush()
    sa_text = __import__("sqlalchemy").text
    db.execute(sa_text("update llm_runs set started_at='2026-09-20' where id=:i"), {"i": old.id})
    db.execute(sa_text("update llm_runs set started_at='2026-10-20' where id=:i"), {"i": new.id})
    prompt = "What is the best natural sunscreen?"
    for platform, mentioned, cited in (("openai", True, False), ("gemini", True, True), ("anthropic", False, False)):
        db.add(LlmResponse(run_id=new.id, client_id=client_a.id, query_text=prompt, platform=platform, visibility_type="Mentioned", brand_mentioned=mentioned, url_cited=cited))
    db.add(LlmResponse(run_id=old.id, client_id=client_a.id, query_text=prompt, platform="openai", visibility_type="Mentioned", brand_mentioned=False, url_cited=False))
    db.commit()
    out = client.get("/v2/bi", params={"from": START.isoformat(), "to": END.isoformat()}, headers=h(client_a, admin_user)).json()["keywords"]["keywords"]
    k = next(x for x in out if x["keyword"] == "natural sunscreen")
    assert k["volume"] == 3200 and k["prompt"] == prompt and k["in_watchlist"] is True and k["state"] == "up"
    ai = k["ai"]
    assert (ai["platforms"], ai["mentioned"], ai["cited"]) == (3, 2, 1) and (ai["previous_mentioned"], ai["previous_cited"]) == (0, 0)
    assert ai["by_platform"]["gemini"] == {"cited": True, "named": True}
