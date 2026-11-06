export type OptKind = "opening" | "terms" | "faq";
export type OptDepth = "quick" | "deep" | "deepest";
export type OptQueueItem = { task_id: string; task_title: string; month: string; page: string; part_id: string; part_name: string; kind: OptKind; status: "open" | "done" };
export type OptQueue = { kinds: Record<OptKind, { label: string; does: string }>; queue: OptQueueItem[]; model_ready: boolean };
export type OptDraft = {
  id: string;
  kind: OptKind;
  status: "running" | "done" | "failed";
  error: string | null;
  depth: OptDepth;
  cost_usd: number;
  created_by: string;
  created_at: string | null;
  /** Where the page text came from: read live, the site crawl (our reader was blocked), or text a person pasted. */
  source?: { kind: "live" | "crawl" | "pasted"; note: string };
  searches_used?: number;
  from?: string;
  to?: string;
  // opening
  before?: string;
  diagnosis?: string;
  options?: { text: string; serves: string[]; why: string }[];
  // terms
  edits?: { before: string; after: string; terms: string[]; why: string }[];
  left_out?: string[];
  // faq
  items?: { question: string; answer: string; from_search: string }[];
  markup?: string;
  already_has_faq?: boolean;
};
export type OptPage = {
  url: string;
  title: string | null;
  searches: { query: string; impressions: number; clicks: number; position: number }[];
  searches_total: number;
  kinds: OptQueue["kinds"];
  drafts: Record<OptKind, OptDraft | null>;
  model_ready: boolean;
};
