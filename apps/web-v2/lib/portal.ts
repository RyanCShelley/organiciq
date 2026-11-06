import { cache } from "react";

import { apiFetch } from "@/lib/api";

/** A site as the portal shows it: name and address only, never its plan or connections. */
export type PortalSite = { id: string; slug: string; name: string; domain: string; group: string | null };
export type PortalHome = { client: PortalSite; sites: PortalSite[]; brand: { name: string; powered_by: string }; previewing: boolean };

/** The portals this person may open. */
export const getPortals = cache(async () => apiFetch<{ clients: PortalSite[]; is_staff: boolean }>("/v2/consulting/clients"));

export type Profile = {
  goals: string | null;
  primary_objective: string | null;
  audiences: string | null;
  markets: string | null;
  priority_services: string | null;
  constraints: string | null;
  editorial_rules: string | null;
  resources: string | null;
  internal_notes: string | null;
  ai_visibility_focus: boolean;
  updated_by: string | null;
  updated_at: string | null;
};

export type RecState = "draft" | "under_review" | "approved" | "published" | "archived";
export type RecSummary = {
  id: string;
  title: string;
  category: "visibility" | "traffic" | "leads";
  focus: "seo" | "geo" | "both";
  source_kind: string;
  priority: "high" | "medium" | "low";
  confidence: "high" | "medium" | "low";
  review_state: RecState;
  impl_status: "recommended" | "planned" | "in_progress" | "completed" | "blocked";
  impl_status_source: "consultant" | "client" | "live_check" | null;
  verification: "unverified" | "verified" | "not_seen" | "unreadable";
  published_at: string | null;
  revision: number;
  updated_at: string | null;
  last_follow_up_on: string | null;
};
export type RecList = { counts: Record<RecState, number>; recommendations: RecSummary[]; follow_ups: number };
export type Rec = RecSummary & {
  finding: string | null;
  explanation: string | null;
  cause_kind: "hypothesis" | "confirmed";
  cause_text: string | null;
  action: string | null;
  instructions: { text: string }[];
  target_urls: { url: string; check: { state: string; live_url?: string | null; note?: string | null } }[];
  expected_impact: string | null;
  confidence_reasons: string[];
  effort_min: number | null;
  owner: string | null;
  baseline: { metric: string; value: string; source?: string; period?: string }[];
  success_metrics: { metric: string; baseline?: string; target?: string; window_days?: number }[];
  measure_on: string | null;
  evidence: { text: string; source?: string; as_of?: string }[];
  internal_notes: string | null;
  implemented_on: string | null;
  implemented_on_estimated: boolean;
  client_notes: string | null;
  evidence_links: string[];
  verified_how: string | null;
  verified_at: string | null;
  publish_gaps: string[];
  next_states: RecState[];
  published_by: string | null;
  events?: { kind: string; from: string | null; to: string | null; by: string; at: string; detail: Record<string, unknown> }[];
};

export const STATE_LABEL: Record<RecState, string> = { draft: "Draft", under_review: "Under review", approved: "Approved", published: "Published", archived: "Archived" };
export const CATEGORY_LABEL = { visibility: "Visibility", traffic: "Traffic", leads: "Leads" } as const;
export const FOCUS_LABEL = { seo: "Search", geo: "AI visibility", both: "Search and AI" } as const;
export const IMPL_LABEL = { recommended: "Recommended", planned: "Planned", in_progress: "In progress", completed: "Completed", blocked: "Blocked" } as const;

/** A published brief as its client sees it. */
export type ClientRec = {
  id: string;
  title: string;
  category: "visibility" | "traffic" | "leads";
  focus: "seo" | "geo" | "both";
  priority: "high" | "medium" | "low";
  confidence: "high" | "medium" | "low";
  finding: string | null;
  explanation: string | null;
  cause_kind: "hypothesis" | "confirmed";
  cause_text: string | null;
  action: string | null;
  instructions: { text: string }[];
  target_urls: { url: string; state: string; live_url: string | null }[];
  expected_impact: string | null;
  effort_min: number | null;
  owner: string | null;
  baseline: { metric: string; value: string; source?: string; period?: string }[];
  success_metrics: { metric: string; baseline?: string; target?: string; window_days?: number }[];
  measure_on: string | null;
  evidence: { text: string; source?: string; as_of?: string }[];
  impl_status: "recommended" | "planned" | "in_progress" | "completed" | "blocked";
  implemented_on: string | null;
  implemented_on_estimated: boolean;
  client_notes: string | null;
  evidence_links: string[];
  verification: "unverified" | "verified" | "not_seen" | "unreadable";
  verified_at: string | null;
  published_at: string | null;
  reported: boolean;
  can_update?: boolean;
};
export type PortalOverview = {
  total: number;
  counts: Record<ClientRec["impl_status"], number>;
  not_reported: number;
  verified: number;
  top: ClientRec[];
};
