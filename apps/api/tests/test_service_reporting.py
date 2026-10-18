from datetime import date
from decimal import Decimal
from uuid import uuid4
from unittest.mock import patch
import pytest
from app.models.config import ChannelRule, OrganicChannel as C, ConversionDefinition
from app.models.ga4 import Ga4NativeChannelObservation as Native, FactGa4Traffic, StagingGa4Traffic, StagingGa4Event
from app.models.job import SyncJob, SyncJobStatus
from app.ingestion.channels import classify_channel
from app.ingestion.ga4.publish import publish_ga4
from app.services.service_reporting import build_service_reporting

DAY = date(2026, 9, 30)


def job(db, owner):
    from app.models.integration import Integration, IntegrationProvider
    from app.core.urls import normalize_path_prefix
    integration = db.query(Integration).filter_by(client_id=owner.id, provider=IntegrationProvider.GA4).one()
    integration.external_property_id = '123'
    from app.ingestion.ga4.publish import _rules
    from app.ingestion.ga4.publish_native import native_mapping_definition
    mapping_version, _ = native_mapping_definition(_rules(db))
    row=SyncJob(client_id=owner.id, source='ga4', start_date=DAY, end_date=DAY,
        status=SyncJobStatus.SUCCESSFUL, fact_watermark=DAY,
        params_json={'ga4_extract': {'complete':True, 'native_complete':True,
            'start':str(DAY),'end':str(DAY),'property':'123','native_mapping_version':mapping_version,
            'native_scope':{'domain':owner.domain,'path_prefix':normalize_path_prefix(owner.path_prefix),'timezone':owner.timezone},'traffic_rows':0,'event_rows':0,
            'native_traffic_rows':0,'native_event_rows':0}})
    db.add(row);db.flush();return row


def native(owner, channel, sessions, events, source, google):
    common=dict(client_id=owner.id,date=DAY,raw_url='/',normalized_url='https://example.com/',
        channel=channel,session_source=source,session_medium='referral',session_default_channel_group=google)
    return [Native(**common,event_name='',sessions=sessions),Native(**common,event_name='lead',event_count=events)]


@pytest.mark.parametrize('google',['Referral','Unassigned','Organic Search','Paid Search'])
def test_identifiable_ai_keeps_its_category_over_google(google):
    rules=[ChannelRule(priority=1,active=True,channel=C.AI_REFERRAL,match_host_contains='chatgpt')]
    assert classify_channel('chatgpt.com','referral',rules,google) == C.AI_REFERRAL
    assert classify_channel('(direct)','(none)',rules,'Direct') == C.DIRECT_UNATTRIBUTED


def test_google_preserves_paid_classification_when_source_is_missing():
    assert classify_channel('(data not available)','(data not available)',[],'Cross-network') == C.CROSS_NETWORK
    assert classify_channel('facebook','cpc',[],'Paid Social') == C.PAID_SOCIAL
    assert classify_channel('newsletter','email',[],'Email') == C.EMAIL


def test_service_union_keeps_whole_site_separate_and_ai_visible(db,client_a,client_b):
    client_a.service_reporting={'organiciq':True,'ad_accelerator':True}
    job(db,client_a)
    db.add(ConversionDefinition(client_id=client_a.id,event_name='lead',conversion_name='Lead',conversion_type='lead',active=True))
    for channel,sessions,events,source,google in [(C.ORGANIC_SEARCH,40,3,'google','Organic Search'),
        (C.AI_REFERRAL,10,1,'chatgpt.com','Referral'),(C.DIRECT_UNATTRIBUTED,20,2,'(direct)','Direct'),
        (C.CROSS_NETWORK,25,4,'(data not available)','Cross-network'),(C.EMAIL,5,1,'newsletter','Email')]:
        db.add_all(native(client_a,channel,sessions,events,source,google))
    db.add_all(native(client_b,C.PAID_SEARCH,999,99,'google','Paid Search'))
    # The old whole-site source/baseline basis is a distinct extract.
    db.add(FactGa4Traffic(client_id=client_a.id,date=DAY,raw_url='/',normalized_url='https://example.com/',
        channel=C.OTHER,sessions=101))
    db.flush()
    result=build_service_reporting(db,client_a,(DAY,DAY),None)
    assert result['status']=='measured' and result['headline_scope']=='whole_site'
    rows={r['key']:r for r in result['rows']}
    assert rows['organiciq']['sessions']['current']==70
    assert rows['ad_accelerator']['sessions']['current']==25
    assert result['combined']['sessions']['current']==95
    assert result['outside_services']['sessions']['current']==5
    assert result['combined']['lead_events']['current']==10
    assert result['ai_referrals']['sessions']['current']==10
    assert result['ai_sources']==[{'source':'chatgpt.com','sessions':10,'lead_events':1,'google_channels':['Referral']}]
    assert db.query(FactGa4Traffic).filter_by(client_id=client_a.id).one().sessions==101
    client_a.service_reporting={'organiciq':True,'ad_accelerator':False}
    result=build_service_reporting(db,client_a,(DAY,DAY),None)
    assert [r['key'] for r in result['rows']]==['organiciq']
    assert result['outside_services']['sessions']['current']==30


