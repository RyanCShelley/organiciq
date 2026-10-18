from datetime import date

import pytest

from app.decisions.triage import VisibilitySignals, assess_visibility, Status
from app.models.crawl import FactCrawlPageSnapshot
from app.models.decision import KeywordTarget, KeywordPageSuggestion
from app.models.gsc import FactGscQueryPage
from app.models.seranking import FactSerKeyword, FactSerRanking, FactSerpFeature
from app.services.automatic_keyword_map import build
from app.services.ctr_diagnostic import read as read_ctr
from app.services.decision_measurements import monthly_keyword_trend

DAY = date(2026, 9, 30)


def keyword(db, client, term, position=12, url=None):
    db.add(FactSerKeyword(client_id=client.id, site_engine_id="test", keyword_id=term,
        keyword=term, current_position=position, ranking_url=url, checked_at=DAY))


def page(db, client, path, title):
    url = f"https://{client.domain}/{path}"
    db.add(FactCrawlPageSnapshot(client_id=client.id, source="site_crawl", snapshot_date=DAY,
        raw_url=url, normalized_url=url, indexable=True, title=title, sections=[]))
    return url


def test_auto_map_preserves_overrides_and_retains_uncertainty(db, client_a, monkeypatch):
    monkeypatch.setattr("app.services.automatic_keyword_map.active_crawl_source", lambda: "site_crawl")
    first = page(db, client_a, "pump", "Industrial pump repair")
    second = page(db, client_a, "cloud", "Managed cloud services")
    keyword(db, client_a, "industrial pump repair", url=first)
    keyword(db, client_a, "managed cloud services", url=second)
    keyword(db, client_a, "client decision", url=first)
    db.add(KeywordTarget(client_id=client_a.id, keyword="client decision", target_url=None, source="confirmed", priority=True))
    db.add(KeywordPageSuggestion(client_id=client_a.id, keyword="managed cloud services", page_url=first,
        score=.9, margin=.3, model="test", computed_on=DAY))
    db.flush()
    result = build(db, client_a, today=DAY)
    assert result == {"mapped": 1, "preserved": 1, "gaps": 0, "conflicts": 1}
    mapped = db.query(KeywordTarget).filter_by(client_id=client_a.id, keyword="industrial pump repair").one()
    assert mapped.source == "auto" and mapped.target_url == first
    assert mapped.term_role is None  # page ownership does not invent strategic primacy
    manual = db.query(KeywordTarget).filter_by(client_id=client_a.id, keyword="client decision").one()
    assert manual.target_url is None and manual.priority
    mapped.source, mapped.target_url = "confirmed", second
    db.flush()
    build(db, client_a, today=DAY)
    assert mapped.target_url == second  # repeated refresh cannot replace an override


def test_ctr_applies_reference_to_all_devices_without_serp_gate(db, client_a):
    url = f"https://{client_a.domain}/service"
    for device, impressions in [("desktop", 1000), ("mobile", 500)]:
        db.add(FactGscQueryPage(client_id=client_a.id, date=date(2026, 9, 20), query="service",
            raw_url=url, normalized_url=url, country="usa", device=device, impressions=impressions, clicks=10, average_position=1))
    db.add(FactSerpFeature(client_id=client_a.id, pulled_on=date(2026, 9, 19), keyword="service",
        location_code=2840, source="dataforseo", item_types=["ai_overview"]))
    db.flush()
    result = read_ctr(db, client_a.id, date(2026, 9, 1), DAY)
    assert result["matched"]
    assert result["missed_clicks"] == pytest.approx(92.8)
    assert result["actual_clicks"] == 20
    assert result["evidence"]["matched_impressions"] == 1500
    assert result["evidence"]["coverage_pct"] == 100
    # A non-AIO SERP does not change the chosen reference policy.
    db.add(FactSerpFeature(client_id=client_a.id, pulled_on=date(2026, 9, 20), keyword="service",
        location_code=2840, source="dataforseo", item_types=["organic"]))
    db.flush()
    assert read_ctr(db, client_a.id, date(2026, 9, 1), DAY)["matched"] is True


def test_monthly_visibility_pairs_same_terms_and_excludes_unobserved_terms(db, client_a):
    for term, previous, current in [("pump repair", 5, 14), ("cloud services", 30, 7)]:
        keyword(db, client_a, term, current)
        db.add(FactSerRanking(client_id=client_a.id, site_engine_id="test", keyword_id=term,
            keyword=term, date=date(2026, 8, 31), position=previous))
    keyword(db, client_a, "new term", 2)
    db.add(FactSerRanking(client_id=client_a.id, site_engine_id="different-market", keyword_id="new term", keyword="new term", date=date(2026, 8, 31), position=90))
    db.flush()
    result = monthly_keyword_trend(db, client_a, DAY)
    assert result["cohort"] == 2
    assert result["declined"] == result["improved"] == 1
    assert result["entered_top_10"] == result["left_top_10"] == 1
    tests = {t.id: t for t in assess_visibility(VisibilitySignals(monthly_keyword_trend={**result, "cohort": 5}), thresholds={})}
    assert tests["V2"].status is Status.PASS
    assert tests["V2"].evidence["source"] == "matched_monthly_keyword_history"


