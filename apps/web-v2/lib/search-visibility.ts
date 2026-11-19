export type SvTerm = {
  term: string;
  key: string;
  volume: number | null;
  bucket_id: string;
  bucket: string;
  google: { impressions: number; clicks: number; position: number | null; position_before: number | null };
  bing: { impressions: number; clicks: number; position: number | null; position_before: number | null; move: number | null };
  ser: { position: number | null; position_start: number | null; tracked: boolean; url: string | null };
  best: number | null;
  band: "top3" | "top10" | "top20" | "beyond" | "none";
  move: number | null;
  disagree: string | null;
  trend: (number | null)[];
};

export type SvTotals = { showing: number; page_one: number; clicks: number; impressions: number; position: number | null };
export type SvUpdate = { id: string; title: string; begin: string; end: string | null; summary: string | null; url: string | null };
export type SvWeek = { week: string; impressions: number; clicks: number; position: number | null };
export type SvUnsungHero = {
  query: string;
  key: string;
  page: string | null;
  impressions: number;
  impressions_before: number;
  impressions_change_pct: number | null;
  clicks: number;
  position: number | null;
  position_before: number | null;
  move: number | null;
  ctr: number | null;
  signals: string[];
  relevance_note: string;
};
export type SvAnnotation = {
  id: string;
  date: string;
  type: string;
  type_label: string;
  description: string;
  notes: string | null;
};

export type Sv = {
  from: string;
  to: string;
  buckets: { id: string; name: string }[];
  terms_total: number;
  now: SvTotals;
  before: SvTotals;
  bing_now: SvTotals;
  bing_before: SvTotals;
  bing_site: { now: SvTotals; before: SvTotals };
  distribution: { now: Record<string, number>; before: Record<string, number> };
  weeks: string[];
  series: SvWeek[];
  bing_series: SvWeek[];
  bing_series_scope: "watchlist" | "site" | "none";
  winners: SvTerm[];
  losers: SvTerm[];
  bing_winners: SvTerm[];
  bing_losers: SvTerm[];
  terms: SvTerm[];
  unsung_heroes: SvUnsungHero[];
  annotations: SvAnnotation[];
  updates: SvUpdate[];
  sources: {
    google_through: string | null;
    ser_tracked: number;
    bing_terms: number;
    has_bing: boolean;
    bing_through: string | null;
    bing_site_terms: number;
    ser_from: string | null;
    ser_to: string | null;
  };
};

export type SvDetail = {
  term: string;
  pages: { url: string; impressions: number; clicks: number; position: number | null }[];
  competitors: { domain: string; position: number; url: string | null }[];
  competitors_read_on: string | null;
  serp: { pulled_on: string; features: string[]; holders: Record<string, unknown> } | null;
};
