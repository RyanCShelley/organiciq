from copy import deepcopy
from datetime import date, datetime, timedelta, timezone

from app.decisions.planning import proposals, validate_plan
from app.models.decision import MonthlyRecord, EngineAction
from app.models.watch_target import WatchTarget
from app.services.results import _slotted, check_due
from tests.conftest import client_header

MONTH = "2026-09"


def brief(uid="manual-one", url="https://example.com/service"):
    return dict(action_uid=uid, id="MANUAL", family="investigation", title="Review the conversion path",
        branch="leads", target_url=url, term=None, why="Priority service needs a reviewed next step.",
        done_when="Evidence and selected next step recorded.", steps=["Inspect page and verify the offer."],
        evidence=["Reviewed strategic priority"], finding_ids=[], effort_min=60,
        metric="Documented next step", metric_key="decision", check_after_days=28)


def seed(db, client):
    row = MonthlyRecord(client_id=client.id, month=MONTH, constraint_name="visibility",
        held_since=MONTH, confidence="low", record={"month": MONTH, "constraint": "visibility",
        "action_slots": 1, "review_required": True, "actions": [], "candidates": [], "incidents": []})
    db.add(row)
    db.commit()
    return row


def payload(items=None, revision=0):
    return dict(revision=revision, strategy="Prioritize the service launch.", focus="leads",
                reason="The launch needs a clear conversion route.", items=[brief()] if items is None else items)


def test_review_can_select_healthy_branch_and_survives_assessment(db, client, client_a, admin_user, monkeypatch):
    row = seed(db, client_a)
    headers = client_header(client_a.id, admin_user.email)
    path = f"/decisions/records/{MONTH}/review"
    saved = client.put(path, headers=headers, json=payload())
    assert saved.status_code == 200, saved.text
    approved = client.post(path + "/approve", headers=headers, json={"revision": 1})
    assert approved.status_code == 200, approved.text
    assert len(approved.json()["versions"]) == 1
    record = client.get(f"/decisions/records/{MONTH}", headers=headers).json()
    assert record["constraint"] == "leads"
    assert record["engine_constraint"] == "visibility"
    assert record["actions"][0]["action_uid"] == "manual-one"
    from app.services import monthly_run
    fresh = {**deepcopy(row.record), "constraint": "traffic", "plan_review": None,
             "data_through": "2026-09-30", "held_since": MONTH, "confidence": "low"}
    fresh.pop("plan_review")
    monkeypatch.setattr(monthly_run, "build_record", lambda *a, **k: fresh)
    monkeypatch.setattr(monthly_run, "capture_before", lambda *a, **k: 0)
    monthly_run.save_record(db, client_a, month=MONTH)
    db.refresh(row)
    assert row.record["plan_review"]["approved_at"]
    assert row.record["plan_review"]["items"][0]["action_uid"] == "manual-one"


def test_review_rejects_stale_writes_and_capacity(db, client, client_a, admin_user):
    seed(db, client_a)
    headers = client_header(client_a.id, admin_user.email)
    path = f"/decisions/records/{MONTH}/review"
    assert client.put(path, headers=headers, json=payload()).status_code == 200
    assert client.put(path, headers=headers, json=payload()).status_code == 409
    saved = client.put(path, headers=headers, json=payload([brief(), brief("manual-two", "https://example.com/other")], 1))
    assert saved.status_code == 200
    assert client.post(path + "/approve", headers=headers, json={"revision": 2}).status_code == 422


def test_duplicate_intervention_is_refused_but_distinct_work_on_a_page_is_allowed():
    import pytest
    with pytest.raises(ValueError, match="same action"):

        validate_plan(payload([brief(), brief("second")]), 2)
    validate_plan({**payload(), "strategy": "", "reason": ""}, 2)
    second = {**brief("second"), "steps": ["Add verified entity schema."]}
    validate_plan(payload([brief(), second]), 2)
    with pytest.raises(ValueError, match="allows 2"):
        validate_plan(payload([{**brief(), "steps": ["One", "Two", "Three"]}]), 2)


def test_reviewed_work_cannot_be_sent_before_approval(db, client, client_a, admin_user, monkeypatch):
    seed(db, client_a)
    headers = client_header(client_a.id, admin_user.email)
    path = f"/decisions/records/{MONTH}"
    client.put(path + "/review", headers=headers, json=payload())
    monkeypatch.setattr("app.integrations.teamwork.create_task", lambda **kwargs: (_ for _ in ()).throw(AssertionError("must not send")))
    assert client.post(path + "/slots/manual-one/send", headers=headers).status_code == 422


