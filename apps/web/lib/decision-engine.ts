export type LeverSummary = {
  lever: string;
  label: string;
  findings_count: number;
  recommended_actions_count: number;
  status: string;
};

export type Finding = {
  rule_key: string;
  lever: string;
  label: string;
  stage: string;
  diagnosis: string;
  recommended_action: string;
  success_metric: string;
  priority_score: number;
  impact: number;
  confidence: number;
  urgency: number;
  effort: number;
  severity?: number | null;
  page_url: string | null;
  query: string | null;
  evidence_json: Record<string, unknown>;
  is_recommended_action?: boolean;
  promotion_blocked_reason?: string | null;
  priority_band?: string;
  priority_band_reason?: string | null;
  /** UI-only: filled to meet tier Growth Action allowance (shown as Suggested growth action) */
  plan_fill?: boolean;
};

export type SearchOpportunity = {
  rule_key: string;
  page_url: string | null;
  query: string | null;
  topic: string | null;
  impressions: number | null;
  clicks: number | null;
  ctr_percent: number | null;
  average_position: number | null;
  page_type: string | null;
  opportunity_type: string;
  diagnosis: string;
};

export type DiagnoseResponse = {
  ready: boolean;
  message: string | null;
  readiness: Record<string, boolean>;
  formula: string;
  requested_from?: string | null;
  requested_to?: string | null;
  analysis_from?: string | null;
  analysis_to?: string | null;
  partial_message?: string | null;
  findings_count: number;
  recommended_actions_count: number;
  levers: LeverSummary[];
  findings: Finding[];
  recommended_actions: Finding[];
  search_opportunities?: SearchOpportunity[];
  content_planning_signals?: SearchOpportunity[];
  recommendations: Finding[];
};

const STAGE_LABELS: Record<string, string> = {
  visibility: "Visibility",
  traffic: "Traffic",
  conversion: "Outcomes",
};

const PROMOTION_BLOCKED_LABELS: Record<string, string> = {
  impact_below_threshold: "Estimated business impact below actionable threshold.",
  confidence_below_threshold: "Confidence below actionable threshold.",
  insufficient_business_signal: "Insufficient business signal for promotion.",
  page_ineligible: "Page is not eligible for Growth Actions.",
  opt_out_preferences: "Utility or preference page excluded from Growth Actions.",
};

const LEVER_STATUS_LABELS: Record<string, string> = {
  clear: "Clear",
  findings: "Findings",
  insufficient_data: "Insufficient data",
  source_not_connected: "Source not connected",
  stale_data: "Stale data",
};

export function normalizeDiagnoseResponse(data: DiagnoseResponse): DiagnoseResponse {
  const searchOpportunities =
    data.search_opportunities ??
    data.content_planning_signals ??
    [];
  return {
    ...data,
    search_opportunities: searchOpportunities,
  };
}

export function stageLabel(stage: string): string {
  return STAGE_LABELS[stage] ?? stage;
}

export function leverStatusLabel(status: string): string {
  return LEVER_STATUS_LABELS[status] ?? status.replaceAll("_", " ");
}

export function promotionBlockedLabel(reason: string | null | undefined): string {
  if (!reason) return "Not promoted for this period.";
  return PROMOTION_BLOCKED_LABELS[reason] ?? reason.replaceAll("_", " ");
}

export function formatPriorityBand(band: string | undefined): string | null {
  if (band === "high") return "High";
  if (band === "medium") return "Medium";
  if (band === "low") return "Low";
  return null;
}

export function findingSubject(item: Finding): string {
  return item.page_url ?? item.query ?? item.diagnosis;
}

