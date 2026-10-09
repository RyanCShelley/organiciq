"""Decisions 2 and 3: which targets score, and which get a slot.

The scoring is a product, so a zero on any factor removes the candidate.
That is the rule that stops four good factors carrying a disqualifying one —
a term with no volume is not worth an hour however well it fits.

Slots fill from the constraint and spill only to branches that are failing.
The old engine ranked every finding together and handed slots to branches
that were fine, so a client with healthy traffic got traffic work.
"""

from __future__ import annotations

from app.decisions.slots import Prescription, fill_slots
from app.decisions.targets import Candidate, rank_candidates, reach, score_candidate
from app.decisions.triage import Branch, BranchResult, Status, TestResult


def _c(**kw) -> Candidate:
    base = dict(
        keyword="seo agency", target_url="https://x/seo", ranking_url="https://x/seo",
        position=12.0, volume=1000.0, priority=True, target_page_type="commercial",
    )
    base.update(kw)
    return Candidate(**base)


def _branch(branch: Branch, status: Status) -> BranchResult:
    t = TestResult(
        id=branch.value[:2].upper(), name="n", metric_label="m",
        value=1.0, pass_line=1.0, direction="min", unit="pct", status=status,
    )
    return BranchResult(branch=branch, status=status, headline_test=t.id, tests=(t,))


def _p(action_id="V-1", url="https://x/a", score=100.0) -> Prescription:
    return Prescription(
        action_id=action_id, title="t", branch=Branch.VISIBILITY, target_url=url,
        term="k", score=score, effort_min=30, why="w", done_when="d", metric="m",
    )


# ── Decision 2: the product ──


def test_no_volume_removes_the_candidate():
    """Four good factors must not carry a disqualifying one."""
    assert score_candidate(_c(volume=0)).score == 0.0
    assert rank_candidates([_c(volume=0)]) == []


def test_already_in_the_top_three_is_nearly_worthless():
    """The clicks are already being earned. The hour goes elsewhere."""
    high = score_candidate(_c(position=2.0)).score
    reachable = score_candidate(_c(position=8.0)).score
    assert high < reachable / 5


def test_reach_rewards_the_short_trip():
    assert reach(8.0, None) > reach(15.0, None) > reach(25.0, None)
    assert reach(2.0, None) < reach(25.0, None)


def test_an_unranked_term_is_discounted_by_difficulty():
    """And an unknown difficulty is pessimistic, because it is usually
    unknown for a reason."""
    easy = reach(None, 10.0)
    hard = reach(None, 90.0)
    unknown = reach(None, None)
    assert easy > hard
    assert hard < unknown < easy


def test_a_priority_term_outranks_an_equal_ordinary_one():
    assert score_candidate(_c(priority=True)).score > score_candidate(
        _c(priority=False)
    ).score


def test_intent_is_read_from_the_page_not_the_words():
    """'what is local seo' and 'local seo services' differ by intent and not
    reliably by vocabulary."""
    buying = score_candidate(_c(target_page_type="commercial")).score
    reading = score_candidate(_c(target_page_type="article")).score
    assert reading < buying


def test_an_unmapped_term_is_not_assumed_informational():
    """Assuming the cheaper weight quietly demotes every unmapped term."""
    assert score_candidate(_c(target_url=None, target_page_type=None)).factors[
        "intent"
    ] == 1.0


def test_a_term_ranking_on_the_wrong_page_is_flagged_for_re_homing():
    """Not a weaker version of the same job — a decision about which page
    should own it, which is V-6."""
    result = score_candidate(_c(ranking_url="https://x/blog/other"))
    assert result.rehoming is True
    assert result.factors["fit"] == 0.5
    assert "ranks on" in result.notes[0]


def test_an_unmapped_term_still_scores():
    result = score_candidate(_c(target_url=None, ranking_url=None))
    assert result.factors["fit"] == 0.7
    assert result.score > 0


