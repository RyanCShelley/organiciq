from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.decisions.catalog import PageFacts
from app.decisions.slots import Prescription
from app.decisions.triage import Branch
from app.services.crawl_source import crawl_evidence_limit


@pytest.mark.parametrize('age,limited', [(0, False), (14, False), (15, True), (365, True), (-1, True)])
def test_crawl_age_boundary(age, limited):
    checked = date(2026, 10, 20)
    assert bool(crawl_evidence_limit(checked - timedelta(days=age), checked_on=checked)) is limited


def test_missing_crawl_is_unknown_not_empty():
    assert 'No successful' in crawl_evidence_limit(None)


def prescription(action_id):
    return Prescription(action_id=action_id, title='Verify page', branch=Branch.VISIBILITY,
        target_url='https://example.com/service', term='service', score=100,
        effort_min=30, why='Verified evidence', done_when='Verified change', metric='Position')


@pytest.mark.parametrize('age,has_faq', [(14, True), (15, False)])
def test_backdated_assessment_limits_new_fixes_but_keeps_performance_and_approval(db, client_a, monkeypatch, age, has_faq):
    from app.services import monthly_run, plan_review
    from app.models.decision import MonthlyRecord

    url = 'https://example.com/service'
    faq, ctr = prescription('V-7'), prescription('T-1')
    scored = SimpleNamespace(candidate=SimpleNamespace(keyword='service', target_url=url))
    inputs = SimpleNamespace(crawl_date=date.today() - timedelta(days=age),
        candidates=[], pages={url: PageFacts(url=url, page_type='service')}, excluded=[])
    monkeypatch.setattr(monthly_run, 'load_target_inputs', lambda *a, **k: inputs)
    monkeypatch.setattr(monthly_run, 'rank_candidates', lambda *a, **k: [scored])
    monkeypatch.setattr(monthly_run, 'VISIBILITY_ACTIONS', [lambda *a: faq, lambda *a: ctr])
    monkeypatch.setattr(monthly_run, 'prescribe', lambda *a: faq)
    # A historical reporting month must not make a months-old crawl fresh.
    record = monthly_run.build_record(db, client_a, today=date(2026, 9, 30))
    ids = {x['id'] for x in record['findings']}
    assert ('V-7' in ids) is has_faq
    assert 'T-1' in ids
    assert bool(record['crawl_evidence_limit']) is not has_faq

    approval = {'revision': 2, 'approved_at': '2026-10-19T12:00:00Z', 'items': [dict(id='V-7', title='Approved FAQ')], 'versions': []}
    row = MonthlyRecord(client_id=client_a.id, month='2026-09', constraint_name='visibility',
        held_since='2026-09', confidence='low', record={**record, 'plan_review': approval})
    view = plan_review.view(row)
    assert view['approved_at'] == approval['approved_at']
    assert view['items'] == approval['items']
    assert view['crawl_evidence_limit'] == record['crawl_evidence_limit']
