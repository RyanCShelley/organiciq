from datetime import date

from app.models.config import ConversionDefinition, OrganicChannel
from app.models.ga4 import FactGa4Traffic, FactGa4Event
from app.services.decision_measurements import measure
from tests.conftest import client_header


def test_measurement_scope_unknowns_and_rate_target(db, client, client_a, admin_user):
    headers = client_header(client_a.id, admin_user.email)
    path = "/decisions/measurement-settings"
    assert client.put(path, headers=headers, json={"target_lead_rate_pct": 0}).status_code == 422
    assert client.put(path, headers=headers, json={"target_lead_rate_pct": 101}).status_code == 422
    assert client.put(path, headers=headers, json={"target_lead_rate_pct": 3.25}).status_code == 200
    assert client.get(path, headers=headers).json()["target_lead_rate_pct"] == 3.25
    empty = measure(db, client_a, end=date(2026, 9, 30))
    assert empty["traffic"]["current"]["total"] is None
    assert empty["leads"]["rate_pct"] is None
    db.add(ConversionDefinition(client_id=client_a.id, event_name="lead", conversion_name="Lead", conversion_type="lead", active=True))
    for channel, sessions in [(OrganicChannel.ORGANIC_SEARCH, 100), (OrganicChannel.DIRECT_UNATTRIBUTED, 200), (OrganicChannel.PAID_SEARCH, 300), (OrganicChannel.OTHER, 400)]:
        db.add(FactGa4Traffic(client_id=client_a.id, date=date(2026, 9, 20), raw_url="/", normalized_url="https://example.com/", channel=channel, sessions=sessions))
    db.add(FactGa4Event(client_id=client_a.id, date=date(2026, 9, 20), raw_url="/", normalized_url="https://example.com/", channel=OrganicChannel.PAID_SEARCH, event_name="lead", event_count=20))
    db.add(FactGa4Traffic(client_id=client_a.id, date=date(2026, 10, 1), raw_url="/", normalized_url="https://example.com/", channel=OrganicChannel.ORGANIC_SEARCH, sessions=5000))
    db.commit()
    result = measure(db, client_a, end=date(2026, 9, 30))
    assert result["traffic"]["current"]["total"] == 1000
    assert result["traffic"]["current"]["channels"]["direct_unattributed"] == 200
    assert result["leads"]["count"] == 20
    assert result["leads"]["rate_pct"] is None  # Event totals cannot supply converting visits.
    assert result["leads"]["event_rate_pct"] == 2
    assert result["leads"]["target_rate_pct"] == 3.25
    assert result["traffic"]["ctr_reference"]["positions"][0]["ctr_pct"] == 7.52
    assert client.put(path, headers=headers, json={"target_lead_rate_pct": None}).status_code == 200
    assert client.get(path, headers=headers).json()["target_lead_rate_pct"] is None


def test_keyword_visibility_uses_dated_observations_without_future_leakage(db, client_a):
    from app.models.seranking import FactSerKeyword, FactSerRanking
    db.add(FactSerKeyword(client_id=client_a.id, site_engine_id="test", keyword_id="one", keyword="priority service", current_position=1, checked_at=date(2026, 10, 1), ranking_url="https://example.com/future"))
    db.add(FactSerRanking(client_id=client_a.id, site_engine_id="test", keyword_id="one", keyword="priority service", date=date(2026, 9, 29), position=14, ranking_url="https://example.com/service"))
    db.add(FactSerKeyword(client_id=client_a.id, site_engine_id="test", keyword_id="two", keyword="unmeasured service", current_position=None))
    db.commit()
    rows = {row["text"]: row for row in measure(db, client_a, end=date(2026, 9, 30))["visibility"]["keywords"]}
    assert rows["priority service"]["position"] == 14
    assert rows["priority service"]["ranking_url"] == "https://example.com/service"
    assert rows["priority service"]["observed_on"] == "2026-09-29"
    assert rows["unmeasured service"]["status"] == "not_measured"


