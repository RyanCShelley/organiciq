export type ShDuplicateGroup = { text: string; urls: string[]; count: number };
export type ShSeverity = "high" | "medium" | "low";
export type ShIssueSource = "seo" | "geo";

export type ShPageIssue = {
  source: ShIssueSource;
  key: string;
  label: string;
  severity: ShSeverity;
  subject?: string | null;
  problem: string;
  fix: string;
};

export type ShPageEntry = {
  url: string;
  issue_count: number;
  seo_count: number;
  geo_count: number;
  highest_severity: ShSeverity;
  issues: ShPageIssue[];
};

export type ShCheck = {
  key: string;
  label: string;
  weight: number;
  score: number;
  affected: number;
  total: number;
  detail: string;
  urls: string[];
  duplicate_groups?: ShDuplicateGroup[];
};
export type ShItem = { text: string; url: string | null; subject?: string | null; problem?: string | null; fix?: string | null };
export type ShSignal = { key: string; label: string; weight: number; score: number | null; measured: boolean; detail: Record<string, unknown>; note: string; summary: string | null; items: ShItem[]; affected: number };
export type ShChange = { key: string; label: string; new: string[]; fixed: string[]; new_count: number; fixed_count: number };

export type ShData = {
  month: string;
  locked: boolean;
  crawl_date: string;
  crawl: { date: string; pages: number; limit: number; hit_limit: boolean };
  seo: { score: number; grade: string; checks: ShCheck[]; pages: number };
  geo: { score: number; grade: string; signals: ShSignal[]; partial: boolean; answers: { run_date: string; answers: number; platforms_naming: string[] } | null };
  previous: { month: string; seo: number; geo: number; crawl_date: string } | null;
  changes: ShChange[];
  by_page?: ShPageEntry[];
  site_wide?: ShPageIssue[];
};

export type ShCrawlSummary = { month: string; crawl_date: string; seo?: number | null; geo?: number | null };

export type ShResponse = {
  month: string | null;
  months: string[];
  crawls?: ShCrawlSummary[];
  compare_to?: string | null;
  data: ShData | null;
};
