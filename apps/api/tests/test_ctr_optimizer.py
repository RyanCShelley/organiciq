"""CTR optimizer: pages and searches earning fewer clicks than their position should, the score by month, and sending a page to the plan."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from app.models.annotation import Annotation, AnnotationType
from app.models.bing_stats import FactBingQueryStat
from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSnapshot
from app.models.engine_task import EngineTask
from app.models.gsc import FactGscQueryPage
from app.services import ctr_optimizer as co
from tests.conftest import client_header

START, END = date(2026, 10, 1), date(2026, 10, 28)
LOW, FINE, BRAND = "https://shop.example/low", "https://shop.example/fine", "https://shop.example/home"


def row(db, client, day, query, url, impressions, clicks, position):
    db.add(FactGscQueryPage(client_id=client.id, date=day, query=query, raw_url=url, normalized_url=url, country="usa", device="DESKTOP",
                            impressions=Decimal(impressions), clicks=Decimal(clicks), ctr=Decimal(0), average_position=Decimal(position)))


def seed(db, client):
    d = date(2026, 10, 10)
    row(db, client, d, "natural sunscreen", LOW, 2000, 10, 3.0)       # far under what position 3 earns
    row(db, client, d, "mineral spf", LOW, 500, 2, 3.0)
    row(db, client, d, "best spf", FINE, 2000, 60, 3.0)              # close to what position 3 earns
    row(db, client, d, f"{client.client_name.lower()} sunscreen", BRAND, 1000, 5, 3.0)  # a brand search: left out
    row(db, client, d, "far away", LOW, 5000, 1, 40.0)               # beyond position 20: left out
    row(db, client, d, "tiny", LOW, 20, 0, 3.0)                      # too few impressions to judge
    db.add(FactCrawlPageSnapshot(client_id=client.id, source=CRAWL_SOURCE_FIRST_PARTY, snapshot_date=date(2026, 10, 1), raw_url=LOW, normalized_url=LOW, indexable=True, status_code=200,
                                 title="Sunscreen", description="Buy sunscreen."))
    db.commit()


def get(client, client_a, admin_user, path="/v2/ctr", **extra):
    return client.get(path, params={"from": START.isoformat(), "to": END.isoformat(), **extra}, headers=client_header(client_a.id, admin_user.email))


def test_pages_below_benchmark_are_ranked_by_the_clicks_available(client, db, client_a, admin_user):
    seed(db, client_a)
    out = get(client, client_a, admin_user).json()
    exp3 = co.expected_ctr(3.0)
    low = next(p for p in out["pages"] if p["url"] == LOW)
    fine = next(p for p in out["pages"] if p["url"] == FINE)
    assert [p["url"] for p in out["pages"]][0] == LOW, "the page losing the most clicks comes first"
    assert low["below"] is True and low["searches_below"] == 2 and low["impressions"] == 2520 and low["searches"] == 3, "the far-away search is out of range; the tiny one counts toward the page but is not judged"
    assert abs(low["extra_clicks"] - ((2000 + 500) * exp3 / 100 - 12)) < 0.6 and fine["below"] is False and fine["extra_clicks"] == 0
    assert not any("home" in p["url"] for p in out["pages"]), "a brand search is navigation and is left out"
    assert out["pages_below"] == 1 and out["searches_below"] == 2 and [s["query"] for s in out["searches"]][0] == "natural sunscreen"
    assert 0 < out["score"] < 100 and out["extra_clicks"] == round(low["extra_clicks"])


def test_the_score_is_tracked_month_by_month(client, db, client_a, admin_user):
    seed(db, client_a)
    row(db, client_a, date(2026, 9, 12), "natural sunscreen", LOW, 2000, 300, 3.0)  # a good September
    db.commit()
    months = {m["month"]: m for m in get(client, client_a, admin_user).json()["monthly"]}
    assert len(months) == 12 and months["2026-09"]["score"] > months["2026-10"]["score"]
    assert months["2026-08"]["score"] is None, "a month with nothing to judge has no score"


def test_a_page_opens_to_its_snippet_its_searches_bing_and_what_was_changed(client, db, client_a, admin_user):
    seed(db, client_a)
    db.add(FactBingQueryStat(client_id=client_a.id, week_start=date(2026, 10, 5), query="natural sunscreen", query_key="natural sunscreen", impressions=80, clicks=1, avg_impression_position=Decimal("4.0")))
    row(db, client_a, date(2026, 9, 5), "natural sunscreen", LOW, 400, 4, 3.0)      # the 28 days before the change
    row(db, client_a, date(2026, 9, 25), "natural sunscreen", LOW, 400, 40, 3.0)    # the 28 days after
    db.add(Annotation(client_id=client_a.id, date=date(2026, 9, 15), annotation_type=AnnotationType.MANUAL_NOTE, description="New title", page_url=LOW, baseline_metrics_json={}))
    db.commit()
    out = get(client, client_a, admin_user, "/v2/ctr/page", url=LOW).json()
    assert out["title"] == "Sunscreen" and out["title_length"] == 9 and out["description"] == "Buy sunscreen."
    assert out["searches"][0]["query"] == "natural sunscreen" and out["searches"][0]["bing"] == {"impressions": 80, "clicks": 1, "position": 4.0}
    change = out["changes"][0]
    assert change["kind"] == "Noted" and change["text"] == "New title"
    assert change["before"]["ctr"] == 1.0 and change["after"] is None or change["after"]["ctr"] > change["before"]["ctr"]


def test_sending_a_page_to_the_plan_makes_a_task_with_the_evidence(client, db, client_a, admin_user):
    seed(db, client_a)
    h = client_header(client_a.id, admin_user.email)
    made = client.post("/v2/ctr/plan", json={"url": LOW, "from": START.isoformat(), "to": END.isoformat()}, headers=h)
    assert made.status_code == 200
    task = db.query(EngineTask).filter(EngineTask.client_id == client_a.id).one()
    assert task.page_url == LOW and task.kind == "suggestion" and task.search == "natural sunscreen"
    assert "Rewrite the title and description of /low" in task.title and any("Sunscreen" in s for s in task.steps) and any("natural sunscreen" in s for s in task.steps)
    again = client.post("/v2/ctr/plan", json={"url": LOW, "from": START.isoformat(), "to": END.isoformat()}, headers=h)
    assert again.status_code == 200 and db.query(EngineTask).count() == 1, "sending it twice is one task"
    fine = client.post("/v2/ctr/plan", json={"url": FINE, "from": START.isoformat(), "to": END.isoformat()}, headers=h)
    assert fine.status_code == 400 and "not below" in fine.json()["detail"]


def test_a_bad_range_is_refused(client, db, client_a, admin_user):
    assert client.get("/v2/ctr", params={"from": "2026-10-31", "to": "2026-10-01"}, headers=client_header(client_a.id, admin_user.email)).status_code == 400
