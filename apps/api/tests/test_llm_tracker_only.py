"""AI visibility has one source: the LLM tracker. The Decision Engine's AI rule, the results screen, the watchlist and the daily pull all follow it."""

from __future__ import annotations

from datetime import date, timedelta

from app.models.integration import IntegrationProvider
from app.models.seranking import FactSerAiPresence, FactSerAiTrackerStats
from app.services import daily_sync, results, triage_signals, watchlist
from tests.test_dashboard_phase6 import _llm_run


def test_the_ai_rule_reads_the_llm_tracker_not_se_ranking(db, client_a):
    today = date(2026, 10, 30)
    # SE Ranking says 90%; the tracker says 25%. The tracker is what is scored.
    db.add(FactSerAiTrackerStats(client_id=client_a.id, metric_date=today, prompts_count=40, mention_presence_pct=90))
    _llm_run(db, client_a.id, today - timedelta(days=2), [("openai", "p1", "Mentioned", False, False), ("gemini", "p1", "Not visible", False, False), ("openai", "p2", "Not visible", False, False), ("gemini", "p2", "Not visible", False, False)])
    db.commit()
    signals = triage_signals.visibility_signals(db, client_a, today=today, ai_period=None)
    assert signals.ai_mention_pct == 25.0 and signals.tracked_prompts == 2


def test_no_tracker_run_means_no_reading_rather_than_se_rankings(db, client_a):
    today = date(2026, 10, 30)
    db.add(FactSerAiTrackerStats(client_id=client_a.id, metric_date=today, prompts_count=40, mention_presence_pct=90))
    db.commit()
    signals = triage_signals.visibility_signals(db, client_a, today=today, ai_period=None)
    assert signals.ai_mention_pct is None and signals.tracked_prompts == 0


def test_the_ai_presence_a_decision_is_judged_on_is_the_trackers(db, client_a):
    db.add(FactSerAiPresence(client_id=client_a.id, metric_date=date(2026, 10, 1), overall_presence_pct=80))
    _llm_run(db, client_a.id, date(2026, 10, 10), [("openai", "p1", "Mentioned", False, False), ("gemini", "p1", "Not visible", False, False)])
    db.commit()
    assert results._ai_presence(db, client_a.id, date(2026, 10, 30)).value == 50.0
    early = results._ai_presence(db, client_a.id, date(2026, 10, 5))
    assert early.value is None and "LLM tracker" in early.missing


def test_the_watchlists_prompts_are_the_trackers_and_brand_checks_are_not_actions(db, client_a):
    _llm_run(db, client_a.id, date(2026, 10, 10), [("openai", "Who fixes leaks?", "Not visible", False, False), ("gemini", "Who fixes leaks?", "Mentioned", False, False), ("openai", "Is Acme good?", "Cited", True, True)])
    db.commit()
    rows = [r for r in watchlist.read(db, client_a) if r["kind"] == "prompt"]
    assert sorted((r["text"], r["provider"]) for r in rows) == [("Who fixes leaks?", "gemini"), ("Who fixes leaks?", "openai")]
    assert all(r["observation"]["source"] == "LLM tracker" for r in rows)


def test_the_daily_pull_no_longer_fetches_se_rankings_ai_data():
    assert daily_sync._PROVIDER_SOURCES[IntegrationProvider.SE_RANKING] == ("se_ranking_search",)
