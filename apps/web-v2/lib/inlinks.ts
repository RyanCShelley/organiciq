export type InSuggestion = {
  source_url: string;
  source_title: string;
  similarity: number;
  score: number;
  reasons: string[];
  source_clicks: number;
  suggested_anchor: string;
  anchor_type: string;
  anchor_alternates: { anchor: string; type: string }[];
  /** What kind of page the source is, in words. */
  source_type?: string;
  /** The source's paragraph closest to the target: where the link goes. Null when the crawl holds no body text for the page. */
  paragraph?: { heading: string | null; text: string } | null;
  /** A phrase already in that paragraph to link from, as the paragraph writes it. Null when a sentence would need adding. */
  anchor_in_paragraph?: string | null;
  paragraph_similarity?: number | null;
  /** What a person did with this link. "live" is set only by the live check. */
  status?: InStatus;
  /** The link text a person chose for this link. */
  chosen_anchor?: string | null;
  /** For a live link: the words the link was found with on the page, and when it was checked. */
  live_anchor?: string | null;
  checked_at?: string | null;
  /** The sentence written to carry this link, and the link text in it as written. Shared by the team. */
  sentence?: string | null;
  sentence_anchor?: string | null;
};
export type InStatus = "todo" | "added" | "live" | "skipped";
export type InTarget = {
  target_url: string;
  target_title: string;
  title: string;
  inbound: number;
  wanted: number;
  need: number;
  impressions: number;
  clicks: number;
  position: number | null;
  queries: string[];
  suggestions: InSuggestion[];
};
export type InData = {
  q: string | null;
  crawl_date: string;
  pages: number;
  summary: { targets: number; suggestions: number; orphans: number; live: number; ignored: number };
  targets: InTarget[];
  /** How many of the source pages had body paragraphs to compare. None means the crawl predates them. */
  body_text?: { sources: number; with_paragraphs: number };
  ignored: { id: string; target: string; source: string | null; status: string }[];
  rule: string;
  /** How alike (percent) a linking page must be, and how many editorial links a page should have. */
  min_similarity?: number;
  wanted_links?: number;
};
export type InResponse = { data: InData | null };
