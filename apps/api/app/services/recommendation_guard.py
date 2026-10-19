"""Withhold repeated work while the same intervention is active or measuring."""
from datetime import date, timedelta
from app.decisions.planning import page_identity
from app.models.decision import EngineAction, MonthlyRecord

# These interventions concern the whole page, regardless of which tracked term found it.
PAGE_RULES = {'V-4', 'V-7', 'T-1', 'T-3', 'L-1', 'L-2', 'L-3'}
RETIRED_RULES = {'V-1', 'V-8', 'V-3', 'V-2'}


def _steps(item):
    return {' '.join(s.casefold().split()) for s in item.get('steps') or [item.get('done_when') or ''] if s.strip()}


def _items(data):
    for key in ('actions', 'candidates', 'updates', 'update_candidates', 'new_content', 'content_candidates'):
        yield from data.get(key, [])
    review = data.get('plan_review') or {}
    for snapshot in [*review.get('versions', []), review]:
        yield from snapshot.get('items', [])


def blockers(db, record, rows, *, today=None):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from app.models.client import Client
    client = db.get(Client, record.client_id)
    today = today or datetime.now(ZoneInfo(client.timezone or 'UTC')).date()
    histories = db.query(MonthlyRecord).filter_by(client_id=record.client_id).all()
    briefs = {item.get('action_uid'): item for history in histories for item in _items(history.record or {})}
    active = []
    for state in db.query(EngineAction).filter_by(client_id=record.client_id):
        if state.status == 'skipped' or not (state.assignee_email or state.sent_at or state.shipped_on or state.status == 'done'):
            continue
        brief = getattr(state, "action_snapshot", None) or briefs.get(state.uid) or {}
        if state.shipped_on:
            days = max(28, int(brief.get('check_after_days') or 28))
            if state.shipped_on + timedelta(days=days) <= today:
                continue
        active.append((state, brief))
    reasons = {}
    for index, row in enumerate(rows):
        if row.get('id') in RETIRED_RULES:
            reasons[index] = 'This legacy trigger is retired. Review the page and specify a supported custom action instead.'
            continue
        for state, brief in active:
            if row.get('action_uid') == state.uid:
                continue  # existing delivery identity remains accessible
            if page_identity(row.get('target_url') or '') != page_identity(state.target_url or brief.get('target_url') or ''):
                continue
            rule = state.action_id or brief.get('id')
            same_scope = bool(_steps(row) & _steps(brief)) or (
                row.get('id') == rule and (rule in PAGE_RULES or
                    bool(row.get('term')) and row.get('term', '').casefold() == (brief.get('term') or '').casefold()))
            if same_scope:
                reasons[index] = ('The same intervention is awaiting its results window.' if state.shipped_on
                                  else 'The same intervention is already assigned or delivered.')
                break
    return reasons
