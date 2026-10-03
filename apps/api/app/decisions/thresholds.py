from __future__ import annotations

from copy import deepcopy
from typing import Any

DEFAULT_DECISION_THRESHOLDS: dict[str, Any] = {
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
    # Lists rather than numbers, but this is the per-client config store and a
    # separate column for two lists would not earn its migration.
    "cluster_generic_terms": [],
    "cluster_excluded_topics": [],
    # T7: clicks down this far, with impressions holding, is a listing problem.
    "decay_impressions_flat_pct": 10.0,
    "light_refresh_min_drop_pct": 20.0,
    # T8: a rule gets another chance once the work has moved on.
    "contested_reset_days": 90,
    # --- Phase 3 ---
    # An orphan page needs demand to be worth reporting: most pages nothing
    # links to are drafts and thank-you pages.
    "orphan_min_impressions": 30,
    # A page needs this much traffic before "nothing to convert through" is
    # worth saying. From the review's own ">= 30 sessions" for CRO checks.
    "cta_min_sessions": 30,
    # Gate 0 anomalies. Neither suppresses anything.
    "partial_break_days": 14,
    "partial_break_min_expected_leads": 3,
    "lead_spike_multiple": 3.0,
    # 3x of two leads is six, which is a good week, not a spike.
    "lead_spike_min_leads": 10,
    # --- Phase 4: new rules, each behind a flag that defaults on ---
    "rule_ai_sov_falling_enabled": 1,
    "rule_link_reclamation_enabled": 1,
    # Share of the tracked prompt set mentioning the brand, read over this
    # many days. A relative fall past the percentage is the finding.
    "ai_sov_window_days": 30,
    "ai_sov_drop_pct": 20.0,
    # Below this the share is too small for a 20% relative move to mean
    # anything: 2% to 1.5% is one prompt changing its mind.
    "ai_sov_min_presence_pct": 5.0,
    # A broken URL worth reclaiming has at least this many referring domains.
    "reclaim_min_refdomains": 1,
    # --- Phase 5: effort ---
    # Between two findings worth the same, the cheaper one should come first.
    # These re-order the queue; they never promote or block anything.
    "effort_weight_small": 1.0,
    "effort_weight_medium": 1.5,
    "effort_weight_large": 2.5,
    "effort_reorder_top_n": 25,
    # C1: confidence read from the evidence rather than from the lever.
    # Applying it is off until the distribution across real clients has been
    # looked at — see app/decisions/confidence.py.
    "data_driven_confidence_enabled": 0,
    "confidence_tier_high": 1.0,
    "confidence_tier_medium": 0.9,
    "confidence_tier_low": 0.75,
    "confidence_small_sample_factor": 0.8,
    "confidence_min_sample_leads": 3,
    "confidence_min_sample_impressions": 100,
    "confidence_stale_after_days": 14,
    "confidence_stale_factor": 0.85,
    "property_low_ctr_max_pct": 0.05,
    "property_low_ctr_min_impressions": 10000,
    "minimum_actionable_impact": 25,
    # Lowered from 60 once C1 made confidence a measured number rather than a
    # per-lever constant. Against constants that started at 70 the old gate had
    # never rejected anything; against the measured score the distribution runs
    # 45-76 with a median of 54, so 60 would have rejected 83% of findings. At
    # 50 the gate keeps today's recommendations and rejects the band that rests
    # on both a weak source and thin evidence.
    "minimum_recommendation_confidence": 50,
    "high_priority_threshold": 70,
    "medium_priority_threshold": 50,
    "meaningful_gsc_impressions": 100,
    "meaningful_ga4_sessions": 10,
    "content_planning_min_impressions": 200,
    "content_planning_top_n": 50,
}


def merge_thresholds(overrides: dict[str, Any] | None) -> dict[str, Any]:
    merged = deepcopy(DEFAULT_DECISION_THRESHOLDS)
    if overrides:
        for key, value in overrides.items():
            if key not in merged:
                continue
            # Two of these keys hold lists of terms. They were being dropped
            # here, which made them tunable only by deploy — the opposite of
            # what this store is for.
            if isinstance(merged[key], list):
                if isinstance(value, list):
                    merged[key] = [str(item) for item in value]
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                merged[key] = value
    return merged
