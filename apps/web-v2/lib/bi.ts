export type BiChannel = {
  channel: string;
  label: string;
  sessions: number;
  sessions_before: number;
  engagement_rate: number | null;
  avg_seconds: number | null;
  conversions: number;
  conversions_before: number;
  conversion_rate: number | null;
};

export type BiPage = {
  url: string;
  sessions: number;
  engagement_rate: number | null;
  avg_seconds: number | null;
  conversions: number;
  conversion_rate: number | null;
};

export type BiKeyword = {
  keyword: string;
  start: number | null;
  end: number | null;
  volume: number | null;
  url: string | null;
  change: number | null;
  state: "up" | "down" | "steady" | "new" | "lost";
};

export type BiChange = { id: string; date: string; type: string; description: string; page: string | null; from_task: boolean };

export type BiTotals = {
  sessions: number;
  engaged: number;
  engagement_rate: number | null;
  avg_seconds: number | null;
  conversions: number;
  conversion_rate: number | null;
};

export type BiDay = { date: string; sessions: number; sessions_before: number; engaged: number; conversions: number; conversions_before: number };

export type BiBands = { top3: number; top10: number; top20: number; top100: number; outside: number };

export type BiAi = {
  date: string;
  checks: number;
  mention_rate: number | null;
  cited_rate: number | null;
  mention_rate_before: number | null;
  cited_rate_before: number | null;
  date_before: string | null;
  platforms: { platform: string; checks: number; mentioned: number; cited: number }[];
};

export type Bi = {
  totals: BiTotals;
  totals_before: BiTotals;
  daily: BiDay[];
  ai: BiAi | null;
  from: string;
  to: string;
  key_events: { event: string; name: string; type: string }[];
  has_engagement_time: boolean;
  channels: BiChannel[];
  pages: BiPage[];
  keywords: { from: string | null; to: string | null; coverage: { start: BiBands; end: BiBands; tracked: number } | null; keywords: BiKeyword[] };
  changes: BiChange[];
};

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

/** The ranges offered above the screen, worked out from today. Data runs to yesterday at the latest. */
export function presets(today = new Date()): { key: string; label: string; from: string; to: string }[] {
  const y = today.getFullYear();
  const m = today.getMonth();
  const yesterday = new Date(y, m, today.getDate() - 1);
  const daysAgo = (n: number) => new Date(y, m, today.getDate() - n);
  return [
    { key: "last-month", label: "Last month", from: iso(new Date(y, m - 1, 1)), to: iso(new Date(y, m, 0)) },
    { key: "28", label: "Last 28 days", from: iso(daysAgo(28)), to: iso(yesterday) },
    { key: "90", label: "Last 3 months", from: iso(daysAgo(90)), to: iso(yesterday) },
    { key: "365", label: "Last 12 months", from: iso(daysAgo(365)), to: iso(yesterday) },
  ];
}

export type AskQuery = { query: string; rows: number; error: string | null };
export type AskDepth = "quick" | "deep" | "deepest";
export type AskItem = {
  id: string;
  status: "running" | "done" | "failed";
  question: string;
  depth: AskDepth;
  model: string;
  answer: string | null;
  error: string | null;
  queries: AskQuery[];
  cost_usd: number;
  asked_by: string;
  created_at: string | null;
};
export type AskInfo = {
  spend: { used_usd: number; cap_usd: number; left_usd: number };
  depths: Record<AskDepth, { model: string }>;
  ready: boolean;
  recent: AskItem[];
};
