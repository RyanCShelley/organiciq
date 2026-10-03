"""What to do, not what we found.

A finding that says "review traffic and UX" has moved the work from the
engine to the person reading it, which is the opposite of the point. The
reports already answer the gates — whether leads are down, whether a page
slipped. The engine exists to say what to do about it.

So every finding carries a `Prescription`: the cause the checks settled on,
the evidence that decided it, one to three steps specific enough to act on
without opening another tab, and the metric and date that will say whether
it worked.

`UNDETERMINED` is allowed and is not an escape hatch — it still has to
carry a named experiment or a specific human check. "Review it" is not a
cause and is not a step.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: The cause a lever's decision tree settled on. One enum across all levers:
#: routing sends a finding from one lever to another, and a cause that only
#: made sense inside its original lever would not survive the trip.
CAUSES: dict[str, str] = {
    # Tracking (playbook 1)
    "analytics_tag_broken": "The analytics tag stopped firing site-wide",
    "conversion_event_broken": "Sessions are normal and the lead event is not firing",
    "form_broken": "The form itself is not submitting",
    "partial_tracking_break": "One form or template stopped while the rest convert",
    # Converting page dropped (playbook 2)
    "sessions_fell": "The page lost traffic, so the drop is search, not the page",
    "traffic_mix_shifted": "The same page is getting lower-intent visitors",
    "mobile_regression": "Mobile converts far below desktop, or fell on its own",
    "page_changed": "The page itself changed",
    "speed_regression": "The page got materially slower",
    # Site conversion (playbook 3)
    "drop_concentrated": "Most of the lost leads are on one page group",
    "drop_sitewide": "The drop is even across segments, so something global changed",
    "behind_plan": "Nothing fell; the site has never converted at the level the plan needs",
    "seasonal": "The same dip happened a year ago",
    "spam_filtered": "Lead count fell while qualified leads held",
    # Decay routing (playbook 5)
    "ctr_loss": "Impressions held and clicks fell, so the listing lost the click",
    "true_decay": "Impressions and rankings both fell",
    "demand_fell": "Rankings held and search demand fell",
    "self_competition": "Another of our URLs took the queries",
    # Keyword not ranking (playbook 7)
    "no_page_for_term": "Nothing on the site targets the term",
    "page_cannot_rank": "A page exists and something stops it ranking",
    "page_not_competitive": "The page can rank and is being beaten",
    # Prompt not cited (playbook 8)
    "ai_crawlers_blocked": "Answer engines are not allowed to fetch the site",
    "no_page_answers_prompt": "No page answers the question",
    "page_not_quotable": "A page answers it in a form an engine cannot quote",
    # Internal linking (playbook 6)
    "under_linked_donors_found": "Pages that share its subject do not link to it",
    "under_linked_no_donor": "Nothing on the site shares its subject",
    # Always available
    "undetermined": "The checks did not settle on a cause",
}


@dataclass(frozen=True)
class Step:
    """One thing to do, specific enough to do it.

    `target` is the URL or form the step applies to. `detail` carries the
    text to write, the element to change, or the check to run — whatever
    makes the step actionable without going and working it out again.
    """

    text: str
    target: str | None = None
    detail: str | None = None
    human: bool = False

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"text": self.text, "human": self.human}
        if self.target:
            out["target"] = self.target
        if self.detail:
            out["detail"] = self.detail
        return out


@dataclass
class Prescription:
    cause: str
    evidence: dict[str, Any] = field(default_factory=dict)
    steps: list[Step] = field(default_factory=list)
    expected_impact: str | None = None
    verify_metric: str | None = None
    verify_after_days: int = 28
    #: Set when a lever hands the finding to another lever, so the card can
    #: say where it went rather than silently disappearing.
    routed_to: str | None = None

    def __post_init__(self) -> None:
        if self.cause not in CAUSES:
            raise ValueError(f"unknown cause: {self.cause!r}")
        if not self.steps:
            raise ValueError(f"{self.cause}: a prescription with no steps is a diagnosis")
        for step in self.steps:
            lowered = step.text.strip().lower()
            # The whole point. A step that says "review" has handed the work
            # back to the reader.
            if lowered.startswith(("review", "look at", "investigate", "consider ")):
                raise ValueError(f"step is not an action: {step.text!r}")

    @property
    def summary(self) -> str:
        return CAUSES[self.cause]

    def as_dict(self) -> dict[str, Any]:
        return {
            "cause": self.cause,
            "cause_summary": self.summary,
            "evidence": self.evidence,
            "actions": [step.as_dict() for step in self.steps],
            "expected_impact": self.expected_impact,
            "verify_metric": self.verify_metric,
            "verify_after_days": self.verify_after_days,
            "routed_to": self.routed_to,
        }

    def action_text(self) -> str:
        """The steps as one readable instruction, for the existing card."""
        if len(self.steps) == 1:
            step = self.steps[0]
            return step.text if not step.detail else f"{step.text} {step.detail}"
        return " ".join(
            f"{index}. {step.text}" + (f" {step.detail}" if step.detail else "")
            for index, step in enumerate(self.steps, start=1)
        )
