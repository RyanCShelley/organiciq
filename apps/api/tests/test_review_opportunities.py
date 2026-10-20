from copy import deepcopy
from types import SimpleNamespace
import pytest

from app.decisions.review_opportunities import review_opportunities
from app.services.plan_review import view


def assessment():
    return {'month':'2026-09','action_slots':3,'measurements':{
        'start':'2026-09-01','end':'2026-09-30','prior_start':'2026-08-02','prior_end':'2026-08-31',
        'traffic':{'current':{'total':400,'channels':{'direct_unattributed':200}},
                   'previous':{'total':1000,'channels':{'direct_unattributed':800}}},
        'visibility':{'keywords':[],'monthly_trend':{'rows':[]}}}}


def test_traffic_review_is_not_a_prescribed_fix_or_approved_task():
    data=assessment();before=deepcopy(data)
    rows=review_opportunities(data)
    assert len(rows)==1 and rows[0]['kind']=='traffic_decline'
    assert '60.0%' in rows[0]['summary'] and '600 visits' in rows[0]['summary']
    assert 'not a verified page defect' in rows[0]['limitation']
    assert 'does not prove SEO impact' in rows[0]['review_checks'][1]
    assert not {'action_uid','steps','approved_at'} & rows[0].keys()
    assert data==before
    review=view(SimpleNamespace(id='assessment-one', record=data))
    assert review['items']==[] and review['proposals']==[] and review['approved_at'] is None
    assert review['review_opportunities']==rows
    assert review['capacity']==3 and data==before


@pytest.mark.parametrize('now,before', [(1,50),(990,1000),(None,1000),(10,None),(-1,1000),(float('nan'),1000)])
def test_tiny_unknown_or_invalid_traffic_is_not_a_material_decline(now,before):
    data=assessment();data['measurements']['traffic']['current']['total']=now
    data['measurements']['traffic']['previous']['total']=before
    assert review_opportunities(data)==[]


def test_non_comparable_periods_do_not_create_traffic_opportunities():
    data=assessment();data['measurements']['prior_start']='2026-08-01'
    assert review_opportunities(data)==[]


def test_keyword_loss_needs_a_current_tracked_term_and_dated_comparison():
    data=assessment();data['measurements']['traffic']={}
    visibility=data['measurements']['visibility']
    visibility['keywords']=[{'text':'Target','target_url':'https://example.com/service'}]
    row={'text':'target','previous':2,'current':69,'previous_date':'2026-08-31','current_date':'2026-09-30'}
    visibility['monthly_trend']['rows']=[row, {**row,'text':'old untracked term'}]
    result=review_opportunities(data)
    assert len(result)==1 and result[0]['kind']=='ranking_loss'
    assert result[0]['target_url']=='https://example.com/service'
    assert '1 current tracked term' in result[0]['summary']
    assert 'position 69' in result[0]['evidence'][0]
    for patch in ({'previous_date':None},{'current_date':'2026-10-01'},{'previous':101},{'current':3}):
        visibility['monthly_trend']['rows']=[{**row,**patch}]
        assert review_opportunities(data)==[]


def test_limited_reach_does_not_turn_unknown_or_stale_rankings_into_failure():
    data=assessment();data['measurements']['traffic']={}
    rows=[{'text':f'term {i}','status':'not_in_top_100','observed_on':'2026-09-30'} for i in range(4)]
    rows += [{'text':'ranked','status':'top_100','observed_on':'2026-09-30'},
             {'text':'unknown','status':'unmeasured','observed_on':None},
             {'text':'old','status':'not_in_top_100','observed_on':'2026-08-31'}]
    data['measurements']['visibility']['keywords']=rows
    result=review_opportunities(data)
    assert len(result)==1 and '4 of 5' in result[0]['summary']
    assert 'do not establish a decline' in result[0]['review_checks'][1]
    rows[0]['observed_on']=None
    assert review_opportunities(data)==[]


def test_existing_approval_is_retained_and_opportunity_identity_is_stable():
    data=assessment();data['plan_review']={'revision':7,'items':[], 'approved_at':'2026-10-19','versions':[{'revision':7}]}
    before=deepcopy(data)
    result=view(SimpleNamespace(id='assessment-one', record=data))
    assert result['approved_at']=='2026-10-19' and result['revision']==7
    assert result['review_opportunities'][0]['uid']==view(SimpleNamespace(id='assessment-one', record=data))['review_opportunities'][0]['uid']
    assert data==before


def test_duplicate_target_terms_cannot_inflate_review_coverage():
    data=assessment();data['measurements']['traffic']={}
    data['measurements']['visibility']['keywords']=[{'text':'same term','status':'not_in_top_100','observed_on':'2026-09-30'}]*10
    assert review_opportunities(data)==[]
