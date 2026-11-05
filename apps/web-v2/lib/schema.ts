export type ScItem = { url: string; text: string };
export type ScType = {
  page_type: string;
  label: string;
  pages: number;
  expects: string[];
  recommended: string[];
  score: number | null;
  affected: number;
  items: ScItem[];
  recommended_affected: number;
  recommended_items: ScItem[];
};
export type ScCategory = "error" | "warning" | "enhancement" | "informational";
export type ScLayer = "schemaorg" | "graph" | "google" | "recommendation";
/** One finding on one page. */
export type ScFinding = {
  rule_id: string;
  layer: ScLayer;
  category: ScCategory;
  title: string;
  message: string;
  explanation: string;
  recommendation: string;
  doc: string;
  url: string;
  entity_id: string | null;
  type: string | null;
  property: string | null;
  evidence: unknown;
  auto_fixable: boolean;
  confidence: "high" | "medium" | "low";
};
/** Findings with the same cause, across pages: one row with the true page count. */
export type ScFindingGroup = Omit<ScFinding, "url" | "message" | "evidence" | "entity_id"> & {
  template_key: string;
  pages: number;
  occurrences: number;
  sample_urls: string[];
  example: { url: string; entity_id: string | null; message: string; evidence: unknown };
};
export type ScCheck = { key: string; label: string; status: "pass" | "warn" | "fail" | "ignored"; detail: string; fix: string | null };
export type ScIgnoreScope = "check" | "expect" | "page_type" | "page" | "cleanup";
export type ScIgnoreRule = { id: string; scope: ScIgnoreScope; key: string; label: string };
export type ScConcept = { id: string; name: string; qid: string; label: string; description: string; url: string };
export type ScData = {
  crawl_date: string;
  pages: number;
  with_markup: number;
  score: number;
  cleanups: number;
  types: ScType[];
  findings: ScFindingGroup[];
  finding_counts: Record<ScCategory, { groups: number; pages: number; occurrences: number }>;
  validator: { schemaorg_version: string; google_reviewed: string };
  fixes: { text: string; pages: number; example: string; ignore: { scope: ScIgnoreScope; key: string; label: string } }[];
  ignored: ScIgnoreRule[];
  present: { type: string; pages: number }[];
  invalid: { url: string; error: string }[];
  entity: { brand: string; names: { name: string; blocks: number }[]; same_as: string[]; checks: ScCheck[] };
  concepts: ScConcept[];
};
export type ScResponse = { data: ScData | null; ready: boolean; depths: Record<string, string> };
export type ScDepth = "quick" | "deep" | "deepest";
export type ScCandidate = { qid: string; label: string; description: string; url: string };

export type ScReport = {
  id: string;
  kind: "audit" | "markup";
  status: "running" | "done" | "failed";
  error: string | null;
  depth: ScDepth;
  cost_usd: number;
  created_by: string;
  created_at: string | null;
  // audit
  intent?: string;
  intent_explanation?: string;
  diagnosis?: string[];
  fix_plan?: string[];
  concepts?: { name: string; approved_qid: string; candidates: ScCandidate[] }[];
  // markup
  json_ld?: string;
  approved?: { name: string; qid: string }[];
  post_corrections?: string[];
};
export type ScPage = {
  url: string;
  page_type: string;
  present: string[];
  missing_required: string[];
  missing_recommended: string[];
  corrections: { transform: string; node_id: string; detail: string }[];
  findings?: ScFinding[];
  score: number;
  existing: string[];
  reports: { audit?: ScReport; markup?: ScReport };
};
