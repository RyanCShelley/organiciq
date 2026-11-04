from datetime import date
from app.models.decision import EngineAction, MonthlyRecord
from app.services.recommendation_guard import blockers
from app.decisions.planning import proposals


def record(db, client, month='2026-09', rows=None):
    r=MonthlyRecord(client_id=client.id,month=month,constraint_name='visibility',held_since=month,confidence='low',record={'actions': rows or []})
    db.add(r);db.commit();return r


def test_active_page_work_blocks_same_intervention_not_other_work_or_clients(db,client_a,client_b):
    r=record(db,client_a)
    row={'id':'V-7','target_url':'https://www.clienta.example/service/','steps':['Add visible FAQ markup.']}
    db.add(EngineAction(uid='active',client_id=client_a.id,month='2026-08',action_id='V-7',target_url='http://clienta.example/service',status='assigned',assignee_email='editor@example.com'))
    db.add(EngineAction(uid='other-client',client_id=client_b.id,month='2026-09',action_id='T-1',target_url=row['target_url'],status='assigned',assignee_email='editor@example.com'))
    db.commit()
    assert set(blockers(db,r,[row,{**row,'id':'T-1'},{**row,'action_uid':'active'}]))=={0}


def test_completed_work_waits_for_measurement_window_and_skipped_work_does_not_block(db,client_a):
    r=record(db,client_a)
    row={'id':'V-4','target_url':'https://clienta.example/service'}
    state=EngineAction(uid='shipped',client_id=client_a.id,month='2026-09',action_id='V-4',target_url=row['target_url'],status='done',shipped_on=date(2026,10,1))
    db.add(state);db.commit()
    assert blockers(db,r,[row],today=date(2026,10,28))
    assert not blockers(db,r,[row],today=date(2026,10,29))
    state.status='skipped';db.commit()
    assert not blockers(db,r,[row],today=date(2026,10,2))


def test_prompt_work_is_matched_by_prompt_not_just_page(db,client_a):
    before={'action_uid':'active','id':'G-1','target_url':'https://clienta.example/service','term':'Which provider?','steps':['Review that answer.']}
    record(db,client_a,'2026-08',[before]);r=record(db,client_a)
    db.add(EngineAction(uid='active',client_id=client_a.id,month='2026-08',action_id='G-1',target_url=before['target_url'],status='assigned',assignee_email='editor@example.com'));db.commit()
    rows=[{**before,'action_uid':'new'},{**before,'action_uid':'different','term':'Which alternative?','steps':['Review another answer.']}]
    assert set(blockers(db,r,rows))=={0}


def test_repeated_keyword_evidence_produces_one_executable_page_step():
    row={'id':'V-7','target_url':'https://clienta.example/service','done_when':'Add visible FAQ markup.','evidence':['FAQ section observed'],'why':'No FAQ markup','term':'one'}
    grouped=proposals({'month':'2026-09','findings':[row,{**row,'term':'two'}]})
    assert len(grouped)==1 and grouped[0]['steps']==['Add visible FAQ markup.']


def test_question_heading_absence_is_not_an_automatic_answer_gap():
    from app.decisions.catalog import VISIBILITY_ACTIONS,v2_answer_block
    assert v2_answer_block not in VISIBILITY_ACTIONS
