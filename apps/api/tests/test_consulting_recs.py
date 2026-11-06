"""Consulting briefs: the review track, the implementation track, and the audit trail."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.models.consulting import ConsultingRecommendation
from tests.conftest import client_header
from tests.test_portal_access import consult, viewer

FULL = {
    "title": "Rewrite the title of the slab leak page", "category": "visibility", "focus": "both", "source_kind": "ctr",
    "finding": "The page ranks on page one but earns fewer clicks than its position usually does.", "explanation": "The title does not say what the page offers.",
    "action": "Rewrite the SEO title.", "instructions": [{"text": "Open the page in the CMS."}, {"text": "Publish."}], "priority": "high",
    "target_urls": ["https://clienta.example/services/slab-leak"],
}


def setup(client, db, client_a, admin_user, **over):
    consult(db, client_a)
    h = client_header(client_a.id, admin_user.email)
    res = client.post("/v2/consulting/recommendations", json={**FULL, **over}, headers=h)
    assert res.status_code == 201, res.text
    return h, res.json()


def move(client, h, rec, to):
    return client.post(f"/v2/consulting/recommendations/{rec['id']}/state", json={"to": to}, headers=h)


def test_a_brief_is_created_as_a_draft_with_cleaned_fields(client, db, client_a, admin_user):
    _, rec = setup(client, db, client_a, admin_user)
    assert rec["review_state"] == "draft" and rec["revision"] == 1 and rec["impl_status"] == "recommended" and rec["verification"] == "unverified"
    assert rec["instructions"] == [{"text": "Open the page in the CMS."}, {"text": "Publish."}] and rec["target_urls"][0]["check"] == {"state": "unchecked"}
    assert rec["next_states"] == ["under_review", "approved", "archived"]


def test_a_brief_needs_a_title_and_a_valid_category_focus_and_priority(client, db, client_a, admin_user):
    consult(db, client_a)
    h = client_header(client_a.id, admin_user.email)
    assert client.post("/v2/consulting/recommendations", json={"title": "x"}, headers=h).status_code == 400
    assert client.post("/v2/consulting/recommendations", json={"title": "x", "category": "ranking"}, headers=h).status_code == 400
    assert client.post("/v2/consulting/recommendations", json={"title": "x", "category": "leads", "priority": "urgent"}, headers=h).status_code == 400
    assert client.post("/v2/consulting/recommendations", json={"title": "x", "category": "leads", "surprise": 1}, headers=h).status_code == 422


def test_an_edit_needs_the_revision_it_opened_and_bumps_it(client, db, client_a, admin_user):
    h, rec = setup(client, db, client_a, admin_user)
    ok = client.patch(f"/v2/consulting/recommendations/{rec['id']}", json={"revision": 1, "title": "A better title"}, headers=h)
    assert ok.status_code == 200 and ok.json()["revision"] == 2 and ok.json()["title"] == "A better title"
    stale = client.patch(f"/v2/consulting/recommendations/{rec['id']}", json={"revision": 1, "title": "Overwrite"}, headers=h)
    assert stale.status_code == 409 and "changed in another window" in stale.json()["detail"]


def test_only_a_complete_brief_is_published_and_each_step_is_one_a_brief_may_take(client, db, client_a, admin_user):
    h, rec = setup(client, db, client_a, admin_user, explanation=None)
    assert move(client, h, rec, "published").status_code == 400
    assert move(client, h, rec, "approved").status_code == 200
    gap = move(client, h, rec, "published")
    assert gap.status_code == 400 and "why it matters" in gap.json()["detail"]
    client.patch(f"/v2/consulting/recommendations/{rec['id']}", json={"revision": 2, "explanation": "Searchers pick another result."}, headers=h)
    back = client.get(f"/v2/consulting/recommendations/{rec['id']}", headers=h).json()
    assert back["review_state"] == "under_review"  # an approval covers the text that was approved
    assert move(client, h, rec, "approved").status_code == 200
    pub = move(client, h, rec, "published").json()
    assert pub["review_state"] == "published" and pub["published_by"] == admin_user.email and pub["published_at"]
    assert move(client, h, rec, "draft").status_code == 400
    assert move(client, h, rec, "archived").json()["review_state"] == "archived"
    assert client.patch(f"/v2/consulting/recommendations/{rec['id']}", json={"revision": 99, "title": "x"}, headers=h).status_code in (400, 409)
    assert move(client, h, rec, "draft").json()["archived_at"] is None


def test_the_trail_records_every_change_and_who_made_it(client, db, client_a, admin_user):
    h, rec = setup(client, db, client_a, admin_user)
    client.patch(f"/v2/consulting/recommendations/{rec['id']}", json={"revision": 1, "priority": "low"}, headers=h)
    move(client, h, rec, "approved")
    events = client.get(f"/v2/consulting/recommendations/{rec['id']}", headers=h).json()["events"]
    assert [e["kind"] for e in events] == ["state", "edited", "created"] and events[0]["from"] == "draft" and events[0]["to"] == "approved" and events[1]["detail"]["fields"] == ["priority"]
    assert all(e["by"] == admin_user.email for e in events)


def test_what_the_client_did_is_recorded_with_who_said_so_and_completed_is_not_verified(client, db, client_a, admin_user):
    h, rec = setup(client, db, client_a, admin_user)
    out = client.post(f"/v2/consulting/recommendations/{rec['id']}/progress", json={"status": "completed", "implemented_on": "2026-11-05", "estimated": True, "notes": "Dana said it went live last week."}, headers=h).json()
    assert out["impl_status"] == "completed" and out["impl_status_source"] == "consultant" and out["implemented_on"] == "2026-11-05" and out["implemented_on_estimated"] is True
    assert out["verification"] == "unverified" and out["client_notes"].startswith("Dana")
    assert client.post(f"/v2/consulting/recommendations/{rec['id']}/progress", json={"status": "done"}, headers=h).status_code == 400
    assert client.post(f"/v2/consulting/recommendations/{rec['id']}/progress", json={"source": "robot"}, headers=h).status_code == 400


def test_a_brief_is_verified_only_with_a_reason(client, db, client_a, admin_user):
    h, rec = setup(client, db, client_a, admin_user)
    assert client.post(f"/v2/consulting/recommendations/{rec['id']}/verify", json={"state": "verified"}, headers=h).status_code == 400
    ok = client.post(f"/v2/consulting/recommendations/{rec['id']}/verify", json={"state": "verified", "how": "Saw the new title in the browser tab on Nov 8."}, headers=h).json()
    assert ok["verification"] == "verified" and ok["verified_at"] and ok["verified_how"].startswith("Saw")
    assert client.post(f"/v2/consulting/recommendations/{rec['id']}/verify", json={"state": "unverified"}, headers=h).json()["verified_at"] is None


def test_the_follow_up_list_is_published_briefs_nobody_reported_on_and_nobody_chased(client, db, client_a, admin_user):
    h, a = setup(client, db, client_a, admin_user, title="A")
    _, b = setup(client, db, client_a, admin_user, title="B")
    _, c = setup(client, db, client_a, admin_user, title="C")
    for rec in (a, b, c):
        move(client, h, rec, "approved")
        move(client, h, rec, "published")
    old = datetime.now(timezone.utc) - timedelta(days=30)
    db.query(ConsultingRecommendation).update({"published_at": old})
    db.commit()
    client.post(f"/v2/consulting/recommendations/{b['id']}/progress", json={"status": "planned"}, headers=h)
    client.post(f"/v2/consulting/recommendations/{c['id']}/follow-up", json={"note": "Emailed Dana, no reply."}, headers=h)
    listed = client.get("/v2/consulting/recommendations/follow-ups", headers=h).json()
    assert [r["title"] for r in listed["recommendations"]] == ["A"]
    assert client.get("/v2/consulting/recommendations", headers=h).json()["follow_ups"] == 1


def test_the_queue_counts_each_state_and_filters(client, db, client_a, admin_user):
    h, rec = setup(client, db, client_a, admin_user)
    setup(client, db, client_a, admin_user, title="Second")
    move(client, h, rec, "under_review")
    listed = client.get("/v2/consulting/recommendations", headers=h).json()
    assert listed["counts"] == {"draft": 1, "under_review": 1, "approved": 0, "published": 0, "archived": 0}
    assert [r["title"] for r in client.get("/v2/consulting/recommendations?state=under_review", headers=h).json()["recommendations"]] == ["Rewrite the title of the slab leak page"]
    assert "internal_notes" not in listed["recommendations"][0]


def test_briefs_are_staff_only_and_one_client_cannot_read_anothers(client, db, client_a, client_b, admin_user):
    h, rec = setup(client, db, client_a, admin_user)
    viewer(db, client_a, "viewer@cato.example")
    v = client_header(client_a.id, "viewer@cato.example")
    assert client.get("/v2/consulting/recommendations", headers=v).status_code == 403
    assert client.get(f"/v2/consulting/recommendations/{rec['id']}", headers=v).status_code == 403
    other = client_header(client_b.id, admin_user.email)
    assert client.get(f"/v2/consulting/recommendations/{rec['id']}", headers=other).status_code == 404


def test_the_ai_visibility_focus_is_kept_on_the_profile(client, db, client_a, admin_user):
    consult(db, client_a)
    h = client_header(client_a.id, admin_user.email)
    assert client.get("/v2/consulting/profile", headers=h).json()["ai_visibility_focus"] is False
    assert client.put("/v2/consulting/profile", json={"ai_visibility_focus": True, "goals": "x"}, headers=h).json()["ai_visibility_focus"] is True
