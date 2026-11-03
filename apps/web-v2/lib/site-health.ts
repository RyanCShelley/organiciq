export type ShCheck = { key: string; label: string; weight: number; score: number; affected: number; total: number; detail: string; urls: string[] };
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
};

export type ShResponse = { month: string | null; months: string[]; data: ShData | null };
