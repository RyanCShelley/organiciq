"""The consulting report: headline numbers shaped for a client, the consultant's analysis, and publishing."""

from __future__ import annotations

from app.services import consulting_report as cr
from tests.conftest import client_header
from tests.test_portal_access import consult, viewer

REVIEW = {
    "month": "2026-10", "previous_month": "2026-09", "has_search_data": True,
    "search": {"impressions": {"current": 12000, "previous": 10000, "change_pct": 20.0}, "clicks": {"current": 480, "previous": 500, "change_pct": -4.0}, "average_position": {"current": 8.2, "previous": 9.0, "change_pct": -8.9}},
    "freshness": [{"source": "bing", "available": False}, {"source": "ga4", "available": True}],
}
CARDS = {
    "headline": "Visibility is up, leads are flat.",
    "visibility": {"available": True, "headline": 3, "of": 5, "ai_mentions": 4, "ai_links": 1, "ai_runs": 2},
    "traffic": {"headline": 900, "previous": 850, "change_pct": 5.9, "channels": [
        {"key": "organic_search", "label": "Search", "sessions": 500, "previous": 450, "change_pct": 11.1},
        {"key": "ai_referral", "label": "AI", "sessions": 12, "previous": 3, "change_pct": 300.0},
        {"key": "direct_unattributed", "label": "Direct", "sessions": 200, "previous": 180, "change_pct": 11.1}]},
    "conversions": {"noun": "leads", "headline": 0, "previous": 4, "change_pct": -100.0, "conversion_rate": {"current": 0.0, "previous": 0.5, "change_pct": -100.0}, "revenue": None},
    "reads": {"visibility": "Your terms are showing up more.", "traffic": "Visits are up a little.", "conversions": "No leads were tracked."},
}


def test_the_headline_is_shaped_for_a_client_with_sources_and_plain_notes():
    out = cr.shape(REVIEW, CARDS)
    sections = {s["key"]: s for s in out["sections"]}
    assert [s["label"] for s in out["sections"]] == ["Visibility", "Traffic", "Leads"]
    labels = [m["label"] for m in sections["visibility"]["metrics"]]
    assert labels == ["Search impressions", "Search clicks", "Average position", "Tracked terms showing in Google", "AI answers that name you", "AI answers that link to you"]
    assert all(m["source"] for s in out["sections"] for m in s["metrics"])
    pos = next(m for m in sections["visibility"]["metrics"] if m["label"] == "Average position")
    assert pos["lower_is_better"] is True
    ai = next(m for m in sections["visibility"]["metrics"] if m["label"] == "AI answers that name you")
    assert "sample from 2 checks" in ai["note"]
    assert sections["visibility"]["read"] == "Your terms are showing up more."


def test_ai_visits_are_counted_only_where_measured_and_direct_is_never_called_ai():
    out = cr.shape(REVIEW, CARDS)
    traffic = next(s for s in out["sections"] if s["key"] == "traffic")["metrics"]
    labels = {m["label"] for m in traffic}
    assert "Visits from AI assistants" in labels and "Website visits" in labels and not any("irect" in l for l in labels)
    ai = next(m for m in traffic if m["label"] == "Visits from AI assistants")
    assert "never guessed from direct visits" in ai["note"]


def test_missing_lead_tracking_is_said_plainly_not_filled_in():
    out = cr.shape(REVIEW, CARDS)
    leads = next(s for s in out["sections"] if s["key"] == "leads")
    assert "tracking may be incomplete" in leads["limitation"] and "estimate" in leads["limitation"]
    empty = cr.shape({"month": "2026-10"}, {})
    assert all(s["metrics"] == [] and s["limitation"] for s in empty["sections"])


def test_a_source_that_is_not_in_yet_is_named_in_the_caveats():
    out = cr.shape(REVIEW, CARDS)
    assert out["caveats"][0] == "No data yet from: bing." and "may not be caused by that work alone" in out["caveats"][-1]


def put(client, h, **body):
    return client.put("/v2/consulting/report", json={"month": "2026-10", **body}, headers=h)


def test_the_analysis_is_saved_with_a_revision_and_a_stale_save_is_refused(client, db, client_a, admin_user):
    consult(db, client_a)
    h = client_header(client_a.id, admin_user.email)
    first = put(client, h, analysis=" Search visibility is up. ", title="October").json()
    assert first["analysis"] == "Search visibility is up." and first["revision"] == 1 and first["review_state"] == "draft"
    second = put(client, h, analysis="Search visibility is up a lot.", revision=1).json()
    assert second["revision"] == 2
    assert put(client, h, analysis="Overwrite", revision=1).status_code == 409


def test_the_report_needs_analysis_before_it_is_published_and_the_client_sees_only_what_is_published(client, db, client_a, admin_user):
    consult(db, client_a)
    h = client_header(client_a.id, admin_user.email)
    viewer(db, client_a, "viewer@cato.example")
    v = client_header(client_a.id, "viewer@cato.example")
    assert client.post("/v2/consulting/report/state", json={"month": "2026-10", "to": "published"}, headers=h).status_code == 404
    put(client, h, analysis=None)
    refused = client.post("/v2/consulting/report/state", json={"month": "2026-10", "to": "published"}, headers=h)
    assert refused.status_code == 400 and "Write your analysis" in refused.json()["detail"]
    put(client, h, analysis="Here is what happened in October.", revision=1)
    assert client.get("/v2/consulting/portal/report", headers=v).json() == {"report": None}
    pub = client.post("/v2/consulting/report/state", json={"month": "2026-10", "to": "published"}, headers=h).json()
    assert pub["review_state"] == "published" and pub["published_by"] == admin_user.email
    seen = client.get("/v2/consulting/portal/report", headers=v).json()["report"]
    assert seen["analysis"] == "Here is what happened in October." and seen["month"] == "2026-10" and [s["key"] for s in seen["data"]["sections"]] == ["visibility", "traffic", "leads"]
    assert admin_user.email not in str(seen) and "updated_by" not in str(seen) and "revision" not in str(seen)
    client.post("/v2/consulting/report/state", json={"month": "2026-10", "to": "draft"}, headers=h)
    assert client.get("/v2/consulting/portal/report", headers=v).json() == {"report": None}


