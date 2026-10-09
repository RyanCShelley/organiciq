"""Decision 1: the eleven tests, and which branch wins.

Three rules settled on 9 Oct 2026 and encoded here, because each replaces
something the engine did differently and would otherwise drift back.
"""

from __future__ import annotations

from app.decisions.triage import (
    VISIBILITY_EXPANSION,
    WITHHELD,
    Branch,
    LeadSignals,
    Status,
    TrafficSignals,
    VisibilitySignals,
    assess_leads,
    assess_traffic,
    assess_visibility,
    select_constraint,
    summarise_branch,
)

T: dict = {}


def _branches(vis=Status.PASS, traf=Status.PASS, leads=Status.PASS):
    """Branches forced to a status, for testing the ladder itself."""
    from app.decisions.triage import BranchResult, TestResult

    def one(branch, status):
        t = TestResult(
            id=branch.value[:2].upper(),
            name="n",
            metric_label="m",
            value=None if status is Status.BLOCKED else 1.0,
            pass_line=1.0,
            direction="min",
            unit="pct",
            status=status,
            missing="no data" if status is Status.BLOCKED else None,
        )
        return BranchResult(
            branch=branch, status=status, headline_test=t.id, tests=(t,)
        )

    return [
        one(Branch.VISIBILITY, vis),
        one(Branch.TRAFFIC, traf),
        one(Branch.LEADS, leads),
    ]


# ── A branch's status ──


def test_one_failing_test_fails_the_branch():
    tests = assess_visibility(
        VisibilitySignals(
            priority_keywords=10, priority_in_top_10=1, priority_group_set=True,
            ai_mention_pct=90.0, tracked_prompts=10,
        ),
        thresholds=T,
    )
    assert summarise_branch(Branch.VISIBILITY, tests).status is Status.FAIL


def test_blocked_only_when_nothing_failed():
    """A branch with one failure and four unknowns is failing, not unknown."""
    tests = assess_visibility(
        VisibilitySignals(priority_keywords=10, priority_in_top_10=1, priority_group_set=True),
        thresholds=T,
    )
    assert summarise_branch(Branch.VISIBILITY, tests).status is Status.FAIL

    unknown = assess_visibility(VisibilitySignals(), thresholds=T)
    assert summarise_branch(Branch.VISIBILITY, unknown).status is Status.BLOCKED


def test_a_test_with_no_input_is_never_a_pass():
    """How a client with no conversion tracking came out converting fine."""
    for t in assess_leads(LeadSignals(conversions_configured=False), thresholds=T):
        assert t.status is Status.BLOCKED, t.id
        assert t.missing


# ── The eleven ──


def test_v1_reads_priority_terms_not_every_term():
    blocked = assess_visibility(
        VisibilitySignals(priority_keywords=0, priority_group_set=False), thresholds=T
    )[0]
    assert blocked.status is Status.BLOCKED
    assert "priority" in (blocked.missing or "")


def test_v2_and_v3_judge_a_fall_not_a_level():
    tests = {
        t.id: t
        for t in assess_visibility(
            VisibilitySignals(
                visibility_percent=70.0, visibility_percent_90d_ago=100.0,
                impressions_28d=1000.0, impressions_prior_28d=1050.0,
            ),
            thresholds=T,
        )
    }
    assert tests["V2"].status is Status.FAIL   # lost 30%, bar is 15
    assert tests["V3"].status is Status.PASS   # lost ~5%


def test_v4_fails_on_a_single_unreachable_target_page():
    tests = {
        t.id: t
        for t in assess_visibility(
            VisibilitySignals(
                priority_pages=8, priority_pages_without_reach=1,
                priority_pages_declared=True,
            ),
            thresholds=T,
        )
    }
    assert tests["V4"].status is Status.FAIL


