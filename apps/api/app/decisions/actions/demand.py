"""How many people an action is about, counted in its outcome's own unit.

Actions used to be priced in expected leads a month. Three of them had no
clicks-to-leads model at all and carried a flat credit instead, so every
tracked prompt was worth 0.15 leads by fiat — twenty-five identical numbers
at the top of the ledger, presented as a ranking. What actually ordered them
was the search volume hidden in the tie-break, and the lead figure was
decoration over it.

The engine measures three outcomes, so it counts in three units and converts
between none of them:

* **visibility** — searches. The volume behind a prompt nothing cites; the
  impressions a page already draws from a position too low to be clicked.
* **traffic** — clicks. What the measured CTR curve says the ranking would
  earn at its target position and does not earn now.
* **conversion** — sessions. The people who arrive on the page.

All three are counted rather than forecast. Nothing is multiplied by a lead
rate to reach a common currency, because the common currency was the
invention: a site-wide rate applied to one page's clicks predicts that
page's leads only if that page converts like the site, which is the thing
nobody checked.

Ordering across layers is not this module's job. The constraint decides
which outcome the month is about, and the layers follow it; within a layer
these counts decide.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from app.decisions.constraint import Layer

#: What each outcome counts. Reaches the column heading and the card, so a
#: reader never has to ask what the number on a row is.
DEMAND_UNIT: dict[str, str] = {
    Layer.VISIBILITY.value: "searches / mo",
    Layer.TRAFFIC.value: "clicks / mo",
    Layer.CONVERSION.value: "sessions / mo",
}

#: Actions that unblock a whole site rather than improve one page. They have
#: no demand of their own — an engine that cannot fetch the site will not
#: cite any page on it — so they sort ahead of everything in their layer
#: instead of being handed a number to sort by.
PRECONDITION_RULES = frozenset({"ai_crawlers_unblock", "5a"})

#: How long each action takes. Estimates, not measurements — and the cap
#: that makes an action an action lives here, enforced by a test.
DEFAULT_MINUTES: dict[str, int] = {
    "1a": 45,
    "1b": 15,
    "2a": 30,
    "2c": 45,
    "3a": 45,
    "3b": 60,
    "6": 45,
    "5a": 45,
    "ai_crawlers_unblock": 15,
}

GROWTH_ACTION_MAX_MINUTES = 60


@dataclass(frozen=True)
class ActionDemand:
    """What an action is about, and how long it takes."""

    rule_id: str
    layer: str
    #: In `unit`, per month. None when the source has no number for this
    #: one, which is not the same as nobody wanting it: SE Ranking returns
    #: no volume on prompts, and where no tracked term is close enough to
    #: stand in, the honest answer is that we cannot size it. Zero for a
    #: precondition, which does not rank on size.
    demand: float | None
    unit: str
    estimated_minutes: int
    #: measured | inferred | estimated. Describes where the count came
    #: from and never alters it — an engine that discounts an estimate in
    #: the number *and* labels it an estimate has discounted it twice.
    evidence_label: str
    precondition: bool = False

    @property
    def known(self) -> bool:
        return self.demand is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "demand": None if self.demand is None else round(self.demand, 1),
            "demand_unit": self.unit,
            "estimated_minutes": self.estimated_minutes,
            "evidence_label": self.evidence_label,
            **({"precondition": True} if self.precondition else {}),
        }


def monthly_from_window(counted: float, window_days: int) -> float:
    """A window's count, restated per month.

    Windows are not months — the analysis period is whatever Search Console
    could serve — so comparing a 28-day count against a 30-day one would
    rank by how much data arrived rather than by how many people the work
    is about.
    """
    if window_days <= 0:
        return 0.0
    return float(counted) * 30.0 / float(window_days)


def demand_for(
    rule_id: str,
    *,
    layer: str,
    thresholds: Mapping[str, Any],
    window_days: int,
    counted_in_window: float | None = None,
    counted_monthly: float | None = None,
    known: bool = True,
    evidence_label: str = "estimated",
) -> ActionDemand:
    """How many people this action is about, per month.

    `counted_in_window` is a count over the analysis period — impressions,
    recoverable clicks, sessions — and is restated per month.
    `counted_monthly` is already a monthly figure, which search volume is,
    and passes through untouched.

    `known=False` says the rule looked and the source had no number. The
    action is real and cannot be sized, so it ranks last in its layer and
    the card says so rather than printing a zero that would read as "nobody
    is asking this".
    """
    precondition = rule_id in PRECONDITION_RULES
    monthly: float | None
    if precondition:
        monthly = 0.0
    elif not known:
        monthly = None
    elif counted_monthly is not None:
        monthly = float(counted_monthly)
    elif counted_in_window is not None:
        monthly = monthly_from_window(counted_in_window, window_days)
    else:
        raise ValueError(f"{rule_id} has no count and is not a precondition")

    return ActionDemand(
        rule_id=rule_id,
        layer=layer,
        demand=monthly,
        unit=DEMAND_UNIT.get(layer, "people / mo"),
        estimated_minutes=_minutes(rule_id, thresholds),
        evidence_label=evidence_label,
        precondition=precondition,
    )


def _minutes(rule_id: str, thresholds: Mapping[str, Any]) -> int:
    configured = thresholds.get("estimated_minutes")
    if isinstance(configured, dict) and rule_id in configured:
        return int(configured[rule_id])
    return DEFAULT_MINUTES.get(rule_id, GROWTH_ACTION_MAX_MINUTES)