export function formatEvidence(evidence: Record<string, unknown>): string {
  const parts: string[] = [];
  if (typeof evidence.position === "number") parts.push(`position ${evidence.position}`);
  if (typeof evidence.average_position === "number") {
    parts.push(`avg position ${evidence.average_position}`);
  }
  if (typeof evidence.inbound_internal_links === "number") {
    parts.push(`${evidence.inbound_internal_links} inbound links (floor ${evidence.link_floor ?? "—"})`);
  }
  if (typeof evidence.impressions === "number") {
    parts.push(`${evidence.impressions.toLocaleString()} impressions`);
  }
  if (typeof evidence.lead_rate_change_pct === "number") {
    parts.push(`lead rate ${evidence.lead_rate_change_pct}%`);
  }
  if (typeof evidence.sessions_change_pct === "number") {
    parts.push(`sessions ${evidence.sessions_change_pct}%`);
  }
  if (evidence.tracking_validated) parts.push("tracking-validated");
  if (typeof evidence.ctr_percent === "number" && typeof evidence.expected_ctr_percent === "number") {
    parts.push(`CTR ${evidence.ctr_percent}% vs expected ${evidence.expected_ctr_percent}%`);
    if (typeof evidence.recoverable_clicks === "number") {
      parts.push(`~${evidence.recoverable_clicks} recoverable clicks`);
    }
  }
  if (typeof evidence.page_type === "string") parts.push(`page type ${evidence.page_type}`);
  return parts.join(" · ");
}

export function impactExplanation(evidence: Record<string, unknown>): string[] {
  const lines = evidence.impact_explanation;
  return Array.isArray(lines) ? lines.filter((line): line is string => typeof line === "string") : [];
}

export function scoreBar(value: number): string {
  return `${Math.max(0, Math.min(100, value))}%`;
}

export function formatNum(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(digits);
}

export const GROWTH_ACTION_FILTERS: { value: string; label: string }[] = [
  { value: "all", label: "All Growth Actions" },
  { value: "internal_linking", label: "Internal Linking" },
  { value: "technical_seo", label: "Technical SEO" },
  { value: "serp_ctr", label: "SERP CTR" },
  { value: "structured_data_ai", label: "Search & AI Visibility" },
  { value: "conversion_path", label: "Conversion Path" },
];

export function growthActionLabel(lever: string): string {
  return GROWTH_ACTION_FILTERS.find((row) => row.value === lever)?.label ?? lever.replaceAll("_", " ");
}

/**
 * Surface at least `planMin` recommendations by filling from additional findings
 * sorted by existing priority_score — no score inflation.
 */
export function applyPlanMinimum(
  recommended: Finding[],
  additional: Finding[],
  planMin: number,
): Finding[] {
  if (planMin <= 0 || recommended.length >= planMin) return recommended;
  const used = new Set(recommended.map((item) => item.rule_key));
  const fillers = [...additional]
    .filter((item) => !used.has(item.rule_key))
    .sort((a, b) => b.priority_score - a.priority_score)
    .slice(0, planMin - recommended.length)
    .map((item) => ({ ...item, is_recommended_action: true, plan_fill: true }));
  return [...recommended, ...fillers];
}

export type StoredDecision = {
  id: string;
  rule_key: string;
  status: string;
  growth_action: string | null;
  page_url: string | null;
  dismissal_reason?: string | null;
};

export function decisionStatusLabel(status: string): string {
  switch (status) {
    case "new":
      return "New";
    case "reviewed":
      return "Reviewed";
    case "accepted":
      return "Accepted";
    case "dismissed":
      return "Dismissed";
    case "task_created":
      return "Task created";
    case "completed":
      return "Completed";
    case "measuring":
      return "Measuring";
    case "validated":
      return "Validated";
    default:
      return status.replaceAll("_", " ");
  }
}

export function decisionStatusBadgeVariant(
  status: string,
): "neutral" | "success" | "warning" | "accent" {
  switch (status) {
    case "accepted":
    case "completed":
    case "validated":
      return "success";
    case "dismissed":
      return "warning";
    case "task_created":
    case "measuring":
      return "accent";
    case "reviewed":
    case "new":
      return "neutral";
    default:
      return "neutral";
  }
}