def test_t1_compares_missed_clicks_to_clicks_actually_earned():
    tests = {t.id: t for t in assess_traffic(
        TrafficSignals(missed_clicks=30.0, actual_clicks=100.0), thresholds=T)}
    assert tests["T1"].status is Status.FAIL
    tests = {t.id: t for t in assess_traffic(
        TrafficSignals(missed_clicks=10.0, actual_clicks=100.0), thresholds=T)}
    assert tests["T1"].status is Status.PASS


def test_t2_needs_both_halves_to_diverge():
    rising_both = assess_traffic(
        TrafficSignals(impressions_change_pct=40.0, sessions_change_pct=35.0), thresholds=T)
    assert {t.id: t for t in rising_both}["T2"].status is Status.PASS

    diverging = assess_traffic(
        TrafficSignals(impressions_change_pct=40.0, sessions_change_pct=-5.0), thresholds=T)
    assert {t.id: t for t in diverging}["T2"].status is Status.FAIL


def test_t3_catches_a_site_that_was_always_poor():
    """An absolute floor alone passes a site that has always been bad; the
    median alone passes one that is consistently terrible."""
    tests = {t.id: t for t in assess_traffic(
        TrafficSignals(engaged_rate=55.0, engaged_rate_median=90.0), thresholds=T)}
    assert tests["T3"].status is Status.PASS
    assert tests["T3b"].status is Status.FAIL


def test_l1_judges_against_the_goal_so_far_not_the_whole_month():
    """Day three against a monthly goal fails everyone."""
    tests = {t.id: t for t in assess_leads(
        LeadSignals(conversions_configured=True, leads_month_to_date=4,
                    goal_to_date=5, monthly_goal=50), thresholds=T)}
    assert tests["L1"].status is Status.PASS


def test_l1_fails_when_the_pace_is_genuinely_short():
    tests = {t.id: t for t in assess_leads(
        LeadSignals(conversions_configured=True, leads_month_to_date=4,
                    goal_to_date=16, monthly_goal=50), thresholds=T)}
    assert tests["L1"].status is Status.FAIL
    assert tests["L1"].display == "4 of 50 leads"


# ── The ladder ──


def test_the_first_failing_branch_wins():
    t = select_constraint(_branches(vis=Status.FAIL, leads=Status.FAIL))
    assert t.constraint == "visibility"


def test_a_blocked_branch_is_skipped_not_fatal():
    """Settled 9 Oct: Visibility blocked and Leads failing means Leads."""
    t = select_constraint(_branches(vis=Status.BLOCKED, leads=Status.FAIL))
    assert t.constraint == "leads"


def test_nothing_failing_is_visibility_expansion():
    """Not "the weakest of the three", which was a sentence nobody could act
    on."""
    t = select_constraint(_branches())
    assert t.constraint == VISIBILITY_EXPANSION


def test_everything_blocked_is_still_not_a_constraint():
    t = select_constraint(_branches(Status.BLOCKED, Status.BLOCKED, Status.BLOCKED))
    assert t.constraint == VISIBILITY_EXPANSION


def test_a_relaunch_forces_visibility_over_a_failing_lead_branch():
    t = select_constraint(
        _branches(vis=Status.PASS, leads=Status.FAIL), relaunch_within_180d=True
    )
    assert t.constraint == "visibility"
    assert t.override == "relaunch_180d"


def test_stale_data_beats_everything():
    t = select_constraint(
        _branches(vis=Status.FAIL),
        relaunch_within_180d=True,
        withheld_reason="Search Console data is 11 days stale",
    )
    assert t.constraint == WITHHELD
    assert "11 days" in t.reason_text


def test_the_reason_names_the_failing_number():
    """"Leads is the constraint" is not a reason. The sentence has to carry
    the number that failed and the bar it missed."""
    tests = assess_leads(
        LeadSignals(conversions_configured=True, leads_month_to_date=4,
                    goal_to_date=16, monthly_goal=50), thresholds=T)
    leads = summarise_branch(Branch.LEADS, tests)
    t = select_constraint([*_branches()[:2], leads])
    assert "4 of 50 leads" in t.reason_text
    assert "80%" in t.reason_text
