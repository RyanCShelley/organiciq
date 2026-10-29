export type Flag = {
  code: string;
  level: "blocker" | "warning" | "info";
  message: string;
  months: string[];
  acknowledged: boolean;
};

export type Range = { low: number; high: number; pct: number };

export type Checkpoint = {
  label: string;
  month: number;
  monthly_sessions: number;
  lead_rate_pct: number;
  monthly_leads: number;
};

export type SeriesMonth = {
  month: string;
  sessions: number;
  organic_sessions: number;
  leads: number;
  lead_rate_pct: number;
  in_window: boolean;
};

export type Analysis = {
  status: string;
  window: { from: string; to: string; months: number; regime_start: string | null; suggested_regime_start: string | null };
  baseline: { monthly_sessions: number; monthly_organic_sessions: number; lead_rate_pct: number; monthly_leads: number };
  ranges: Record<string, Range | string>;
  goal_basis: { monthly_sessions: number; monthly_leads: number; lead_rate_pct: number; basis: string };
  projection: {
    plan_label: string;
    suggested_monthly_lead_goal: number;
    goal_horizon_months: number;
    checkpoints: Checkpoint[];
    disclaimer: string;
  };
  series: SeriesMonth[];
  flags: Flag[];
  blockers: unknown[];
  can_lock: boolean;
  source: { type: string; lead_events: string[]; notes: string[] };
};

export type BaselineVersion = {
  version: number;
  status: string;
  reason_code: string;
  reason_note: string | null;
  locked_by: string;
  locked_at: string | null;
  window_from: string;
  window_to: string;
  lead_events: string[];
  monthly_sessions: number | null;
  monthly_organic_sessions: number | null;
  monthly_leads: number | null;
  goal_monthly_leads: number | null;
};

export type AnalysisResult = { ok: true; analysis: Analysis } | { ok: false; error: string };

export const REBASELINE_REASONS = [
  { value: "relaunch", label: "The site was relaunched or migrated" },
  { value: "tracking_change", label: "Tracking changed" },
  { value: "definition_change", label: "What counts as a conversion changed" },
  { value: "correction", label: "The earlier baseline was wrong" },
] as const;

/** What a client's conversions are called: orders for a shop, leads for a service business. */
export function conversionNoun(model: string | null | undefined): { plural: string; singular: string } {
  if (model === "ecommerce") return { plural: "orders", singular: "order" };
  if (model === "both") return { plural: "conversions", singular: "conversion" };
  return { plural: "leads", singular: "lead" };
}
