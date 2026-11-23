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
  /** When the site crawl last read this page, YYYY-MM-DD. Null when the crawl does not hold it. */
  page_crawled_on?: string | null;
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

export type RejectionReasonKey =
  | "wrong_intent"
  | "wrong_page_type"
  | "wrong_target"
  | "template_constraint"
  | "insufficient_evidence"
  | "crawl_misread"
  | "duplicate"
  | "low_value";

export type RejectionReason = {
  key: string;
  label: string;
};

export type RejectionReasonsResponse = {
  reasons: RejectionReason[];
};

export const REJECTION_REASONS: RejectionReason[] = [
  { key: "wrong_intent", label: "Wrong search intent" },
  { key: "wrong_page_type", label: "Wrong page type" },
  { key: "wrong_target", label: "Wrong target URL" },
  { key: "template_constraint", label: "Template constraint" },
  { key: "insufficient_evidence", label: "Insufficient evidence" },
  { key: "crawl_misread", label: "Incorrect crawl interpretation" },
  { key: "duplicate", label: "Duplicate recommendation" },
  { key: "low_value", label: "Low business value" },
];

export type ChecklistItem = {
  id: string;
  title: string;
  why: string;
  steps: string[];
  action_type: string;
  benefit: string;
  status: "needed" | "done" | "check";
  category: string;
};

export type CrawlChangeDiffSummary = {
  previous_count: number;
  current_count: number;
  added_count: number;
  removed_count: number;
  added_samples: string[];
  removed_samples: string[];
};

export type CrawlChangeItem = {
  snapshot_date: string;
  content_updated_on: string | null;
  content_changed_on: string | null;
  previous_replaced_on: string | null;
  title: string | null;
  meta_description: string | null;
  word_count: number | null;
  paragraphs_count: number;
  previous_paragraphs_count: number;
  diff_summary: CrawlChangeDiffSummary | null;
};

export type HistoryTaskItem = {
  id: string;
  month: string;
  title: string;
  status: TaskStatus | string;
  kind: string;
  rule_id: string;
  search: string;
  parts: { id: string; name: string; status: string }[];
  confirmed_by: string | null;
  confirmed_at: string | null;
  sent_at: string | null;
  shipped_at: string | null;
  rejected_at: string | null;
  rejected_by: string | null;
  rejection_reason: string | null;
  rejection_reason_label: string | null;
  rejection_note: string | null;
  created_at: string | null;
};

export type HistoryAnnotationItem = {
  id: string;
  date: string;
  annotation_type: string;
  description: string;
  verified_how: string | null;
  result: string | null;
  notes: string | null;
};

export type PageHistory = {
  page: string;
  crawl_changes: CrawlChangeItem[];
  tasks: HistoryTaskItem[];
  annotations: HistoryAnnotationItem[];
};

export type SerpOrganicResult = {
  rank: number;
  url: string;
  domain: string;
  title: string;
  snippet?: string;
};

export type SerpLookupResult = {
  search: string;
  pulled_on: string | null;
  item_types: string[];
  features: string[];
  holders: Record<string, string[]>;
  results: SerpOrganicResult[];
  questions: string[];
  reading: ActionContext["intent"] & { search?: string; labels?: string[] };
  labels: string[];
  configured: boolean;
};

export type PriorRejection = {
  id: string;
  month: string;
  search: string;
  rule_id: string;
  title: string;
  rejection_reason: string | null;
  rejection_reason_label: string | null;
  rejection_note: string | null;
  rejected_by: string | null;
  rejected_at: string | null;
};

export type PageFactsSummary = {
  title: string | null;
  description: string | null;
  h1: string;
  word_count: number;
  schema_types: string[];
  search_terms_missing?: string[];
  has_faq: boolean;
  conversion_elements: number;
  contact_only_in_footer: boolean;
  outline?: {
    title: string | null;
    h1: string;
    word_count: number;
    sections: { heading: string; text: string; has_table: boolean; has_list: boolean }[];
    schema_types: string[];
    faq_questions: number;
    faq_list: string[];
    conversion_elements: number;
  };
};