def test_all_findings_are_grouped_and_mapping_uses_no_growth_slot():
    rows = [{**brief(), "id": rule, "family": None} for rule in ("V-1", "T-1", "V-6", "V-4")]
    found = proposals({"month": MONTH, "findings": rows})
    assert [x["family"] for x in found] == ["priority_page", "internal_links"]
    assert found[0]["finding_ids"] == ["V-1", "T-1"]
    assert proposals({"month": "2026-10", "findings": rows})[0]["action_uid"] != found[0]["action_uid"]


def test_results_follow_approved_selection_not_original_slots():
    original = brief("original")
    selected = brief("selected")
    data = {"actions": [original], "plan_review": {"approved_at": "now", "items": [selected]}}
    assert [x["action_uid"] for _, x in _slotted(data)] == ["selected"]
    data["plan_review"] = {"approved_at": None, "items": [], "versions": [{"items": [selected]}]}
    assert [x["action_uid"] for _, x in _slotted(data)] == ["selected"]


def test_unshipped_work_is_not_measured_or_completed(db, client_a, monkeypatch):
    row = seed(db, client_a)
    row.record = {**row.record, "review_required": False, "actions": [{**brief(), "check_on": "2026-01-01"}]}
    action = EngineAction(uid="manual-one", client_id=client_a.id, month=MONTH, kind="action", status="assigned", before_value=1)
    db.add(action)
    db.commit()
    monkeypatch.setattr("app.services.results.measure", lambda *a, **k: (_ for _ in ()).throw(AssertionError("not shipped")))
    assert check_due(db, client_a, today=date(2026, 10, 17)) == []
    assert action.status == "assigned"


def test_prompt_and_keyword_targets_preserve_unknown_and_explicit_states(db, client, client_a, admin_user):
    headers = client_header(client_a.id, admin_user.email)
    body = dict(kind="prompt", text="Which service is appropriate?", provider="Tester / model A",
                state="existing", target_url="https://example.com/service", priority=True,
                observation={"observed_on": "2026-09-20", "brand_mentioned": False})
    response = client.put("/decisions/watchlist", headers=headers, json=body)
    assert response.status_code == 200, response.text
    prompt = next(x for x in response.json() if x["kind"] == "prompt")
    assert prompt["observation"]["brand_mentioned"] is False
    assert "brand_cited" not in prompt["observation"]
    assert prompt["target_url"] == body["target_url"]
    body.update(kind="keyword", text="priority service", state="planned", note="Create service comparison page", target_url=None, observation={})
    assert client.put("/decisions/watchlist", headers=headers, json=body).status_code == 200
    assert db.query(WatchTarget).filter_by(client_id=client_a.id).count() == 2
    body.update(state="excluded", note=None)
    assert client.put("/decisions/watchlist", headers=headers, json=body).status_code == 422


def test_approved_delivery_carries_the_reviewed_checklist_and_locks_sent_scope(db, client, client_a, admin_user, monkeypatch):
    seed(db, client_a)
    headers = client_header(client_a.id, admin_user.email)
    path = f"/decisions/records/{MONTH}"
    client.put(path + "/review", headers=headers, json=payload())
    client.post(path + "/review/approve", headers=headers, json={"revision": 1})
    captured = {}
    def create_task(**kwargs):
        captured.update(kwargs)
        return {"id": "test-task", "url": "https://example.com/task"}
    monkeypatch.setattr("app.integrations.teamwork.create_task", create_task)
    result = client.post(path + "/slots/manual-one/send", headers=headers)
    assert result.status_code == 200, result.text
    assert "Inspect page and verify the offer." in captured["description"]
    assert "Reviewed strategic priority" in captured["description"]
    changed = brief()
    changed["done_when"] = "A different job."
    assert client.put(path + "/review", headers=headers, json=payload([changed], 2)).status_code == 422
    assert client.put(path + "/review", headers=headers, json=payload([], 2)).status_code == 422


def test_draft_cannot_bypass_approval_by_assignment_or_shipping(db, client, client_a, admin_user):
    seed(db, client_a)
    headers = client_header(client_a.id, admin_user.email)
    path = f"/decisions/records/{MONTH}"
    client.put(path + "/review", headers=headers, json=payload())
    assert client.post(path + "/slots/manual-one/assign", headers=headers, json={"assignee_email": admin_user.email, "due": None}).status_code == 422
    assert client.post(path + "/slots/manual-one/shipped", headers=headers, json={"shipped_on": "2026-10-01"}).status_code == 422
    assert client.post(path + "/slots/manual-one/in-plan", headers=headers, json={"in_plan": False}).status_code == 422


