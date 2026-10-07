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
    # What a new page can plausibly reach on a term nothing currently ranks
    # for. Read off the measured CTR curve rather than assumed: position 5 is
    # 1.08% organic, not the 6% a flat weight was implying.
    "keyword_target_position": 3,
    # A hard term is discounted towards this, never below it.
    "keyword_difficulty_floor": 0.2,
    # No single unbuilt page may claim more than this share of the period
    # goal. One keyword was being valued at four times the site's output.
    "single_opportunity_max_lead_share": 0.5,
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
    # Where CTR work stops mattering. On the measured curve position six
    # earns 0.73%, so there is no click to win back by rewriting a listing.
    # Outside the top five the work is rank, not the listing.
    "serp_ctr_max_position": 5,
    # Positions six to ten: the term is winnable and the page earns almost
    # nothing where it sits, so the work is rank rather than the listing.
    "rank_push_max_position": 10,
    "rank_push_min_impressions": 200,
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
    # --- Growth actions: valued in expected leads per month ---
    # Nothing is dropped for being small. Going from 36 leads to 37 is
    # worth doing; only work worth less than a tenth of a lead a month
    # falls away.
    "min_expected_leads_monthly": 0.1,
    #: Per-rule discount, for when measured outcomes exist. Until then
    #: every rule is trusted at face value and the learning loop is not
    #: built.
    "reliability_default": 1.0,
    #: Per rule, so one can be discounted without touching the rest.
    "reliability_1a": 1.0,
    "reliability_1b": 1.0,
    "reliability_2a": 1.0,
    "reliability_2c": 1.0,
    "reliability_6": 1.0,
    "reliability_5a": 1.0,
    "reliability_ai_crawlers_unblock": 1.0,
    #: How long each action takes. Estimates, not measurements. The cap
    #: that makes an action an action is sixty minutes, enforced by a test.
    "estimated_minutes": {
        "1a": 45,
        "1b": 15,
        "2a": 30,
        "2c": 45,
        "6": 45,
        "5a": 45,
        "ai_crawlers_unblock": 15,
    },
    #: Actions with no honest clicks-to-leads model. Placeholders whose
    #: only job is to order them sensibly against the search actions, and
    #: they are shown openly as such.
    "flat_credit_6_prompt_gap": 0.3,
    "flat_credit_5a_entity_fix": 0.2,
    "flat_credit_ai_crawlers_unblock": 1.0,
    #: How many donor links one rank-push action may ask for. The cap is
    #: what keeps it inside an hour.
    "donor_link_cap": 5,
    # --- Decision engine v1.1: the six triggers ---
    # T1 asks which pages people land on and never convert from. Ranked by
    # traffic instead, the gate was one page per client — the homepage,
    # which converts.
    "t1_min_sessions": 30,
    "t1_max_findings": 5,
    "t1_bounce_multiple": 1.2,
    #: Below this the site's own bounce rate is not an average.
    "t1_baseline_min_sessions": 200,
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
    # A growth action is a small task that moves the account forward. One
    # worth this much, and doable inside an hour, is worth doing whatever
    # share of the monthly goal it represents. Needs the client's
    # `lead_value` to be set; without it the engine falls back to counting
    # leads and this route never opens.
    "growth_action_min_value": 250,
    # A critical technical fault clears a lower bar than ordinary work, but
    # not a bar of zero: a broken page with no demand behind it is still a
    # page with no demand behind it.
    "critical_override_min_impact": 5,
    # Lowered from 60 once C1 made confidence a measured number rather than a
    # per-lever constant. Against constants that started at 70 the old gate had
    # never rejected anything; against the measured score the distribution runs
    # 45-76 with a median of 54, so 60 would have rejected 83% of findings. At
    # 50 the gate keeps today's recommendations and rejects the band that rests
    # on both a weak source and thin evidence.
    "minimum_recommendation_confidence": 50,
    # The priority formula itself, so the ranking can be argued with rather
    # than only read. Impact leads; the rest are scaled by how real the
    # impact is, so a tidy and urgent finding worth nothing cannot climb on
    # confidence and ease alone.
    "score_weight_impact": 0.60,
    "score_weight_confidence": 0.15,
    "score_weight_urgency": 0.15,
    "score_weight_effort": 0.10,
    #: Impact at or above this counts in full; below it the secondary terms
    #: are scaled down in proportion.
    "score_impact_relevance_scale": 20,
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
            elif isinstance(merged[key], dict):
                # Per-rule maps, like how long each action takes. Merged
                # key by key so overriding one rule's minutes does not
                # silently delete the others.
                if isinstance(value, dict):
                    merged[key] = {**merged[key], **value}
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                merged[key] = value
    return merged
