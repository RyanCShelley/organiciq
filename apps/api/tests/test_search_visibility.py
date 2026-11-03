"""Search visibility: terms across Google, Bing and SE Ranking, whether they agree, and Google's updates."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.models.bing_stats import FactBingQueryStat
from app.models.gsc import FactGscQueryPage
from app.models.seranking import FactSerCompetitorKeyword, FactSerRanking
from app.models.watchlist import WatchlistBucket, WatchlistKeyword
from app.services import google_updates
from tests.conftest import client_header

START, END = date(2026, 10, 1), date(2026, 10, 28)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """The report reads Google's feed; the tests never do."""
    def refuse(*a, **k):
        raise RuntimeError("no network in tests")

    monkeypatch.setattr(google_updates.httpx, "get", refuse)


def gsc(db, client, day, query, impressions, position, clicks=1, url="https://shop.example/spf"):
    db.add(FactGscQueryPage(client_id=client.id, date=day, query=query, raw_url=url, normalized_url=url, country="usa", device="DESKTOP",
                            impressions=Decimal(impressions), clicks=Decimal(clicks), ctr=Decimal(0), average_position=Decimal(position)))


def watch(db, client, name="Sunscreen", *terms):
    b = WatchlistBucket(client_id=client.id, name=name, name_key=name.lower(), sort_order=0)
    db.add(b)
    db.flush()
    for t in terms:
        db.add(WatchlistKeyword(client_id=client.id, bucket_id=b.id, keyword=t, keyword_key=t.lower()))
    db.commit()
    return b


def get(client, client_a, admin_user, path="/v2/search-visibility", **extra):
    params = {"from": START.isoformat(), "to": END.isoformat(), **extra}
    return client.get(path, params=params, headers=client_header(client_a.id, admin_user.email))


def seed(db, client_a):
    watch(db, client_a, "Sunscreen", "Natural Sunscreen", "mineral spf", "tanning oil")
    # This period (Oct 1-28) and the one before (Sep 3-30).
    gsc(db, client_a, date(2026, 10, 6), "natural sunscreen", 200, 4.0, clicks=20)
    gsc(db, client_a, date(2026, 10, 20), "natural sunscreen", 200, 6.0, clicks=10)
    gsc(db, client_a, date(2026, 9, 10), "natural sunscreen", 300, 12.0)
    gsc(db, client_a, date(2026, 10, 7), "mineral spf", 100, 15.0)
    gsc(db, client_a, date(2026, 9, 12), "mineral spf", 100, 9.0)
    gsc(db, client_a, date(2026, 10, 8), "tanning oil", 3, 2.0)  # too few impressions to believe
    gsc(db, client_a, date(2026, 10, 8), "unrelated query", 500, 1.0)
    db.add(FactBingQueryStat(client_id=client_a.id, week_start=date(2026, 10, 5), query="natural sunscreen", query_key="natural sunscreen", impressions=40, clicks=2, avg_impression_position=Decimal("14.0")))
    for day, pos in ((date(2026, 10, 2), 20), (date(2026, 10, 27), 18)):
        db.add(FactSerRanking(client_id=client_a.id, date=day, site_engine_id="1", keyword_id="k1", keyword="Natural Sunscreen", position=Decimal(pos), volume=Decimal(3200), ranking_url="https://shop.example/spf"))
    db.commit()


def test_terms_show_each_source_and_a_move_and_flag_where_the_sources_disagree(client, db, client_a, admin_user):
    seed(db, client_a)
    out = get(client, client_a, admin_user).json()
    by = {t["term"]: t for t in out["terms"]}
    natural = by["Natural Sunscreen"]
    assert natural["google"]["impressions"] == 400 and natural["google"]["position"] == 5.0  # (200*4 + 200*6) / 400
    assert natural["google"]["position_before"] == 12.0 and natural["move"] == 7.0 and natural["band"] == "top10"
    assert natural["bing"]["position"] == 14.0 and natural["ser"]["position"] == 18.0 and natural["ser"]["position_start"] == 20.0
    assert natural["disagree"] == "Google has it at 5, SE Ranking at 18"
    mineral = by["mineral spf"]
    assert mineral["move"] == -6.0 and mineral["disagree"] is None and mineral["band"] == "top20"
    assert by["tanning oil"]["google"]["position"] is None and by["tanning oil"]["band"] == "none", "3 impressions say nothing"


