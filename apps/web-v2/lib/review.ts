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
  ai: { platforms: number; cited: number; mentioned: number; previous_cited: number | null; previous_mentioned: number | null } | null;
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

export type Review = {
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