export type Diagnosis = {
  search: string;
  page: string;
  position?: number;
  impressions?: number;
  clicks?: number;
  focus?: EngineKind;
  focus_order_reason?: string | null;
  read: {
    ok: boolean;
    status?: number | null;
    error?: string | null;
    at?: string;
    final_url?: string;
    outcome?: string;
    outcome_name?: string;
    evidence_source?: "live" | "crawl" | "none";
    crawl_date?: string | null;
    usable?: boolean;
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
  context?: {
    intent?: ActionContext["intent"];
    page_type?: ActionContext["page_type"];
    fit?: ActionContext["fit"];
    template?: ActionContext["template"];
    checklist?: ChecklistItem[];
    style_notes?: string | null;
  };
  page_history?: PageHistory;
  page_facts?: PageFactsSummary;
  evidence?: unknown;
};

export type DiagnoseResult = { ok: true; results: Diagnosis[]; month?: string; focus?: EngineKind } | { ok: false; error: string };

export type TaskStatus = "confirmed" | "sent" | "shipped" | "dropped" | "rejected";

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
  custom?: boolean;
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
  confirmed_at?: string | null;
  assignee_email: string | null;
  due: string | null;
  teamwork_task_id: string | null;
  teamwork_task_url: string | null;
  teamwork_subtasks?: number;
  parts?: TaskPart[];
  shipped_at?: string | null;
  check_on?: string | null;
  rejection_reason?: string | null;
  rejection_reason_label?: string | null;
  rejection_note?: string | null;
  rejected_by?: string | null;
  rejected_at?: string | null;
};

export type Allowance = { monthly: number | null; used: number; over: boolean };

/** A month's approved work counted by the tool that does it. */
export type WorkItem = { task_id: string; part: number; name: string; page: string; search: string; kind: string | null; done: boolean; seen_live: boolean };
export type WorkTool = { tool: string; label: string; path: string | null; param: string | null; open: number; done: number; seen_live: number; items: WorkItem[] };
export type MonthWork = { month: string; actions: number; parts: number; done: number; open: number; seen_live: number; by_tool: WorkTool[] };