def test_reviewed_results_wait_from_shipping_even_without_a_prescribed_check_date(db, client_a, monkeypatch):
    from app.services.results import Measurement
    row = seed(db, client_a)
    selected = {**brief(), "metric_key": "page_clicks", "check_on": None, "check_after_days": 28}
    row.record = {**row.record, "plan_review": {"approved_at": "now", "items": [selected]}}
    action = EngineAction(uid="manual-one", client_id=client_a.id, month=MONTH, kind="action", status="done", shipped_on=date(2026, 10, 1), before_value=10)
    db.add(action)
    db.commit()
    monkeypatch.setattr("app.services.results.measure", lambda *a, **k: Measurement(20))
    assert check_due(db, client_a, today=date(2026, 10, 28)) == []
    assert [x.result for x in check_due(db, client_a, today=date(2026, 10, 29))] == ["improved"]


def test_legacy_review_adoption_preserves_assigned_identity(db, client, client_a, admin_user):
    row = seed(db, client_a)
    selected = {**brief("legacy-one"), "slot": 1}
    row.record = {**row.record, "review_required": False, "actions": [selected]}
    db.add(EngineAction(uid="legacy-one", client_id=client_a.id, month=MONTH, kind="action", status="assigned", assignee_email=admin_user.email))
    db.commit()
    headers = client_header(client_a.id, admin_user.email)
    path = f"/decisions/records/{MONTH}/review"
    initial = client.get(path, headers=headers).json()
    assert initial["items"][0]["action_uid"] == "legacy-one"
    response = client.put(path, headers=headers, json={**payload(), "items": initial["items"]})
    assert response.status_code == 200, response.text
    assert db.query(EngineAction).filter_by(uid="legacy-one").one().assignee_email == admin_user.email


def test_prompt_findings_and_planned_pages_do_not_require_keyword_volume(db, client_a):
    from app.schemas.watchlist import WatchTargetUpdate
    from app.services.watchlist import write
    from app.services.monthly_run import build_record
    observed = WatchTargetUpdate(kind="prompt", text="Which service should I choose?", provider="test-model",
        state="existing", target_url="https://example.com/service", priority=True,
        observation={"observed_on": "2026-09-20", "brand_cited": False})
    write(db, client_a, observed)
    record = build_record(db, client_a, today=date(2026, 9, 30))
    assert any(x["id"] == "G-1" for x in record["findings"])
    assert record["growth_capacity"] == 1  # independent review even without GSC
    observed.state = "planned"
    observed.target_url = None
    observed.note = "Build a service comparison for the selected audience."
    write(db, client_a, observed)
    record = build_record(db, client_a, today=date(2026, 9, 30))
    assert any(x["id"] == "C-P" for x in record["new_content"])


def test_five_individual_actions_on_two_pages_approve_and_deliver_independently(db, client, client_a, admin_user, monkeypatch):
    row = seed(db, client_a)
    row.record = {**row.record, "growth_capacity": 5}
    db.commit()
    headers = client_header(client_a.id, admin_user.email)
    path = f"/decisions/records/{MONTH}"
    items = [{**brief(f"task-{i}", f"https://example.com/page-{1 if i < 3 else 2}"),
              "title": f"Selected action {i}", "steps": [f"Do intervention {i}"], "done_when": f"Intervention {i} verified"} for i in range(5)]
    saved = client.put(path + "/review", headers=headers, json=payload(items))
    assert saved.status_code == 200, saved.text
    approved = client.post(path + "/review/approve", headers=headers, json={"revision": 1})
    assert approved.status_code == 200, approved.text
    delivered = []
    def send(**kwargs):
        delivered.append(kwargs)
        return {"id": str(len(delivered)), "url": f"https://example.com/task/{len(delivered)}"}
    monkeypatch.setattr("app.integrations.teamwork.create_task", send)
    for item in items:
        response = client.post(path + f"/slots/{item['action_uid']}/send", headers=headers)
        assert response.status_code == 200, response.text
    assert len(delivered) == 5
    for i, task in enumerate(delivered):
        assert f"Do intervention {i}" in task["description"]


def test_existing_assessment_gets_measurement_view_without_rewriting_history(db, client, client_a, admin_user):
    row = seed(db, client_a)
    headers = client_header(client_a.id, admin_user.email)
    before = deepcopy(row.record)
    result = client.get(f"/decisions/records/{MONTH}", headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()["measurements"]["end"] == "2026-09-30"
    assert "currently stored facts" in result.json()["measurements"]["source_note"]
    db.refresh(row)
    assert row.record == before
