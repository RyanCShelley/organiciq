from datetime import date
from decimal import Decimal

from app.ga4_reconcile import _compare, reconcile_client
from app.ingestion.ga4.client import ReportRows
from app.models.config import ConversionDefinition, OrganicChannel
from app.models.ga4 import FactGa4Traffic, FactGa4Event
from app.models.integration import Integration, IntegrationProvider

DAY = date(2026, 9, 30)


def test_audit_detects_channel_duplicates_even_when_totals_match():
    key = (DAY, '/', 'google', 'cpc')
    result = _compare({key: [Decimal(100)]}, [(key, [60]), (key, [40])], ['sessions'])
    assert result['metrics']['sessions']['stored_minus_source'] == 0
    assert result['duplicate_channel_keys'] == 1


def test_source_reconciliation_distinguishes_property_grain_and_stale_facts(db, client_a, monkeypatch):
    db.query(Integration).filter_by(client_id=client_a.id, provider=IntegrationProvider.GA4).one().external_property_id = '123'
    db.add(ConversionDefinition(client_id=client_a.id, event_name='lead', conversion_name='Lead', conversion_type='lead', active=True))
    db.add(FactGa4Traffic(client_id=client_a.id, date=DAY, raw_url='/service', normalized_url=f'https://{client_a.domain}/service',
        session_source='google', session_medium='cpc', channel=OrganicChannel.PAID_SEARCH, sessions=100, views=120, engaged_sessions=50))
    db.add(FactGa4Traffic(client_id=client_a.id, date=DAY, raw_url='/removed', normalized_url=f'https://{client_a.domain}/removed',
        session_source='google', session_medium='cpc', channel=OrganicChannel.OTHER, sessions=5, views=5))
    db.add(FactGa4Event(client_id=client_a.id, date=DAY, raw_url='/service', normalized_url=f'https://{client_a.domain}/service',
        session_source='google', session_medium='cpc', channel=OrganicChannel.PAID_SEARCH, event_name='lead', event_count=3))
    db.commit()
    before = [(row.id, row.sessions) for row in db.query(FactGa4Traffic).all()]
    monkeypatch.setattr('app.ga4_reconcile.access_token_for_client', lambda *args: 'not-a-real-token')
    def source(**kwargs):
        dimensions = kwargs['dimensions']
        def row(dims, measures):
            return {'dimensionValues': [{'value': str(value)} for value in dims],
                'metricValues': [{'value': str(value)} for value in measures]}
        if not dimensions:
            data = [row([], [99, 120, 50])]
        elif dimensions == ['eventName']:
            data = [row(['lead'], [3])]
        elif len(dimensions) == 4:
            data = [row(['20260930', '/service', 'google', 'cpc'], [60, 70, 30]),
                row(['20260930', '/service?campaign=x', 'google', 'cpc'], [40, 50, 20])]
        else:
            data = [row(['20260930', '/service', 'google', 'cpc', 'lead'], [3])]
        rows = ReportRows(); rows.extend(data); rows.complete = True
        rows.pages = [{'row_count': len(data), 'metadata': {'timeZone': 'America/New_York'}}]
        return rows
    monkeypatch.setattr('app.ga4_reconcile.run_report', source)
    report = reconcile_client(db, client_a, DAY, DAY)
    assert report['status'] == 'differences_found'
    assert report['traffic']['stored_keys_absent_from_source'] == 1
    assert report['traffic']['metrics']['sessions'] == {'source_extract': 100, 'stored': 105, 'stored_minus_source': 5}
    assert report['property_totals_not_folder_scoped']['sessions'] == 99
    assert report['leads']['metrics']['lead_events']['stored_minus_source'] == 0
    assert report['lead_events'] == ['lead']
    assert [(row.id, row.sessions) for row in db.query(FactGa4Traffic).all()] == before
