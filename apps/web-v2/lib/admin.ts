export type AdminClient = {
  id: string;
  name: string;
  slug: string;
  domain: string;
  tier: string | null;
  status: string | null;
  business_model: string | null;
  integrations: number;
  bing: boolean;
  watchlist_keywords: number;
  has_baseline: boolean;
  team: number;
  gsc_through: string | null;
  ga4_through: string | null;
};

export type DeletePreview = {
  name: string;
  synced_rows: number;
  setup_rows: number;
  setup: Record<string, number>;
  integrations: number;
  team_access: number;
  annotations: number;
  copilot_conversations: number;
};
