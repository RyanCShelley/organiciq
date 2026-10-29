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
