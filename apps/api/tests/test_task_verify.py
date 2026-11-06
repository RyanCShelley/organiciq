"""The live check: what counts as seen on the page, and what never does."""

from __future__ import annotations

from datetime import date, datetime, timezone

from app.models.annotation import Annotation
from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSnapshot
from app.models.engine_task import EngineTask
from app.models.schema_tools import InlinkState
from app.services import page_diagnostic as pd
from app.services import task_verify as tv
from tests.conftest import client_header

URL = "https://clienta.example/products/spf-15"
BEFORE = dict(title="SPF 15 Sunscreen", description="Old description.", sections=[{"level": 1, "heading": "SPF 15", "first_paragraph": "Our sunscreen is made in small batches with mineral filters."}], faq_questions=[])


def crawl(db, client):
    db.add(FactCrawlPageSnapshot(client_id=client.id, source=CRAWL_SOURCE_FIRST_PARTY, snapshot_date=date(2026, 11, 3), raw_url=URL, normalized_url=URL, status_code=200, word_count=300, indexable=True, **BEFORE))
    db.commit()


def page(title="SPF 15 Sunscreen", desc="Old description.", opening="Our sunscreen is made in small batches with mineral filters.", extra=""):
    html = f"<html><head><title>{title}</title><meta name='description' content='{desc}'>{extra}</head><body><h1>SPF 15</h1><p>{opening}</p><p>More words about it that make the page real.</p></body></html>"

    async def fetch(url):
        return pd.Fetched(status=200, final_url=url, headers={}, body=html, requested_url=url, user_agent=pd.USER_AGENT, fetched_at="2026-11-08T12:00:00+00:00", size=len(html))

    return fetch


def confirm(client, client_a, admin_user, parts, **over):
    h = client_header(client_a.id, admin_user.email)
    body = {"month": "2026-11", "kind": "growth_action", "rule_id": "GA", "search": "spf 15", "page": URL, "title": "Grow spf 15", "steps": [f"# {i + 1}. {p['name']}" for i, p in enumerate(parts)], "evidence": [], "parts": parts, **over}
    return h, client.post("/v2/engine/tasks", json=body, headers=h).json()["task"]


def reload(db, task_id):
    db.expire_all()
    return db.get(EngineTask, task_id)


def test_confirming_keeps_the_page_as_the_crawl_saw_it(client, db, client_a, admin_user):
    crawl(db, client_a)
    _, task = confirm(client, client_a, admin_user, [{"id": "S-5", "name": "Reread the title and description"}])
    before = reload(db, task["id"]).parts[0]["before"]
    assert before["title"] == "SPF 15 Sunscreen" and before["date"] == "2026-11-03" and before["from"] == "crawl"


def test_a_changed_title_is_seen_live_marked_done_and_annotated_with_how_it_was_known(client, db, client_a, admin_user):
    crawl(db, client_a)
    _, task = confirm(client, client_a, admin_user, [{"id": "S-5", "name": "Reread the title and description"}])
    t = reload(db, task["id"])
    out = tv.check_task(db, client_a, t, fetch=page(title="SPF 15 Mineral Sunscreen | Shop"))
    assert out["live"] == 1
    t = reload(db, task["id"])
    part = t.parts[0]
    assert part["status"] == "done" and part["done_by"] == "the live check" and "changed from “SPF 15 Sunscreen” to “SPF 15 Mineral Sunscreen | Shop”" in part["verified_how"]
    note = db.query(Annotation).one()
    assert note.verified_how.startswith("Read live from https://clienta.example/products/spf-15 on ") and t.status == "shipped"


def test_a_page_that_has_not_changed_is_not_done_and_says_so(client, db, client_a, admin_user):
    crawl(db, client_a)
    _, task = confirm(client, client_a, admin_user, [{"id": "S-5", "name": "Reread the title and description"}])
    tv.check_task(db, client_a, reload(db, task["id"]), fetch=page())
    part = reload(db, task["id"]).parts[0]
    assert part["status"] == "open" and part["last_check"]["result"] == "not_live" and "Not seen yet" in part["last_check"]["note"] and db.query(Annotation).count() == 0


def test_a_bot_check_is_could_not_read_never_not_live(client, db, client_a, admin_user):
    crawl(db, client_a)
    _, task = confirm(client, client_a, admin_user, [{"id": "S-5", "name": "Reread the title and description"}])

    async def captcha(url):
        return pd.Fetched(status=202, final_url=url, headers={"sg-captcha": "challenge"}, body="<html><head><meta http-equiv='refresh' content='0;/.well-known/sgcaptcha/'></head></html>", requested_url=url, user_agent=pd.USER_AGENT, size=90)

    out = tv.check_task(db, client_a, reload(db, task["id"]), fetch=captcha)
    part = reload(db, task["id"]).parts[0]
    assert out["unreadable"] and part["last_check"]["result"] == "unreadable" and "nothing was judged" in part["last_check"]["note"] and part["status"] == "open"


