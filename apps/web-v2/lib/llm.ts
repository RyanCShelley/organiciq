export type Pair = { current: number; previous: number | null; delta: number | null };

export type LlmRunInfo = {
  id: string;
  started_at: string;
  completed_at: string | null;
  status: string;
  platforms: string[];
  total_calls: number | null;
  total_errors: number;
  estimated_cost_usd: number | null;
  triggered_by: string | null;
  error: string | null;
};

export type PlatformRow = {
  platform: string;
  queries_checked: number;
  by_type: { cited_mentioned: number; cited: number; mentioned: number; not_visible: number };
  mentions: Pair;
  citations: Pair;
  visibility_rate: Pair;
  avg_brand_rank: { current: number | null; previous: number | null };
};

export type SovRow = {
  topic_cluster: string;
  brand: string;
  is_self: boolean;
  mentions: Pair;
  share: Pair;
  responses: number;
};

export type QueryRow = {
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

export type LlmOverview = {
  brand: string;
  runs: LlmRunInfo[];
  running: LlmRunInfo | null;
  run: LlmRunInfo | null;
  previous_run?: LlmRunInfo | null;
  summary?: { mentions: Pair; citations: Pair; visibility_rate: Pair; responses: number };
  platforms?: PlatformRow[];
  share_of_voice?: SovRow[];
  queries?: QueryRow[];
  movers?: { improved: QueryRow[]; declined: QueryRow[] };
  trend?: { run_id: string; started_at: string; visibility_rate: number; mentions: number; citations: number }[];
  errors?: { platform: string; message: string; count: number }[];
  other_brands?: { name: string; count: number }[];
};

export type LlmSettings = {
  brand_name: string;
  brand_patterns: string[];
  domain: string;
  competitors: { domain: string; name: string; patterns: string[] }[];
  prompts: number;
  clusters: string[];
  platforms: { key: string; name: string; enabled: boolean }[];
  calls_per_run: number;
};

export type LlmResponseRow = {
  query: string;
  keyword: string | null;
  topic_cluster: string | null;
  platform: string;
  visibility: string | null;
  brand_mentioned: boolean;
  url_cited: boolean;
  cited_urls: string[];
  position: string | null;
  brand_rank: number | null;
  competitors: string[];
  other_brands: string[];
  answer: string | null;
  error: string | null;
};

export type LlmResult<T> = { ok: true; value: T } | { ok: false; error: string };
