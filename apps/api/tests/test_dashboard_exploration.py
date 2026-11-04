from datetime import date
from app.models.seranking import FactSerKeyword, FactSerRanking, FactSerAiCheck
from app.services.dashboard_exploration import visibility_detail, prompt_detail


def test_visibility_matches_dated_cohort_and_preserves_unknown(db, client_a, client_b):
    for term in ('stable', 'new', 'unmeasured'):
        db.add(FactSerKeyword(client_id=client_a.id, keyword=term, site_engine_id="google", keyword_id=term, is_tracked=True))
    for term, day, pos in [('stable', date(2026,8,31),12), ('stable',date(2026,9,30),8), ('new',date(2026,9,30),4), ('stable',date(2026,10,2),1)]:
        db.add(FactSerRanking(client_id=client_a.id,keyword=term,site_engine_id="google",keyword_id=term,date=day,position=pos))
    db.add(FactSerKeyword(client_id=client_b.id,keyword='other client',site_engine_id='google',keyword_id='other',is_tracked=True))
    db.flush()
    result=visibility_detail(db,client_a.id,(date(2026,9,1),date(2026,9,30)),(date(2026,8,2),date(2026,8,31)))
    assert result['tracked']==3
    assert result['measured']==2
    assert result['top_10']==2
    assert result['matched']==1
    assert result['matched_previous_top_10']==0
    assert result['matched_current_top_10']==1
    rows={row['term']:row for row in result['keywords']}
    assert rows['stable']['current']['position']==8
    assert rows['unmeasured']['current'] is None
    assert rows['new']['previous'] is None


def test_prompt_details_use_only_period_observations(db,client_a,client_b):
    for owner,day,mentioned in [(client_a,date(2026,8,31),True),(client_a,date(2026,9,20),None),(client_a,date(2026,10,1),False),(client_b,date(2026,9,25),True)]:
        db.add(FactSerAiCheck(client_id=owner.id,date=day,llm_id='chatgpt',prompt_id='p1',prompt='Who can help?',brand_mentioned=mentioned,brand_cited=False))
    db.flush()
    rows=prompt_detail(db,client_a.id,(date(2026,9,1),date(2026,9,30)))
    assert len(rows)==1
    assert rows[0]['observed_on']=='2026-09-20'
    assert rows[0]['mentioned'] is None
    assert rows[0]['cited'] is False
    assert prompt_detail(db,client_a.id,None)==[]
