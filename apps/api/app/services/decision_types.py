"""Shared Decision Engine datatypes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.models.decision import DiagnosticLayer


@dataclass
class LeverFinding:
    rule_key: str
    lever: str
    stage: DiagnosticLayer
    diagnosis: str
    recommended_action: str
    success_metric: str
    evidence_json: dict[str, Any]
    baseline_metrics_json: dict[str, Any]
    impact: float
    confidence: float
    urgency: float
    effort: float
    priority_score: float
    page_url: str | None = None
    query: str | None = None
    is_recommended_action: bool = False
    promotion_blocked_reason: str | None = None
    priority_band: str = "none"
    priority_band_reason: str | None = None
    severity: float | None = None
    finding_group_key: str | None = None
    #: Work the plan already covers every month, so it is reported rather than
    #: queued for the flexible Growth Action capacity a client actually buys.
    core_work: bool = False
    #: Set when a higher gate failed and this finding cannot be trusted or
    #: acted on until that is fixed.
    suppressed_by: str | None = None
    #: How many times this client's team has dismissed this kind of
    #: suggestion. Past the retirement count the rule is the problem.
    override_count: int = 0


@dataclass
class LeverSummary:
    lever: str
    label: str
    findings_count: int
    recommended_actions_count: int
    status: str


@dataclass
class DiagnoseResult:
    ready: bool
    message: str | None
    readiness: dict[str, bool]
    formula: str
    requested_from: date | None = None
    requested_to: date | None = None
    analysis_from: date | None = None
    analysis_to: date | None = None
    partial_message: str | None = None
    #: The last day each source has facts for. A boolean readiness flag says
    #: a source reported; it cannot say that Search Console stopped a
    #: fortnight ago while GA4 is current, which is the difference between
    #: a run worth reading and one worth re-syncing first.
    source_freshness: dict[str, str | None] = field(default_factory=dict)
    levers: list[LeverSummary] = field(default_factory=list)
    findings: list[LeverFinding] = field(default_factory=list)
    #: What can spend the client's monthly allowance, ranked.
    growth_actions: list[LeverFinding] = field(default_factory=list)
    #: Which of visibility / traffic / conversion is holding this client
    #: back this month. None when no rung had the inputs to be read.
    constraint: Any | None = None
    #: What has to be fixed before the rest can be trusted. A failed gate
    #: suppresses everything under it, and an empty plan with no reason
    #: given reads as a broken tool rather than a broken tag.
    blocking_findings: list[LeverFinding] = field(default_factory=list)
    #: Valued, and under the floor. Shown so the floor can be argued with.
    below_floor_actions: list[LeverFinding] = field(default_factory=list)
    #: Actions the valuer could not price, which is a bug worth seeing.
    unvalued_actions: list[LeverFinding] = field(default_factory=list)
    search_opportunities: list[LeverFinding] = field(default_factory=list)
    #: Which rules ran this period and why the rest did not. "No findings"
    #: and "never looked" are different answers and must not share a row.
    coverage: list[dict[str, Any]] = field(default_factory=list)

    @property
    def findings_count(self) -> int:
        return len(self.findings)

    @property
    def recommended_actions_count(self) -> int:
        return len(self.growth_actions)

    @property
    def recommendations(self) -> list[LeverFinding]:
        """Backward-compatible alias."""
        return self.growth_actions
