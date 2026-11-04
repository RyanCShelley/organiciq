export type SvTerm = {
  term: string;
  key: string;
  volume: number | null;
  bucket_id: string;
  bucket: string;
  google: { impressions: number; clicks: number; position: number | null; position_before: number | null };
  bing: { impressions: number; clicks: number; position: number | null };
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

export type Sv = {
  from: string;
  to: string;
  buckets: { id: string; name: string }[];
  terms_total: number;
  now: SvTotals;
  before: SvTotals;
  distribution: { now: Record<string, number>; before: Record<string, number> };
  weeks: string[];
  series: SvWeek[];
  winners: SvTerm[];
  losers: SvTerm[];
  terms: SvTerm[];
  updates: SvUpdate[];
  sources: { ser_tracked: number; bing_terms: number; ser_from: string | null; ser_to: string | null };
};

export type SvDetail = {
  term: string;
  pages: { url: string; impressions: number; clicks: number; position: number | null }[];
  competitors: { domain: string; position: number; url: string | null }[];
  competitors_read_on: string | null;
  serp: { pulled_on: string; features: string[]; holders: Record<string, unknown> } | null;
};