def test_missing_service_setup_or_source_coverage_does_not_become_zero(db,client_a):
    assert build_service_reporting(db,client_a,(DAY,DAY),None)['status']=='not_configured'
    client_a.service_reporting={'organiciq':True,'ad_accelerator':False}
    missing=build_service_reporting(db,client_a,(DAY,DAY),None)
    assert missing['status']=='needs_refresh' and missing['rows'][0]['sessions']['current'] is None
    job(db,client_a)
    observed=build_service_reporting(db,client_a,(DAY,DAY),None)
    assert observed['status']=='measured' and observed['rows'][0]['sessions']['current']==0
    assert observed['rows'][0]['lead_events']['current'] is None


def test_native_publication_is_idempotent_and_does_not_replace_baseline_extract(db,client_a,client_b):
    j=job(db,client_a)
    j.params_json={'ga4_extract': {**j.params_json['ga4_extract'],'native_traffic_rows':2,'traffic_rows':1}}
    db.add(StagingGa4Traffic(job_id=j.id,client_id=client_a.id,raw={},date=DAY,landing_page='/',
        session_source='google',session_medium='cpc',sessions=100,views=100,report_basis='legacy'))
    for google,visits in [('Paid Search',60),('Cross-network',41)]:
        db.add(StagingGa4Traffic(job_id=j.id,client_id=client_a.id,raw={},date=DAY,landing_page='/',
            session_source='google',session_medium='cpc',session_default_channel_group=google,
            sessions=visits,views=visits,report_basis='native'))
    db.add_all(native(client_b,C.CROSS_NETWORK,7,1,'google','Cross-network'))
    db.flush()
    publish_ga4(db,j);publish_ga4(db,j)
    assert db.query(FactGa4Traffic).filter_by(client_id=client_a.id).one().sessions==100
    rows=db.query(Native).filter_by(client_id=client_a.id).all()
    assert len(rows)==2 and sum(r.sessions for r in rows)==101
    assert {r.channel for r in rows}=={C.PAID_SEARCH,C.CROSS_NETWORK}
    assert db.query(Native).filter_by(client_id=client_b.id).count()==2
    j.params_json={'ga4_extract':{**j.params_json['ga4_extract'],'native_traffic_rows':3}}
    with pytest.raises(ValueError,match='manifest'):
        publish_ga4(db,j)
    db.rollback()
    assert db.query(Native).filter_by(client_id=client_a.id).count()==2


def test_native_ai_labels_and_legacy_app_alias_do_not_require_generic_referral_credit():
    assert classify_channel('chat.openai.com','referral',[],'Referral') == C.AI_REFERRAL
    assert classify_channel('new-assistant','ai-assistant',[],'AI Assistant') == C.AI_REFERRAL
    assert classify_channel('openai.com','referral',[],'Referral') == C.REFERRAL
    assert classify_channel('(direct)','(none)',[],'Direct') == C.DIRECT_UNATTRIBUTED


