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

export type ReportMetric = { label: string; current: number | null; previous: number | null; change_pct: number | null; unit: string; source: string; lower_is_better: boolean; note: string | null };
export type ReportSection = { key: "visibility" | "traffic" | "leads"; label: string; question: string; metrics: ReportMetric[]; read: string | null; limitation: string | null };
export type ReportData = {
  month: string;
  previous_month: string;
  headline: string | null;
  sections: ReportSection[];
  caveats: string[];
  as_of?: Record<string, string | null> | null;
  locked?: boolean;
  /** The monthly review's own payload and scorecards, as published, and a little more from Insights. Absent on a report published before they were kept. */
  review?: import("@/lib/review").Review;
  cards?: import("@/lib/review").Scorecards;
  insights?: { keywords: import("@/lib/bi").Bi["keywords"] | null; ai: import("@/lib/bi").Bi["ai"]; key_events: string[] };
  /** How each AI prompt did on each platform over the month's runs. */
  visibility_detail?: { prompts: PromptRow[]; runs: number; run_dates: string[]; in_month: boolean } | null;
  /** The monthly performance layout's figures: outcomes with year-over-year and a three-month run, and a table per topic. */
  performance?: Performance;
  /** The two Site health scores for the month, from the site crawl. Absent when the site had no crawl that month. */
  site_health?: SiteHealthSummary | null;
};
export type Highlights = { going_well: string[]; to_watch: string[]; gaps: string[] };
export type SiteHealthSummary = {
  month: string; crawl_date: string | null; pages: number | null; hit_limit: boolean; previous_month: string | null;
  seo: { score: number; grade: string; previous: number | null; change: number | null; checks: { label: string; score: number; affected: number; total: number }[] };
  geo: { score: number; grade: string; previous: number | null; change: number | null; partial: boolean; signals: { label: string; score: number | null; summary: string | null }[] };
  new_issues: number | null; fixed_issues: number | null; source: string;
};
export type ExecKpi = { label: string; value: number | string | null; unit: string; sub: string; tone: "good" | "bad" | "neutral" };
export type ExecTopic = {
  name: string; keywords: number; searches_per_month: number | null;
  google_top10_pct: number | null; google_heat: "green" | "amber" | "red" | null;
  ai_share_pct: number | null; ai_heat: "green" | "amber" | "red" | null;
  ai_leader: { name: string; share_pct: number; is_self: boolean } | null;
  ai_overview_pct: number | null;
  clicks: { value: number | null; last_year: number | null; change: number | null };
  read_out: string;
};
export type ExecCompetitor = { name: string; is_self: boolean; visibility: number; change_pct: number | null; ai_share_pct: number | null };
export type ExecData = {
  month: string; brand: string; kpis: ExecKpi[];
  clicks_by_month: { month: string; value: number | null }[]; clicks_year_ago_month: string;
  competitors: ExecCompetitor[]; topics: ExecTopic[];
  ai_vendors: { name: string; share_pct: number; is_self: boolean }[]; ai_runs: number; ai_run_dates: string[];
  site_health?: SiteHealthSummary | null; priorities: { title: string; action: string }[]; about: string[]; sources: string[];
};
export type ReportKind = "monthly" | "executive";
export type Notes = Record<string, string>;
export type ExecReport = { kind: "executive"; month: string; title: string | null; analysis: string | null; highlights: Highlights; notes: Notes; published_at: string | null; data: ExecData };
export type PortalReports = { monthly: ClientReport | null; executive: ExecReport | null };
export type StaffReport = { month: string; title: string | null; analysis: string | null; highlights: Highlights; kind?: ReportKind; notes?: Notes; review_state: "draft" | "published"; revision: number; exists: boolean; published_at: string | null; published_by: string | null; updated_by: string | null };
export type ClientReport = { month: string; title: string | null; analysis: string | null; highlights: Highlights; published_at: string | null; data: ReportData };

export type PromptRow = {
  query: string;
  keyword: string | null;
  topic_cluster: string | null;
  by_platform: Record<string, string>;
  score: number;
  max_score: number;
  previous_score: number | null;
  change: number | null;
  avg_brand_rank: number | null;
  top_competitors: { name: string; count: number }[];
};

export type Compare = { value: number | null; change_pct: number | null };
export type OutcomeCard = { label: string; caption: string; value: number | null; unit: string; lower_is_better: boolean; vs_previous: Compare; vs_last_year: Compare; run: { month: string; value: number | null }[]; facts?: string[] };
export type Performance = {
  month: string;
  site: string;
  previous_month: string;
  last_year: string;
  outcomes: { conversions: OutcomeCard | null; visibility: OutcomeCard | null; traffic: OutcomeCard | null };
  google_clicks: { value: number | null; vs_previous: number | null; vs_last_year: number | null };
  key_actions: { rows: { label: string; count: number; previous: number; change_pct: number | null; last_year: number | null }[]; total: { count: number; previous: number; change_pct: number | null } | null; has_definitions: boolean };
  rankings: { checked_from: string | null; checked_to: string | null; coverage: { tracked: number } | null; rows: { keyword: string; volume: number | null; start: number | null; end: number | null; change: number | null; state: string }[] };
  channels: { key: string; label: string; sessions: number; share_pct: number | null; previous: number; change_pct: number | null }[];
  all_visits: number | null;
  landing_pages: { page: string; sessions: number; previous: number | null; change_pct: number | null; key_actions: number }[];
  ai_assistants: { label: string; sessions: number; previous: number; change_pct: number | null; key_actions: number | null }[];
  sources: string[];
};
