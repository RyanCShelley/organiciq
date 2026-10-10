"""Decision 1 — which of the three is holding this client back this month.

Eleven named tests, grouped into three branches. A branch **fails** if any of
its tests fails, is **blocked** if any test lacks its input and none fails, and
**passes** otherwise. The first failing branch, walking visibility → traffic →
leads, is the month's constraint.

Upstream first, because visibility earns traffic earns leads: a conversion fix
on a page nobody can find is an hour spent at the wrong end of the funnel.

Three rules settled on 9 Oct 2026 that the spec leaves open or that replace
what was here before:

* **Blocked is skipped, not fatal.** Blocked is not failing, so the ladder
  passes over it and the first genuinely failing branch wins — Visibility
  blocked and Leads failing means Leads. A blocked branch still cannot take a
  slot, and it lowers the run's confidence through `missing_input`.
* **Nothing failing means Visibility expansion**, not "the weakest of the
  three". The engine used to name a constraint even when nothing was broken,
  which produced a sentence nobody could act on.
* **A test with no input is blocked, never passed.** Passing a test we could
  not run is how a client with no conversion tracking came out "converting
  fine".

Pure functions over explicit signals. Nothing here touches the database, so
every test can be exercised at its own boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Branch(str, Enum):
    VISIBILITY = "visibility"
    TRAFFIC = "traffic"
    LEADS = "leads"


class Status(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    BLOCKED = "blocked"


#: Upstream first. The order is the argument.
LADDER: tuple[Branch, ...] = (Branch.VISIBILITY, Branch.TRAFFIC, Branch.LEADS)

#: Constraints that are not one of the three branches.
WITHHELD = "withheld"
VISIBILITY_EXPANSION = "visibility_expansion"


@dataclass(frozen=True)
class TestResult:
    """One named test, and what it found.

    `value` is in the unit the reader sees, and `pass_line` is the bar in the
    same unit — the old engine normalised everything to a ratio and the screen
    could say only "43% of a 30% bar", which is not a metric anyone recognises.

    `missing` names the input that was absent, so a blocked branch can say what
    to fix rather than just that it could not be judged.
    """

    id: str
    name: str
    metric_label: str
    value: float | None
    pass_line: float
    #: "min" — at least the pass line. "max" — at most it.
    direction: str
    unit: str
    status: Status
    missing: str | None = None
    display: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)


def _judge(
    test_id: str,
    name: str,
    metric_label: str,
    value: float | None,
    *,
    pass_line: float,
    direction: str = "min",
    unit: str = "pct",
    missing: str | None = None,
    display: str | None = None,
    evidence: dict[str, Any] | None = None,
) -> TestResult:
    """Build a result, blocking when the input is absent.

    A missing input never produces a pass. That is the whole of rule 5 in the
    spec — "no data, no rule" — and it is the difference between a client the
    engine cannot judge and one it has judged favourably.
    """
    if value is None or missing:
        status = Status.BLOCKED
    elif direction == "min":
        status = Status.PASS if value >= pass_line else Status.FAIL
    else:
        status = Status.PASS if value <= pass_line else Status.FAIL
    return TestResult(
        id=test_id,
        name=name,
        metric_label=metric_label,
        value=value,
        pass_line=pass_line,
        direction=direction,
        unit=unit,
        status=status,
        missing=missing,
        display=display,
        evidence=evidence or {},
    )


# ── Visibility ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class VisibilitySignals:
    #: Priority-group keywords only. V1 is about the terms the client is
    #: actually judged on, not every term anyone ever tracked.
    priority_keywords: int = 0
    priority_in_top_10: int = 0
    #: True when no keyword group has been marked priority, which is a
    #: different statement from a client whose priority terms rank badly.
    priority_group_set: bool = False
    #: SE Ranking's visibility score now and 90 days ago.
    visibility_percent: float | None = None
    visibility_percent_90d_ago: float | None = None
    #: Managed Search Console impressions, last 28 days and the 28 before.
    impressions_28d: float | None = None
    impressions_prior_28d: float | None = None
    #: Declared target and conversion pages with no tracked term in the top 20.
    priority_pages: int = 0
    priority_pages_without_reach: int = 0
    priority_pages_declared: bool = False
    #: Share of tracked prompts that mention the brand, 0-100.
    ai_mention_pct: float | None = None
    tracked_prompts: int = 0
    ai_sov: float | None = None
    ai_sov_90d_ago: float | None = None


def assess_visibility(
    signals: VisibilitySignals, *, thresholds: dict[str, Any]
) -> list[TestResult]:
    def t(key: str, fallback: float) -> float:
        return float(thresholds.get(key, fallback))

    results: list[TestResult] = []

    # V1 — priority-term coverage.
    share = (
        signals.priority_in_top_10 / signals.priority_keywords * 100.0
        if signals.priority_keywords
        else None
    )
    results.append(
        _judge(
            "V1",
            "Priority-term coverage",
            "Priority terms in the top 10",
            share,
            pass_line=t("v1_priority_top10_pct", 30.0),
            missing=None
            if signals.priority_group_set and signals.priority_keywords
            else "no keyword group is marked priority",
            display=(
                f"{signals.priority_in_top_10} of {signals.priority_keywords}"
                if signals.priority_keywords
                else None
            ),
            evidence={
                "priority_keywords": signals.priority_keywords,
                "in_top_10": signals.priority_in_top_10,
            },
        )
    )

    # V2 — visibility trend. A fall is reported as a positive percentage so
    # the bar reads "lose no more than 15%".
    drop = None
    if signals.visibility_percent is not None and signals.visibility_percent_90d_ago:
        before = signals.visibility_percent_90d_ago
        drop = max(0.0, (before - signals.visibility_percent) / before * 100.0)
    results.append(
        _judge(
            "V2",
            "Visibility trend",
            "Visibility lost over 90 days",
            drop,
            pass_line=t("v2_visibility_drop_pct", 15.0),
            direction="max",
            unit="chg",
            missing=None if drop is not None else "no visibility history",
        )
    )

    # V3 — impression trend.
    impression_drop = None
    if signals.impressions_28d is not None and signals.impressions_prior_28d:
        prior = signals.impressions_prior_28d
        impression_drop = max(0.0, (prior - signals.impressions_28d) / prior * 100.0)
    results.append(
        _judge(
            "V3",
            "Impression trend",
            "Impressions lost against the previous 28 days",
            impression_drop,
            pass_line=t("v3_impression_drop_pct", 15.0),
            direction="max",
            unit="chg",
            missing=None
            if impression_drop is not None
            else "not enough Search Console history",
        )
    )

    # V4 — priority-page reach. One page out of reach fails it: a page the
    # client sells from, with nothing in the top 20, is the definition of
    # being unfindable.
    results.append(
        _judge(
            "V4",
            "Priority-page reach",
            "Target pages with no term in the top 20",
            float(signals.priority_pages_without_reach)
            if signals.priority_pages_declared
            else None,
            pass_line=0.0,
            direction="max",
            unit="count",
            missing=None
            if signals.priority_pages_declared
            else "no target or conversion pages declared",
            display=(
                f"{signals.priority_pages_without_reach} of {signals.priority_pages}"
                if signals.priority_pages_declared
                else None
            ),
        )
    )

    # V5 — AI answer presence. Two readings, and either one failing fails it.
    mention = signals.ai_mention_pct if signals.tracked_prompts else None
    results.append(
        _judge(
            "V5",
            "AI answer presence",
            "Tracked prompts mentioning the brand",
            mention,
            pass_line=t("v5_ai_mention_pct", 20.0),
            missing=None if mention is not None else "no tracked prompts",
            evidence={"tracked_prompts": signals.tracked_prompts},
        )
    )
    sov_drop = None
    if signals.ai_sov is not None and signals.ai_sov_90d_ago:
        sov_drop = max(0.0, (signals.ai_sov_90d_ago - signals.ai_sov) / signals.ai_sov_90d_ago * 100.0)
    if sov_drop is not None:
        results.append(
            _judge(
                "V5b",
                "AI share of voice trend",
                "Share of voice lost over 90 days",
                sov_drop,
                pass_line=t("v5_ai_sov_drop_pct", 25.0),
                direction="max",
                unit="chg",
            )
        )
    return results


# ── Traffic ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TrafficSignals:
    #: Clicks the measured CTR curve says the rankings should earn and do not.
    missed_clicks: float | None = None
    actual_clicks: float | None = None
    impressions_change_pct: float | None = None
    sessions_change_pct: float | None = None
    engaged_rate: float | None = None
    engaged_rate_median: float | None = None


def assess_traffic(
    signals: TrafficSignals, *, thresholds: dict[str, Any]
) -> list[TestResult]:
    def t(key: str, fallback: float) -> float:
        return float(thresholds.get(key, fallback))

    results: list[TestResult] = []

    # T1 — missed clicks as a share of the clicks actually earned.
    missed_share = None
    if signals.missed_clicks is not None and signals.actual_clicks:
        missed_share = signals.missed_clicks / signals.actual_clicks * 100.0
    results.append(
        _judge(
            "T1",
            "Missed clicks",
            "Clicks the rankings should earn and do not",
            missed_share,
            pass_line=t("t1_missed_click_pct", 20.0),
            direction="max",
            missing=None if missed_share is not None else "no Search Console clicks",
            display=(
                f"{int(signals.missed_clicks):,} missed against "
                f"{int(signals.actual_clicks):,} earned"
                if missed_share is not None
                else None
            ),
        )
    )

    # T2 — divergence. More people seeing the listing and no more arriving is
    # a listing problem, and it is invisible in either number alone.
    diverging = None
    if (
        signals.impressions_change_pct is not None
        and signals.sessions_change_pct is not None
    ):
        diverging = (
            signals.impressions_change_pct - signals.sessions_change_pct
            if signals.impressions_change_pct > t("t2_impression_rise_pct", 10.0)
            and signals.sessions_change_pct <= 0
            else 0.0
        )
    results.append(
        _judge(
            "T2",
            "Divergence",
            "Impressions rising while visits do not",
            diverging,
            pass_line=0.0,
            direction="max",
            unit="chg",
            missing=None if diverging is not None else "no period-over-period data",
        )
    )

    # T3 — engagement quality. Either an absolute floor or a fall against the
    # client's own median; the second catches a site that was always poor.
    results.append(
        _judge(
            "T3",
            "Engagement quality",
            "Engaged sessions",
            signals.engaged_rate,
            pass_line=t("t3_engaged_rate_pct", 50.0),
            missing=None if signals.engaged_rate is not None else "no GA4 engagement data",
        )
    )
    if signals.engaged_rate is not None and signals.engaged_rate_median:
        against_median = signals.engaged_rate / signals.engaged_rate_median * 100.0
        results.append(
            _judge(
                "T3b",
                "Engagement against its own history",
                "Engaged rate against the 6-month median",
                against_median,
                pass_line=t("t3_engaged_vs_median_pct", 80.0),
            )
        )
    return results


# ── Leads ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LeadSignals:
    #: No conversion definitions means Leads is blocked, never passed.
    conversions_configured: bool = False
    leads_month_to_date: float | None = None
    #: The monthly goal, pro-rated to the day of the month.
    goal_to_date: float | None = None
    monthly_goal: float | None = None
    lead_rate: float | None = None
    baseline_lead_rate: float | None = None
    tofu_sessions_share: float | None = None
    next_step_measurable: bool = False
    #: Why L3 cannot run, in the reader's terms. Hardcoded prose here once
    #: told clients with conversion pages declared that they had none, which
    #: sent them to fix something that was not broken.
    next_step_blocked_by: str | None = None


def assess_leads(signals: LeadSignals, *, thresholds: dict[str, Any]) -> list[TestResult]:
    def t(key: str, fallback: float) -> float:
        return float(thresholds.get(key, fallback))

    blocked = None if signals.conversions_configured else "no conversion events set"
    results: list[TestResult] = []

    # L1 — goal pace, against the goal pro-rated to today rather than the
    # whole month. Judging day three against a monthly goal fails everyone.
    pace = None
    if (
        signals.leads_month_to_date is not None
        and signals.goal_to_date
        and signals.conversions_configured
    ):
        pace = signals.leads_month_to_date / signals.goal_to_date * 100.0
    results.append(
        _judge(
            "L1",
            "Goal pace",
            "Leads against the goal so far this month",
            pace,
            pass_line=t("l1_goal_pace_pct", 80.0),
            missing=blocked or (None if pace is not None else "no monthly lead goal"),
            display=(
                f"{int(signals.leads_month_to_date)} of "
                f"{int(signals.monthly_goal)} leads"
                if signals.leads_month_to_date is not None and signals.monthly_goal
                else None
            ),
        )
    )

    # L2 — lead rate against the client's own baseline.
    against_baseline = None
    if (
        signals.lead_rate is not None
        and signals.baseline_lead_rate
        and signals.conversions_configured
    ):
        against_baseline = signals.lead_rate / signals.baseline_lead_rate * 100.0
    results.append(
        _judge(
            "L2",
            "Lead rate",
            "Lead rate against this client's baseline",
            against_baseline,
            pass_line=t("l2_lead_rate_pct", 80.0),
            missing=blocked or (None if against_baseline is not None else "no baseline lead rate"),
        )
    )

    # L3 — next-step flow. Sessions landing on a page with nowhere to go.
    results.append(
        _judge(
            "L3",
            "Next-step flow",
            "Sessions landing with no route onward",
            signals.tofu_sessions_share if signals.next_step_measurable else None,
            pass_line=t("l3_dead_end_share_pct", 50.0),
            direction="max",
            missing=None
            if signals.next_step_measurable
            else (
                signals.next_step_blocked_by
                or "no conversion pages declared to route to"
            ),
        )
    )
    return results


# ── Branches and the constraint ─────────────────────────────────────────────


@dataclass(frozen=True)
class BranchResult:
    branch: Branch
    status: Status
    headline_test: str
    tests: tuple[TestResult, ...]
    display: str | None = None

    @property
    def missing(self) -> tuple[str, ...]:
        return tuple(
            t.missing for t in self.tests if t.status is Status.BLOCKED and t.missing
        )


def summarise_branch(branch: Branch, tests: list[TestResult]) -> BranchResult:
    """A branch fails if any test fails, blocked if any is blocked and none
    failed, and passes otherwise."""
    failing = [t for t in tests if t.status is Status.FAIL]
    blocked = [t for t in tests if t.status is Status.BLOCKED]
    if failing:
        status, headline = Status.FAIL, failing[0]
    elif blocked:
        status, headline = Status.BLOCKED, blocked[0]
    else:
        status, headline = Status.PASS, tests[0] if tests else None
    return BranchResult(
        branch=branch,
        status=status,
        headline_test=headline.id if headline else "",
        tests=tuple(tests),
        display=headline.display if headline else None,
    )


@dataclass(frozen=True)
class Triage:
    """The month's answer, and the evidence for it."""

    constraint: str
    reason_text: str
    branches: tuple[BranchResult, ...]
    override: str | None = None

    def of(self, branch: Branch) -> BranchResult | None:
        return next((b for b in self.branches if b.branch is branch), None)


