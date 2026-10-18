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


def test_ctr_uses_only_matching_dated_desktop_aio_observations(db, client_a):
    url = f"https://{client_a.domain}/service"
    for device, impressions in [("desktop", 1000), ("mobile", 500)]:
        db.add(FactGscQueryPage(client_id=client_a.id, date=date(2026, 9, 20), query="service",
            raw_url=url, normalized_url=url, country="usa", device=device, impressions=impressions, clicks=10, average_position=1))
    db.add(FactSerpFeature(client_id=client_a.id, pulled_on=date(2026, 9, 19), keyword="service",
        location_code=2840, source="dataforseo", item_types=["ai_overview"]))
    db.flush()
    result = read_ctr(db, client_a.id, date(2026, 9, 1), DAY)
    assert result["matched"]
    assert result["missed_clicks"] == pytest.approx(65.2)
    assert result["actual_clicks"] == 10
    assert result["evidence"]["matched_impressions"] == 1000
    assert result["evidence"]["coverage_pct"] == pytest.approx(1000 / 1500 * 100)
    # The newest observed SERP says no AIO: do not cherry-pick an older AIO snapshot.
    db.add(FactSerpFeature(client_id=client_a.id, pulled_on=date(2026, 9, 20), keyword="service",
        location_code=2840, source="dataforseo", item_types=["organic"]))
    db.flush()
    assert read_ctr(db, client_a.id, date(2026, 9, 1), DAY)["matched"] is False


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
