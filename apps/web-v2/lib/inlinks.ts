export type InSuggestion = {
  source_url: string;
  source_title: string;
  similarity: number;
  score: number;
  reasons: string[];
  source_clicks: number;
  suggested_anchor: string;
  anchor_type: string;
  anchor_alternates: { anchor: string; type: string }[];
};
export type InTarget = {
  target_url: string;
  target_title: string;
  title: string;
  inbound: number;
  wanted: number;
  need: number;
  impressions: number;
  clicks: number;
  position: number | null;
  queries: string[];
  suggestions: InSuggestion[];
};
export type InData = {
  crawl_date: string;
  pages: number;
  summary: { targets: number; suggestions: number; orphans: number; live: number; ignored: number };
  targets: InTarget[];
  ignored: { id: string; target: string; source: string | null; status: string }[];
  rule: string;
};
export type InResponse = { data: InData | null };