def select_constraint(
    branches: list[BranchResult],
    *,
    relaunch_within_180d: bool = False,
    withheld_reason: str | None = None,
) -> Triage:
    """The one thing to work on this month.

    A stale-data gate beats everything: serving actions off numbers that
    stopped updating is worse than serving none.
    """
    ordered = tuple(
        next(b for b in branches if b.branch is rung)
        for rung in LADDER
        if any(b.branch is rung for b in branches)
    )

    if withheld_reason:
        return Triage(
            constraint=WITHHELD,
            reason_text=withheld_reason,
            branches=ordered,
        )

    if relaunch_within_180d:
        return Triage(
            constraint=Branch.VISIBILITY.value,
            reason_text=(
                "The site relaunched in the last 180 days, so rankings are still "
                "settling and visibility comes first whatever the other branches say."
            ),
            branches=ordered,
            override="relaunch_180d",
        )

    for result in ordered:
        if result.status is Status.FAIL:
            headline = next(
                (t for t in result.tests if t.id == result.headline_test), None
            )
            return Triage(
                constraint=result.branch.value,
                reason_text=_reason_for(result, headline),
                branches=ordered,
            )

    # Nothing failing. Blocked branches are skipped rather than fatal, so this
    # is reached when every branch either passed or could not be judged.
    return Triage(
        constraint=VISIBILITY_EXPANSION,
        reason_text=(
            "Nothing is failing. The next tier of keyword groups and the prompts "
            "nobody is tracking become this month's visibility targets."
        ),
        branches=ordered,
    )


def _reason_for(result: BranchResult, headline: TestResult | None) -> str:
    if headline is None:
        return f"{result.branch.value.title()} is failing."
    shown = headline.display or (
        f"{headline.value:.0f}%" if headline.value is not None else "—"
    )
    bar = (
        f"pass at {headline.pass_line:.0f}% or more"
        if headline.direction == "min"
        else f"pass at {headline.pass_line:.0f}% or less"
    )
    return f"{headline.metric_label}: {shown} — {bar}."
