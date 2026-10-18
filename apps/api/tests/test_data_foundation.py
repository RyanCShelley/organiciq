"""Data-contract regressions: a refresh cannot manufacture growth or decline."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func
from app.models.config import ChannelRule, OrganicChannel
from app.models.ga4 import FactGa4Traffic, StagingGa4Traffic, FactGa4Event, StagingGa4Event
from app.models.job import SyncJob, DataWatermark, ValidationStatus
from app.ingestion.ga4.publish import publish_ga4
from app.services.dashboard import build_dashboard
from app.services.data_health import data_health_rows

DAY = date(2026, 9, 30)

def job_and_row(db, client):
    job = SyncJob(client_id=client.id, source='ga4', start_date=DAY, end_date=DAY)
    db.add(job); db.flush()
    db.add(StagingGa4Traffic(job_id=job.id, client_id=client.id, raw={}, date=DAY,
        landing_page='/service', session_source='google', session_medium='cpc',
        sessions=100, active_users=50, views=120))
    db.add(StagingGa4Event(job_id=job.id, client_id=client.id, raw={}, date=DAY,
        landing_page='/service', session_source='google', session_medium='cpc', event_name='lead', event_count=3))
    db.commit()
    return job

def test_channel_reclassification_preserves_source_totals(db, client_a, client_b):
    a, b = job_and_row(db, client_a), job_and_row(db, client_b)
    publish_ga4(db, a); publish_ga4(db, b)
    db.add(ChannelRule(match_source='google', match_medium='cpc', channel=OrganicChannel.PAID_SEARCH, priority=1, active=True))
    db.commit(); publish_ga4(db, a)
    rows = db.query(FactGa4Traffic).filter_by(client_id=client_a.id).all()
    assert len(rows) == 1 and rows[0].channel == OrganicChannel.PAID_SEARCH
    assert rows[0].sessions == 100
    assert db.query(FactGa4Event).filter_by(client_id=client_a.id).one().event_count == 3
    assert db.query(FactGa4Traffic).filter_by(client_id=client_b.id).one().channel == OrganicChannel.OTHER

def test_verified_restatement_removes_omitted_rows_only_in_its_scope(db, client_a, client_b):
    a, b = job_and_row(db, client_a), job_and_row(db, client_b)
    publish_ga4(db, a); publish_ga4(db, b)
    db.add(FactGa4Traffic(client_id=client_a.id, date=DAY-timedelta(days=1), raw_url='/old', normalized_url='/old', channel=OrganicChannel.OTHER, sessions=20))
    db.query(StagingGa4Traffic).filter_by(job_id=a.id).delete()
    db.query(StagingGa4Event).filter_by(job_id=a.id).delete()
    a.params_json = {'ga4_extract': {'complete': True, 'start': DAY.isoformat(), 'end': DAY.isoformat(), 'traffic_rows': 0, 'event_rows': 0}}
    db.commit(); publish_ga4(db, a)
    assert db.query(FactGa4Traffic).filter_by(client_id=client_a.id).one().date == DAY-timedelta(days=1)
    assert db.query(FactGa4Event).filter_by(client_id=client_a.id).count() == 0
    assert db.query(FactGa4Traffic).filter_by(client_id=client_b.id).one().sessions == 100

def test_unverified_empty_extract_preserves_existing_facts(db, client_a):
    job = job_and_row(db, client_a); publish_ga4(db, job)
    db.query(StagingGa4Traffic).filter_by(job_id=job.id).delete()
    db.query(StagingGa4Event).filter_by(job_id=job.id).delete()
    db.commit(); publish_ga4(db, job)
    assert db.query(FactGa4Traffic).filter_by(client_id=client_a.id).one().sessions == 100

def test_failed_replacement_rolls_back_previous_snapshot(db, client_a, monkeypatch):
    job = job_and_row(db, client_a); publish_ga4(db, job)
    job.params_json = {'ga4_extract': {'complete': True, 'start': DAY.isoformat(), 'end': DAY.isoformat(), 'traffic_rows': 1, 'event_rows': 1}}
    db.commit()
    execute = db.execute
    def fail_insert(statement, *args, **kwargs):
        if getattr(statement, 'is_insert', False):
            raise RuntimeError('write failed after deletion')
        return execute(statement, *args, **kwargs)
    monkeypatch.setattr(db, 'execute', fail_insert)
    with pytest.raises(RuntimeError): publish_ga4(db, job)
    db.rollback()
    monkeypatch.undo()
    assert db.query(FactGa4Traffic).filter_by(client_id=client_a.id).one().sessions == 100

def test_lagged_dashboard_does_not_manufacture_decline(db, client_a):
    start, end = date(2026, 10, 1), date(2026, 10, 17)
    db.add(DataWatermark(client_id=client_a.id, source='ga4', fact_through_date=date(2026,10,14), validation_status=ValidationStatus.PASSED))
    for day in range(31):
        db.add(FactGa4Traffic(client_id=client_a.id, date=date(2026,9,14)+timedelta(days=day), raw_url='/', normalized_url='/', channel=OrganicChannel.ORGANIC_SEARCH, sessions=100))
    db.commit()
    data = build_dashboard(db, client_a, start, end)
    metric = data['traffic']['ga4_sessions']
    assert metric['current'] == metric['previous'] == 1400
    assert metric['change_pct'] == 0
    assert data['effective_periods']['ga4']['previous'] == ['2026-09-14','2026-09-27']

def test_old_and_future_watermarks_are_not_healthy():
    today = date(2026,10,17)
    for stamp in [date(2025,1,1), today+timedelta(days=1)]:
        row = DataWatermark(source='site_crawl', fact_through_date=stamp, validation_status=ValidationStatus.PASSED)
        assert next(x for x in data_health_rows({}, {'site_crawl':row}, today=today) if x['source']=='site_crawl')['status'] == 'Stale'
    row.fact_through_date=today-timedelta(days=7)
    assert next(x for x in data_health_rows({}, {'site_crawl':row}, today=today) if x['source']=='site_crawl')['status']=='Healthy'


def test_provider_completeness_is_required_for_authoritative_refresh(monkeypatch):
    from app.ingestion.ga4.client import run_report
    from unittest.mock import Mock
    def report(pages):
        responses = [Mock(json=lambda data=data: data) for data in pages]
        monkeypatch.setattr('app.ingestion.ga4.client.post_json', Mock(side_effect=responses))
        return run_report(access_token='test', property_id='123', start_date=DAY, end_date=DAY, dimensions=['date'], metrics=['sessions'], limit=1)
    rows=report([{'rowCount':2,'rows':[{'dimensionValues':[{'value':'a'}]}]}, {'rowCount':2,'rows':[{'dimensionValues':[{'value':'b'}]}]}])
    assert rows.complete and len(rows)==2 and len(rows.pages)==2
    with pytest.raises(RuntimeError, match='ended before'):
        report([{'rowCount':1,'rows':[]}])
    with pytest.raises(RuntimeError, match='thresholding'):
        report([{'rowCount':0,'metadata':{'subjectToThresholding':True}}])
    with pytest.raises(RuntimeError, match='duplicate'):
        report([{'rowCount':2,'rows':[{'dimensionValues':[{'value':'a'}]}]}, {'rowCount':2,'rows':[{'dimensionValues':[{'value':'a'}]}]}])
    assert report([{'rowCount':0,'rows':[]}]).complete
    assert report([{'dimensionHeaders':[{'name':'date'}], 'metricHeaders':[{'name':'sessions'}]}]).complete
    with pytest.raises(RuntimeError, match='row count'):
        report([{}])


def test_failed_refresh_preserves_last_verified_cutoff_and_reports_error(db, client_a, monkeypatch):
    from app.ingestion.ga4.pipeline import run_ga4_job
    from app.models.integration import Integration, IntegrationProvider, ConnectionStatus
    integration=db.query(Integration).filter_by(client_id=client_a.id,provider=IntegrationProvider.GA4).one()
    integration.connection_status=ConnectionStatus.CONNECTED
    db.add(DataWatermark(client_id=client_a.id,source='ga4',fact_through_date=DAY,validation_status=ValidationStatus.PASSED))
    job=job_and_row(db,client_a);publish_ga4(db,job)
    monkeypatch.setattr('app.ingestion.ga4.pipeline.fetch_ga4', lambda *a: (_ for _ in ()).throw(RuntimeError('incomplete provider report')))
    run_ga4_job(db,job)
    watermark=db.query(DataWatermark).filter_by(client_id=client_a.id,source='ga4').one()
    assert watermark.fact_through_date==DAY and watermark.validation_status==ValidationStatus.PASSED
    assert db.query(FactGa4Traffic).filter_by(client_id=client_a.id).one().sessions==100
    assert next(x for x in data_health_rows({'ga4':integration},{'ga4':watermark},today=DAY) if x['source']=='ga4')['status']=='Sync error'


def test_complete_fetch_rejects_missing_metrics_before_touching_staging(db, client_a, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from app.ingestion.ga4.client import ReportRows
    from app.ingestion.ga4.fetch import fetch_ga4
    job = job_and_row(db, client_a)
    def rows(dimensions, metrics):
        report = ReportRows()
        report.complete = True
        report.append({"dimensionValues": [{"value": value} for value in dimensions],
            "metricValues": metrics})
        return report
    traffic = rows(['20260930', '/service', 'google', 'cpc'], [{'value':'100'}, {'value':'50'}, {'value':'120'}, {'value':'50'}])
    events = rows(['20260930', '/service', 'google', 'cpc', 'lead'], [{}])
    monkeypatch.setattr('app.ingestion.ga4.fetch._load_ga4_integration', lambda *args: SimpleNamespace(external_property_id='123'))
    monkeypatch.setattr('app.ingestion.ga4.fetch.access_token_for_client', lambda *args: 'test')
    source = Mock(side_effect=[traffic, events])
    monkeypatch.setattr('app.ingestion.ga4.fetch.run_report', source)
    with pytest.raises(ValueError, match='metrics are incomplete'):
        fetch_ga4(db, job)
    assert db.query(StagingGa4Traffic).filter_by(job_id=job.id).one().sessions == 100
    assert db.query(StagingGa4Event).filter_by(job_id=job.id).one().event_count == 3


def test_historical_repair_does_not_move_current_reporting_cutoff_backwards(db, client_a):
    from app.ingestion.ga4.pipeline import _upsert_watermark, _touch_integration
    from app.models.integration import Integration, IntegrationProvider
    current = date(2026, 10, 16)
    db.add(DataWatermark(client_id=client_a.id, source='ga4', fact_through_date=current, validation_status=ValidationStatus.PASSED))
    integration = db.query(Integration).filter_by(client_id=client_a.id, provider=IntegrationProvider.GA4).one()
    integration.last_fact_date = current
    db.commit()
    _upsert_watermark(db, client_id=client_a.id, fact_through=DAY, validation_status=ValidationStatus.PASSED)
    _touch_integration(db, client_a.id, success=True, fact_date=DAY, error=None)
    assert db.query(DataWatermark).filter_by(client_id=client_a.id, source='ga4').one().fact_through_date == current
    assert integration.last_fact_date == current
