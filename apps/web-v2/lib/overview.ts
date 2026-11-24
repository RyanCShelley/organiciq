import { apiFetch } from "@/lib/api";

export type ClientsOverviewWindow = {
  from_date: string;
  to_date: string;
  previous_from: string;
  previous_to: string;
  days: number;
};

export type ClientOverviewItem = {
  id: string;
  client_name: string;
  slug: string;
  domain: string;
  status: "active" | "paused" | "onboarding" | "archived" | string;
  service_mode: "execution" | "consulting" | string;
  group_name: string | null;
  plan_label: string | null;
  business_model: "lead_gen" | "ecommerce" | "both" | null;
  monthly_lead_goal: number | null;
  current_lead_goal: number | null;

  impressions: number | null;
  clicks: number | null;
  avg_position: number | null;
  impressions_change_pct: number | null;

  total_sessions: number | null;
  organic_sessions: number | null;
  organic_change_pct: number | null;

  leads: number | null;
  lead_label: "leads" | "orders" | "conversions";
  leads_change_pct: number | null;

  gsc_through: string | null;
  ga4_through: string | null;
};

export type ClientsOverviewResponse = {
  window: ClientsOverviewWindow;
  clients: ClientOverviewItem[];
};

export async function getClientsOverview(asOf?: string): Promise<ClientsOverviewResponse> {
  const qs = asOf ? `?as_of=${encodeURIComponent(asOf)}` : "";
  return apiFetch<ClientsOverviewResponse>(`/v2/clients/overview${qs}`);
}
