from copy import deepcopy
from app.decisions.action_reasoning import connect, explain


def finding(rule='V-7', page='https://example.com/pool', term='pool'):
    return {'id':rule,'target_url':page,'term':term,'action_uid':'finding-one',
            'why':'Visible FAQ has no matching markup.','evidence':['Observed FAQ; no FAQPage block.']}


def test_task_links_only_its_own_page_and_rule_without_claiming_ranking_causation():
    faq=finding()
    assessment={'findings':[faq,finding(page='https://example.com/other')], 'measurements':{'visibility':{'monthly_trend':{'rows':[{'text':'pool','previous':1,'current':101}]}}}}
    task={**faq,'action_uid':'task-one','finding_ids':['V-7'],'metric':'Validate visible answers and markup'}
    before=deepcopy(assessment)
    result=connect([{**task,'interventions':[task]}],assessment)
    linked=result[0]['interventions'][0]['reasoning']
    assert [x['uid'] for x in linked['findings']]==['finding-one']
    assert linked['findings'][0]['page']=='https://example.com/pool'
    assert 'does not explain a ranking loss' in linked['why_this_action']
    assert linked['outcome']==task['metric']
    assert assessment==before and 'reasoning' not in task


def test_same_branch_or_page_is_insufficient_without_matching_rule():
    result=explain({'id':'T-1','finding_ids':['T-1'],'target_url':'https://example.com/pool'}, {'findings':[finding()]})
    assert result['status']=='unresolved' and result['findings']==[]


def test_term_specific_work_cannot_borrow_another_terms_evidence():
    source=finding(rule='V-5',term='different intent')
    result=explain({**source,'term':'pool'}, {'findings':[source]})
    assert result['status']=='unresolved'


def test_page_wide_checks_can_link_across_term_variants_and_url_scheme():
    task={**finding(),'target_url':'http://example.com/pool/','term':'another query'}
    assert explain(task,{'findings':[finding()]})['status']=='supported'


def test_site_wide_traffic_change_cannot_justify_a_page_task():
    task={'id':'T-1','target_url':'https://example.com/pool'}
    assert explain(task,{'measurements':{'traffic':{'current':{'total':100},'previous':{'total':1000}}}})['status']=='unresolved'


def test_review_response_carries_links_without_mutating_the_saved_assessment():
    from types import SimpleNamespace
    from app.services.plan_review import view
    source={**finding(),'steps':['Add matching FAQ markup.'],'done_when':'Markup matches the visible FAQ.','title':'Mark up FAQ','metric':'Validate FAQ markup'}
    data={'month':'2026-09','action_slots':1,'review_required':True,'findings':[source]}
    before=deepcopy(data)
    result=view(SimpleNamespace(id='assessment-one',record=data))
    linked=result['proposals'][0]['interventions'][0]['reasoning']
    assert linked['status']=='supported'
    assert linked['findings'][0]['uid']=='finding-one'
    assert result['items']==[] and result['approved_at'] is None
    assert data==before


def test_server_rebuilds_and_preserves_finding_links_through_approval(db, client, client_a, admin_user):
    from app.models.decision import MonthlyRecord
    from tests.conftest import client_header
    from tests.test_reviewed_planning import brief
    source = {**brief('source'), 'id': 'T-1', 'family': 'priority_page',
              'why': 'Observed clicks below the reference scenario.', 'finding_ids': ['T-1']}
    row = MonthlyRecord(client_id=client_a.id, month='2026-09', constraint_name='traffic',
        held_since='2026-09', confidence='low', record={'month':'2026-09',
        'constraint':'traffic','action_slots':1,'review_required':True,'findings':[source],
        'actions':[],'candidates':[],'incidents':[]})
    db.add(row)
    db.commit()
    headers = client_header(client_a.id, admin_user.email)
    path = '/decisions/records/2026-09/review'
    proposal = client.get(path, headers=headers).json()['proposals'][0]['interventions'][0]
    proposal['reasoning'] = {'status':'supported','why_this_action':'Forged client claim'}
    response = client.put(path, headers=headers, json={'revision':0,'focus':'traffic','items':[proposal]})
    assert response.status_code == 200, response.text
    linked = response.json()['items'][0]['reasoning']
    assert linked['status'] == 'supported'
    assert linked['findings'][0]['uid'] == 'source'
    assert 'Forged' not in linked['why_this_action']
    approved = client.post(path + '/approve', headers=headers, json={'revision':1})
    assert approved.status_code == 200, approved.text
    assert approved.json()['versions'][0]['items'][0]['reasoning'] == linked


def test_rewritten_scope_cannot_inherit_an_automated_prescription():
    source = {**finding(), 'steps': ['Mark up the visible FAQ.']}
    changed = {**source, 'steps': ['Rewrite the service offering.']}
    assert explain(changed, {'findings':[source]})['status'] == 'unresolved'
    custom = {**source, 'id':'MANUAL', 'finding_ids':['V-7']}
    assert explain(custom, {'findings':[source]})['status'] == 'unresolved'
