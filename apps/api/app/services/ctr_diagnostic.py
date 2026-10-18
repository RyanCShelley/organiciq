"""Match the supplied desktop AIO benchmark to stored query-level observations.

No network requests or billable SERP pulls. DataForSEO's current collector is
desktop US; other sources/markets/devices are not inferred to match it.
"""
from datetime import timedelta

from app.decisions.ctr_curve import AI_OVERVIEW_FEATURES, expected_ctr_percent
from app.models.gsc import FactGscQueryPage
from app.models.seranking import FactSerpFeature

SCENARIO = "ai_overviews_desktop_aug_2026"
MAX_SERP_AGE_DAYS = 45
MIN_IMPRESSIONS = 100


def read(db, client_id, start, end):
    snapshots = {}
    for row in db.query(FactSerpFeature).filter(
        FactSerpFeature.client_id == client_id,
        FactSerpFeature.source == "dataforseo", FactSerpFeature.location_code == 2840,
        FactSerpFeature.pulled_on >= start - timedelta(days=MAX_SERP_AGE_DAYS),
        FactSerpFeature.pulled_on <= end,
    ).order_by(FactSerpFeature.pulled_on.desc()):
        snapshots.setdefault(row.keyword.strip().lower(), []).append(row)
    total = matched = clicks = shortfall = 0.0
    queries = set()
    for row in db.query(FactGscQueryPage).filter(
        FactGscQueryPage.client_id == client_id, FactGscQueryPage.date >= start,
        FactGscQueryPage.date <= end,
    ):
        impressions = float(row.impressions or 0)
        total += impressions
        position = float(row.average_position or 0)
        if row.device.lower() != "desktop" or row.country.lower() not in ("usa", "us") or not 1 <= position <= 20:
            continue
        snapshot = next((item for item in snapshots.get(row.query.strip().lower(), [])
            if item.pulled_on <= row.date and (row.date - item.pulled_on).days <= MAX_SERP_AGE_DAYS), None)
        if snapshot is None or not (set(snapshot.item_types or []) & AI_OVERVIEW_FEATURES):
            continue
        actual = float(row.clicks or 0)
        expected = impressions * expected_ctr_percent(position, scenario=SCENARIO) / 100
        matched += impressions
        clicks += actual
        shortfall += max(0, expected - actual)
        queries.add(row.query.strip().lower())
    missing = "no query-level Search Console observations" if not total else (
        "no matching desktop US queries with a dated AI Overview SERP observation" if not matched else
        "fewer than 100 matched impressions for the CTR reference" if matched < MIN_IMPRESSIONS else None)
    return {"matched": matched >= MIN_IMPRESSIONS, "missing": missing,
        "missed_clicks": shortfall if matched else None, "actual_clicks": clicks if matched else None,
        "evidence": {"benchmark": SCENARIO, "matched_impressions": matched,
            "total_query_impressions": total, "matched_queries": len(queries),
            "coverage_pct": matched / total * 100 if total else None}}
