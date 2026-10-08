from __future__ import annotations

from copy import deepcopy
from typing import Any

DEFAULT_DECISION_THRESHOLDS: dict[str, Any] = {
    "gsc_striking_distance_min_pos": 8,
    "gsc_striking_distance_max_pos": 20,
    "gsc_striking_distance_min_impressions": 50,
    "conversion_sessions_growth_min_pct": 5.0,
    "conversion_lead_rate_decline_min_pct": 10.0,
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
    # Lists rather than numbers, but this is the per-client config store and a
    # separate column for two lists would not earn its migration.
    "cluster_generic_terms": [],
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
    "reliability_3a": 1.0,
    "reliability_3b": 1.0,
    "reliability_6": 1.0,
    "reliability_5a": 1.0,
    "reliability_ai_crawlers_unblock": 1.0,
    # 3a — the page ranks for a question and buries the answer.
    #: Below this the ranking is too thin for a rewrite to be worth an hour.
    "answer_first_min_impressions": 200,
    #: How many of the page's question queries to judge. Beyond a handful
    #: it stops being one edit.
    "answer_first_max_queries": 5,
    #: What an opening answer looks like: long enough to be an answer,
    #: short enough to be read before the reader leaves.
    "answer_first_words": [15, 70],
    #: Share of the query's meaningful words the paragraph has to use.
    "answer_first_token_overlap": 0.5,
    # 3b — questions the page draws and does not answer.
    "faq_min_questions": 3,
    "faq_min_uncovered": 2,
    "faq_max_added": 3,
    #: Above this overlap the FAQ already says it, in other words.
    "faq_coverage_overlap": 0.7,
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
    # Lowered from 0.3 after the first dry run: at 0.3 the placeholder
    # outranked every measured estimate SMA had, and twenty-five prompt
    # actions decided the whole month. A guess should sit below a
    # measurement, not above it.
    "flat_credit_6_prompt_gap": 0.15,
    "flat_credit_5a_entity_fix": 0.2,
    "flat_credit_ai_crawlers_unblock": 1.0,
    #: How many donor links one rank-push action may ask for. The cap is
    #: what keeps it inside an hour.
    "donor_link_cap": 5,
    #: Rankings take weeks to move, so a page with work completed or being
    #: measured inside this window is left alone rather than recommended
    #: again.
    "rank_settle_days": 60,
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
    "minimum_actionable_impact": 25,
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
