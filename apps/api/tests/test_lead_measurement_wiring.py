from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import Mock

from app.models.config import ConversionDefinition, OrganicChannel
from app.models.decision import DecisionThreshold
from app.models.ga4 import FactGa4Traffic, FactGa4Event, Ga4LeadMeasurement
from app.models.integration import Integration, IntegrationProvider
from app.models.job import DataWatermark, ValidationStatus
from app.services.dashboard import build_dashboard
from app.services.decision_measurements import measure, lead_rate_target
from app.services.lead_measurements import session_lead_measurement

START, END = date(2026, 9, 1), date(2026, 9, 30)


def configured(db, client, monkeypatch):
    db.add(ConversionDefinition(client_id=client.id, event_name='lead', conversion_name='Lead', active=True))
    db.query(Integration).filter_by(client_id=client.id, provider=IntegrationProvider.GA4).one().external_property_id = 'properties/123'
    monkeypatch.setattr('app.services.lead_measurements.client_has_google_credentials', lambda *args: True)
    monkeypatch.setattr('app.services.lead_measurements.access_token_for_client', lambda *args: 'test')
    def fetched(**kwargs):
        return {'status':'measured', 'basis':'sessions_with_selected_lead_event', 'lead_events':kwargs['lead_events'],
            'period':[kwargs['start_date'].isoformat(),kwargs['end_date'].isoformat()],
            'sessions':100, 'lead_sessions':10, 'conversion_rate_pct':10,
            'path_scope':kwargs['path_prefix'], 'channel_scope':'all_channels'}
    fetch = Mock(side_effect=fetched)
    monkeypatch.setattr('app.services.lead_measurements.fetch_lead_session_measurement', fetch)
    db.flush()
    return fetch


def test_dashboard_and_engine_share_verified_rate_and_preserve_legacy_target(db, client_a, monkeypatch):
    fetch = configured(db, client_a, monkeypatch)
    db.add(DecisionThreshold(client_id=client_a.id, thresholds={'target_lead_rate_pct':4.5}))
    db.add(DataWatermark(client_id=client_a.id, source='ga4', fact_through_date=END, validation_status=ValidationStatus.PASSED))
    db.add(FactGa4Traffic(client_id=client_a.id, date=END, raw_url='/', normalized_url='https://example.com/', channel=OrganicChannel.ORGANIC_SEARCH, sessions=120))
    db.add(FactGa4Event(client_id=client_a.id, date=END, raw_url='/', normalized_url='https://example.com/', channel=OrganicChannel.ORGANIC_SEARCH, event_name='lead', event_count=30))
    client_a.baseline_lead_rate_pct = Decimal('20')
    db.commit()
    dashboard = build_dashboard(db, client_a, START, END)
    engine = measure(db, client_a, end=END)
    assert dashboard['conversions']['leads']['current'] == engine['leads']['count'] == 30
    assert dashboard['conversions']['session_lead_rate']['current'] == engine['leads']['rate_pct'] == 10
    assert dashboard['conversions']['lead_rate']['current'] == engine['leads']['event_rate_pct'] == 25
    assert dashboard['conversions']['lead_sessions']['current'] == engine['leads']['lead_sessions'] == 10
    assert dashboard['traffic']['ga4_reported_sessions']['current'] == engine['traffic']['current']['total'] == 100
    assert fetch.call_count == 2  # current and previous periods, reused by the engine
    assert lead_rate_target(db, client_a.id) is None
    assert lead_rate_target(db, client_a.id, basis='event') == 4.5
    assert client_a.baseline_lead_rate_pct == 20
    from app.services.triage_signals import lead_signals
    signals = lead_signals(db, client_a, today=END)
    assert signals.lead_rate == 10 and signals.target_lead_rate is None and signals.baseline_lead_rate is None


def test_cache_isolated_by_client_period_and_lead_definition(db, client_a, client_b, monkeypatch):
    fetch = configured(db, client_a, monkeypatch)
    session_lead_measurement(db, client_a, START, END)
    session_lead_measurement(db, client_a, START, END)
    assert fetch.call_count == 1
    assert session_lead_measurement(db, client_b, START, END)['status'] == 'not_configured'
    assert fetch.call_count == 1
    db.add(ConversionDefinition(client_id=client_a.id, event_name='call', conversion_name='Call', active=True))
    db.flush()
    session_lead_measurement(db, client_a, START, END)
    session_lead_measurement(db, client_a, START, END-timedelta(days=1))
    assert fetch.call_count == 3
    assert db.query(Ga4LeadMeasurement).filter_by(client_id=client_a.id).count() == 3
    assert db.query(Ga4LeadMeasurement).filter_by(client_id=client_b.id).count() == 0


def test_failed_refresh_never_becomes_zero_or_uses_expired_rate(db, client_a, monkeypatch):
    fetch = configured(db, client_a, monkeypatch)
    session_lead_measurement(db, client_a, START, END)
    snapshot = db.query(Ga4LeadMeasurement).one()
    snapshot.measured_at -= timedelta(days=2)
    db.flush()
    fetch.side_effect = RuntimeError('provider unavailable')
    result = session_lead_measurement(db, client_a, START, END)
    assert result['status'] == 'unavailable' and result['conversion_rate_pct'] is None
    assert snapshot.measurement['conversion_rate_pct'] == 10