# ── Decision 3: the slots ──


def test_the_constraint_fills_first():
    plan = fill_slots(
        slots=2,
        constraint=Branch.VISIBILITY,
        branches=[_branch(Branch.VISIBILITY, Status.FAIL), _branch(Branch.LEADS, Status.FAIL)],
        prescriptions_by_branch={
            Branch.VISIBILITY: [_p(url="https://x/a")],
            Branch.LEADS: [_p(url="https://x/b")],
        },
    )
    assert [f.prescription.target_url for f in plan.filled] == ["https://x/a", "https://x/b"]
    assert [f.spillover for f in plan.filled] == [False, True]


def test_a_passing_branch_never_gets_a_slot():
    """The rule the old engine broke most visibly."""
    plan = fill_slots(
        slots=3,
        constraint=Branch.VISIBILITY,
        branches=[_branch(Branch.VISIBILITY, Status.FAIL), _branch(Branch.TRAFFIC, Status.PASS)],
        prescriptions_by_branch={
            Branch.VISIBILITY: [_p(url="https://x/a")],
            Branch.TRAFFIC: [_p(action_id="T-1", url="https://x/t")],
        },
    )
    assert len(plan.filled) == 1
    assert any(n["branch"] == "traffic" and "passes" in n["reason"] for n in plan.not_this_month)


def test_a_blocked_branch_never_gets_a_slot_either():
    plan = fill_slots(
        slots=3,
        constraint=Branch.VISIBILITY,
        branches=[_branch(Branch.VISIBILITY, Status.FAIL), _branch(Branch.LEADS, Status.BLOCKED)],
        prescriptions_by_branch={
            Branch.VISIBILITY: [_p(url="https://x/a")],
            Branch.LEADS: [_p(action_id="L-1", url="https://x/l")],
        },
    )
    assert len(plan.filled) == 1
    assert any("could not be judged" in n["reason"] for n in plan.not_this_month)


def test_one_action_per_url():
    """Three findings on one page is one job."""
    plan = fill_slots(
        slots=3,
        constraint=Branch.VISIBILITY,
        branches=[_branch(Branch.VISIBILITY, Status.FAIL)],
        prescriptions_by_branch={
            Branch.VISIBILITY: [_p(url="https://x/a"), _p(action_id="V-4", url="https://x/a/")],
        },
    )
    assert len(plan.filled) == 1
    assert any("one page is one job" in n["reason"] for n in plan.not_this_month)


def test_a_short_plan_stays_short():
    """Filling the gap with the next-best thing is how a plan stops meaning
    anything."""
    plan = fill_slots(
        slots=5,
        constraint=Branch.VISIBILITY,
        branches=[_branch(Branch.VISIBILITY, Status.FAIL)],
        prescriptions_by_branch={Branch.VISIBILITY: [_p()]},
    )
    assert len(plan.filled) == 1
    assert len(plan.empty) == 4
    assert "rather than being filled with weaker work" in plan.empty[0].reason


def test_the_empty_reason_names_the_branches_not_a_count():
    """'No qualifying target' is true and useless."""
    plan = fill_slots(
        slots=2,
        constraint=Branch.VISIBILITY,
        branches=[_branch(Branch.VISIBILITY, Status.FAIL), _branch(Branch.LEADS, Status.BLOCKED)],
        prescriptions_by_branch={Branch.VISIBILITY: [_p()]},
    )
    assert "visibility" in plan.empty[0].reason
    assert "blocked" in plan.empty[0].reason.lower()


def test_never_more_than_the_plan_allows():
    plan = fill_slots(
        slots=1,
        constraint=Branch.VISIBILITY,
        branches=[_branch(Branch.VISIBILITY, Status.FAIL)],
        prescriptions_by_branch={
            Branch.VISIBILITY: [_p(url=f"https://x/{i}") for i in range(10)]
        },
    )
    assert len(plan.filled) == 1
    assert plan.empty == ()