def test_watchlist_coverage_is_client_scoped_without_priority_or_mapping(db, client_a, client_b):
    from app.services.triage_signals import visibility_signals
    from app.models.watch_target import WatchTarget
    from app.services.watchlist import item_key
    for client, term, position in [(client_a, 'shared term', 1), (client_a, 'another term', 101), (client_b, 'shared term', 50)]:
        keyword(db, client, term, position)
    db.add(KeywordTarget(client_id=client_a.id, keyword='shared term', source='confirmed', priority=True))
    keyword(db, client_a, 'excluded term', 1)
    db.add(WatchTarget(client_id=client_a.id, kind='keyword', item_key=item_key('keyword', 'excluded term'), text='excluded term', state='excluded', priority=True))
    db.add(FactSerKeyword(client_id=client_a.id, site_engine_id='test', keyword_id='future', keyword='future term', current_position=1, checked_at=date(2026, 10, 10)))
    db.flush()
    a = visibility_signals(db, client_a, today=DAY, ai_period=None)
    b = visibility_signals(db, client_b, today=DAY, ai_period=None)
    assert (a.priority_keywords, a.priority_in_top_10) == (2, 1)
    assert (b.priority_keywords, b.priority_in_top_10) == (1, 0)
    assert assess_visibility(a, thresholds={})[0].status is not Status.BLOCKED


def test_declared_conversion_page_without_mapping_is_coverage_not_missing_setup(db, client_a):
    from app.models.config import ClientConversionPage
    from app.services.triage_signals import visibility_signals
    db.add(ClientConversionPage(client_id=client_a.id, normalized_url=f'https://{client_a.domain}/contact', label='Contact'))
    db.flush()
    signal = visibility_signals(db, client_a, today=DAY, ai_period=None)
    test = next(t for t in assess_visibility(signal, thresholds={}) if t.id == 'V4')
    assert test.status is Status.BLOCKED
    assert test.missing == 'declared pages have no Watch List keyword mappings'


def test_ctr_without_serp_observations_is_client_scoped(db, client_a, client_b):
    for client, device, country, impressions, position in [(client_a, 'mobile', 'can', 200, 2), (client_b, 'desktop', 'usa', 500, 1), (client_a, 'tablet', 'gbr', 100, 25)]:
        url=f'https://{client.domain}/'
        db.add(FactGscQueryPage(client_id=client.id, date=DAY, query='service', raw_url=url, normalized_url=url, country=country, device=device, impressions=impressions, clicks=1, average_position=position))
    db.flush()
    a = read_ctr(db, client_a.id, DAY, DAY)
    b = read_ctr(db, client_b.id, DAY, DAY)
    assert a['matched'] and b['matched']
    assert a['evidence']['matched_impressions'] == 200
    assert a['evidence']['total_query_impressions'] == 300
    assert b['evidence']['matched_impressions'] == 500
    assert a['evidence']['application'] == 'all_terms_reference'


def test_current_measurement_settings_do_not_leak_between_clients(db, client_a, client_b):
    from app.api.routers.decisions import get_measurement_settings
    from app.models.config import ClientConversionPage
    from app.models.decision import DecisionThreshold
    db.add(DecisionThreshold(client_id=client_a.id, thresholds={'target_lead_rate_pct': 2}))
    db.add(ClientConversionPage(client_id=client_a.id, normalized_url=f'https://{client_a.domain}/contact', label='Contact'))
    db.flush()
    a = get_measurement_settings(client=client_a, _=None, db=db)
    b = get_measurement_settings(client=client_b, _=None, db=db)
    assert a == {'target_lead_rate_pct': 2, 'conversion_page_count': 1}
    assert b == {'target_lead_rate_pct': None, 'conversion_page_count': 0}


def test_page_action_uses_same_reference_and_supported_positions(db, client_a):
    from app.models.gsc import FactGscPage
    from app.services.page_signals import load_page_candidates
    from app.decisions.ctr_curve import expected_ctr_percent, REFERENCE_SCENARIO
    for path, position in [('service', 2), ('outside-reference', 25)]:
        url = f'https://{client_a.domain}/{path}'
        db.add(FactGscPage(client_id=client_a.id, date=DAY, raw_url=url, normalized_url=url,
            impressions=200, clicks=1, average_position=position))
    db.flush()
    pages = {p.url: p for p in load_page_candidates(db, client_a, today=DAY)}
    assert pages[f'https://{client_a.domain}/service'].expected_clicks == pytest.approx(2 * expected_ctr_percent(2, scenario=REFERENCE_SCENARIO))
    assert pages[f'https://{client_a.domain}/outside-reference'].expected_clicks is None
