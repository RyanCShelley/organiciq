"""A shipped task's result: the 28 days before against the 28 days after, kept once measured."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.models.engine_task import EngineTask
from app.models.gsc import FactGscQueryPage
from app.models.llm_visibility import LlmResponse, LlmRun
from app.models.watchlist import WatchlistBucket, WatchlistKeyword
from app.services import task_results as tr
from tests.conftest import client_header

PAGE = "https://shop.example/collections/spf"
OTHER = "https://shop.example/products/x"
SHIPPED = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def gsc(db, client_a, day, query, url, impressions, clicks, position=10.0):
    db.add(FactGscQueryPage(client_id=client_a.id, date=day, query=query, raw_url=url, normalized_url=url, country="usa",
                            device="DESKTOP", impressions=impressions, clicks=clicks, ctr=0, average_position=position))


def task(db, client_a, **kw):
    t = EngineTask(client_id=client_a.id, month="2026-10", kind="growth_action", rule_id="GA", search="natural sunscreen",
                   page_url=PAGE, title="Growth action", confirmed_by="a@b.co", status="shipped", shipped_at=SHIPPED, **kw)
    db.add(t)
    db.commit()
    return t


def seed(db, client_a):
    # before: Sept 3 to Sept 30, after: Oct 2 to Oct 29
    gsc(db, client_a, date(2026, 9, 10), "natural sunscreen", PAGE, 200, 4, position=14.0)
    gsc(db, client_a, date(2026, 9, 12), "best natural sunscreen", PAGE, 100, 1, position=18.0)
    gsc(db, client_a, date(2026, 9, 12), "natural sunscreen", OTHER, 500, 30)  # another page: not this task
    gsc(db, client_a, date(2026, 9, 12), "tanning oil", PAGE, 900, 50)  # another topic: not this task
    gsc(db, client_a, date(2026, 10, 10), "natural sunscreen", PAGE, 300, 12, position=9.0)
    gsc(db, client_a, date(2026, 10, 29), "natural sunscreen", PAGE, 100, 4, position=11.0)
    gsc(db, client_a, date(2026, 11, 1), "natural sunscreen", PAGE, 1, 0)  # keeps Search Console's newest day past the window
    db.commit()


def test_the_baseline_is_the_page_and_topic_over_the_28_days_before_shipping(db, client_a):
    seed(db, client_a)
    t = task(db, client_a)
    tr.take_baseline(db, client_a, t)
    assert t.baseline["window"] == ["2026-09-03", "2026-09-30"]
    assert t.baseline["gsc"] == {"clicks": 5, "impressions": 300, "position": 15.3}
    assert t.check_on == date(2026, 11, 1)  # 28 days after, plus Search Console's lag


def test_until_the_days_after_are_in_it_is_measuring_and_afterwards_the_change_is_shown_and_kept(db, client_a):
    seed(db, client_a)
    t = task(db, client_a)
    tr.take_baseline(db, client_a, t)
    db.commit()
    early = tr.evaluate(db, client_a, t, today=date(2026, 10, 20))
    assert early["status"] == "measuring" and early["before"]["impressions"] == 300 and "after" not in early

    done = tr.evaluate(db, client_a, t, today=date(2026, 11, 2))
    assert done["status"] == "measured"
    assert done["after"] == {"clicks": 16, "impressions": 400, "position": 9.5}
    assert done["change"] == {"clicks": 11, "impressions": 100, "position": -5.8}  # a lower position is better
    assert done["note"] is None  # 300 impressions before is enough to read

    # Kept: more data arriving later does not move it.
    gsc(db, client_a, date(2026, 10, 15), "natural sunscreen", PAGE, 5000, 500)
    db.commit()
    assert tr.evaluate(db, client_a, t, today=date(2026, 12, 1))["after"]["impressions"] == 400


def test_it_waits_for_search_console_even_after_the_check_date(db, client_a):
    gsc(db, client_a, date(2026, 9, 10), "natural sunscreen", PAGE, 200, 4)
    gsc(db, client_a, date(2026, 10, 20), "natural sunscreen", PAGE, 200, 4)  # newest day is before the window ends
    db.commit()
    t = task(db, client_a)
    tr.take_baseline(db, client_a, t)
    assert tr.evaluate(db, client_a, t, today=date(2026, 12, 1))["status"] == "measuring"


def test_a_small_starting_point_is_flagged_not_judged(db, client_a):
    gsc(db, client_a, date(2026, 9, 10), "natural sunscreen", PAGE, 40, 1)
    gsc(db, client_a, date(2026, 10, 10), "natural sunscreen", PAGE, 90, 6)
    gsc(db, client_a, date(2026, 11, 1), "natural sunscreen", PAGE, 1, 0)
    db.commit()
    t = task(db, client_a)
    tr.take_baseline(db, client_a, t)
    out = tr.evaluate(db, client_a, t, today=date(2026, 11, 2))
    assert "Only 40 impressions in the 28 days before" in out["note"]


def _watch_and_runs(db, client_a, before_cited, after_cited):
    b = WatchlistBucket(client_id=client_a.id, name="Sun", name_key="sun", sort_order=0)
    db.add(b)
    db.flush()
    db.add(WatchlistKeyword(client_id=client_a.id, bucket_id=b.id, keyword="natural sunscreen", keyword_key="natural sunscreen", paired_ai_prompt="Best natural sunscreen?"))
    for when, cited in ((datetime(2026, 9, 20, 12, tzinfo=timezone.utc), before_cited), (datetime(2026, 10, 25, 12, tzinfo=timezone.utc), after_cited)):
        run = LlmRun(client_id=client_a.id, status="completed", started_at=when, platforms=["openai", "gemini"])
        db.add(run)
        db.flush()
        for i, platform in enumerate(("ChatGPT", "Gemini")):
            db.add(LlmResponse(run_id=run.id, client_id=client_a.id, query_text="Best natural sunscreen?", platform=platform,
                               visibility_type="Cited" if i < cited else "Not visible", url_cited=i < cited, brand_mentioned=False))
    db.commit()


def test_the_ai_platforms_before_and_since_are_compared(db, client_a):
    seed(db, client_a)
    _watch_and_runs(db, client_a, before_cited=0, after_cited=2)
    t = task(db, client_a)
    tr.take_baseline(db, client_a, t)
    assert t.baseline["ai"] == {"run_date": "2026-09-20", "cited": 0, "platforms": 2}
    out = tr.evaluate(db, client_a, t, today=date(2026, 11, 2))
    assert out["ai_after"] == {"run_date": "2026-10-25", "cited": 2, "platforms": 2}


def test_marking_a_task_shipped_takes_the_baseline_and_the_route_lists_results(client, db, client_a, admin_user):
    seed(db, client_a)
    t = task(db, client_a)
    t.status, t.shipped_at, t.baseline, t.check_on = "confirmed", None, None, None
    db.commit()
    h = client_header(client_a.id, admin_user.email)
    shipped = client.patch(f"/v2/engine/tasks/{t.id}", json={"status": "shipped"}, headers=h).json()
    assert shipped["status"] == "shipped" and shipped["check_on"]
    results = client.get("/v2/engine/tasks/results", headers=h).json()
    assert len(results) == 1 and results[0]["status"] == "measuring" and results[0]["topic"] == "natural sunscreen"
