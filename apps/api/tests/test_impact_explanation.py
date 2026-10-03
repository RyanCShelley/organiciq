"""What the expanded finding says, and what it no longer says.

The explanation used to print how the score was computed: the normalization
basis, the reference scale, the lead-rate source, a severity integer. All
true, none of it usable by someone deciding what to do on Tuesday.
"""

from __future__ import annotations

from app.services.decision_impact import build_impact_explanation

#: The engine internals that were being shown to strategists.
JARGON = (
    "normalization",
    "reference (period leads scale)",
    "Lead rate source",
    "upstream fallback",
    "Critical technical override",
    "Technical severity",
    "Impact driven by available business opportunity evidence",
)


def test_the_scoring_internals_are_gone():
    lines = build_impact_explanation(
        {
            "impact_basis": "downstream",
            "impact_normalization_basis": "leads_at_risk",
            "impact_reference_leads": 8.75,
            "estimated_leads_at_risk": 22.52,
            "lead_rate_source": "page_type",
            "severity": 70,
            "critical_override": True,
            "critical_override_reason": "conversion_page",
        }
    )
    joined = " ".join(lines)
    for phrase in JARGON:
        assert phrase not in joined, f"still showing engine internals: {phrase}"


def test_it_says_what_is_at_stake_in_leads():
    lines = build_impact_explanation(
        {"impact_normalization_basis": "leads_at_risk", "estimated_leads_at_risk": 22.52}
    )
    assert lines == ["About 23 leads a period at risk"]


def test_a_small_number_of_leads_keeps_its_decimal():
    """"About 1 lead" and "about 1.4" are different claims at this size."""
    lines = build_impact_explanation({"estimated_incremental_leads": 1.44})
    assert lines == ["Worth about 1.4 more leads a period"]


def test_clicks_are_the_fallback_when_leads_could_not_be_estimated():
    lines = build_impact_explanation({"recoverable_clicks": 180.0})
    assert lines == ["About 180 clicks a period being left behind"]


def test_leads_win_over_clicks_when_both_are_present():
    lines = build_impact_explanation(
        {"estimated_incremental_leads": 4.0, "recoverable_clicks": 180.0}
    )
    assert lines == ["Worth about 4.0 more leads a period"]


def test_a_broken_page_says_so_in_words():
    lines = build_impact_explanation(
        {"estimated_leads_at_risk": 12.0, "status_code": 503, "indexable": False}
    )
    assert "The page returns HTTP 503 — nobody can read it" in lines


def test_the_ai_segment_is_reported_when_there_is_one():
    lines = build_impact_explanation(
        {
            "estimated_incremental_leads": 3.0,
            "ai_referral_sessions": 150.0,
            "ai_referral_leads": 4.0,
        }
    )
    assert "AI assistants sent 150 sessions and 4 leads a period" in lines


def test_nothing_is_invented_when_there_is_nothing_to_say():
    assert build_impact_explanation({}) == []
