export type AdsTotals = {
  impressions: number;
  clicks: number;
  cost: number;
  conversions: number;
  ctr: number | null;
  avg_cpc: number | null;
  cost_per_conversion: number | null;
  /** The share of the searches the ads could have shown on that they did show on, in percent. */
  share: number | null;
  missed_budget: number | null;
  missed_rank: number | null;
};
export type AdsGroup = AdsTotals & { name: string };
export type AdsSplitSide = AdsTotals & { from: string; days: number; clicks_per_day: number };
export type AdsNote = { id: string; date: string; text: string; by: string };
export type AdsReport =
  | { enabled: false; month: string }
  | { enabled: true; available: false; month: string; reason: string }
  | {
      enabled: true;
      available: true;
      month: string;
      period: { from: string; to: string; through: string | null };
      source: string;
      reason: string | null;
      totals: AdsTotals;
      previous: AdsTotals | null;
      weekly: { week: string; impressions: number; clicks: number; cost: number; avg_cpc: number | null }[];
      groups: AdsGroup[];
      terms: { term: string; ad_group: string; clicks: number; cost: number }[];
      terms_note: string | null;
      markets: AdsGroup[];
      devices: AdsGroup[];
      networks: AdsGroup[];
      only_search: boolean;
      notes: AdsNote[];
      split: { date: string; label: string; note: string; before: AdsSplitSide; after: AdsSplitSide } | null;
      summary: string[];
    };
export type AdsSummary =
  | { enabled: false; month: string }
  | { enabled: true; available: false; month: string; reason: string }
  | {
      enabled: true;
      available: true;
      month: string;
      source: string;
      totals: AdsTotals;
      previous: AdsTotals | null;
      top_group: AdsGroup | null;
      top_term: { term: string; ad_group: string; clicks: number; cost: number } | null;
      text: string | null;
    };

export const money = (n: number | null | undefined) => (n == null ? "–" : `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`);
export const pct = (n: number | null | undefined) => (n == null ? "–" : `${n.toFixed(n % 1 === 0 ? 0 : 1)}%`);