export type TaskPlan = {
  month: string;
  work?: MonthWork;
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

export type TaskPartInput = {
  id: string;
  name: string;
  status?: "open" | "done";
  custom?: boolean;
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
  parts?: { id: string; name: string; custom?: boolean }[];
};

export type RejectTaskInput = {
  month?: string;
  kind?: "prescription" | "suggestion" | "growth_action";
  rule_id?: string;
  search?: string;
  page: string;
  title?: string;
  why?: string | null;
  steps?: string[];
  parts?: { id: string; name: string; custom?: boolean }[];
  rejection_reason: string;
  rejection_note?: string;
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
  /** False when the site turned our crawler away from the page, so its title is not known. */
  title_read?: boolean;
  score: number;
  page_type?: string;
  page_type_name?: string;
  /** Whether this kind of page suits the search's intent: high, medium, low or unverified. */
  fit?: "high" | "medium" | "low" | "unverified";
  fit_why?: string;
};

export type ActionContext = {
  /** The search's intent as read from its results page. `read` is false when there was no page, or it did not settle the intent. */
  intent: {
    intent: string; name: string; primary: string | null; secondary: string | null; confidence: string; read: boolean;
    searcher_goal: string | null; evidence: string[]; uncertainty: string | null;
    content_types: Record<string, number>; content_styles: Record<string, number>; features: string[];
    label_disagreement: string | null; labels: string[]; serp_date: string | null; content_to_match: string | null;
    /** The top organic results as read, each with the kind of page it is. Absent when no results page was read. */
    ranked?: { rank: number; url: string; domain: string; title: string; content_type: string | null; content_style: string | null }[];
    consumer_need: { need: string; name: string; basis: "observed" | "inferred"; evidence: string } | null;
  };
  page_type: { type: string; name: string; confidence: string; basis: string[]; purpose: string; note: string | null };
  fit: { level: "high" | "medium" | "low" | "unverified"; why: string };
  template: { shared: boolean | null; peers: number; pattern: string | null; basis: string; note: string };
  evidence: { crawl_status: string; crawl_status_name: string; source: "live" | "crawl" | "none"; crawl_date: string | null; confidence: string; sufficient: boolean; unverified: string[]; summary: string };
  validation: { verdict: "publish" | "needs_verification" | "reject"; summary: string; checks: { key: string; question: string; state: "pass" | "unverified" | "fail"; detail: string; critical: string }[] };
  /** The page is not the kind that ranks for the search: nothing is done to it for the search, and the right kind of page is named separately. */
  mismatch: boolean;
  winners?: Winners | null;
  action_types: string[];
  benefits: string[];
  checklist?: ChecklistItem[];
  style_notes?: string | null;
  focus?: EngineKind;
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
  /** One part is the primary action; the others support it or are offered unselected. */
  role?: "primary" | "supporting" | "optional" | "held";
  /** Shown but not approvable: it depends on the search's intent, which was not read. */
  held?: boolean;
  held_reason?: string;
  action_type?: string;
  benefit?: string;
  benefit_why?: string;
  /** Where the change lands: page-specific, template-wide, sitewide or new supporting content. */
  scope?: string;
  note?: string;
  custom?: boolean;
  tool?: string | null;
  needs_to_confirm?: string;
  confidence?: string;
  classification?: string;
};

export type GrowthActionBundle =
  | {
      ok: false;
      error: string;
      context?: ActionContext;
      focus?: EngineKind;
      focus_order_reason?: string | null;
      checklist?: ChecklistItem[];
      prior_rejections?: PriorRejection[];
      page_history?: PageHistory;
    }
  | {
      ok: true;
      keyword: string;
      page: string;
      chosen: TopicPage;
      search: string;
      parts: GrowthPart[];
      left_out: { id: string; name: string; reason: string }[];
      optional: GrowthPart[];
      /** Tasks that depend on intent, when intent was not read. Released by reading the results page. */
      held?: GrowthPart[];
      /** Absent when nothing is recommended: there is nothing to add to the plan. */
      draft?: TaskDraft;
      /** A finding without work: the reason no change is recommended for this page and search. */
      nothing_recommended?: { reason: string } | null;
      /** The page of the right kind for a search this page does not suit. Reviewed on its own; the action is never moved to it. */
      suggested_page?: { kind: string | null; exists: boolean; url: string | null; title: string | null; why: string; next: string } | null;
      context?: ActionContext;
      /** How the search was arrived at: the one selected, or the page's top search when none was. */
      search_source?: string;
      topic?: TopicPages;
      /** Another page of the site that suits the term better. Offered, never switched to. */
      better_page?: { url: string; fit: string; impressions: number; why: string } | null;
      focus?: EngineKind;
      focus_order_reason?: string | null;
      checklist?: ChecklistItem[];
      prior_rejections?: PriorRejection[];
      page_history?: PageHistory;
      observations?: { level: "problem" | "note" | "ok"; text: string; how?: string }[];
      opening?: string | null;
    };

export type CandidateTopic = { keyword: string | null; source: string; search?: string | null; pages: TopicPages | null };

export type WinnerPage = { url: string; read: boolean; reason?: string | null; title?: string | null; word_count?: number | null; schema_types?: string[] | null };
/** Who is winning for the term: the ranking pages, the AI platforms' answers, and what the winners do that the page does not. */
export type Winners = {
  search: {
    ranked: { rank: number; url: string; domain: string; title: string; content_type: string | null; content_style: string | null }[];
    client_ranks: { rank: number; url: string }[];
    pages: WinnerPage[];
  };
  llm: {
    ok: boolean; reason?: string; prompt?: string; run_date?: string;
    platforms?: { platform: string; brands: string[]; brand_mentioned: boolean; brand_rank: number | null; total_brands: number | null; client_cited: boolean; sources: number }[];
    cited_pages?: { url: string; domain: string; platforms: string[]; own: boolean; page_type: string }[];
    pages: WinnerPage[];
  };
  comparison: { ok: boolean; reason?: string; best_page: { verdict: "yes" | "partly" | "no"; why: string } | null; gaps: unknown[]; questions?: { checked: number; missing: { question: string; source: string; source_name: string; detail: string | null; why: string }[] } | null };
};

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
