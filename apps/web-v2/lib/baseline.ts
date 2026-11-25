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
  monthly_gsc_impressions?: number | null;
  monthly_gsc_clicks?: number | null;
  ai_visibility_pct?: number | null;
};

export type PillarGoals = {
  monthly_leads?: number | null;
  monthly_traffic?: number | null;
  monthly_visibility_impressions?: number | null;
  monthly_visibility_clicks?: number | null;
  ai_visibility_pct?: number | null;
};

export type Projection = {
  plan: "launch" | "lift" | "lead" | string;
  plan_label: string;
  baseline_monthly_sessions: number;
  baseline_monthly_leads: number;
  baseline_lead_rate_pct: number;
  baseline_monthly_gsc_impressions?: number | null;
  baseline_monthly_gsc_clicks?: number | null;
  baseline_ai_visibility_pct?: number | null;
  suggested_monthly_lead_goal: number;
  suggested_monthly_traffic_goal?: number | null;
  suggested_monthly_visibility_impressions_goal?: number | null;
  suggested_monthly_visibility_clicks_goal?: number | null;
  suggested_ai_visibility_pct_goal?: number | null;
  goal_horizon_months: number;
  checkpoints: Checkpoint[];
  disclaimer: string;
};

export type SeriesMonth = {
  month: string;
  sessions: number;
  organic_sessions: number | null;
  leads: number;
  lead_rate_pct: number | null;
  in_window: boolean;
  by_event: Record<string, number>;
};

export type AnalysisSource =
  | { type: "ga4"; lead_events: string[]; notes: string[] }
  | { type: "csv"; skipped_rows: string[] };

export type Analysis = {
  method_version: string;
  status: "provisional" | "draft" | string;
  parameters: {
    half_life_months: number;
    sessions_window_months: number;
    lead_rate_window_months: number;
    plan: string;
  };
  window: {
    from: string;
    to: string;
    months: number;
    regime_start: string | null;
    regime_start_source: "given" | "none" | string;
    suggested_regime_start: string | null;
  };
  baseline: {
    monthly_sessions: number;
    monthly_organic_sessions: number | null;
    lead_rate_pct: number;
    monthly_leads: number;
  };
  ranges: {
    monthly_sessions: Range;
    monthly_organic_sessions: Range | null;
    lead_rate_pct: Range;
    monthly_leads: Range;
    note: string;
  };
  goal_basis: { monthly_sessions: number; monthly_leads: number; lead_rate_pct: number; basis: string };
  references: {
    mean_leads_last_3_months: number;
    mean_leads_last_12_months: number;
    pooled_lead_rate_pct_window: number;
  };
  projection: Projection;
  projection_point?: Projection;
  series: SeriesMonth[];
  flags: Flag[];
  blockers: string[];
  can_lock: boolean;
  source: AnalysisSource;
};

export type WindowPair = { avg_30d: number; recent_30d: number; total_90d: number };

export type PillarsSnapshot = {
  window: { as_of: string; start_30d: string; start_90d: string };
  visibility: {
    gsc: {
      clicks: WindowPair;
      impressions: WindowPair;
      ctr_30d_pct: number | null;
      ctr_90d_pct: number | null;
      avg_position_30d: number | null;
      avg_position_90d: number | null;
    };
    bing: {
      clicks: WindowPair;
      impressions: WindowPair;
      avg_position_30d: number | null;
      avg_position_90d: number | null;
    };
    watchlist: {
      tracked_keywords: number;
      paired_ai_prompts: number;
      rankings_date: string | null;
      ranked_keywords: number;
      top_3: number;
      top_10: number;
      avg_position: number | null;
    };
    llm: {
      run_date: string | null;
      visibility_rate_pct: number | null;
      mentions: number | null;
      citations: number | null;
      share_of_voice_pct: number | null;
    };
    site_health: {
      month: string | null;
      crawl_date: string | null;
      seo_score: number | null;
      geo_score: number | null;
    };
  };
  traffic: {
    total_sessions: WindowPair;
    organic_sessions: WindowPair;
    channels: Array<{ channel: string } & WindowPair>;
    top_pages: Array<{ url: string } & WindowPair>;
  };
  leads: {
    lead_events: string[];
    total: WindowPair;
    lead_rate_30d_pct: number | null;
    lead_rate_90d_pct: number | null;
    by_event: Array<{ event_name: string } & WindowPair>;
  };
};

export type BaselineVersion = {
  version: number;
  status: string;
  reason_code: string;
  reason_note: string | null;
  locked_by: string;
  locked_at: string | null;
  method_version?: string | null;
  source_type?: string | null;
  regime_start?: string | null;
  window_from: string;
  window_to: string;
  lead_events: string[];
  acknowledged?: string[];
  monthly_sessions: number | null;
  monthly_organic_sessions: number | null;
  lead_rate_pct?: number | null;
  monthly_leads: number | null;
  goal_monthly_leads: number | null;
  goals?: PillarGoals | null;
  has_pillars?: boolean;
};

export type BaselineGoalState = {
  current: number | null;
  suggested: number | null;
  version: number | null;
  target_lead_rate_pct: number | null;
  pillar_goals?: PillarGoals | null;
};

export type BaselineEventsResponse = {
  events: Array<{ name: string; total: number; first_month: string | null; last_month: string | null }>;
  defaults: string[];
  locked: { version: number; events: string[] } | null;
  goal: BaselineGoalState;
};

export type BaselineLockResponse = {
  version: BaselineVersion;
  lead_conversions_changed: { add: string[]; remove: string[]; keep?: string[] } | null;
  monthly_lead_goal: number;
  suggested_monthly_lead_goal: number;
  goal_set_by_lock: boolean;
  target_lead_rate_pct: number | null;
  pillar_goals?: PillarGoals | null;
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
