from datetime import date
from unittest.mock import Mock
import pytest

from app.ingestion.ga4.client import ReportRows, run_report
from app.ingestion.ga4.lead_sessions import fetch_lead_session_measurement

DAY = date(2026, 9, 30)


def report(count):
    rows = ReportRows()
    rows.complete = True
    rows.pages = [{'metadata': {'timeZone': 'America/New_York'}}]
    rows.append({'metricValues': [{'value': str(count)}]})
    return rows


def measure(**overrides):
    return fetch_lead_session_measurement(access_token='test', property_id='123', start_date=DAY,
        end_date=DAY, **{'lead_events': ['form_submission', 'phone_calls'], **overrides})


def test_selected_outcomes_use_one_union_report_not_summed_event_sessions(monkeypatch):
    source = Mock(side_effect=[report(100), report(15)])
    monkeypatch.setattr('app.ingestion.ga4.lead_sessions.run_report', source)
    result = measure(lead_events=['phone_calls', 'form_submission', 'phone_calls'])
    assert result['lead_sessions'] == 15
    assert result['conversion_rate_pct'] == 15
    assert result['basis'] == 'sessions_with_selected_lead_event'
    assert source.call_count == 2
    numerator = source.call_args_list[1].kwargs
    assert numerator['dimensions'] == []
    assert numerator['timeout_seconds'] == 6.0 and numerator['max_attempts'] == 1
    assert numerator['dimension_filter']['filter']['inListFilter']['values'] == ['form_submission', 'phone_calls']


def test_folder_scope_applies_to_both_denominator_and_union(monkeypatch):
    source = Mock(side_effect=[report(100), report(10)])
    monkeypatch.setattr('app.ingestion.ga4.lead_sessions.run_report', source)
    measure(path_prefix='/unmanned/')
    scope = source.call_args_list[0].kwargs['dimension_filter']
    union = source.call_args_list[1].kwargs['dimension_filter']
    assert union['andGroup']['expressions'][0] == scope
    assert scope['filter']['stringFilter']['value'] == r'/unmanned(?:/.*|\?.*)?'
    assert scope['filter']['stringFilter']['matchType'] == 'FULL_REGEXP'


def test_missing_definitions_and_empty_traffic_are_not_zero_percent(monkeypatch):
    source = Mock(side_effect=[report(0), report(0)])
    monkeypatch.setattr('app.ingestion.ga4.lead_sessions.run_report', source)
    result = measure(lead_events=[])
    assert result['status'] == 'not_configured' and result['conversion_rate_pct'] is None
    source.assert_not_called()
    result = measure()
    assert result['status'] == 'no_sessions' and result['conversion_rate_pct'] is None


def test_impossible_or_unverified_counts_are_rejected(monkeypatch):
    for rows in [report(101), ReportRows(), report('-1'), report('NaN')]:
        source = Mock(side_effect=[report(100), rows])
        monkeypatch.setattr('app.ingestion.ga4.lead_sessions.run_report', source)
        with pytest.raises(ValueError):
            measure()


def test_ga4_request_preserves_union_filter(monkeypatch):
    request = Mock(return_value=Mock(json=lambda: {'rowCount': 1, 'rows': [{'metricValues': [{'value': '15'}]}]}))
    monkeypatch.setattr('app.ingestion.ga4.client.post_json', request)
    selected = {'filter': {'fieldName': 'eventName', 'inListFilter': {'values': ['form', 'call'], 'caseSensitive': True}}}
    rows = run_report(access_token='test', property_id='123', start_date=DAY, end_date=DAY,
        dimensions=[], metrics=['sessions'], dimension_filter=selected)
    assert rows.complete
    assert request.call_args.kwargs['json']['dimensionFilter'] == selected