def test_opted_in_fetch_keeps_the_old_and_native_reports_separate(db,client_a,monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from app.ingestion.ga4.client import ReportRows
    from app.ingestion.ga4.fetch import fetch_ga4
    from app.models.integration import IntegrationProvider,Integration
    client_a.service_reporting={'organiciq':True,'ad_accelerator':True}
    integration=db.query(Integration).filter_by(client_id=client_a.id,provider=IntegrationProvider.GA4).one()
    integration.external_property_id='123'
    j=job(db,client_a)
    def report(*,dimensions,metrics,**kwargs):
        rows=ReportRows();rows.complete=True
        if 'eventName' not in dimensions:
            dims=[DAY.strftime('%Y%m%d'),'/', 'google','cpc']
            if 'sessionDefaultChannelGroup' in dimensions:dims+=['Cross-network']
            rows.append({'dimensionValues':[{'value':v} for v in dims],
                         'metricValues':[{'value':'10'} for _ in metrics]})
        return rows
    source=Mock(side_effect=report)
    monkeypatch.setattr('app.ingestion.ga4.fetch.run_report',source)
    monkeypatch.setattr('app.ingestion.ga4.fetch._load_ga4_integration',lambda *args:integration)
    monkeypatch.setattr('app.ingestion.ga4.fetch.access_token_for_client',lambda *args:'test')
    assert fetch_ga4(db,j)==(2,0)
    assert 'sessionDefaultChannelGroup' not in source.call_args_list[0].kwargs['dimensions']
    assert source.call_args_list[2].kwargs['dimensions'][-1]=='sessionDefaultChannelGroup'
    assert j.params_json['ga4_extract']['complete'] and j.params_json['ga4_extract']['native_complete']
    assert {r.report_basis for r in db.query(StagingGa4Traffic).filter_by(job_id=j.id)}=={'legacy','native'}


@pytest.mark.parametrize('source',['gsc_pages','se_ranking_search','se_ranking_ai'])
def test_backfills_and_failures_preserve_the_verified_source_cutoff(db,client_a,source):
    from app.models.job import DataWatermark,ValidationStatus
    from app.ingestion.gsc.pipeline import _upsert_watermark as gsc
    from app.ingestion.seranking.pipeline import _upsert_watermark as search
    from app.ingestion.seranking.pipeline_ai import _upsert_watermark as ai
    through=date(2026,10,18)
    db.add(DataWatermark(client_id=client_a.id,source=source,fact_through_date=through,validation_status=ValidationStatus.PASSED))
    db.commit()
    update={'gsc_pages':gsc,'se_ranking_search':search,'se_ranking_ai':ai}[source]
    args={'client_id':client_a.id}
    if source=='gsc_pages':args['source']=source
    for status,observed in [(ValidationStatus.PASSED,date(2026,8,31)),(ValidationStatus.FAILED,None)]:
        update(db,**args,fact_through=observed,validation_status=status)
        assert db.query(DataWatermark).filter_by(client_id=client_a.id,source=source).one().fact_through_date==through


def test_service_coverage_cannot_be_reused_after_site_or_property_changes(db,client_a):
    from app.models.integration import Integration,IntegrationProvider
    client_a.service_reporting={'organiciq':True,'ad_accelerator':False}
    job(db,client_a)
    assert build_service_reporting(db,client_a,(DAY,DAY),None)['status']=='measured'
    integration=db.query(Integration).filter_by(client_id=client_a.id,provider=IntegrationProvider.GA4).one()
    integration.external_property_id='456'
    assert build_service_reporting(db,client_a,(DAY,DAY),None)['status']=='needs_refresh'
    integration.external_property_id='123'
    client_a.path_prefix='/another-brand'
    assert build_service_reporting(db,client_a,(DAY,DAY),None)['status']=='needs_refresh'


def test_daily_native_extracts_cover_a_month_but_a_gap_or_rule_change_does_not(db,client_a):
    from app.services.service_reporting import has_native_coverage
    client_a.service_reporting={'organiciq':True,'ad_accelerator':False}
    first=job(db,client_a);first.start_date=date(2026,9,1);first.end_date=date(2026,9,15);first.fact_watermark=first.end_date
    second=job(db,client_a);second.start_date=date(2026,9,10)
    db.flush()
    assert has_native_coverage(db,client_a.id,(date(2026,9,1),DAY))
    second.start_date=date(2026,9,17);db.flush()
    assert not has_native_coverage(db,client_a.id,(date(2026,9,1),DAY))
    second.start_date=date(2026,9,16);db.flush()
    assert has_native_coverage(db,client_a.id,(date(2026,9,1),DAY))
    db.add(ChannelRule(priority=1,active=True,channel=C.AI_REFERRAL,match_host_contains='new-assistant'))
    db.flush()
    assert not has_native_coverage(db,client_a.id,(date(2026,9,1),DAY))
