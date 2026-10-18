export function dataGapGuidance(input: string): { title: string; next: string; kind: "setup" | "coverage" | "history"; tool?: "client" | "watchlist" } {
  if (input.includes("CTR reference") || input.includes("matched impressions") || input.includes("matching desktop US queries")) return {
    title: "CTR reference covers a limited search sample", kind: "coverage", tool: "client",
    next: "Sync query/page Search Console data and collect dated desktop US SERP observations for those queries. Only queries observed with an AI Overview can use the supplied curve. Mobile, other markets and unmatched queries stay outside this diagnostic; they still count in actual traffic.",
  };
  if (input.includes("target lead conversion rate")) return {
    title: "Set the target lead conversion rate", kind: "setup", tool: "client",
    next: "Choose the target rate alongside the monthly lead goal when locking a baseline. For an existing baseline, use Set target conversion rate under Explore the evidence → Leads. The measured baseline rate and the target are separate numbers.",
  };
  if (input.includes("measured lead rate") || input.includes("measured sessions")) return {
    title: "Lead-rate observations are missing for this period", kind: "setup", tool: "client",
    next: "Confirm the client's configured lead events and sync GA4 visits and events for the assessment month. A rate needs the numerator and denominator from the same period; setting a target alone does not supply these observations.",
  };
  if (input.includes("visibility history")) return {
    title: "Comparable visibility trend is not available yet", kind: "history", tool: "watchlist",
    next: "The engine first compares at least five of the same keywords with dated readings in both months. Sync historical keyword positions for both months. A 90-day site-score comparison is another source when available; a current summary cannot reconstruct its past score. Current visibility still works with one month of data.",
  };
  if (input.includes("keyword group is marked priority")) return {
    title: "Choose priority keywords", kind: "setup", tool: "watchlist",
    next: "Mark the terms that matter in the keyword and prompt targets. Existing measured tracked keywords can still appear in the overview; choosing priorities defines the smaller set used by the priority-coverage test.",
  };
  return { title: input, next: "Review this source requirement before using the affected diagnostic to choose work.", kind: "setup" };
}
