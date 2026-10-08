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
  /** The last day each source has facts for, keyed as `readiness` is. */
  source_freshness?: Record<string, string | null>;
  findings_count: number;
  recommended_actions_count: number;
  levers: LeverSummary[];
  findings: Finding[];
  /** The month's growth actions, ranked by the engine. */
  growth_actions?: Finding[];
  below_floor_actions?: Finding[];
  unvalued_actions?: Finding[];
  search_opportunities?: SearchOpportunity[];
  content_planning_signals?: SearchOpportunity[];
  recommendations: Finding[];
};

const STAGE_LABELS: Record<string, string> = {
  visibility: "Visibility",
  traffic: "Traffic",
  conversion: "Outcomes",
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

export type FindingAction = {
  text: string;
  target?: string;
  detail?: string;
  human?: boolean;
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

export const SOURCE_LABELS: Record<string, string> = {
  search_console: "Search Console",
  analytics: "GA4 conversions",
  crawl_audit: "Site crawl",
  ai_visibility: "AI visibility",
};

/** Everything the card needs to show how a measured estimate was built. */
export type ValueDerivation = { label: string; value: string }[];

export function valueDerivation(finding: Finding): ValueDerivation {
  const evidence = finding.evidence_json ?? {};
  const rows: ValueDerivation = [];
  const sessions = numberField(evidence, "sessions");
  const leads = numberField(evidence, "leads");
  const benchmark = numberField(evidence, "benchmark_rate_pct");
  const shortfall = numberField(evidence, "shortfall_leads");
  const reliability = numberField(evidence, "reliability_prior");

  if (sessions !== null) rows.push({ label: "Organic sessions", value: formatNum(sessions, 0) });
  if (leads !== null) rows.push({ label: "Leads from them", value: formatNum(leads, 0) });
  if (benchmark !== null) {
    const source = stringField(evidence, "benchmark_source");
    rows.push({
      label: source && source !== "site" ? `${source} pages convert at` : "Site converts at",
      value: `${benchmark.toFixed(2)}%`,
    });
  }
  if (shortfall !== null) rows.push({ label: "Shortfall", value: formatNum(shortfall, 2) });
  if (reliability !== null && reliability !== 1) {
    rows.push({ label: "Discounted for a claim not yet observed", value: `×${reliability}` });
  }
  return rows;
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
