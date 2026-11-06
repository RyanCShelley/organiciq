export type Candidate = {
  search: string;
  page: string;
  pages_for_search: number;
  impressions: number;
  clicks: number;
  position: number;
  band: "2-3" | "4-10" | "11-20";
  band_label: string;
  target_position: number;
  expected_extra_clicks: number;
  strength: "strong" | "possible";
  brand: boolean;
  reason: string | null;
  previous: { impressions: number; position: number } | null;
  impressions_change_pct: number | null;
  /** Places moved up since the three months before (negative = moved down). */
  position_change: number | null;
  last_year: { impressions: number; position: number } | null;
};

export type VisibilityCandidates = {
  month: string;
  window: { from: string; to: string; previous_from: string; previous_to: string; months: number; has_last_year: boolean };
  bucket: { id: string; name: string; terms: string[] } | null;
  site_trend: { impressions_change_pct: number | null; clicks_change_pct: number | null };
  bands: { key: string; label: string; target_position: number; count: number }[];
  counts: { strong: number; possible: number; listed: number; found: number; brand: number };
  candidates: Candidate[];
  unranked: { keyword: string; volume: number | null; strength: string; note: string }[];
  notes: string[];
};

export type BucketOverview = {
  id: string;
  name: string;
  terms: number;
  found: number;
  strong: number;
  possible: number;
  expected_extra_clicks: number;
  unranked_terms: number;
  reach: "thin" | "some" | "good";
};

export type Advice = {
  level: "ok" | "shift" | "thin_data";
  headline: string;
  reasons: string[];
  suggestions: { kind: "bucket" | "content" | "focus" | "data"; text: string; bucket_id?: string; name?: string }[];
};

export type EngineOverview = {
  buckets: BucketOverview[];
  coverage: { days: number; window_days: number };
  advice: Advice;
};

export const EMPTY_OVERVIEW: EngineOverview = {
  buckets: [],
  coverage: { days: 0, window_days: 0 },
  advice: { level: "ok", headline: "", reasons: [], suggestions: [] },
};

export type Diagnosis = {
  search: string;
  page: string;
  position?: number;
  impressions?: number;
  clicks?: number;
  read: {
    ok: boolean;
    status?: number | null;
    error?: string | null;
    final_url?: string;
    /** Set when the response was not the page (a host's bot check, or nothing readable): nothing is judged from it. */
    blocked?: string;
    /** "crawl" when the host blocked our reader and the page was read from the site crawl instead; the note says which crawl and what that means. */
    source?: string;
    source_note?: string;
    /** What our reader was served, kept so any finding can be traced to it. */
    received?: {
      requested_url: string | null;
      final_url: string;
      status: number;
      user_agent: string | null;
      fetched_at: string | null;
      bytes: number;
      headers: Record<string, string>;
      body_starts: string;
    };
  };
  /** `how` says exactly where the finding was read from: the tag or header, the address, the status, the time and who asked. */
  observations: { level: "problem" | "note" | "ok"; text: string; how?: string }[];
  prescriptions: {
    action_id: string;
    title: string;
    why: string;
    done_when: string;
    metric: string;
    effort_min: number;
    steps: string[];
    evidence: string[];
  }[];
  not_judged: { action_id: string; name: string; reason: string }[];
  /** Worth looking at, but not provable with the data we have yet. Never a prescription. */
  suggestions: {
    id: string;
    title: string;
    why: string;
    steps: string[];
    needs_to_confirm: string;
    confidence: "unconfirmed";
    evidence: string[];
  }[];
  skipped_suggestions: { id: string; name: string; reason: string }[];
};

export type DiagnoseResult = { ok: true; results: Diagnosis[] } | { ok: false; error: string };

export type TaskStatus = "confirmed" | "sent" | "shipped" | "dropped";

/** One part of a growth action, with the tool that carries it out (none for a plain step). */
export type TaskPart = {
  id: string;
  name: string;
  tool: string | null;
  tool_label: string | null;
  tool_path: string | null;
  tool_param: string | null;
  tool_verb: string | null;
  tool_kind?: string | null;
  done_how?: string | null;
  verified_at?: string | null;
  verified_how?: string | null;
  last_check?: { at: string; result: "live" | "not_live" | "unreadable" | "cannot"; note: string } | null;
  auto?: boolean;
  status: "open" | "done";
  done_at: string | null;
  done_by: string | null;
};

export type EngineTask = {
  id: string;
  month: string;
  kind: "prescription" | "suggestion" | "growth_action";
  rule_id: string;
  search: string;
  page: string;
  title: string;
  why: string | null;
  steps: string[];
  done_when: string | null;
  metric: string | null;
  effort_min: number | null;
  evidence: string[];
  status: TaskStatus;
  confirmed_by: string;
  assignee_email: string | null;
  due: string | null;
  teamwork_task_id: string | null;
  teamwork_task_url: string | null;
  teamwork_subtasks?: number;
  parts?: TaskPart[];
  shipped_at?: string | null;
  check_on?: string | null;
};

