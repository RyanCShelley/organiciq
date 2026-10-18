"""Versioned human decisions stored beside, never in place of, assessments."""
from copy import deepcopy
from datetime import datetime, timezone

from app.decisions.planning import effective_record, initial_review, page_identity, proposals, validate_plan
from app.models.decision import MonthlyRecord


class ReviewConflict(ValueError):
    pass


def locked_record(db, client, month):
    return db.query(MonthlyRecord).filter(
        MonthlyRecord.client_id == client.id, MonthlyRecord.month == month,
    ).with_for_update().one_or_none()


def view(record):
    data = record.record
    review = deepcopy(data.get("plan_review") or initial_review(data))
    return {**review, "proposals": proposals(data), "capacity": data.get("growth_capacity", data["action_slots"]),
            "suggested_focus": data.get("constraint"),
            "setup_findings": [x for x in data.get("findings", data.get("candidates", [])) if x.get("id") == "V-6"]}


def save(db, record, payload, user):
    data = deepcopy(record.record)
    old = data.get("plan_review") or initial_review(data)
    if payload.revision != old["revision"]:
        raise ReviewConflict("This plan changed in another window. Reload before saving.")
    # Once work has left the plan, editing its scope must use a new identity.
    # Keeping the UID is safe only when the actual brief is unchanged.
    from app.models.decision import EngineAction
    previous = {x["action_uid"]: x for x in old["items"]}
    items = [x.model_dump(mode="json") for x in payload.items]
    retained = {x["action_uid"] for x in items}
    for uid in previous.keys() - retained:
        workflow = db.query(EngineAction).filter(EngineAction.client_id == record.client_id, EngineAction.uid == uid).one_or_none()
        if workflow and (workflow.sent_at or workflow.shipped_on or workflow.assignee_email):
            raise ValueError("Assigned, sent or shipped work must remain in this month's plan history. Unassign draft work before replacing it.")
    for item in items:
        other = db.query(EngineAction).filter(
            EngineAction.client_id == record.client_id, EngineAction.uid == item["action_uid"],
        ).one_or_none()
        if other and other.month != record.month:
            raise ValueError("An action identity cannot be reused in another month.")
        if other and other.kind != "action":
            raise ValueError("A growth action cannot reuse a retainer or incident identity.")
        before = previous.get(item["action_uid"])
        if before:
            from app.schemas.plan_review import Brief
            before = Brief.model_validate(before).model_dump(mode="json")
        if before and before != item:
            workflow = db.query(EngineAction).filter(
                EngineAction.client_id == record.client_id,
                EngineAction.uid == item["action_uid"],
            ).one_or_none()
            if workflow and (workflow.sent_at or workflow.shipped_on or workflow.assignee_email):
                raise ValueError("An assigned, sent or shipped brief cannot be rewritten. Unassign it or add a new brief for new scope.")
    review = {**old, **payload.model_dump(mode="json"), "revision": old["revision"] + 1,
              "approved_at": None, "approved_by": None,
              "edited_by": str(user.email)}
    data["plan_review"] = review
    record.record = data
    db.commit()
    return view(record)


def approve(db, record, revision, user):
    data = deepcopy(record.record)
    review = data.get("plan_review") or initial_review(data)
    if revision != review["revision"]:
        raise ReviewConflict("This plan changed. Reload before approving.")
    if review.get("approved_at"):
        return view(record)
    validate_plan(review, data.get("growth_capacity", data["action_slots"]))
    from app.models.decision import EngineAction
    states = {x.uid: x for x in db.query(EngineAction).filter(EngineAction.client_id == record.client_id, EngineAction.month == record.month)}
    reserved = set()
    for key, candidates in (("updates", "update_candidates"), ("new_content", "content_candidates")):
        seen = set()
        for item in [*data.get(key, []), *data.get(candidates, [])]:
            uid = item.get("action_uid")
            if uid in seen:
                continue
            seen.add(uid)
            state = states.get(uid)
            selected = state.in_plan if state and state.in_plan is not None else item.get("slot") is not None
            if selected and item.get("target_url") and (not state or state.status != "skipped"):
                reserved.add(page_identity(item["target_url"]))
    if {page_identity(x["target_url"]) for x in review["items"]} & reserved:
        raise ValueError("A selected page already has retainer work this month. Combine or remove that work first.")
    review = deepcopy(review)
    review.update(approved_at=datetime.now(timezone.utc).isoformat(), approved_by=str(user.email),
                  revision=review["revision"] + 1)
    snapshot = {k: deepcopy(v) for k, v in review.items() if k != "versions"}
    review["versions"] = [*review.get("versions", []), snapshot]
    data["plan_review"] = review
    record.record = data
    db.commit()
    return view(record)


def workflow_record(data):
    """Reviewed items remain addressable after reruns and manual exclusions."""
    out = effective_record(data)
    return out
