export type WatchlistKeyword = {
  id: string;
  keyword: string;
  volume: number | null;
  difficulty: number | null;
  intent: string | null;
  paired_ai_prompt: string | null;
  notes: string | null;
};

export type WatchlistBucket = {
  id: string;
  name: string;
  sort_order: number;
  keywords: WatchlistKeyword[];
};

export type Watchlist = { buckets: WatchlistBucket[]; keyword_count: number };

type Issue = { line: number; keyword?: string; reason: string };

export type ImportReport = {
  dry_run: boolean;
  rows_read: number;
  buckets_created: number;
  keywords_created: number;
  keywords_updated: number;
  keywords_unchanged: number;
  topics_inherited: number;
  skipped: Issue[];
  warnings: Issue[];
  ignored_columns: string[];
};

export type ImportResult = { ok: true; report: ImportReport } | { ok: false; error: string };

export type ActionResult<T> =
  | { ok: true; data: T }
  | { ok: false; error: string; status?: number };

export type WatchlistKeywordCreateInput = {
  keyword: string;
  bucket_id?: string | null;
  bucket_name?: string | null;
  volume?: number | null;
  difficulty?: number | null;
  intent?: string | null;
  paired_ai_prompt?: string | null;
  notes?: string | null;
};

export type WatchlistKeywordUpdateInput = {
  keyword?: string;
  bucket_id?: string | null;
  bucket_name?: string | null;
  volume?: number | null;
  difficulty?: number | null;
  intent?: string | null;
  paired_ai_prompt?: string | null;
  notes?: string | null;
};

export type WatchlistKeywordAddResponse = {
  id: string;
  keyword: string;
  keyword_key: string;
  bucket_id: string;
  bucket_name: string;
  created: boolean;
  bucket_created: boolean;
};

export type WatchlistKeywordDetail = WatchlistKeyword & {
  bucket_id: string;
  bucket_name: string;
  source: string;
};

export type WatchlistKeywordBulkAddResponse = {
  results: WatchlistKeywordAddResponse[];
  created_count: number;
  existing_count: number;
};

export type WatchlistBucketDeleteResponse = {
  deleted: boolean;
  id: string;
  deleted_keywords: number;
  cleared_focuses: number;
};

export type WatchlistSuggestion = {
  query: string;
  key: string;
  page: string | null;
  impressions: number;
  impressions_before: number;
  impressions_change_pct: number | null;
  clicks: number;
  position: number | null;
  position_before: number | null;
  move: number | null;
  ctr: number | null;
  signals: string[];
  relevance_note: string;
};

export type WatchlistSuggestionsResponse = {
  gsc_connected: boolean;
  has_gsc_data: boolean;
  google_through: string | null;
  days: number;
  suggestions: WatchlistSuggestion[];
};
