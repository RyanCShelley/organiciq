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
  /** Upkeep the plan covers every month — reported, never spends an action. */
  core_work?: boolean;
  /** Rule key of the gate that failed; this finding cannot be trusted yet. */
  suppressed_by?: string | null;
  /** Times this team has dismissed this kind of suggestion. */
  override_count?: number;
  priority_band?: string;
  priority_band_reason?: string | null;
  /** UI-only: optional alternative surfaced when hard recommendations are below the plan allowance */
  is_suggested?: boolean;
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
  /** Tracked SE Ranking keywords already ranking on this page. */
  tracked_keywords: number;
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

/**
 * Badges, not sentences.
 *
 * "Estimated business impact below actionable threshold." was the chip on
 * twenty rows at once, which is a paragraph repeated down a column. The
 * reason belongs in the hint underneath, where it is read once.
 */
const PROMOTION_BLOCKED_LABELS: Record<string, string> = {
  impact_below_threshold: "Too small",
  confidence_below_threshold: "Low confidence",
  insufficient_business_signal: "Not enough data",
  page_ineligible: "Page excluded",
  opt_out_preferences: "Page excluded",
};

export const PROMOTION_BLOCKED_HINTS: Record<string, string> = {
  impact_below_threshold:
    "Worth less than the threshold this period, so it does not spend a growth action.",
  confidence_below_threshold:
    "The evidence behind the number is too thin to act on yet.",
  insufficient_business_signal:
    "Not enough traffic or leads on this page for the comparison to mean anything.",
  page_ineligible: "This page is not eligible for Growth Actions.",
  opt_out_preferences:
    "A utility or preference page, excluded from Growth Actions.",
};

export function promotionBlockedHint(reason: string | null | undefined): string | undefined {
  return reason ? PROMOTION_BLOCKED_HINTS[reason] : undefined;
}

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

/**
 * How a finding should read on screen.
 *
 * Three states the old UI collapsed into one amber "not promoted" chip:
 * work the plan already covers, work that cannot be judged until a gate is
 * cleared, and work that simply did not score high enough this period. They
 * call for different responses, so they should not look the same.
 */
export type FindingState =
  | "recommended"
  | "suggested"
  | "core-work"
  | "blocked"
  | "retired"
  | "deferred";

export function findingState(
  item: Finding,
  recommendedKeys: Set<string>,
  suggestedKeys: Set<string>,
): FindingState {
  // A gate failing outranks everything: the score behind any other state was
  // computed from data the gate says is wrong.
  if (item.suppressed_by) return "blocked";
  // Three dismissals across different pages: the rule is what needs changing,
  // and that is a different message from "not important enough this month".
  if ((item.override_count ?? 0) >= 3) return "retired";
  if (recommendedKeys.has(item.rule_key) || item.is_recommended_action) return "recommended";
  if (item.core_work) return "core-work";
  if (suggestedKeys.has(item.rule_key) || item.is_suggested) return "suggested";
  return "deferred";
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
    // The number the rule actually compared against the floor. Printing the
    // total here put "475 inbound links (floor 6)" under the word
    // "under-linked", which reads as nonsense — the floor is editorial links
    // only, and navigation makes up most of the total.
    const counted =
      typeof evidence.inbound_links_counted === "number"
        ? evidence.inbound_links_counted
        : evidence.inbound_internal_links;
    const basis = evidence.inbound_links_basis === "editorial" ? "editorial " : "";
    parts.push(`${counted} ${basis}inbound links (floor ${evidence.link_floor ?? "—"})`);
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

export type FindingAction = {
  text: string;
  target?: string;
  detail?: string;
  human?: boolean;
};

export type ScoreTerm = {
  name: string;
  value: number;
  weight: number;
  contribution: number;
  scaled_by_impact: boolean;
};

export type ScoreBreakdown = {
  terms: ScoreTerm[];
  impact_relevance: number;
  impact_relevance_scale: number;
  total: number;
};

/** The prescribed steps, as steps. */
export function findingActions(evidence: Record<string, unknown>): FindingAction[] {
  const actions = evidence.actions;
  if (!Array.isArray(actions)) return [];
  return actions.filter(
    (row): row is FindingAction =>
      typeof row === "object" && row !== null && typeof (row as FindingAction).text === "string",
  );
}

export function scoreBreakdown(
  evidence: Record<string, unknown>,
): ScoreBreakdown | null {
  const value = evidence.score_breakdown;
  if (typeof value !== "object" || value === null) return null;
  const breakdown = value as ScoreBreakdown;
  return Array.isArray(breakdown.terms) ? breakdown : null;
}

export function stringField(
  evidence: Record<string, unknown>,
  key: string,
): string | null {
  const value = evidence[key];
  return typeof value === "string" && value.trim() ? value : null;
}

export function numberField(
  evidence: Record<string, unknown>,
  key: string,
): number | null {
  const value = evidence[key];
  return typeof value === "number" && !Number.isNaN(value) ? value : null;
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

export type StoredDecision = {
  id: string;
  rule_key: string;
  status: string;
  growth_action: string | null;
  page_url: string | null;
  dismissal_reason?: string | null;
};

/** Expected leads a month, for actions valued in that unit. */
export function expectedLeadsMonthly(finding: Finding): number | null {
  const value = finding.evidence_json?.expected_leads_monthly;
  return typeof value === "number" ? value : null;
}

/**
 * The month's actions, best first.
 *
 * Growth actions are valued in expected leads per month, so that is what
 * orders them. `priority_score` is the old 0–100 scale and still ranks the
 * report-only work, which has no lead value — sorting everything by it put
 * a finding worth 0.63 leads below one worth nothing.
 *
 * Nothing is truncated to the plan allowance. The allowance says how many
 * are included this month, not how many are worth knowing about: a Launch
 * client with two good actions should see both and choose.
 */
export function rankActions(findings: Finding[]): Finding[] {
  return [...findings].sort((a, b) => {
    const aLeads = expectedLeadsMonthly(a);
    const bLeads = expectedLeadsMonthly(b);
    if (aLeads !== null && bLeads !== null) {
      if (bLeads !== aLeads) return bLeads - aLeads;
      // Every prompt action carries the same flat credit, so without this
      // the order among them is whatever the database returned.
      const aTie = Number(a.evidence_json?.tiebreak_volume ?? 0);
      const bTie = Number(b.evidence_json?.tiebreak_volume ?? 0);
      if (bTie !== aTie) return bTie - aTie;
    } else if (aLeads !== null) {
      return -1;
    } else if (bLeads !== null) {
      return 1;
    }
    return b.priority_score - a.priority_score;
  });
}

/**
 * When hard recommendations are below the growth-plan allowance, surface additional
 * findings as suggested alternatives (sorted by priority_score — no score inflation).
 */
export function applySuggestedAlternatives(
  recommended: Finding[],
  additional: Finding[],
  allowance: number,
): Finding[] {
  if (allowance <= 0 || recommended.length >= allowance) return [];
  const used = new Set(recommended.map((item) => item.rule_key));
  return [...additional]
    .filter((item) => !used.has(item.rule_key))
    .sort((a, b) => b.priority_score - a.priority_score)
    .slice(0, allowance - recommended.length)
    .map((item) => ({ ...item, is_suggested: true }));
}

const SELECTED_TOWARD_PLAN_STATUSES = new Set([
  "accepted",
  "task_created",
  "completed",
  "measuring",
  "validated",
]);

export function countSelectedTowardPlan(decisions: StoredDecision[]): number {
  return decisions.filter((row) => SELECTED_TOWARD_PLAN_STATUSES.has(row.status)).length;
}

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

