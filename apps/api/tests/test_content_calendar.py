"""The content calendar: who can change it, adding from a gap or a page, sending to Teamwork, and the watchlist signal on refreshes."""

from __future__ import annotations

import uuid
from decimal import Decimal
from uuid import uuid4

from app.integrations import teamwork
from app.models.schema_tools import ContentModelRun
from app.models.seranking import FactSerKeyword
from app.models.user import User, UserClient, UserRole
from tests.conftest import client_header
from tests.test_content import OLD, STEADY, h, seed_gaps, seed_refresh


def staff(db, client_a, role, email):
    user = User(id=uuid.uuid4(), email=email, name=role.value, google_sub=f"{role.value}-sub", role=role)
    db.add(user)
    db.flush()
    db.add(UserClient(user_id=user.id, client_id=client_a.id, role=role))
    db.commit()
    return client_header(client_a.id, email)


def brief(db, client_a, term):
    db.add(ContentModelRun(client_id=client_a.id, kind="brief", key=term, depth="quick", status="done", created_by="x",
                           payload={"working_title": "AEO agency guide", "angle": "Who needs one and what it does.", "sections": ["What it is", "Pricing"], "questions": ["Is it worth it?"]}))
    db.commit()


ITEM = {"kind": "new_page", "title": "AEO agency guide", "target": "aeo agency", "source_area": "gap", "source_key": "aeo agency"}


def test_admins_and_content_managers_change_the_calendar_and_everyone_else_only_reads(client, db, client_a, admin_user):
    manager = staff(db, client_a, UserRole.CONTENT_MANAGER, "cm@smamarketing.com")
    lead = staff(db, client_a, UserRole.SEO_LEAD, "lead@smamarketing.com")
    team = staff(db, client_a, UserRole.SMA_TEAM, "team@smamarketing.com")
    assert client.post("/v2/content/calendar", json=ITEM, headers=manager).status_code == 200
    assert client.post("/v2/content/calendar", json={**ITEM, "source_key": "other", "target": "other"}, headers=h(client_a, admin_user)).status_code == 200
    for who in (lead, team):
        assert client.post("/v2/content/calendar", json={**ITEM, "source_key": "x"}, headers=who).status_code == 403
        read = client.get("/v2/content/calendar", headers=who).json()
        assert read["can_edit"] is False and len(read["items"]) == 2
    assert client.get("/v2/content/calendar", headers=manager).json()["can_edit"] is True
    item = client.get("/v2/content/calendar", headers=manager).json()["items"][0]
    assert client.patch(f"/v2/content/calendar/{item['id']}", json={"status": "writing"}, headers=lead).status_code == 403
    assert client.delete(f"/v2/content/calendar/{item['id']}", headers=lead).status_code == 403
    assert client.post(f"/v2/content/calendar/{item['id']}/send", headers=lead).status_code == 403


def test_adding_from_a_gap_copies_its_brief_once_and_the_gap_shows_it_is_on_the_calendar(client, db, client_a, admin_user):
    seed_gaps(db, client_a)
    brief(db, client_a, "aeo agency")
    first = client.post("/v2/content/calendar", json=ITEM, headers=h(client_a, admin_user)).json()
    assert first["created"] is True and first["status"] == "idea"
    assert "Working title: AEO agency guide" in first["notes"] and "- Pricing" in first["notes"]
    again = client.post("/v2/content/calendar", json=ITEM, headers=h(client_a, admin_user)).json()
    assert again["created"] is False and again["id"] == first["id"]
    gaps = client.get("/v2/content/gaps", headers=h(client_a, admin_user)).json()
    assert gaps["calendar"] == {"aeo agency": "idea"} and gaps["can_edit"] is True
    client.patch(f"/v2/content/calendar/{first['id']}", json={"status": "dropped"}, headers=h(client_a, admin_user))
    assert client.get("/v2/content/gaps", headers=h(client_a, admin_user)).json()["calendar"] == {}
    assert client.post("/v2/content/calendar", json=ITEM, headers=h(client_a, admin_user)).json()["created"] is True


def test_an_item_is_planned_by_giving_it_a_date_published_by_status_and_removed(client, db, client_a, admin_user):
    a = h(client_a, admin_user)
    item = client.post("/v2/content/calendar", json={"kind": "refresh", "title": "Update guide", "target": OLD, "source_area": "refresh", "source_key": OLD}, headers=a).json()
    planned = client.patch(f"/v2/content/calendar/{item['id']}", json={"due": "2026-11-20", "assignee_email": "w@x.com"}, headers=a).json()
    assert planned["status"] == "planned" and planned["due"] == "2026-11-20" and planned["assignee_email"] == "w@x.com"
    done = client.patch(f"/v2/content/calendar/{item['id']}", json={"status": "published"}, headers=a).json()
    assert done["status"] == "published" and done["published_at"]
    assert client.patch(f"/v2/content/calendar/{item['id']}", json={"clear_due": True}, headers=a).json()["due"] is None
    assert client.get("/v2/content/refreshes", params={"month": "2026-10"}, headers=a).json()["calendar"] == {OLD: "published"}
    assert client.delete(f"/v2/content/calendar/{item['id']}", headers=a).status_code == 200
    assert client.get("/v2/content/calendar", headers=a).json()["items"] == []
    assert client.patch(f"/v2/content/calendar/{uuid4()}", json={"status": "idea"}, headers=a).status_code == 404


