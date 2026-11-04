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
  gsc_lean: boolean;
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

export type PullSource = {
  source: string;
  label: string;
  reach: string;
  from: string;
  to: string;
  state: "not_started" | "queued" | "running" | "stopping" | "done" | "partial" | "failed" | "stopped";
  stage: string | null;
  running_seconds: number | null;
  error: string | null;
  rows: number | null;
  finished_at: string | null;
  current: boolean;
};

export type PullStatus = {
  sources: PullSource[];
  running: boolean;
  finished: boolean;
  up_to_date: boolean;
  stopping: boolean;
  failed: string[];
  jobs_done: number;
  jobs_total: number;
  jobs_ahead: number;
};