def test_prompt_history_is_used_for_past_assessments_without_future_or_client_leakage(db, client_a, client_b):
    from app.models.seranking import FactSerAiPrompt, FactSerAiCheck
    for c in (client_a,client_b):
        db.add(FactSerAiPrompt(client_id=c.id,llm_id='engine',prompt_id='p',engine='chatgpt',prompt='Which service?',checked_at=date(2026,10,18),brand_mentioned=False,brand_cited=False))
    for c,day,mentioned,cited in [(client_a,date(2026,9,30),True,True),(client_a,date(2026,10,18),False,False),(client_b,date(2026,9,30),False,False)]:
        db.add(FactSerAiCheck(client_id=c.id,llm_id='engine',prompt_id='p',prompt='Which service?',date=day,brand_mentioned=mentioned,brand_cited=cited))
    db.commit()
    row=measure(db,client_a,end=date(2026,9,30))['visibility']['prompts'][0]
    assert row['observed_on']=='2026-09-30' and row['mentioned'] is True and row['cited'] is True
    row=measure(db,client_a,end=date(2026,8,31))['visibility']['prompts'][0]
    assert row['observed_on'] is None and row['mentioned'] is None and row['cited'] is None


def test_automatic_focus_excludes_legacy_maps_and_inactive_tracker_terms(db, client_a, client_b):
    from app.models.decision import KeywordTarget
    from app.models.seranking import FactSerKeyword, FactSerRanking
    from app.services.watchlist import automatic_focus, read

    day = date(2026, 9, 30)
    for client, term, tracked in [(client_a, "current", True), (client_a, "retired", False),
                                   (client_b, "another client", True)]:
        db.add(FactSerKeyword(client_id=client.id, site_engine_id="engine", keyword_id=term,
                              keyword=term, is_tracked=tracked, checked_at=day, current_position=5))
    for term in ["current", "retired", "map only"]:
        db.add(KeywordTarget(client_id=client_a.id, keyword=term, source="confirmed",
                             target_url="https://example.com/service"))
    db.add(FactSerRanking(client_id=client_a.id, site_engine_id="engine", keyword_id="retired",
                          keyword="retired", date=day, position=3))
    db.commit()
    assert {row["text"] for row in automatic_focus(db, client_a)} == {"current"}
    assert {row["text"] for row in read(db, client_a)} == {"current", "retired", "map only"}
    assert [row["text"] for row in measure(db, client_a, end=day)["visibility"]["keywords"]] == ["current"]
    assert db.query(FactSerRanking).filter_by(client_id=client_a.id, keyword="retired").count() == 1
    from app.services.triage_signals import visibility_signals
    signals = visibility_signals(db, client_a, today=day, ai_period=None)
    assert signals.priority_keywords == 1
    assert signals.priority_in_top_10 == 1


def test_saved_comparison_uses_prior_visit_conversion_not_event_rate(db, client_a, monkeypatch):
    calls = []
    def measurement(db, client, start, end):
        calls.append((start, end))
        current = start == date(2026, 9, 1)
        return {"conversion_rate_pct": 3.13 if current else 4.63,
                "lead_sessions": 38 if current else 58,
                "sessions": 1215 if current else 1253, "status": "measured"}
    monkeypatch.setattr("app.services.lead_measurements.session_lead_measurement", measurement)
    result = measure(db, client_a, end=date(2026, 9, 30))
    assert calls == [(date(2026, 9, 1), date(2026, 9, 30)), (date(2026, 8, 2), date(2026, 8, 31))]
    assert result["leads"]["previous_rate_pct"] == 4.63
    assert result["leads"]["rate_pct"] == 3.13
    assert result["traffic"]["previous"]["total"] == 1253
    assert result["leads"]["count"] is None


def test_missing_prior_visit_rate_remains_unknown(db, client_a):
    result = measure(db, client_a, end=date(2026, 9, 30))
    assert result["leads"]["previous_rate_pct"] is None