def test_a_rewritten_opening_and_new_faq_markup_are_seen(client, db, client_a, admin_user):
    crawl(db, client_a)
    _, task = confirm(client, client_a, admin_user, [{"id": "A-1", "name": "Answer the question at the top"}, {"id": "V-7", "name": "Mark up the FAQ"}])
    faq = '<script type="application/ld+json">{"@context":"https://schema.org","@type":"FAQPage","mainEntity":[]}</script>'
    out = tv.check_task(db, client_a, reload(db, task["id"]), fetch=page(opening="SPF 15 protects against sunburn for people who burn easily, and it is reef friendly.", extra=faq))
    assert out["live"] == 2 and [p["status"] for p in reload(db, task["id"]).parts] == ["done", "done"]


def test_links_are_seen_through_the_inlink_suggester(client, db, client_a, admin_user):
    crawl(db, client_a)
    _, task = confirm(client, client_a, admin_user, [{"id": "V-4", "name": "Add internal links"}])
    db.add(InlinkState(client_id=client_a.id, source_url="https://clienta.example/blog/a", target_url=URL, status="live", checked_at=datetime.now(timezone.utc), created_by="x"))
    db.commit()
    assert tv.check_task(db, client_a, reload(db, task["id"]), fetch=page())["live"] == 1


def test_a_kind_that_cannot_be_seen_is_left_for_a_person(client, db, client_a, admin_user):
    crawl(db, client_a)
    _, task = confirm(client, client_a, admin_user, [{"id": "L-S2", "name": "Something on the phone"}])
    out = tv.check_task(db, client_a, reload(db, task["id"]), fetch=page())
    assert out["live"] == 0 and reload(db, task["id"]).parts[0]["last_check"]["result"] == "cannot"


def test_a_part_a_person_took_back_is_not_marked_again_by_the_daily_run_but_can_be_checked_by_hand(client, db, client_a, admin_user):
    crawl(db, client_a)
    h, task = confirm(client, client_a, admin_user, [{"id": "S-5", "name": "Reread the title and description"}])
    client.patch(f"/v2/engine/tasks/{task['id']}/parts/0", json={"done": True}, headers=h)
    client.patch(f"/v2/engine/tasks/{task['id']}/parts/0", json={"done": False}, headers=h)
    t = reload(db, task["id"])
    assert t.parts[0]["no_auto"] is True
    assert tv.check_task(db, client_a, t, fetch=page(title="A brand new title"))["checked"] == 0
    assert tv.check_task(db, client_a, reload(db, task["id"]), force=True, fetch=page(title="A brand new title"))["live"] == 1


def test_a_part_a_person_marked_done_gains_the_live_evidence(client, db, client_a, admin_user):
    crawl(db, client_a)
    h, task = confirm(client, client_a, admin_user, [{"id": "S-5", "name": "Reread the title and description"}, {"id": "V-4", "name": "Add internal links"}])
    client.patch(f"/v2/engine/tasks/{task['id']}/parts/0", json={"done": True}, headers=h)
    tv.check_task(db, client_a, reload(db, task["id"]), fetch=page(title="A brand new title"))
    part = reload(db, task["id"]).parts[0]
    assert part["done_by"] == admin_user.email and "brand new title" in part["verified_how"]
    assert db.query(Annotation).one().verified_how == part["verified_how"]


def test_the_route_checks_the_page_now(client, db, client_a, admin_user, monkeypatch):
    crawl(db, client_a)
    h, task = confirm(client, client_a, admin_user, [{"id": "S-5", "name": "Reread the title and description"}])
    monkeypatch.setattr(pd, "_fetch", page(title="A brand new title"))
    res = client.post(f"/v2/engine/tasks/{task['id']}/check", headers=h).json()
    assert res["check"]["live"] == 1 and res["task"]["parts"][0]["status"] == "done" and res["task"]["parts"][0]["verified_how"]


def test_the_daily_run_checks_once_a_day(client, db, client_a, admin_user, monkeypatch):
    from app.core.settings import get_settings

    crawl(db, client_a)
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    h = client_header(client_a.id, admin_user.email)
    client.post("/v2/engine/tasks", json={"month": month, "kind": "growth_action", "rule_id": "GA", "search": "s", "page": URL, "title": "t", "steps": ["# 1. Reread the title and description"], "evidence": [], "parts": [{"id": "S-5", "name": "Reread the title and description"}]}, headers=h)
    monkeypatch.setattr(pd, "_fetch", page(title="A brand new title"))
    monkeypatch.setattr(get_settings(), "task_verify_hour_utc", 0)
    assert tv.maybe_check_open(db) is True
    assert db.query(Annotation).count() == 1
    assert tv.maybe_check_open(db) is False
