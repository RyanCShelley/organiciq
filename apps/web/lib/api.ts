import { redirect } from "next/navigation";

import { auth, ensureApiAccessToken } from "@/lib/auth";

const API_URL = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function parseApiErrorBody(text: string): string {
  try {
    const body = JSON.parse(text) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) return "Request failed";
  } catch {
    // keep raw text
  }
  return text;
}

export async function apiFetch<T>(
  path: string,
  options: {
    method?: string;
    body?: unknown;
    clientId?: string | null;
  } = {},
): Promise<T> {
  const session = await auth();
  const accessToken = await ensureApiAccessToken(session);
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  if (accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }
  if (options.clientId) {
    headers["X-OrganicIQ-Client-Id"] = options.clientId;
  }

  const res = await fetch(`${API_URL}${path}`, {
    method: options.method ?? "GET",
    headers,
    body: options.body ? JSON.stringify(options.body) : undefined,
    cache: "no-store",
  });

  if (!res.ok) {
    const text = await res.text();
    if (res.status === 401) {
      redirect("/login?error=SessionExpired");
    }
    throw new ApiError(res.status, parseApiErrorBody(text) || res.statusText);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return (await res.json()) as T;
}

export type Client = {
  id: string;
  client_name: string;
  slug: string;
  domain: string;
  tier_id: string;
  start_date: string | null;
  primary_market: string | null;
  timezone: string;
  monthly_lead_goal: number | null;
  account_sheet_url?: string | null;
  baseline_as_of?: string | null;
  baseline_monthly_sessions?: number | null;
  baseline_monthly_leads?: number | null;
  baseline_lead_rate_pct?: number | null;
  baseline_source?: string | null;
  baseline_notes?: string | null;
  custom_tracked_keyword_limit?: number | null;
  custom_tracked_prompt_limit?: number | null;
  custom_content_allowance?: number | null;
  custom_update_allowance?: number | null;
  custom_growth_action_allowance?: number | null;
  custom_watchlist_cadence?: string | null;
  status: string;
  created_at: string;
  updated_at: string;
};

export type Integration = {
  id: string;
  client_id: string;
  provider: string;
  external_account_id: string | null;
  external_property_id: string | null;
  gsc_secondary_site_urls?: string[];
  connection_status: string;
  last_sync_started: string | null;
  last_sync_completed: string | null;
  last_successful_sync: string | null;
  last_fact_date: string | null;
  error_message: string | null;
};

export type SyncJob = {
  id: string;
  client_id: string;
  source: string;
  start_date: string;
  end_date: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  records_fetched: number | null;
  records_written: number | null;
  fact_watermark: string | null;
  validation_status: string | null;
  error_message: string | null;
  created_at: string;
};

export type Tier = {
  id: string;
  tier_name: string;
  tracked_keyword_limit: number;
  tracked_prompt_limit: number;
  content_allowance: number;
  update_allowance: number;
  growth_action_allowance?: number;
  conversion_limit: number;
  reporting_level: string;
  watchlist_cadence?: string;
};

export type ChannelRule = {
  id: string;
  match_source: string | null;
  match_medium: string | null;
  match_host_contains: string | null;
  channel: string;
  priority: number;
  active: boolean;
  description: string | null;
};

export type ConversionDefinition = {
  id: string;
  client_id: string;
  event_name: string;
  conversion_name: string;
  conversion_type: string;
  is_primary: boolean;
  active: boolean;
};

export type DataHealthRow = {
  source: string;
  status: string;
  fact_through: string | null;
  last_sync: string | null;
  validation: string | null;
};

export type PlatformOverviewRow = {
  client_id: string;
  client_name: string;
  client_slug: string;
  domain: string;
  status: string;
  integrations: {
    gsc: string;
    ga4: string;
    se_ranking: string;
  };
  sources_healthy: number;
  sources_total: number;
};

export type PlatformDataHealthRow = DataHealthRow & {
  client_id: string;
  client_name: string;
  client_slug: string;
};

export type PlatformJobRow = {
  id: string;
  client_id: string;
  client_name: string;
  client_slug: string;
  source: string;
  start_date: string;
  end_date: string;
  status: string;
  error_message: string | null;
  created_at: string | null;
};
