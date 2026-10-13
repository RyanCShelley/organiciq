"""The retainer pool, beside the growth plan rather than inside it.

Updating existing content is bought every month whatever the constraint
says. Growth actions are deliberately outside the retainer, so the two
cannot share slots — and they must not share a page either.
"""

from __future__ import annotations

from app.decisions.slots import Prescription, fill_pool
from app.decisions.triage import Branch


def _p(action_id: str, url: str, score: float) -> Prescription:
    return Prescription(
        action_id=action_id,
        title=action_id,
        branch=Branch.TRAFFIC,
        target_url=url,
        term=None,
        score=score,
        effort_min=30,
        why="",
        done_when="",
        metric="Impressions",
    )


def test_the_allowance_is_never_exceeded():
    plan = fill_pool(
        slots=2,
        prescriptions=[_p("U-1", "/a", 900), _p("U-1", "/b", 500), _p("U-1", "/c", 100)],
    )
    assert [s.prescription.target_url for s in plan.filled] == ["/a", "/b"]


def test_what_did_not_fit_is_recorded_rather_than_dropped():
    plan = fill_pool(slots=1, prescriptions=[_p("U-1", "/a", 900), _p("U-1", "/b", 500)])
    left = [c for c in plan.considered if c.slot is None]
    assert len(left) == 1
    assert "higher-scoring work" in left[0].reason


def test_a_short_pool_says_why_rather_than_padding():
    """Filling the gap with the next-best thing is how a plan stops
    meaning anything."""
    plan = fill_pool(
        slots=3,
        prescriptions=[_p("U-1", "/a", 900)],
        empty_reason="No page has lost enough ground to be worth a refresh.",
    )
    assert len(plan.filled) == 1
    assert [e.slot for e in plan.empty] == [2, 3]
    assert all("lost enough ground" in e.reason for e in plan.empty)


def test_one_page_is_one_job_across_the_whole_plan():
    """A page prescribed a growth action and a refresh in the same month
    is two briefs, two Teamwork tasks and one confused writer."""
    plan = fill_pool(
        slots=2,
        prescriptions=[_p("U-1", "https://e.test/a", 900), _p("U-1", "https://e.test/b", 10)],
        reserved_urls={"https://e.test/a"},
    )
    assert [s.prescription.target_url for s in plan.filled] == ["https://e.test/b"]
    blocked = next(c for c in plan.considered if c.slot is None)
    assert "one page is one job" in blocked.reason


def test_a_reserved_url_matches_however_it_was_written():
    plan = fill_pool(
        slots=1,
        prescriptions=[_p("U-1", "https://e.test/a/", 900)],
        reserved_urls={"https://e.test/A"},
    )
    assert plan.filled == ()


def test_one_page_cannot_take_two_slots_in_the_same_pool():
    plan = fill_pool(
        slots=3,
        prescriptions=[_p("U-2", "/a", 900), _p("U-1", "/a", 800), _p("U-1", "/b", 10)],
    )
    assert [s.prescription.target_url for s in plan.filled] == ["/a", "/b"]


def test_a_closed_pool_fills_nothing_and_says_so():
    """Legacy clients buy quarterly; in the other two months the plan is
    empty on purpose and has to say which."""
    plan = fill_pool(
        slots=0,
        prescriptions=[_p("U-1", "/a", 900)],
        empty_reason="Legacy buys this quarterly.",
    )
    assert plan.filled == ()
    assert plan.empty == ()
    # Not outbid — nothing could have fitted, so it says the real reason.
    assert [c.reason for c in plan.considered] == ["Legacy buys this quarterly."]
