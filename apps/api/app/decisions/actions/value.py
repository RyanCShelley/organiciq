"""What an action is worth: expected leads per month.

The old scale was a share of the monthly lead goal, capped at a hundred,
discounted by an evidence tier and then weighed against urgency and
effort. Four transformations between "this page would produce 0.6 more
leads" and the number on the card, and the number on the card could not be
read back as leads by anyone.

So actions are valued in the unit the business uses. Going from 36 leads
to 37 is worth doing; nothing is penalised for being small, and the only
thing that removes an action is being worth less than a tenth of a lead a
month.

The evidence label — measured, inferred, estimated — rides along for
display and never touches the number. A reader can discount an estimate
themselves; an engine that discounts it twice, once in the tier and once
in the reader's head, is just lying quietly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

#: Actions with no honest clicks-to-leads model. The credit is a
#: placeholder whose only job is to order them sensibly against the search
#: actions until real outcomes replace it, and it is shown openly.
FLAT_CREDIT_RULES = frozenset({"6", "5a", "ai_crawlers_unblock"})


@dataclass(frozen=True)
class ActionValue:
    rule_id: str
    expected_leads_monthly: float
    raw_monthly_leads: float
    reliability_prior: float
    value_basis: str
    estimated_minutes: int
    evidence_label: str
    #: Separates actions that share a flat credit. Every prompt is worth
    #: the same credit by definition, so without this the top five of
    #: twenty is whichever order they came out of the database in.
    tiebreak: float = 0.0

    @property
    def above_floor(self) -> bool:
        return self._floor is None or self.expected_leads_monthly >= self._floor

    _floor: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "expected_leads_monthly": round(self.expected_leads_monthly, 3),
            "raw_monthly_leads": round(self.raw_monthly_leads, 3),
            "reliability_prior": self.reliability_prior,
            "value_basis": self.value_basis,
            "estimated_minutes": self.estimated_minutes,
            "evidence_label": self.evidence_label,
            **({"tiebreak_volume": self.tiebreak} if self.tiebreak else {}),
        }


def monthly_from_window(raw_leads_for_window: float, window_days: int) -> float:
    """A window's worth of leads, restated per month.

    Windows are not months — the analysis period is whatever Search
    Console could serve — so comparing a 28-day estimate with a 30-day one
    would rank by how much data arrived rather than by what the work is
    worth.
    """
    if window_days <= 0:
        return 0.0
    return float(raw_leads_for_window) * 30.0 / float(window_days)


def value_for(
    rule_id: str,
    *,
    thresholds: Mapping[str, Any],
    window_days: int,
    raw_leads_for_window: float | None = None,
    evidence_label: str = "estimated",
    tiebreak: float = 0.0,
) -> ActionValue:
    """The action's monthly lead value, before the floor is applied."""
    if rule_id in FLAT_CREDIT_RULES:
        raw_monthly = float(
            thresholds.get(f"flat_credit_{_credit_key(rule_id)}", 0.0) or 0.0
        )
        basis = "flat_credit"
    else:
        if raw_leads_for_window is None:
            raise ValueError(f"{rule_id} has no raw lead estimate and no flat credit")
        raw_monthly = monthly_from_window(raw_leads_for_window, window_days)
        basis = "estimated_incremental_leads"

    prior = float(
        thresholds.get(f"reliability_{rule_id}", thresholds.get("reliability_default", 1.0))
    )
    minutes = int(_minutes(rule_id, thresholds))
    return ActionValue(
        rule_id=rule_id,
        expected_leads_monthly=raw_monthly * prior,
        raw_monthly_leads=raw_monthly,
        reliability_prior=prior,
        value_basis=basis,
        estimated_minutes=minutes,
        evidence_label=evidence_label,
        tiebreak=tiebreak,
        _floor=float(thresholds.get("min_expected_leads_monthly", 0.1)),
    )


#: Flat-credit threshold keys read better with a name than an id.
_CREDIT_KEYS = {
    "6": "6_prompt_gap",
    "5a": "5a_entity_fix",
    "ai_crawlers_unblock": "ai_crawlers_unblock",
}

#: How long each action takes. Estimates, not measurements — and the cap
#: that makes an action an action lives here, enforced by a test.
DEFAULT_MINUTES: dict[str, int] = {
    "1a": 45,
    "1b": 15,
    "2a": 30,
    "2c": 45,
    "6": 45,
    "5a": 45,
    "ai_crawlers_unblock": 15,
}

GROWTH_ACTION_MAX_MINUTES = 60


def _credit_key(rule_id: str) -> str:
    return _CREDIT_KEYS.get(rule_id, rule_id)


def _minutes(rule_id: str, thresholds: Mapping[str, Any]) -> int:
    configured = thresholds.get("estimated_minutes")
    if isinstance(configured, dict) and rule_id in configured:
        return int(configured[rule_id])
    return DEFAULT_MINUTES.get(rule_id, GROWTH_ACTION_MAX_MINUTES)
