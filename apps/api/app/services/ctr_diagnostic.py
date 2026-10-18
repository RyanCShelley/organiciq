"""Apply the user-selected industry CTR reference across all search terms.

A common planning reference, not a claim that each query has an AI Overview
or that its device/market matches the source study. No SERP pulls required.
"""
from app.decisions.ctr_curve import REFERENCE_SCENARIO, expected_ctr_percent
from app.models.gsc import FactGscQueryPage

SCENARIO = REFERENCE_SCENARIO
MIN_IMPRESSIONS = 100


def read(db, client_id, start, end):
    total = matched = clicks = shortfall = 0.0
    queries = set()
    for row in db.query(FactGscQueryPage).filter(
        FactGscQueryPage.client_id == client_id, FactGscQueryPage.date >= start,
        FactGscQueryPage.date <= end,
    ):
        impressions = float(row.impressions or 0)
        total += impressions
        position = float(row.average_position or 0)
        if not 1 <= position <= 20:
            continue
        actual = float(row.clicks or 0)
        expected = impressions * expected_ctr_percent(position, scenario=SCENARIO) / 100
        matched += impressions
        clicks += actual
        shortfall += max(0, expected - actual)
        queries.add(row.query.strip().lower())
    missing = "no query-level Search Console observations" if not total else (
        "no query positions within the CTR reference range (1–20)" if not matched else
        "fewer than 100 reference impressions for the CTR reference" if matched < MIN_IMPRESSIONS else None)
    return {"matched": matched >= MIN_IMPRESSIONS, "missing": missing,
        "missed_clicks": shortfall if matched else None, "actual_clicks": clicks if matched else None,
        "evidence": {"benchmark": SCENARIO, "application": "all_terms_reference",
            "matched_impressions": matched, "total_query_impressions": total,
            "matched_queries": len(queries), "coverage_pct": matched / total * 100 if total else None}}