def test_an_item_is_sent_to_teamwork_once_and_says_plainly_why_it_cannot_be(client, db, client_a, admin_user, monkeypatch):
    a = h(client_a, admin_user)
    item = client.post("/v2/content/calendar", json={**ITEM, "due": "2026-11-20", "notes": "Cover pricing."}, headers=a).json()
    monkeypatch.setattr(teamwork, "configured", lambda: False)
    assert "not set up" in client.post(f"/v2/content/calendar/{item['id']}/send", headers=a).json()["detail"]
    monkeypatch.setattr(teamwork, "configured", lambda: True)
    assert "no Teamwork tasklist" in client.post(f"/v2/content/calendar/{item['id']}/send", headers=a).json()["detail"]
    client_a.teamwork_tasklist_id = "42"
    db.commit()
    sent = []
    monkeypatch.setattr(teamwork, "list_people", lambda: [])
    monkeypatch.setattr(teamwork, "create_task", lambda **kw: sent.append(kw) or {"id": 7, "url": "https://tw.example/app/tasks/7"})
    out = client.post(f"/v2/content/calendar/{item['id']}/send", headers=a).json()
    assert out["teamwork_task_id"] == "7" and out["teamwork_task_url"].endswith("/7")
    assert sent[0]["tasklist_id"] == "42" and sent[0]["due"] == "2026-11-20" and sent[0]["name"] == "Write: AEO agency guide"
    assert "Search to win: aeo agency" in sent[0]["description"] and "Cover pricing." in sent[0]["description"]
    assert client.post(f"/v2/content/calendar/{item['id']}/send", headers=a).json()["teamwork_task_id"] == "7" and len(sent) == 1

    def refuse(**kw):
        raise teamwork.TeamworkError("Teamwork refused the task (403): no")

    other = client.post("/v2/content/calendar", json={**ITEM, "source_key": "b", "target": "b"}, headers=a).json()
    monkeypatch.setattr(teamwork, "create_task", refuse)
    assert client.post(f"/v2/content/calendar/{other['id']}/send", headers=a).status_code == 502


def test_a_tracked_term_that_fell_on_a_page_lists_it_for_a_refresh_and_brand_terms_never_do(client, db, client_a, admin_user):
    seed_refresh(db, client_a)
    client_a.brand_aliases = ["shop example"]
    db.commit()
    a = h(client_a, admin_user)
    assert STEADY not in [p["url"] for p in client.get("/v2/content/refreshes", params={"month": "2026-10"}, headers=a).json()["pages"]]
    for kid, term, now, before in (("k1", "garden hose guide", 11, 5), ("k2", "garden hose repair", 8, 8), (f"k3", "shop example reviews", 14, 4)):
        db.add(FactSerKeyword(id=uuid4(), client_id=client_a.id, site_engine_id="1", keyword_id=kid, keyword=term, is_tracked=True, ranking_url=STEADY,
                              current_position=Decimal(now), previous_position=Decimal(before), volume=Decimal(300)))
    db.commit()
    out = client.get("/v2/content/refreshes", params={"month": "2026-10"}, headers=a).json()
    page = next(p for p in out["pages"] if p["url"] == STEADY)
    assert page["watch_slipping"] is True and out["counts"]["watch"] == 1
    terms = {w["term"]: w for w in page["watch"]}
    assert terms["garden hose guide"]["slipping"] and terms["garden hose guide"]["change"] == -6
    assert terms["garden hose repair"]["striking"] and not terms["garden hose repair"]["slipping"]
    assert "shop example reviews" not in terms, "a search for the business's own name is navigation"
    assert any("garden hose guide" in r and "5 to 11" in r for r in page["reasons"])


def test_a_topic_opens_to_its_searches_gets_a_brief_and_goes_on_the_calendar(client, db, client_a, admin_user, monkeypatch):
    import json

    from tests.test_content import _enable

    seed_gaps(db, client_a)
    seen: dict = {}
    hd = h(client_a, admin_user)
    topics = {"topics": [{"label": "Schema audits", "why": "Searches show demand.", "content_type": "guide", "priority": "high", "example_searches": ["schema markup audit", "local seo checklist", "brand new term"], "next_to": "seo"}]}
    _enable(monkeypatch, json.dumps(topics), seen)
    client.post("/v2/content/draft", json={"kind": "topics", "key": "x"}, headers=hd)
    detail = client.get("/v2/content/topics/detail", params={"label": "schema audits"}, headers=hd).json()
    by = {s["term"]: s for s in detail["searches"]}
    assert by["schema markup audit"]["volume"] == 900 and by["schema markup audit"]["impressions"] == 400 and by["schema markup audit"]["gap"] is True
    assert by["local seo checklist"]["gap"] is True and by["brand new term"]["volume"] is None and by["brand new term"]["gap"] is False
    assert detail["draft"] is None and detail["calendar"] is None and detail["can_edit"] is True
    assert client.get("/v2/content/topics/detail", params={"label": "nope"}, headers=hd).status_code == 404

    _enable(monkeypatch, json.dumps({"working_title": "Schema Audits Explained", "page_type": "guide", "angle": "How to audit.", "sections": ["What to check", "Fixing errors"], "questions": ["Why audit?"]}), seen)
    assert client.post("/v2/content/draft", json={"kind": "tbrief", "key": "Schema audits", "depth": "quick"}, headers=hd).status_code == 202
    assert "“schema markup audit” (volume 900" in seen["prompt"] and "Subject: Schema audits" in seen["prompt"]
    draft = client.get("/v2/content/topics/detail", params={"label": "Schema audits"}, headers=hd).json()["draft"]
    assert draft["status"] == "done" and draft["working_title"] == "Schema Audits Explained"

    item = client.post("/v2/content/calendar", json={"kind": "new_page", "title": "Schema Audits Explained", "target": "Schema audits", "source_area": "topic", "source_key": "Schema audits"}, headers=hd).json()
    assert "Working title: Schema Audits Explained" in item["notes"] and "- Fixing errors" in item["notes"]
    assert client.get("/v2/content/topics/detail", params={"label": "Schema audits"}, headers=hd).json()["calendar"] == "idea"
