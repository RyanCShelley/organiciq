export type IntegrationRow = {
  id: string;
  provider: "gsc" | "ga4" | "se_ranking";
  external_account_id: string | null;
  external_property_id: string | null;
  gsc_secondary_site_urls: string[];
  connection_status: "not_connected" | "connected" | "error" | "disconnected";
  last_successful_sync: string | null;
  last_fact_date: string | null;
  error_message: string | null;
};

export type BingSite = {
  site_url: string;
  status: "connected" | "error" | "unchecked";
  error: string | null;
  checked_at: string | null;
};

export type Connections = {
  teamwork_configured: boolean;
  teamwork_tasklist_id: string | null;
  teamwork_content_project_id: string | null;
  bing_key_configured: boolean;
  bing: BingSite | null;
  se_ranking_key_configured: boolean;
  google_connect_configured: boolean;
};

export type Option = { value: string; label: string };

export type OptionsResult = { ok: true; options: Option[] } | { ok: false; error: string };
export type ConnectResult = { ok: true; url: string } | { ok: false; error: string };

/** One Google Ads account a client has: search ads, Local Services Ads, and so on. */
export type AdsAccount = {
  customer_id: string;
  name: string;
  kind: "ads" | "lsa";
  last_pull_at: string | null;
  last_error: string | null;
};

/** Where Google Ads stands for a client on Ads Accelerator. */
export type AdsConnection = {
  enabled: boolean;
  /** The Google sign-in includes the Google Ads permission. */
  permission: boolean;
  /** The manager account is set on the server. */
  manager_set: boolean;
  accounts: AdsAccount[];
};

/** One read-only check of what Google Ads returns for an account: worked, came back empty, or was refused. */
export type AdsCheck = { name: string; status: "ok" | "empty" | "error"; detail: string; rows: number; sample: string | null };
export type AdsDiagnosis = {
  checked_at: string;
  days: number;
  accounts: { customer_id: string; name: string; kind: "ads" | "lsa"; checks: AdsCheck[] }[];
};

/** What a pull brought, per account. */
export type AdsPullResult = {
  accounts: { account: string; from: string; to: string; days: number; rows: number; markets: number; terms: number; leads: number; errors: string[] }[];
  errors: string[];
};
