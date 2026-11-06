export type ContentDepthChoice = "quick" | "deep" | "deepest";

export type GapSource = "searched" | "competitor" | "watchlist";
export type Gap = {
  term: string;
  sources: GapSource[];
  impressions: number;
  clicks: number;
  position: number | null;
  volume: number | null;
  difficulty: number | null;
  opportunity: number;
  priced: boolean;
  intents: string[];
  competitors: { domain: string; position: number }[];
  also_covers: string[];
  nearest: { url: string; title: string | null; shared: string[] }[];
  why: string;
  action: string;
  page_now: string | null;
  ignored: boolean;
};
export type Gaps = {
  blocked: string | null;
  q?: string | null;
  showing_ignored?: boolean;
  counts: { gaps?: number; searched?: number; competitor?: number; watchlist?: number; opportunity?: number; pages_searched?: number };
  ignored_total: number;
  gaps: Gap[];
  gaps_total?: number;
  notes: string[];
  model_ready?: boolean;
  calendar?: Record<string, CalendarStatus>;
  can_edit?: boolean;
};

export type Draft = {
  id: string;
  status: "running" | "done" | "failed";
  error: string | null;
  depth: ContentDepthChoice;
  cost_usd: number;
  created_by: string;
  created_at: string | null;
  page_read?: boolean;
};
export type Brief = Draft & {
  working_title?: string;
  page_type?: string;
  angle?: string;
  sections?: string[];
  questions?: string[];
  entities?: string[];
  target_words?: number | null;
  avoid?: string[];
  link_from?: { url: string; anchor_idea: string }[];
};
export type Topic = { label: string; why: string; content_type: string; priority: "high" | "medium" | "low"; example_searches: string[]; next_to: string };
export type TopicsDraft = Draft & { topics?: Topic[]; pages_used?: number; searches_used?: number };
export type TopicSearch = { term: string; volume: number | null; difficulty: number | null; impressions: number; clicks: number; position: number | null; gap: boolean; tracked: boolean };
export type TopicDetail = { topic: Topic; searches: TopicSearch[]; draft: Brief | null; calendar: CalendarStatus | null; can_edit: boolean; model_ready: boolean };
export type TopicsResponse = { draft: TopicsDraft | null; dismissed: string[]; model_ready: boolean };

export type RefreshLabel = "tracking" | "growing" | "steady" | "slipping" | "losing" | "quiet" | "new";
export type RefreshPage = {
  url: string;
  title: string | null;
  label: RefreshLabel;
  status: string;
  sessions: { current: number; previous: number; change_pct: number | null };
  three_months: { current: number; last_year: number; change_pct: number | null };
  at_stake: number;
  last_updated: string | null;
  months_since_update: number | null;
  words: number | null;
  stale: boolean;
  thin: boolean;
  reasons: string[];
  ignored: boolean;
  watch: WatchTerm[];
  watch_slipping: boolean;
  /** The watchlist terms the page is for (ranked for, or named in its title or address). */
  on_topic: boolean;
  in_focus: boolean;
  topics: { term: string; volume: number | null; focus: boolean }[];
  /** On a target topic, related to one by meaning, or neither. */
  tier: "topic" | "related" | "unrelated";
  related: { term: string; topic: string | null; similarity: number } | null;
  /** Analytics sessions fell but Search Console clicks held up with the site, so the visits may be unrecorded. */
  tracking_gap: boolean;
  /** Search Console, over the last three months against the same three a year earlier. */
  search: { clicks: Change; impressions: Change };
  /** Bing clicks, counted for the page Search Console shows for each search. Null when Bing has none for this page. */
  bing: { clicks: Change } | null;
};
export type Change = { current: number; last_year: number; change_pct: number | null };
export type WatchTerm = { term: string; position: number; change: number | null; slipping: boolean; striking: boolean; volume: number | null };
export type Competing = { query: string; impressions: number; pages: { url: string; impressions: number; clicks: number; position: number }[] };
export type SplitSearchPage = {
  url: string;
  title: string | null;
  impressions: number;
  clicks: number;
  ctr: number;
  position: number;
  months: { month: string; impressions: number; clicks: number; position: number | null }[];
  sessions: { current: number; last_year: number; change_pct: number | null };
  words: number | null;
  last_updated: string | null;
  months_since_update: number | null;
};
export type SplitSearch = {
  query: string;
  month: string;
  impressions: number;
  clicks: number;
  pages: SplitSearchPage[];
  leaders: { month: string; url: string | null }[];
  swapped: boolean;
  swaps: { from: string; to: string; month: string }[];
  other_searches: Competing[];
};
export type Refreshes = {
  month: string;
  q: string | null;
  showing_ignored: boolean;
  has_last_year: boolean;
  /** False when the client has no watchlist yet, so pages are not split by topic. */
  topics_known: boolean;
  site: { sessions: { current: number; previous: number }; three_months: Change; clicks: Change };
  /** Whether Search Console has enough data for last year to judge a page's clicks against the site's trend. */
  search_available: boolean;
  bing_available: boolean;
  counts: { pages: number; losing: number; quiet: number; slipping: number; stale: number; thin: number; watch: number; at_stake: number; off_topic: number; related: number; tracking_gap: number };
  ignored_total: number;
  pages: RefreshPage[];
  pages_total: number;
  competing: Competing[];
  notes: string[];
  model_ready: boolean;
  calendar: Record<string, CalendarStatus>;
  can_edit: boolean;
};
export type ClickWindow = { impressions: number; clicks: number } | null;
export type RefreshDetail = {
  url: string;
  month: string;
  title: string | null;
  words: number | null;
  last_updated: string | null;
  sessions: { month: string; sessions: number }[];
  lost: { query: string; clicks: { current: number; previous: number }; impressions: { current: number; previous: number }; position: { current: number | null; previous: number }; clicks_lost: number }[];
  competing: Competing[];
  changes: { date: string; kind: string; text: string; before: ClickWindow; after: ClickWindow; measured_on: string | null }[];
  depth: { score: number; signals: { stats_hits?: number; dates_present?: number; role_mentions?: number; list_items?: number; table_present?: boolean; word_count?: number; quotes?: number; citation_marker?: boolean } } | null;
  read: { ok: boolean; note: string | null };
  watch: WatchTerm[];
  plan: RefreshPlan | null;
};
export type RefreshPlan = Draft & {
  month?: string;
  diagnosis?: string;
  keep?: string[];
  add?: { section: string; why: string }[];
  change?: { what: string; why: string }[];
  remove?: string[];
  merge_with?: string;
  target_words?: number | null;
};

export type CalendarStatus = "idea" | "planned" | "writing" | "review" | "published" | "dropped";
export type CalendarItem = {
  id: string;
  kind: "new_page" | "refresh";
  title: string;
  target: string;
  source_area: "gap" | "refresh" | "topic" | "manual";
  source_key: string | null;
  status: CalendarStatus;
  due: string | null;
  assignee_email: string | null;
  notes: string | null;
  teamwork_task_id: string | null;
  teamwork_task_url: string | null;
  teamwork_tasklist_id?: string | null;
  published_at: string | null;
  created_by: string;
  created_at: string | null;
};
export type CalendarData = {
  items: CalendarItem[];
  can_edit: boolean;
  teamwork: { configured: boolean; project_id: string | null };
  counts: Record<string, number>;
};
export type Person = { email: string; name: string | null };
