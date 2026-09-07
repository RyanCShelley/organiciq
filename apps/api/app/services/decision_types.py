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
    levers: list[LeverSummary] = field(default_factory=list)
    findings: list[LeverFinding] = field(default_factory=list)
    recommended_actions: list[LeverFinding] = field(default_factory=list)
    search_opportunities: list[LeverFinding] = field(default_factory=list)

    @property
    def findings_count(self) -> int:
        return len(self.findings)

    @property
    def recommended_actions_count(self) -> int:
        return len(self.recommended_actions)

    @property
    def recommendations(self) -> list[LeverFinding]:
        """Backward-compatible alias."""
        return self.recommended_actions
