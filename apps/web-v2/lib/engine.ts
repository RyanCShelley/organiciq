export type Candidate = {
  search: string;
  page: string;
  pages_for_search: number;
  impressions: number;
  clicks: number;
  position: number;
  band: "2-3" | "4-10" | "11-20";
  band_label: string;
  target_position: number;
  expected_extra_clicks: number;
  strength: "strong" | "possible";
  reason: string | null;
  previous: { impressions: number; position: number } | null;
  impressions_change_pct: number | null;
  /** Places moved up since the three months before (negative = moved down). */
  position_change: number | null;
  last_year: { impressions: number; position: number } | null;
};

export type VisibilityCandidates = {
  month: string;
  window: { from: string; to: string; previous_from: string; previous_to: string; months: number; has_last_year: boolean };
  bucket: { id: string; name: string; terms: string[] } | null;
  site_trend: { impressions_change_pct: number | null; clicks_change_pct: number | null };
  bands: { key: string; label: string; target_position: number; count: number }[];
  counts: { strong: number; possible: number; listed: number; found: number };
  candidates: Candidate[];
  unranked: { keyword: string; volume: number | null; strength: string; note: string }[];
  notes: string[];
};

export type BucketOverview = {
  id: string;
  name: string;
  terms: number;
  found: number;
  strong: number;
  possible: number;
  expected_extra_clicks: number;
  unranked_terms: number;
};