def test_the_report_is_staff_only_for_the_consultant_and_another_clients_is_not_readable(client, db, client_a, client_b, admin_user):
    consult(db, client_a)
    consult(db, client_b)
    viewer(db, client_a, "viewer@cato.example")
    v = client_header(client_a.id, "viewer@cato.example")
    assert client.get("/v2/consulting/report", headers=v).status_code == 403
    assert client.put("/v2/consulting/report", json={"month": "2026-10", "analysis": "x"}, headers=v).status_code == 403
    h = client_header(client_a.id, admin_user.email)
    put(client, h, analysis="A's words")
    client.post("/v2/consulting/report/state", json={"month": "2026-10", "to": "published"}, headers=h)
    assert client.get("/v2/consulting/portal/report", headers=client_header(client_b.id, "viewer@cato.example")).status_code == 403
    assert client.get("/v2/consulting/portal/report", headers=client_header(client_b.id, admin_user.email)).json() == {"report": None}


def test_the_consultant_sees_the_live_numbers_beside_their_draft(client, db, client_a, admin_user):
    consult(db, client_a)
    h = client_header(client_a.id, admin_user.email)
    body = client.get("/v2/consulting/report?month=2026-10", headers=h).json()
    assert body["report"]["exists"] is False and [s["key"] for s in body["data"]["sections"]] == ["visibility", "traffic", "leads"]
    assert client.get("/v2/consulting/report?month=October", headers=h).status_code == 400


def test_a_client_sees_the_reviews_own_sections_but_none_of_its_internal_fields():
    review = {**REVIEW, "locked": True, "locked_by": "ryan@x.com", "locked_at": "2026-11-02", "lock_note": "n", "model": "lead_gen", "work": {"parts": 3}, "noun": "leads", "summary": ["a"]}
    shown = cr.client_review(review)
    assert "locked_by" not in shown and "work" not in shown and "model" not in shown and "lock_note" not in shown
    assert shown["search"]["clicks"]["current"] == 480 and shown["month"] == "2026-10" and shown["summary"] == ["a"]


def test_the_published_report_carries_the_review_sections_and_insights_and_no_internal_fields(client, db, client_a, admin_user):
    consult(db, client_a)
    h = client_header(client_a.id, admin_user.email)
    viewer(db, client_a, "viewer@cato.example")
    put(client, h, analysis="Words.")
    client.post("/v2/consulting/report/state", json={"month": "2026-10", "to": "published"}, headers=h)
    data = client.get("/v2/consulting/portal/report", headers=client_header(client_a.id, "viewer@cato.example")).json()["report"]["data"]
    assert {"review", "cards", "insights", "sections", "visibility_detail"} <= set(data) and set(data["insights"]) == {"keywords", "ai", "key_events"}
    for internal in ("locked_by", "locked_at", "lock_note", "work", "model"):
        assert internal not in data["review"]


def test_the_analysis_is_an_intro_and_three_short_lists_cleaned_and_bounded(client, db, client_a, admin_user):
    consult(db, client_a)
    h = client_header(client_a.id, admin_user.email)
    saved = put(client, h, analysis="Short intro.", highlights={"going_well": [" Demo requests up 37%. ", "", "AI visits up 14%"], "to_watch": ["SD-WAN terms fell out of the top 100"], "gaps": []}).json()
    assert saved["highlights"] == {"going_well": ["Demo requests up 37%.", "AI visits up 14%"], "to_watch": ["SD-WAN terms fell out of the top 100"], "gaps": []}
    too_many = put(client, h, highlights={"gaps": [f"gap {i}" for i in range(9)]}, revision=1)
    assert too_many.status_code == 400 and "At most 8 points" in too_many.json()["detail"]
    too_long = put(client, h, highlights={"to_watch": ["x" * 701]}, revision=1)
    assert too_long.status_code == 400 and "under 700 characters" in too_long.json()["detail"]
    assert client.get("/v2/consulting/report?month=2026-10", headers=h).json()["report"]["highlights"]["going_well"][0] == "Demo requests up 37%."


def test_a_report_with_only_the_lists_can_be_published_and_the_client_reads_the_lists(client, db, client_a, admin_user):
    consult(db, client_a)
    h = client_header(client_a.id, admin_user.email)
    viewer(db, client_a, "viewer@cato.example")
    put(client, h, highlights={"going_well": ["Visits up."], "to_watch": [], "gaps": ["No AI visibility."]})
    assert client.post("/v2/consulting/report/state", json={"month": "2026-10", "to": "published"}, headers=h).status_code == 200
    seen = client.get("/v2/consulting/portal/report", headers=client_header(client_a.id, "viewer@cato.example")).json()["report"]
    assert seen["highlights"] == {"going_well": ["Visits up."], "to_watch": [], "gaps": ["No AI visibility."]} and seen["analysis"] is None


def test_an_empty_report_still_cannot_be_published(client, db, client_a, admin_user):
    consult(db, client_a)
    h = client_header(client_a.id, admin_user.email)
    put(client, h, analysis=None, highlights={"going_well": [], "to_watch": [], "gaps": []})
    assert client.post("/v2/consulting/report/state", json={"month": "2026-10", "to": "published"}, headers=h).status_code == 400
