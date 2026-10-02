from __future__ import annotations

from copy import deepcopy
from typing import Any

DEFAULT_DECISION_THRESHOLDS: dict[str, float | int] = {
    "gsc_high_impression_min": 100,
    "gsc_low_ctr_max_pct": 1.0,
    "gsc_striking_distance_min_pos": 8,
    "gsc_striking_distance_max_pos": 20,
    "gsc_striking_distance_min_impressions": 50,
    "conversion_sessions_growth_min_pct": 5.0,
    "conversion_lead_rate_decline_min_pct": 10.0,
    # Legacy portfolio gap (unused by lever_engine AI Visibility rules).
    "ai_visibility_gap_search_min": 0.05,
    "ai_visibility_gap_mention_max_pct": 2.0,
    "ai_visibility_min_keyword_volume": 50,
    "ai_visibility_keyword_top_n": 25,
    "ai_visibility_prompt_min_checks": 2,
    "ai_visibility_prompt_top_n": 25,
    # A page can be broken and draw no impressions *because* it is broken, so
    # the demand gate is read against the period before for blocking technical
    # checks. B2.
    "technical_blocking_min_prior_impressions": 30,
    # --- Phase 2 ---
    # T1: a rate that moved on four expected leads moved on noise.
    "gate1_min_expected_leads": 10,
    # T2/T6: clicks below this share of what the position should earn.
    "gate2_capture_ratio": 0.5,
    # T3: a page type needs this much behind it to be a fair comparison.
    "gate3_page_type_min_pages": 5,
    "gate3_page_type_min_leads": 10,
    # T4: inbound editorial links expected, by what the page is for.
    "link_floor_money": 10,
    "link_floor_industry": 6,
    "link_floor_blog": 3,
    "link_max_donors": 3,
    # T5: a subject needs a phrase, not a word.
    "cluster_min_phrase_words": 2,
    # T7: clicks down this far, with impressions holding, is a listing problem.
    "decay_impressions_flat_pct": 10.0,
    "light_refresh_min_drop_pct": 20.0,
    # T8: a rule gets another chance once the work has moved on.
    "contested_reset_days": 90,
    "property_low_ctr_max_pct": 0.05,
    "property_low_ctr_min_impressions": 10000,
    "minimum_actionable_impact": 25,
    "minimum_recommendation_confidence": 60,
    "high_priority_threshold": 70,
    "medium_priority_threshold": 50,
    "meaningful_gsc_impressions": 100,
    "meaningful_ga4_sessions": 10,
    "content_planning_min_impressions": 200,
    "content_planning_top_n": 50,
}


def merge_thresholds(overrides: dict[str, Any] | None) -> dict[str, float | int]:
    merged = deepcopy(DEFAULT_DECISION_THRESHOLDS)
    if overrides:
        for key, value in overrides.items():
            if key in merged and isinstance(value, (int, float)):
                merged[key] = value
    return merged
