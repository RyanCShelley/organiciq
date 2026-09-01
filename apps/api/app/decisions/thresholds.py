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
    "ai_visibility_gap_search_min": 0.05,
    "ai_visibility_gap_mention_max_pct": 2.0,
    "property_low_ctr_max_pct": 0.05,
    "property_low_ctr_min_impressions": 10000,
}


def merge_thresholds(overrides: dict[str, Any] | None) -> dict[str, float | int]:
    merged = deepcopy(DEFAULT_DECISION_THRESHOLDS)
    if overrides:
        for key, value in overrides.items():
            if key in merged and isinstance(value, (int, float)):
                merged[key] = value
    return merged
