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
};
export type AdsGroup = AdsTotals & { name: string };
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
      markets: AdsGroup[];
      devices: AdsGroup[];
      /** Local Services Ads, for a client with such an account: the month's leads and what the account spent. Null otherwise. */
      lsa: AdsLsa | null;
    };
export type AdsLsa = {
  leads: number;
  charged: number;
  previous: { leads: number; charged: number } | null;
  cost: number;
  impressions: number;
  clicks: number;
  cost_per_charged_lead: number | null;
  by_status: { name: string; leads: number }[];
  by_type: { name: string; leads: number }[];
  weekly: { week: string; leads: number; charged: number }[];
};
export type AdsSummary =
  | { enabled: false; month: string }
  | { enabled: true; available: false; month: string; reason: string }
  | { enabled: true; available: true; month: string; source: string; totals: AdsTotals; previous: AdsTotals | null };

export const money = (n: number | null | undefined) => (n == null ? "–" : `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`);
export const pct = (n: number | null | undefined) => (n == null ? "–" : `${n.toFixed(n % 1 === 0 ? 0 : 1)}%`);
