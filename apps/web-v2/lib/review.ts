export type Pair = { current: number | null; previous: number | null; change_pct: number | null };

export type RevenueBlock =
  | {
      status: "measured";
      currency_note: string;
      revenue: Pair;
      organic_revenue: Pair;
      orders: Pair;
      average_order_value: Pair;
    }
  | { status: "unavailable"; reason: string };

export type EngineNumbers = { impressions: Pair; clicks: Pair; position: Pair };

export type VisibilityTerm = {
  keyword: string;
  volume: number | null;
  prompt: string | null;
  google: EngineNumbers;
  bing: EngineNumbers;
  status: string;
  ai: { by_platform: Record<string, { cited: boolean; named: boolean }>; platforms: number; cited: number; mentioned: number; previous_cited: number | null; previous_mentioned: number | null } | null;
};

export type AiPair = { current: number; previous: number | null; delta: number | null };

export type VisibilityAi = {
  run_date: string;
  in_month: boolean;
  previous_run_date: string | null;
  summary: { mentions: AiPair; citations: AiPair; visibility_rate: AiPair; responses: number };
  platforms: { platform: string; visibility_rate: AiPair; mentions: AiPair; citations: AiPair }[];
  brand_check: { platform: string; answers: number; site_cited: number }[];
};

export type Visibility = {
  month: string;
  buckets: { id: string; name: string; terms: VisibilityTerm[] }[];
  summary: {
    terms: number;
    showing_in_google: number;
    on_page_one: number;
    showing_in_bing: number;
    google_impressions: number;
    google_clicks: number;
    prompts: number;
  };
  has_google_data: boolean;
  bing: { has_data: boolean; first_week: string | null; last_week: string | null; note: string };
  ai_prompts: string;
  llm: VisibilityAi | null;
};

export type SummaryRow = {
  label: string;
  value: string;
  change: { text: string; tone: "good" | "bad" | "flat"; against: string } | null;
  detail: string | null;
};
export type SummarySection = { title: string; rows: SummaryRow[] };

export type ScoreChange = { change_pct: number | null };
export type TrendPoint = { month: string; value: number | null };
export type RankCheck = {
  checked_on: string;
  tracked: number;
  ranked: number;
  top10: number;
  best: { keyword: string; position: number } | null;
  biggest_drop: { keyword: string; from: number; to: number } | null;
};
export type Scorecards = {
  reads?: { visibility: string | null; traffic: string | null; conversions: string | null };
  month: string;
  previous_month: string;
  headline: string;
  visibility: {
    available: boolean;
    headline: number | null;
    of: number | null;
    verdict: "up" | "down" | "flat";
    page_one: number | null;
    bing: number | null;
    has_bing: boolean;
    impressions: { current: number | null; previous: number | null; change_pct: number | null };
    ai_mentions: number | null;
    ai_links: number | null;
    ai_runs: number | null;
    trend: TrendPoint[];
    rank_check: RankCheck | null;
  };
  traffic: {
    headline: number | null;
    previous: number | null;
    change_pct: number | null;
    verdict: "up" | "down" | "flat";
    organic_change_pct: number | null;
    trend: TrendPoint[];
    channels: { key: string; label: string; sessions: number; previous: number; change_pct: number | null }[];
  };
  conversions: {
    noun: string;
    headline: number | null;
    previous: number | null;
    change_pct: number | null;
    verdict: "up" | "down" | "flat";
    goal: number | null;
    goal_progress_pct: number | null;
    top: { label: string; count: number; previous: number; change_pct: number | null }[];
    revenue: Pair | null;
    conversion_rate: Pair | null;
    trend: TrendPoint[];
  };
};

export type Review = {
  /** True once the month is over and its data complete: the review was worked out once and is read back. */
  locked?: boolean;
  locked_at?: string | null;
  locked_by?: string | null;
  /** Why a finished month is not locked yet, or that the month is still in progress. */
  lock_note?: string | null;
  data_through?: { search_console: string | null; ga4: string | null };
  month: string;
  previous_month: string;
  model: "lead_gen" | "ecommerce" | "both" | null;
  noun: string;
  conversions: Pair;
  conversion_rate: Pair;
  organic_conversions: Pair;
  sessions: Pair;
  organic_sessions: Pair;
  search: { clicks: Pair; impressions: Pair; average_position: Pair; keywords: Record<string, number> | null };
  has_search_data: boolean;
  goal: {
    period_goal: number | null;
    progress_pct: number | null;
    final_goal: number | null;
    checkpoint: { month: number; due: string; projected: number } | null;
    baseline_version: number | null;
  };
  channels: { label: string; sessions: number; conversions: number }[];
  top_pages: { page: string; sessions: number; previous_sessions: number | null; conversions: number | null; clicks: number | null }[];
  services: {
    settings: { organiciq: boolean; ad_accelerator: boolean } | null;
    rows: { key: string; label: string; sessions: Pair; lead_events: Pair }[];
    outside: { label: string; sessions: Pair; lead_events: Pair } | null;
    note: string | null;
  };
  freshness: { source: string; available: boolean }[];
  revenue: RevenueBlock | null;
  visibility: Visibility | null;
  summary: string[];
  summary_sections: SummarySection[];
  scorecards?: Scorecards;
};

export function nextMonth(month: string): string {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(y, m, 1); // JS months are 0-based, so m is already "next"
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function lastCompleteMonth(now: Date = new Date()): string {
  const d = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}
