"""Decision 3 — fill the plan's slots, and say what the empty ones mean.

The plan sets the number: Launch and legacy 1, Lift 3, Lead 5, Enterprise 5
or more. Never exceeded, never padded.

Slots fill from the constraint's targets in score order. Leftovers go to the
next **failing** branch, flagged as spillover. A branch that passes or is
blocked cannot take a slot — passing because there is nothing wrong with it,
blocked because we could not tell. That is the rule the old engine broke most
visibly: it ranked every finding together and handed slots to branches that
were fine, so a client with healthy traffic got traffic work.

One action per URL per month. Three findings on one page is one job, and
three cards is how a month's plan gets spent on an afternoon's work.

When the failing branches together have fewer qualifying targets than slots,
the plan is short and says so. Filling the gap with the next-best thing is
how a plan stops meaning anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.decisions.triage import Branch, BranchResult, Status

#: Upstream first, which is also the order spillover walks.
LADDER: tuple[Branch, ...] = (Branch.VISIBILITY, Branch.TRAFFIC, Branch.LEADS)


@dataclass(frozen=True)
class Prescription:
    """One action, ready for a slot."""

    action_id: str
    title: str
    branch: Branch
    target_url: str
    term: str | None
    score: float
    effort_min: int
    why: str
    done_when: str
    metric: str
    evidence: tuple[str, ...] = field(default_factory=tuple)
    flags: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class FilledSlot:
    slot: int
    prescription: Prescription
    spillover: bool


@dataclass(frozen=True)
class EmptySlot:
    slot: int
    reason: str


@dataclass(frozen=True)
class Plan:
    filled: tuple[FilledSlot, ...]
    empty: tuple[EmptySlot, ...]
    #: Candidates that did not get a slot, and why. The page shows these as
    #: "Not this month" so a passing branch's work is visible without
    #: competing for the month.
    not_this_month: tuple[dict[str, Any], ...] = field(default_factory=tuple)


def _branch_status(branches: list[BranchResult], branch: Branch) -> Status | None:
    found = next((b for b in branches if b.branch is branch), None)
    return found.status if found else None


def fill_slots(
    *,
    slots: int,
    constraint: Branch | None,
    branches: list[BranchResult],
    prescriptions_by_branch: dict[Branch, list[Prescription]],
) -> Plan:
    """Fill the month's slots, constraint first, spilling to failing branches.

    `prescriptions_by_branch` is already in score order — Decision 2 ranked
    it. This decides who gets a slot, not what is worth doing.
    """
    if slots <= 0:
        return Plan(filled=(), empty=(), not_this_month=())

    # The constraint first, then the other failing branches down the ladder.
    order: list[Branch] = []
    if constraint is not None and _branch_status(branches, constraint) is Status.FAIL:
        order.append(constraint)
    for branch in LADDER:
        if branch in order:
            continue
        if _branch_status(branches, branch) is Status.FAIL:
            order.append(branch)

    filled: list[FilledSlot] = []
    used_urls: set[str] = set()
    skipped: list[dict[str, Any]] = []

    for branch in order:
        for prescription in prescriptions_by_branch.get(branch, []):
            if len(filled) >= slots:
                break
            url = (prescription.target_url or "").rstrip("/").lower()
            if url and url in used_urls:
                # One action per URL per month. Three findings on one page is
                # one job.
                skipped.append(
                    {
                        "id": prescription.action_id,
                        "title": prescription.title,
                        "branch": branch.value,
                        "branch_status": Status.FAIL.value,
                        "target_url": prescription.target_url,
                        "reason": (
                            "Another action this month already takes this page, "
                            "and one page is one job."
                        ),
                    }
                )
                continue
            used_urls.add(url)
            filled.append(
                FilledSlot(
                    slot=len(filled) + 1,
                    prescription=prescription,
                    spillover=branch is not constraint,
                )
            )
        if len(filled) >= slots:
            break

    # Everything in a branch that cannot take a slot. Shown, not hidden: a
    # passing branch's candidates are real work, they are simply not this
    # month's work.
    for branch in LADDER:
        status = _branch_status(branches, branch)
        if status is Status.FAIL:
            continue
        for prescription in prescriptions_by_branch.get(branch, []):
            skipped.append(
                {
                    "id": prescription.action_id,
                    "title": prescription.title,
                    "branch": branch.value,
                    "branch_status": status.value if status else "blocked",
                    "target_url": prescription.target_url,
                    "reason": (
                        f"{branch.value.title()} passes, so it cannot take a slot "
                        "this month."
                        if status is Status.PASS
                        else f"{branch.value.title()} could not be judged, so it "
                        "cannot take a slot this month."
                    ),
                }
            )

    empty = tuple(
        EmptySlot(slot=n, reason=_empty_reason(branches, order))
        for n in range(len(filled) + 1, slots + 1)
    )
    return Plan(filled=tuple(filled), empty=empty, not_this_month=tuple(skipped))


def _empty_reason(branches: list[BranchResult], order: list[Branch]) -> str:
    """Why this slot is empty, in terms of the branches rather than counts.

    "No qualifying target" is true and useless. Which branches could have
    filled it, and what stopped them, is the thing that tells someone whether
    to go and fix an input.
    """
    if not order:
        blocked = [
            b.branch.value for b in branches if b.status is Status.BLOCKED
        ]
        if blocked:
            return (
                "No branch is failing, and "
                + ", ".join(blocked)
                + " could not be judged, so nothing qualifies for a slot."
            )
        return "No branch is failing, so there is nothing to prescribe against."

    names = ", ".join(b.value for b in order)
    blocked = [b.branch.value for b in branches if b.status is Status.BLOCKED]
    tail = (
        f" {', '.join(blocked).title()} is blocked, so it cannot take this slot."
        if blocked
        else ""
    )
    return (
        f"No qualifying target left in a failing branch ({names}). "
        "The slot stays empty rather than being filled with weaker work." + tail
    )
