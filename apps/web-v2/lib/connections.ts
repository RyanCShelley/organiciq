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
  bing_key_configured: boolean;
  bing: BingSite | null;
  se_ranking_key_configured: boolean;
  google_connect_configured: boolean;
};

export type Option = { value: string; label: string };

export type OptionsResult = { ok: true; options: Option[] } | { ok: false; error: string };
export type ConnectResult = { ok: true; url: string } | { ok: false; error: string };