export type Allowance = { monthly: number | null; used: number; over: boolean };

export type TaskPlan = {
  month: string;
  tasks: EngineTask[];
  allowance: Allowance;
  teamwork: { configured: boolean; tasklist_id: string | null };
};

export const EMPTY_PLAN: TaskPlan = {
  month: "",
  tasks: [],
  allowance: { monthly: null, used: 0, over: false },
  teamwork: { configured: false, tasklist_id: null },
};

export type TaskDraft = {
  kind: "prescription" | "suggestion" | "growth_action";
  rule_id: string;
  search: string;
  page: string;
  title: string;
  why: string | null;
  steps: string[];
  done_when: string | null;
  metric: string | null;
  effort_min: number | null;
  evidence: string[];
  parts?: { id: string; name: string }[];
};

export type TaskResult<T = EngineTask> = { ok: true; value: T; allowance?: Allowance } | { ok: false; error: string };

export type EngineKind = "visibility" | "traffic" | "leads";

export type TrafficRow = {
  level: "site" | "bucket" | "page";
  key: string;
  label: string;
  bucket: string | null;
  sessions: { current: number; previous: number; change_pct: number | null };
  three_months: { current: number; last_year: number; change_pct: number | null };
  flag: "sudden" | "slow_bleed" | "both" | null;
  strength: "strong" | "possible";
  reason: string | null;
  at_stake: number;
};

export type DroppedPage = {
  page: string;
  sessions: { current: number; previous: number; change_pct: number | null };
  three_months: { current: number; last_year: number; change_pct: number | null };
  lost_month: number;
  lost_year: number;
  flag: "sudden" | "slow_bleed" | "both" | null;
};

export type TrafficCandidates = {
  month: string;
  scope: string;
  bucket: { id: string; name: string } | null;
  windows: { current: string; previous: string; three_months: string[]; last_year: string[] };
  site: {
    sessions: { current: number; previous: number; change_pct: number | null };
    three_months: { current: number; last_year: number; change_pct: number | null };
    has_last_year: boolean;
  };
  counts: { strong: number; possible: number; listed: number };
  candidates: TrafficRow[];
  dropped_pages: DroppedPage[];
  dropped_total: number;
  thresholds: { sudden: string; slow_bleed: string };
  notes: string[];
};

export type LeadRow = {
  page: string;
  sessions: number;
  conversions: number;
  conversion_rate: number;
  engagement_rate: number;
  missed_conversions: number;
  worst_conversion: boolean;
  worst_engagement: boolean;
  strength: "strong" | "possible";
  reason: string | null;
};

export type LeadsPageRow = {
  page: string;
  sessions: number;
  conversions: number;
  conversion_rate: number;
  engagement_rate: number;
  missed_conversions: number;
  compared: boolean;
};

export type LeadsCandidates = {
  month: string;
  window: { from: string; to: string; months: number };
  noun: { plural: string; singular: string };
  conversion_events: string[];
  needs?: "conversions";
  scope?: string;
  bucket?: { id: string; name: string } | null;
  site?: { qualifying_pages: number; median_conversion_rate: number | null; median_engagement_rate: number | null; organic_sessions: number };
  counts: { strong: number; possible: number; listed: number; found?: number };
  candidates: LeadRow[];
  all_pages?: LeadsPageRow[];
  all_pages_total?: number;
  notes: string[];
};

export type TopicPage = {
  url: string;
  impressions: number;
  clicks: number;
  position: number | null;
  searches: number;
  top_search: string;
  title: string;
  title_says_topic: boolean;
  score: number;
};

export type TopicPages = {
  keyword: string;
  window: { from: string; to: string };
  recommended: string | null;
  pages: TopicPage[];
  total_pages: number;
  rule: string;
};

export type GrowthPart = {
  id: string;
  name: string;
  title: string;
  why: string;
  steps: string[];
  evidence: string[];
  core: boolean;
  confirmed_by_rule: boolean;
};

export type GrowthActionBundle =
  | { ok: false; error: string }
  | {
      ok: true;
      keyword: string;
      page: string;
      chosen: TopicPage;
      search: string;
      parts: GrowthPart[];
      left_out: { id: string; name: string; reason: string }[];
      optional: GrowthPart[];
      draft: TaskDraft;
    };

export type CandidateTopic = { keyword: string | null; source: string; pages: TopicPages | null };

export type GscNumbers = { clicks: number; impressions: number; position: number | null };
export type AiNumbers = { run_date: string; cited: number; platforms: number } | null;

export type ShippedResult = {
  task_id: string;
  title: string;
  topic: string;
  page: string;
  kind: string;
  shipped_on: string | null;
  check_on: string | null;
  status: "no_baseline" | "measuring" | "measured";
  before?: GscNumbers;
  after?: GscNumbers;
  change?: { clicks: number; impressions: number; position: number | null };
  ai_before?: AiNumbers;
  ai_after?: AiNumbers;
  note?: string | null;
};