def test_the_headline_distribution_and_movers(client, db, client_a, admin_user):
    seed(db, client_a)
    out = get(client, client_a, admin_user).json()
    assert out["terms_total"] == 3 and out["now"]["showing"] == 3 and out["now"]["page_one"] == 1
    assert out["now"]["clicks"] == 32 and out["before"]["showing"] == 2
    assert out["distribution"]["now"] == {"top10": 1, "top20": 1, "none": 1} and out["distribution"]["before"]["top20"] == 1
    assert [t["term"] for t in out["winners"]] == ["Natural Sunscreen"] and [t["term"] for t in out["losers"]] == ["mineral spf"]
    assert out["weeks"] and out["series"][0]["impressions"] > 0
    assert "unrelated query" not in str(out["terms"]), "only watchlist terms are counted"


def test_a_bucket_narrows_the_report(client, db, client_a, admin_user):
    seed(db, client_a)
    other = WatchlistBucket(client_id=client_a.id, name="Oils", name_key="oils", sort_order=1)
    db.add(other)
    db.flush()
    db.add(WatchlistKeyword(client_id=client_a.id, bucket_id=other.id, keyword="face oil", keyword_key="face oil"))
    db.commit()
    out = get(client, client_a, admin_user, bucket=str(other.id)).json()
    assert [t["term"] for t in out["terms"]] == ["face oil"] and len(out["buckets"]) == 2


def test_a_term_opens_to_its_pages_competitors_and_features(client, db, client_a, admin_user):
    seed(db, client_a)
    db.add(FactSerCompetitorKeyword(client_id=client_a.id, competitor_domain="badgerbalm.com", keyword="natural sunscreen", position=Decimal(2), fetched_at=date(2026, 10, 15), ranking_url="https://badgerbalm.com/spf"))
    db.add(FactSerCompetitorKeyword(client_id=client_a.id, competitor_domain="old.com", keyword="natural sunscreen", position=Decimal(1), fetched_at=date(2026, 9, 1)))
    db.commit()
    out = get(client, client_a, admin_user, "/v2/search-visibility/term", term="Natural Sunscreen").json()
    assert out["pages"][0]["url"] == "https://shop.example/spf" and out["pages"][0]["impressions"] == 400
    assert [c["domain"] for c in out["competitors"]] == ["badgerbalm.com"], "only the latest read of the competitors"
    assert out["serp"] is None


def test_google_updates_are_read_kept_and_listed_for_the_range(client, db, client_a, admin_user, monkeypatch):
    feed = [
        {"id": "a1", "service_name": "Ranking", "begin": "2026-10-05T16:00:00+00:00", "end": "2026-10-12T08:00:00+00:00", "external_desc": "October 2026 spam update", "uri": "incidents/a1", "most_recent_update": {"text": "Complete."}},
        {"id": "b2", "service_name": "Crawling", "begin": "2026-10-06T16:00:00+00:00", "external_desc": "Crawl hiccup"},
        {"id": "c3", "service_name": "Ranking", "begin": "2026-05-21T16:00:00+00:00", "end": "2026-06-02T12:00:00+00:00", "external_desc": "May 2026 core update"},
    ]

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return feed

    monkeypatch.setattr(google_updates.httpx, "get", lambda *a, **k: Resp())
    out = get(client, client_a, admin_user).json()
    assert [u["title"] for u in out["updates"]] == ["October 2026 spam update"], "ranking updates inside the range only"
    assert out["updates"][0]["end"] == "2026-10-12" and out["updates"][0]["url"].endswith("incidents/a1")
    # Held for a day: the feed is not read again, and a feed that fails leaves what is kept.
    monkeypatch.setattr(google_updates.httpx, "get", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    assert google_updates.refresh(db, now=datetime.now(timezone.utc)) == 0
    assert get(client, client_a, admin_user).json()["updates"][0]["id"] == "a1"
