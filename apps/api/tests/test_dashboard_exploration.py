from datetime import date
from app.models.seranking import FactSerKeyword, FactSerRanking
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


def test_prompt_details_use_only_period_observations(db, client_a, client_b):
    from tests.test_dashboard_phase6 import _llm_run

    _llm_run(db, client_a.id, date(2026, 8, 31), [("openai", "Who can help?", "Mentioned", False, False)])
    _llm_run(db, client_a.id, date(2026, 9, 20), [("openai", "Who can help?", "Not visible", False, False)])
    _llm_run(db, client_a.id, date(2026, 10, 1), [("openai", "Who can help?", "Mentioned", True, False)])
    _llm_run(db, client_b.id, date(2026, 9, 25), [("openai", "Who can help?", "Mentioned", True, False)])
    rows = prompt_detail(db, client_a.id, (date(2026, 9, 1), date(2026, 9, 30)))
    assert len(rows) == 1
    assert rows[0]['observed_on'] == '2026-09-20' and rows[0]['provider'] == 'openai'
    assert rows[0]['mentioned'] is False and rows[0]['cited'] is False
    assert prompt_detail(db, client_a.id, None) == []
