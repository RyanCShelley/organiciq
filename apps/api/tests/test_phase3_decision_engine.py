"""Phase 3 tests: Reviewer Feedback (all 8 rejection reasons) & Focus-Driven Action Ordering."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.core.settings import get_settings
from app.decisions import action_context as ac
from app.decisions.provisional import FOCUS_ORDER_REASONS, order_by_focus
from app.integrations import teamwork
from app.models.annotation import Annotation, AnnotationType
from app.models.client_focus import ClientFocus
from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSnapshot
from app.models.decision import GrowthAction
from app.models.engine_task import EngineTask
from app.models.gsc import FactGscQueryPage
from app.services import growth_action as ga
from app.services import month_work, page_diagnostic as pd, page_history, task_verify
from tests.conftest import client_header
from tests.test_growth_action import PROD, SEP, crawled, gsc, reading, sug
from tests.test_growth_action_context import ids, read


# ── Area 1: Reviewer Feedback (all 8 rejection reasons) ──────────────────────


def test_rejection_reasons_endpoint_returns_all_eight_reasons_and_requires_auth(client, client_a, admin_user):
    unauth = client.get("/v2/engine/rejection-reasons")
    assert unauth.status_code == 401

    # Does not require X-OrganicIQ-Client-Id, only SMA staff auth
    res = client.get("/v2/engine/rejection-reasons", headers=client_header(client_a.id, admin_user.email))
    assert res.status_code == 200
    reasons = res.json()["reasons"]
    assert len(reasons) == 8
    assert [(r["key"], r["label"]) for r in reasons] == list(ac.REJECTION_REASONS.items())


@pytest.mark.parametrize("reason_key,reason_label", list(ac.REJECTION_REASONS.items()))
def test_post_tasks_reject_supports_all_eight_reasons(client, db, client_a, admin_user, reason_key, reason_label):
    h = client_header(client_a.id, admin_user.email)
    page_url = f"https://shop.example/products/{reason_key}"
    res = client.post(
        "/v2/engine/tasks/reject",
        json={
            "month": "2026-10",
            "kind": "growth_action",
            "rule_id": "GA",
            "search": f"query {reason_key}",
            "page": page_url,
            "title": f"Growth action: {reason_key}",
            "why": "Diagnostic explanation",
            "steps": ["# 1. Rewrite the meta for clicks", "Update title"],
            "parts": [{"id": "MC-1", "name": "Rewrite the meta for clicks"}],
            "rejection_reason": reason_key,
            "rejection_note": f"Rejected because {reason_label}",
        },
        headers=h,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "rejected"
    assert body["rejection_reason"] == reason_key
    assert body["rejection_reason_label"] == reason_label
    assert body["rejection_note"] == f"Rejected because {reason_label}"
    assert body["rejected_by"] == admin_user.email
    assert body["rejected_at"] is not None

    row = db.query(EngineTask).filter(EngineTask.id == body["id"]).one()
    assert row.status == "rejected"
    assert row.rejection_reason == reason_key
    assert row.rejected_by == admin_user.email
    assert row.rejected_at is not None


def test_post_tasks_reject_validates_reason_and_updates_in_place_without_duplicating(client, db, client_a, admin_user):
    h = client_header(client_a.id, admin_user.email)
    bad = client.post(
        "/v2/engine/tasks/reject",
        json={"page": PROD, "rejection_reason": "made_up_reason"},
        headers=h,
    )
    assert bad.status_code == 400
    assert "Invalid rejection_reason" in bad.json()["detail"]

    first = client.post(
        "/v2/engine/tasks/reject",
        json={
            "month": "2026-10",
            "rule_id": "GA",
            "search": "Natural  Sunscreen",
            "page": PROD,
            "rejection_reason": "crawl_misread",
            "rejection_note": "Initial note",
        },
        headers=h,
    )
    assert first.status_code == 200
    second = client.post(
        "/v2/engine/tasks/reject",
        json={
            "month": "2026-10",
            "rule_id": "GA",
            "search": "natural sunscreen",
            "page": PROD,
            "rejection_reason": "low_value",
            "rejection_note": "Updated note",
        },
        headers=h,
    )
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["rejection_reason"] == "low_value"
    assert second.json()["rejection_note"] == "Updated note"
    assert db.query(EngineTask).filter(EngineTask.client_id == client_a.id).count() == 1


@pytest.mark.parametrize("target_status", ["rejected", "dropped"])
def test_patch_task_to_rejected_or_dropped_excludes_from_active_slots_and_surfaces_prior_rejections(
    client, db, client_a, admin_user, monkeypatch, target_status
):
    h = client_header(client_a.id, admin_user.email)
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    created = client.post(
        "/v2/engine/tasks",
        json={
            "month": month,
            "kind": "growth_action",
            "rule_id": "GA",
            "search": "natural sunscreen",
            "page": PROD,
            "title": "Growth action: /products/spf-30",
            "steps": ["# 1. Answer the question at the top", "Write 2 sentences", "# 2. Rewrite the meta for clicks", "Update title"],
            "parts": [
                {"id": "A-1", "name": "Answer the question at the top"},
                {"id": "MC-1", "name": "Rewrite the meta for clicks"},
            ],
        },
        headers=h,
    )
    assert created.status_code == 200
    task_id = created.json()["task"]["id"]
    assert created.json()["allowance"]["used"] == 1

    # Invalid rejection_reason on PATCH returns 400
    bad_patch = client.patch(
        f"/v2/engine/tasks/{task_id}",
        json={"status": target_status, "rejection_reason": "invalid_key"},
        headers=h,
    )
    assert bad_patch.status_code == 400

    # Valid rejection_reason on PATCH transitions cleanly
    patched = client.patch(
        f"/v2/engine/tasks/{task_id}",
        json={
            "status": target_status,
            "rejection_reason": "template_constraint",
            "rejection_note": "Hero block is locked across all product templates.",
        },
        headers=h,
    )
    assert patched.status_code == 200, patched.text
    pdata = patched.json()
    assert pdata["status"] == target_status
    assert pdata["rejection_reason"] == "template_constraint"
    assert pdata["rejection_reason_label"] == "Template constraint"
    assert pdata["rejection_note"] == "Hero block is locked across all product templates."
    assert pdata["rejected_by"] == admin_user.email
    assert pdata["rejected_at"] is not None

    # Excluded from allowance, month_work, and optimizer queue
    listed = client.get(f"/v2/engine/tasks?month={month}", headers=h).json()
    assert listed["allowance"]["used"] == 0
    assert listed["work"]["actions"] == 0
    assert listed["work"]["parts"] == 0
    assert month_work.build(db, client_a, month)["parts"] == 0

    opt_queue = client.get("/v2/optimizer", headers=h).json()["queue"]
    assert opt_queue == []

    # Excluded from task_verify.maybe_check_open()
    checked_ids: list[str] = []
    monkeypatch.setattr(
        task_verify,
        "check_task",
        lambda _db, _c, t, **kw: checked_ids.append(str(t.id)) or {"checked": 0, "live": 0, "unreadable": None},
    )
    monkeypatch.setattr(get_settings(), "task_verify_hour_utc", 0)
    assert task_verify.maybe_check_open(db) is True
    assert checked_ids == []

    # Sending an inactive (rejected/dropped) task to Teamwork is refused
    send_res = client.post(f"/v2/engine/tasks/{task_id}/send", headers=h)
    assert send_res.status_code == 400
    assert "dropped or rejected" in send_res.json()["detail"].lower()

    # Excluded from growth_action._duplicate() and surfaced in prior_rejections when status == "rejected"
    gsc(db, client_a, "natural sunscreen", PROD, 500)
    db.commit()
    out = ga.build(
        db,
        client_a,
        SEP,
        "natural sunscreen",
        page=PROD,
        planned_month=month,
        diagnose=read([sug("S-5")]),
        evidence_for=lambda s, u: {},
        signals_for=lambda s: {"reading": reading("transactional")},
    )
    assert out["ok"] is True
    if target_status == "rejected":
        assert len(out["prior_rejections"]) == 1
        assert out["prior_rejections"][0]["rejection_reason"] == "template_constraint"
        assert out["prior_rejections"][0]["rejection_reason_label"] == "Template constraint"
        assert out["prior_rejections"][0]["rejection_note"] == "Hero block is locked across all product templates."
    else:
        assert out["prior_rejections"] == []


def test_reconfirming_a_rejected_task_clears_rejection_fields_and_restores_allowance(client, client_a, admin_user):
    h = client_header(client_a.id, admin_user.email)
    rej = client.post(
        "/v2/engine/tasks/reject",
        json={
            "month": "2026-10",
            "kind": "growth_action",
            "rule_id": "GA",
            "search": "natural sunscreen",
            "page": PROD,
            "rejection_reason": "wrong_target",
            "rejection_note": "Try collection instead",
        },
        headers=h,
    )
    assert rej.status_code == 200
    assert rej.json()["status"] == "rejected"

    reconfirmed = client.post(
        "/v2/engine/tasks",
        json={
            "month": "2026-10",
            "kind": "growth_action",
            "rule_id": "GA",
            "search": "natural sunscreen",
            "page": PROD,
            "title": "Growth action: /products/spf-30",
            "steps": ["# 1. Rewrite the meta for clicks", "Update title"],
            "parts": [{"id": "MC-1", "name": "Rewrite the meta for clicks"}],
        },
        headers=h,
    )
    assert reconfirmed.status_code == 200
    body = reconfirmed.json()
    assert body["created"] is True
    assert body["allowance"]["used"] == 1
    task = body["task"]
    assert task["status"] == "confirmed"
    assert task["rejection_reason"] is None
    assert task["rejection_reason_label"] is None
    assert task["rejection_note"] is None
    assert task["rejected_by"] is None
    assert task["rejected_at"] is None


# ── Area 4: Focus-Driven Action Ordering ─────────────────────────────────────


def test_order_by_focus_orders_leads_traffic_and_visibility_with_ti1_always_first():
    sample = [
        {"id": "S-1"},
        {"id": "V-7"},
        {"id": "F-1"},
        {"id": "MC-1"},
        {"id": "IM-1"},
        {"id": "A-1"},
        {"id": "L-S2"},
        {"id": "L-S1"},
        {"id": "FQ-1"},
        {"id": "T-S1"},
        {"id": "T-S2"},
        {"id": "P-1"},
        {"id": "S-2"},
        {"id": "TI-1"},
    ]
    leads_ids = [x["id"] for x in order_by_focus(sample, "leads")]
    assert leads_ids[0] == "TI-1"
    assert leads_ids.index("F-1") < leads_ids.index("L-S2") < leads_ids.index("L-S1")
    assert leads_ids.index("L-S1") < leads_ids.index("P-1") < leads_ids.index("MC-1") < leads_ids.index("S-1")

    traffic_ids = [x["id"] for x in order_by_focus(sample, "traffic")]
    assert traffic_ids[0] == "TI-1"
    assert traffic_ids.index("MC-1") < traffic_ids.index("T-S1") < traffic_ids.index("T-S2") < traffic_ids.index("P-1")
    assert traffic_ids.index("P-1") < traffic_ids.index("A-1") < leads_ids.index("F-1") or traffic_ids.index("A-1") < traffic_ids.index("F-1")

    vis_ids = [x["id"] for x in order_by_focus(sample, "visibility")]
    assert vis_ids[0] == "TI-1"
    assert vis_ids.index("IM-1") < vis_ids.index("A-1") < vis_ids.index("S-1") < vis_ids.index("S-2") < vis_ids.index("FQ-1")
    assert vis_ids.index("V-7") < vis_ids.index("MC-1") < vis_ids.index("F-1")


def test_growth_action_build_focus_ordering_for_visibility_traffic_and_leads(db, client_a):
    blog = "https://shop.example/blogs/spf-guide"
    gsc(db, client_a, "mineral sunscreen benefits", blog, 1200, clicks=10, position=7.0)
    crawled(db, client_a, blog, "Mineral Sunscreen Benefits")
    db.commit()

    suggestions = [sug("A-1"), sug("S-1"), sug("S-2"), sug("MC-1"), sug("P-1")]
    extras = [
        {"id": "L-S1", "title": "Visitors leave without engaging", "why": "w", "steps": ["Check hero"], "evidence": []},
        {"id": "L-S2", "title": "Add link to conversion page", "why": "w", "steps": ["Link to shop"], "evidence": []},
        {"id": "F-1", "title": "Remove friction", "why": "w", "steps": ["Shorten form"], "evidence": []},
    ]
    diag = read(suggestions, facts={"h1": "Mineral Sunscreen Benefits", "title": "Mineral Sunscreen Benefits", "schema_types": ["Article"]})

    vis = ga.build(
        db, client_a, SEP, "mineral sunscreen benefits", page=blog, focus="visibility",
        diagnose=diag, evidence_for=lambda s, u: {}, extra_suggestions=extras,
        signals_for=lambda s: {"reading": reading("informational")},
    )
    assert vis["focus"] == "visibility"
    assert vis["focus_order_reason"] == FOCUS_ORDER_REASONS["visibility"]
    assert ids(vis["parts"]) == ["IM-1", "A-1", "S-1", "S-2", "MC-1", "P-1", "L-S1", "L-S2", "F-1"]
    assert vis["parts"][0]["role"] == "primary"
    assert all(p["role"] == "supporting" for p in vis["parts"][1:])

    trf = ga.build(
        db, client_a, SEP, "mineral sunscreen benefits", page=blog, focus="traffic",
        diagnose=diag, evidence_for=lambda s, u: {}, extra_suggestions=extras,
        signals_for=lambda s: {"reading": reading("informational")},
    )
    assert trf["focus"] == "traffic"
    assert ids(trf["parts"]) == ["MC-1", "P-1", "IM-1", "S-1", "A-1", "S-2", "L-S1", "L-S2", "F-1"]
    assert trf["parts"][0]["id"] == "MC-1" and trf["parts"][0]["role"] == "primary"

    leads = ga.build(
        db, client_a, SEP, "mineral sunscreen benefits", page=blog, focus="leads",
        diagnose=diag, evidence_for=lambda s, u: {}, extra_suggestions=extras,
        signals_for=lambda s: {"reading": reading("informational")},
    )
    assert leads["focus"] == "leads"
    assert ids(leads["parts"]) == ["F-1", "L-S2", "L-S1", "P-1", "MC-1", "IM-1", "S-1", "S-2", "A-1"]
    assert leads["parts"][0]["id"] == "F-1" and leads["parts"][0]["role"] == "primary"


def test_omitting_focus_resolves_active_client_focus_across_diagnose_and_growth_action_endpoints(
    client, db, client_a, admin_user, monkeypatch
):
    url = f"https://{client_a.domain}/services/plumbing"
    db.add(
        FactGscQueryPage(
            client_id=client_a.id,
            date=date(2026, 8, 10),
            query="emergency plumbing service",
            raw_url=url,
            normalized_url=url,
            country="usa",
            device="DESKTOP",
            impressions=800,
            clicks=4,
            ctr=0,
            average_position=5.0,
        )
    )
    db.add(
        FactCrawlPageSnapshot(
            client_id=client_a.id,
            source=CRAWL_SOURCE_FIRST_PARTY,
            snapshot_date=date(2026, 8, 20),
            raw_url=url,
            normalized_url=url,
            indexable=True,
            status_code=200,
            title="Emergency Plumbing Service",
        )
    )
    # Active ClientFocus for next_month("2026-09") == "2026-10"
    db.add(ClientFocus(client_id=client_a.id, month=date(2026, 10, 1), focus="leads"))
    db.commit()

    html = (
        "<html><head><title>Emergency Plumbing Service</title>"
        "<meta name='description' content='24/7 plumbers.'></head>"
        "<body><h1>Emergency Plumbing</h1><p>Licensed plumbers ready now.</p></body></html>"
    )

    async def fetch(u):
        return pd.Fetched(200, u, {}, html)

    monkeypatch.setattr(pd, "_fetch", fetch)
    h = client_header(client_a.id, admin_user.email)

    # POST /v2/engine/diagnose with omitted focus picks up "leads"
    diag_res = client.post(
        "/v2/engine/diagnose",
        json={"month": "2026-09", "selections": [{"search": "emergency plumbing service", "page": url}]},
        headers=h,
    )
    assert diag_res.status_code == 200, diag_res.text
    assert diag_res.json()["focus"] == "leads"
    assert diag_res.json()["results"][0]["focus"] == "leads"
    assert diag_res.json()["results"][0]["context"]["checklist"][0]["category"] == "conversion"

    # Explicit focus overrides active ClientFocus ("service" checklist has content/conversion/schema; traffic puts content before conversion)
    override_res = client.post(
        "/v2/engine/diagnose",
        json={"month": "2026-09", "focus": "traffic", "selections": [{"search": "emergency plumbing service", "page": url}]},
        headers=h,
    )
    assert override_res.status_code == 200
    assert override_res.json()["focus"] == "traffic"
    assert override_res.json()["results"][0]["context"]["checklist"][0]["category"] == "content"

    # POST /v2/engine/diagnose-page with omitted focus picks up "leads"
    dp_res = client.post("/v2/engine/diagnose-page", json={"month": "2026-09", "pages": [url]}, headers=h)
    assert dp_res.status_code == 200
    assert dp_res.json()["focus"] == "leads"

    # POST /v2/engine/growth-action with omitted focus picks up "leads"
    ga_res = client.post(
        "/v2/engine/growth-action",
        json={"month": "2026-09", "keyword": "emergency plumbing service", "search": "emergency plumbing service", "page": url},
        headers=h,
    )
    assert ga_res.status_code == 200, ga_res.text
    assert ga_res.json()["focus"] == "leads"
    assert ga_res.json()["context"]["focus"] == "leads"
    assert ga_res.json()["checklist"][0]["category"] == "conversion"


# ── Iteration 2 Regression Tests ─────────────────────────────────────────────


@pytest.mark.parametrize("inactive_status", ["rejected", "dropped"])
def test_send_rejected_or_dropped_task_with_existing_teamwork_id_returns_400(
    client, db, client_a, admin_user, monkeypatch, inactive_status
):
    client_a.teamwork_tasklist_id = "12345"
    db.commit()
    h = client_header(client_a.id, admin_user.email)

    created = client.post(
        "/v2/engine/tasks",
        json={
            "month": "2026-10",
            "kind": "growth_action",
            "rule_id": "GA",
            "search": f"sunscreen {inactive_status}",
            "page": PROD,
            "title": "Grow sunscreen",
            "steps": ["# 1. Rewrite the meta for clicks", "Update title"],
            "parts": [{"id": "MC-1", "name": "Rewrite the meta for clicks"}],
        },
        headers=h,
    ).json()["task"]
    task_id = created["id"]

    monkeypatch.setattr(teamwork, "configured", lambda: True)
    monkeypatch.setattr(teamwork, "create_task", lambda **kw: {"id": "tw-777", "url": "https://tw.example/777"})
    monkeypatch.setattr(teamwork, "create_subtask", lambda **kw: {"id": "sub-777", "url": ""})
    sent = client.post(f"/v2/engine/tasks/{task_id}/send", headers=h)
    assert sent.status_code == 200
    assert sent.json()["teamwork_task_id"] == "tw-777"
    assert sent.json()["teamwork_subtasks"] == 1
    db.expire_all()
    task_row = db.get(EngineTask, task_id)
    assert task_row is not None
    assert task_row.teamwork_subtasks == {"part-1": "sub-777"}

    patch_body = {"status": inactive_status}
    if inactive_status == "rejected":
        patch_body["rejection_reason"] = "low_value"
    patched = client.patch(f"/v2/engine/tasks/{task_id}", json=patch_body, headers=h)
    assert patched.status_code == 200
    assert patched.json()["status"] == inactive_status

    # Even though teamwork_task_id + all teamwork_subtasks are already recorded, send MUST refuse with 400
    resend = client.post(f"/v2/engine/tasks/{task_id}/send", headers=h)
    assert resend.status_code == 400
    assert "dropped or rejected" in resend.json()["detail"].lower()


def test_patch_custom_parts_settles_shipped_status_merge_parts_preserves_done_and_reject_clears_annotations(
    client, db, client_a, admin_user
):
    h = client_header(client_a.id, admin_user.email)
    created = client.post(
        "/v2/engine/tasks",
        json={
            "month": "2026-10",
            "kind": "growth_action",
            "rule_id": "GA",
            "search": "spf 30",
            "page": PROD,
            "title": "Grow SPF 30",
            "steps": ["# 1. Rewrite the meta for clicks", "Update title"],
            "parts": [{"id": "MC-1", "name": "Rewrite the meta for clicks"}],
        },
        headers=h,
    ).json()["task"]
    task_id = created["id"]

    # Mark the sole part done -> task settles to shipped and writes an Annotation
    marked = client.patch(f"/v2/engine/tasks/{task_id}/parts/0", json={"done": True}, headers=h)
    assert marked.status_code == 200
    assert marked.json()["status"] == "shipped"
    assert marked.json()["parts"][0]["status"] == "done"
    assert marked.json()["parts"][0]["done_at"] is not None
    assert db.query(Annotation).filter(Annotation.client_id == client_a.id).count() == 1

    # Adding an open CUSTOM part to a shipped task reopens status from shipped -> confirmed
    reopened = client.patch(
        f"/v2/engine/tasks/{task_id}",
        json={
            "steps": ["# 1. Rewrite the meta for clicks", "Update title", "# 2. Add trust seal", "Add seal"],
            "parts": [
                {"id": "MC-1", "name": "Rewrite the meta for clicks"},
                {"id": "CUSTOM", "name": "Add trust seal", "custom": True},
            ],
        },
        headers=h,
    )
    assert reopened.status_code == 200, reopened.text
    rdata = reopened.json()
    assert rdata["status"] == "confirmed"
    assert rdata["shipped_at"] is None
    assert rdata["parts"][0]["status"] == "done"
    assert rdata["parts"][1]["id"] == "CUSTOM"
    assert rdata["parts"][1]["status"] == "open"

    # Mark the custom part done too -> shipped again
    done2 = client.patch(f"/v2/engine/tasks/{task_id}/parts/1", json={"done": True}, headers=h)
    assert done2.status_code == 200
    assert done2.json()["status"] == "shipped"
    custom_done_at = done2.json()["parts"][1]["done_at"]
    assert custom_done_at is not None

    # Sending id="" with custom=True preserves status="done" and done_at via _merge_parts normalization
    merged = client.patch(
        f"/v2/engine/tasks/{task_id}",
        json={
            "parts": [
                {"id": "MC-1", "name": "Rewrite the meta for clicks"},
                {"id": "", "name": "Add trust seal", "custom": True},
            ]
        },
        headers=h,
    )
    assert merged.status_code == 200
    mdata = merged.json()
    assert mdata["parts"][1]["id"] == "CUSTOM"
    assert mdata["parts"][1]["status"] == "done"
    assert mdata["parts"][1]["done_at"] == custom_done_at

    # Add an open custom part (reopens), then remove that last open part -> settles back to shipped
    reopened2 = client.patch(
        f"/v2/engine/tasks/{task_id}",
        json={
            "steps": ["# 1. Rewrite the meta for clicks", "Update title", "# 2. Add trust seal", "Add seal", "# 3. Temp open", "Wait"],
            "parts": [
                {"id": "MC-1", "name": "Rewrite the meta for clicks"},
                {"id": "CUSTOM", "name": "Add trust seal", "custom": True},
                {"id": "CUSTOM", "name": "Temp open", "custom": True},
            ],
        },
        headers=h,
    )
    assert reopened2.status_code == 200
    assert reopened2.json()["status"] == "confirmed"

    settled = client.patch(
        f"/v2/engine/tasks/{task_id}",
        json={
            "steps": ["# 1. Rewrite the meta for clicks", "Update title", "# 2. Add trust seal", "Add seal"],
            "parts": [
                {"id": "MC-1", "name": "Rewrite the meta for clicks"},
                {"id": "CUSTOM", "name": "Add trust seal", "custom": True},
            ],
        },
        headers=h,
    )
    assert settled.status_code == 200
    assert settled.json()["status"] == "shipped"
    assert settled.json()["shipped_at"] is not None
    assert db.query(Annotation).filter(Annotation.client_id == client_a.id).count() == 2

    # POST /v2/engine/tasks/reject on the shipped task clears done parts + removes Annotation rows
    rejected = client.post(
        "/v2/engine/tasks/reject",
        json={
            "month": "2026-10",
            "rule_id": "GA",
            "search": "spf 30",
            "page": PROD,
            "rejection_reason": "low_value",
            "rejection_note": "Reverting shipped work",
        },
        headers=h,
    )
    assert rejected.status_code == 200
    jdata = rejected.json()
    assert jdata["status"] == "rejected"
    assert jdata["shipped_at"] is None
    assert all(p["status"] == "open" and p.get("done_at") is None for p in jdata["parts"])
    assert db.query(Annotation).filter(Annotation.client_id == client_a.id).count() == 0


def test_page_history_and_prior_rejections_match_url_variants(client, db, client_a, admin_user):
    canonical = f"https://{client_a.domain}/services/roof-repair"
    variant = f"https://WWW.{client_a.domain.upper()}/Services/Roof-Repair/"

    db.add(
        EngineTask(
            client_id=client_a.id,
            month="2026-10",
            kind="growth_action",
            rule_id="GA",
            search="roof repair",
            page_url=variant,
            title="Rejected roof repair",
            status="rejected",
            confirmed_by=admin_user.email,
            rejected_by=admin_user.email,
            rejected_at=datetime(2026, 10, 5, tzinfo=timezone.utc),
            rejection_reason="wrong_target",
            rejection_note="Stored with www and trailing slash",
            parts=[],
        )
    )
    db.add(
        Annotation(
            client_id=client_a.id,
            date=date(2026, 10, 6),
            annotation_type=AnnotationType.CONTENT_UPDATED,
            description="Edited heading",
            page_url=variant,
        )
    )
    gsc(db, client_a, "roof repair", canonical, 500)
    db.commit()

    hist = page_history.for_page(db, client_a, canonical)
    assert len(hist["tasks"]) == 1
    assert hist["tasks"][0]["rejection_reason"] == "wrong_target"
    assert len(hist["annotations"]) == 1
    assert hist["annotations"][0]["description"] == "Edited heading"

    priors = ga._prior_rejections(db, client_a, canonical)
    assert len(priors) == 1
    assert priors[0]["rejection_reason"] == "wrong_target"

    res = client.get(
        "/v2/engine/page-history",
        params={"page": canonical},
        headers=client_header(client_a.id, admin_user.email),
    )
    assert res.status_code == 200
    assert len(res.json()["tasks"]) == 1
    assert len(res.json()["annotations"]) == 1


# ── Iteration 3 Regression Tests ─────────────────────────────────────────────


def test_patch_parts_syncs_and_reindexes_annotations_and_cleans_up_on_reject(client, db, client_a, admin_user):
    h = client_header(client_a.id, admin_user.email)

    # Case C5: deleting a done part removes its Annotation row (0 orphaned annotations)
    t1 = client.post(
        "/v2/engine/tasks",
        json={
            "month": "2026-10",
            "kind": "growth_action",
            "rule_id": "GA",
            "search": "roof leak",
            "page": "https://shop.example/services/roof",
            "title": "Grow roof",
            "steps": ["# 1. Rewrite the meta for clicks", "Title", "# 2. Custom", "Step"],
            "parts": [
                {"id": "MC-1", "name": "Rewrite the meta for clicks"},
                {"id": "CUSTOM", "name": "Custom", "custom": True},
            ],
        },
        headers=h,
    ).json()["task"]
    t1_id = t1["id"]
    assert client.patch(f"/v2/engine/tasks/{t1_id}/parts/0", json={"done": True}, headers=h).status_code == 200
    assert db.query(Annotation).filter(Annotation.client_id == client_a.id).count() == 1

    del_res = client.patch(
        f"/v2/engine/tasks/{t1_id}",
        json={"parts": [{"id": "CUSTOM", "name": "Custom", "custom": True}]},
        headers=h,
    )
    assert del_res.status_code == 200
    assert [p["id"] for p in del_res.json()["parts"]] == ["CUSTOM"]
    assert del_res.json()["parts"][0]["status"] == "open"
    assert db.query(Annotation).filter(Annotation.client_id == client_a.id).count() == 0

    # Re-indexing: deleting part 0 when parts 0 & 1 are both done shifts part 1's Annotation cleanly to :0
    t2 = client.post(
        "/v2/engine/tasks",
        json={
            "month": "2026-10",
            "kind": "growth_action",
            "rule_id": "GA",
            "search": "roof repair",
            "page": "https://shop.example/services/roof-repair",
            "title": "Grow roof repair",
            "steps": ["# 1. Rewrite the meta for clicks", "Title", "# 2. Add internal links", "Link"],
            "parts": [
                {"id": "MC-1", "name": "Rewrite the meta for clicks"},
                {"id": "V-4", "name": "Add internal links"},
            ],
        },
        headers=h,
    ).json()["task"]
    t2_id = t2["id"]
    assert client.patch(f"/v2/engine/tasks/{t2_id}", json={"status": "shipped"}, headers=h).status_code == 200
    assert db.query(Annotation).filter(Annotation.engine_uid.like(f"task:{t2_id}:%")).count() == 2

    reindexed = client.patch(
        f"/v2/engine/tasks/{t2_id}",
        json={"parts": [{"id": "V-4", "name": "Add internal links"}]},
        headers=h,
    )
    assert reindexed.status_code == 200
    assert reindexed.json()["status"] == "shipped"
    anns = db.query(Annotation).filter(Annotation.engine_uid.like(f"task:{t2_id}:%")).all()
    assert len(anns) == 1
    assert anns[0].engine_uid == f"task:{t2_id}:0"
    assert anns[0].growth_action == GrowthAction.INTERNAL_LINKING
    assert "Add internal links" in anns[0].description

    # Reordering: [V-4 (done), MC-1 (open)] -> [MC-1 (open), V-4 (done)] moves Annotation from :0 to :1
    with_open = client.patch(
        f"/v2/engine/tasks/{t2_id}",
        json={
            "parts": [
                {"id": "V-4", "name": "Add internal links"},
                {"id": "MC-1", "name": "Rewrite the meta for clicks", "status": "open"},
            ]
        },
        headers=h,
    )
    assert with_open.status_code == 200
    assert with_open.json()["status"] == "confirmed"
    reordered = client.patch(
        f"/v2/engine/tasks/{t2_id}",
        json={
            "parts": [
                {"id": "MC-1", "name": "Rewrite the meta for clicks", "status": "open"},
                {"id": "V-4", "name": "Add internal links"},
            ]
        },
        headers=h,
    )
    assert reordered.status_code == 200
    anns_reordered = db.query(Annotation).filter(Annotation.engine_uid.like(f"task:{t2_id}:%")).all()
    assert len(anns_reordered) == 1
    assert anns_reordered[0].engine_uid == f"task:{t2_id}:1"

    # Case C2: PATCH marking remaining open part "done" settles to "shipped" AND creates its Annotation
    marked_via_patch = client.patch(
        f"/v2/engine/tasks/{t2_id}",
        json={
            "parts": [
                {"id": "MC-1", "name": "Rewrite the meta for clicks", "status": "done"},
                {"id": "V-4", "name": "Add internal links"},
            ]
        },
        headers=h,
    )
    assert marked_via_patch.status_code == 200
    mdata = marked_via_patch.json()
    assert mdata["status"] == "shipped"
    assert mdata["shipped_at"] is not None
    assert mdata["parts"][0]["status"] == "done"
    assert mdata["parts"][0]["done_at"] is not None
    assert mdata["parts"][0]["done_by"] == admin_user.email
    assert db.query(Annotation).filter(Annotation.engine_uid.like(f"task:{t2_id}:%")).count() == 2

    # Case C1: PATCH status="rejected" + parts=[status="open"] cleans up all Annotation rows
    rejected_with_parts = client.patch(
        f"/v2/engine/tasks/{t2_id}",
        json={
            "status": "rejected",
            "rejection_reason": "low_value",
            "parts": [
                {"id": "MC-1", "name": "Rewrite the meta for clicks", "status": "open"},
                {"id": "V-4", "name": "Add internal links", "status": "open"},
            ],
        },
        headers=h,
    )
    assert rejected_with_parts.status_code == 200
    assert rejected_with_parts.json()["status"] == "rejected"
    assert all(p["status"] == "open" for p in rejected_with_parts.json()["parts"])
    assert db.query(Annotation).filter(Annotation.engine_uid.like(f"task:{t2_id}:%")).count() == 0


def test_confirm_task_restores_sent_and_deduplicates_url_variants_across_confirm_reject_and_allowance(
    client, db, client_a, admin_user, monkeypatch
):
    client_a.teamwork_tasklist_id = "12345"
    db.commit()
    h = client_header(client_a.id, admin_user.email)

    base_url = f"https://{client_a.domain}/services/plumbing"
    variant_url = f"https://WWW.{client_a.domain.upper()}/Services/Plumbing/"

    # Case C3: sent -> rejected -> confirm_task restores status="sent" when teamwork_task_id is set
    created = client.post(
        "/v2/engine/tasks",
        json={
            "month": "2026-10",
            "kind": "growth_action",
            "rule_id": "GA",
            "search": "plumbing repair",
            "page": base_url,
            "title": "Grow plumbing",
            "steps": ["# 1. Rewrite the meta for clicks", "Update title"],
            "parts": [{"id": "MC-1", "name": "Rewrite the meta for clicks"}],
        },
        headers=h,
    ).json()["task"]
    tid = created["id"]

    monkeypatch.setattr(teamwork, "configured", lambda: True)
    monkeypatch.setattr(teamwork, "create_task", lambda **kw: {"id": "tw-999", "url": "https://tw.example/999"})
    monkeypatch.setattr(teamwork, "create_subtask", lambda **kw: {"id": "sub-999", "url": ""})
    sent = client.post(f"/v2/engine/tasks/{tid}/send", headers=h)
    assert sent.status_code == 200
    assert sent.json()["status"] == "sent"

    # Confirming again while already "sent" preserves "sent"
    again_sent = client.post(
        "/v2/engine/tasks",
        json={
            "month": "2026-10",
            "kind": "growth_action",
            "rule_id": "GA",
            "search": "plumbing repair",
            "page": variant_url,
            "title": "Grow plumbing",
        },
        headers=h,
    )
    assert again_sent.status_code == 200
    assert again_sent.json()["created"] is False
    assert again_sent.json()["task"]["id"] == tid
    assert again_sent.json()["task"]["status"] == "sent"

    # Case C4: reject_task with URL variant matches the existing task instead of inserting a duplicate
    rej = client.post(
        "/v2/engine/tasks/reject",
        json={
            "month": "2026-10",
            "kind": "growth_action",
            "rule_id": "GA",
            "search": "plumbing repair",
            "page": variant_url,
            "rejection_reason": "low_value",
        },
        headers=h,
    )
    assert rej.status_code == 200
    assert rej.json()["id"] == tid
    assert rej.json()["status"] == "rejected"
    assert db.query(EngineTask).filter(EngineTask.client_id == client_a.id).count() == 1

    # Re-confirming via POST /v2/engine/tasks with URL variant restores "sent" (since teamwork_task_id is present)
    reconfirmed = client.post(
        "/v2/engine/tasks",
        json={
            "month": "2026-10",
            "kind": "growth_action",
            "rule_id": "GA",
            "search": "plumbing repair",
            "page": variant_url,
            "title": "Grow plumbing",
            "steps": ["# 1. Rewrite the meta for clicks", "Update title"],
            "parts": [{"id": "MC-1", "name": "Rewrite the meta for clicks"}],
        },
        headers=h,
    )
    assert reconfirmed.status_code == 200
    assert reconfirmed.json()["created"] is True
    assert reconfirmed.json()["task"]["id"] == tid
    assert reconfirmed.json()["task"]["status"] == "sent"
    assert reconfirmed.json()["task"]["teamwork_task_id"] == "tw-999"
    assert reconfirmed.json()["task"]["rejection_reason"] is None
    assert db.query(EngineTask).filter(EngineTask.client_id == client_a.id).count() == 1

    # Confirming a second rule on a URL variant of the same page counts as 1 page in _pages_used()
    second_rule = client.post(
        "/v2/engine/tasks",
        json={
            "month": "2026-10",
            "kind": "suggestion",
            "rule_id": "S-1",
            "search": "plumbing repair",
            "page": variant_url,
            "title": "Use searched phrasing",
            "steps": ["Add terms"],
        },
        headers=h,
    )
    assert second_rule.status_code == 200
    assert second_rule.json()["allowance"]["used"] == 1
    assert client.get("/v2/engine/tasks?month=2026-10", headers=h).json()["allowance"]["used"] == 1


def test_t1_ranks_with_ctr_actions_under_traffic_focus(db, client_a):
    traffic_ids = [x["id"] for x in order_by_focus([{"id": "W-1"}, {"id": "S-2"}, {"id": "T-1"}], "traffic")]
    assert traffic_ids == ["T-1", "S-2", "W-1"]

    url = f"https://{client_a.domain}/services/t1-page"
    gsc(db, client_a, "plumbing estimate", url, 1000, clicks=5, position=4.0)
    crawled(db, client_a, url, "Plumbing Estimate")
    db.commit()

    out = ga.build(
        db,
        client_a,
        SEP,
        "plumbing estimate",
        page=url,
        focus="traffic",
        diagnose=read([sug("S-2"), sug("S-1")], prescriptions=[{"action_id": "T-1", "title": "Rewrite the title tag", "why": "CTR gap", "steps": ["Update title"], "evidence": []}]),
        evidence_for=lambda s, u: {},
        signals_for=lambda s: {"reading": reading("transactional")},
    )
    assert out["ok"] is True
    assert out["parts"][0]["id"] == "T-1"
    assert out["parts"][0]["role"] == "primary"

