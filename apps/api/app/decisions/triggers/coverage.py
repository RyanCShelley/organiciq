"""Whether each rule ran, and why not.

"No findings" is two different statements. One says the site is fine on
that dimension; the other says we never looked. Reporting them the same
way is how a client with no crawl data reads as a client with no problems.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SkipReason(str, Enum):
    NO_QUERY_PAGE_DATA = "no_query_page_data"
    CRAWL_NOT_READY = "crawl_not_ready"
    PAGE_NOT_CRAWLED = "page_not_crawled"
    INSUFFICIENT_BASELINE = "insufficient_baseline"
    NO_GSC_DATA = "no_gsc_data"
    NO_CONVERSION_DATA = "no_conversion_data"
    NO_PAGES_IN_GATE = "no_pages_in_gate"
    NO_RULE_MATCHED = "no_rule_matched"
    #: The source itself never reported, so every rule reading it is
    #: quiet. Distinct from a rule that ran and found nothing.
    SOURCE_MISSING = "source_missing"
    #: No site lead rate, so there is no honest way to turn recoverable
    #: clicks into leads. A missing input, not a rule that found nothing.
    NO_LEAD_RATE = "no_lead_rate"
    #: 1c needs how far down the page people get. Nothing measures it yet,
    #: so the rule is paused rather than guessed at from views/sessions,
    #: which is zero on a quarter of SMA's rows.
    NO_DEPTH_DATA = "no_depth_data"


@dataclass
class RuleCoverage:
    rule_id: str
    ran: bool
    skipped: SkipReason | None = None
    findings: int = 0
    #: Anything worth knowing that is not a finding: how many pages entered
    #: a gate, which pairs were found and not emitted, and so on.
    notes: dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "status": "ran" if self.ran else f"skipped:{self.skipped.value if self.skipped else '?'}",
            "findings": self.findings,
            **({"notes": self.notes} if self.notes else {}),
        }


@dataclass
class Coverage:
    """Collected across one `diagnose()` run."""

    rules: dict[str, RuleCoverage] = field(default_factory=dict)

    def ran(self, rule_id: str, findings: int = 0, **notes: object) -> None:
        self.rules[rule_id] = RuleCoverage(
            rule_id=rule_id, ran=True, findings=findings, notes=dict(notes)
        )

    def skipped(self, rule_id: str, reason: SkipReason, **notes: object) -> None:
        self.rules[rule_id] = RuleCoverage(
            rule_id=rule_id, ran=False, skipped=reason, notes=dict(notes)
        )

    def as_list(self) -> list[dict[str, object]]:
        return [self.rules[key].as_dict() for key in sorted(self.rules)]
