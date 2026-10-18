export function dataGapGuidance(input: string, current?: { target_lead_rate_pct: number | null; conversion_page_count: number }): { title: string; next: string; kind: "setup" | "coverage" | "history"; tool?: "client" | "watchlist" } {
  if (input.includes("target lead conversion rate") && current?.target_lead_rate_pct != null) return {
    title: `Target rate is now configured: ${current.target_lead_rate_pct}%`, kind: "setup", tool: "client",
    next: "This limit belongs to the saved assessment. The current client setup contains a target rate. Rerun the assessment to evaluate the measured lead rate against it; no duplicate entry is needed.",
  };
  if (input.includes("no target or conversion pages declared") && current && current.conversion_page_count > 0) return {
    title: "Conversion pages are configured now", kind: "coverage", tool: "client",
    next: "The saved page-reach diagnostic could not assess mapped target pages. Conversion pages are present in current client setup. Build or review the keyword map, then rerun; you do not need to declare the same conversion pages again.",
  };
  if (input.includes("declared pages have no Watch List keyword mappings")) return {
    title: "Page reach needs keyword mappings", kind: "coverage", tool: "watchlist",
    next: "Target or conversion pages exist, but none has a usable Watch List keyword mapping for the reach test. Build or review the keyword map, then rerun. This is mapping coverage, not a missing conversion-page declaration.",
  };
  if (input.includes("no target or conversion pages declared")) return {
    title: "Declare target or conversion pages", kind: "setup", tool: "client",
    next: "No usable target pages were available to this saved assessment. Review the keyword map and conversion pages in client setup, then rerun. Existing declarations should be reused.",
  };
  if (input.includes("CTR reference") || input.includes("matched impressions") || input.includes("matching desktop US queries") || input.includes("query-level Search Console observations") || input.includes("CTR reference range")) return {
    title: "CTR reference covers a limited search sample", kind: "coverage", tool: "client",
    next: "The supplied industry CTR curve is the common baseline reference for all terms, devices and markets; it does not require an observed AI Overview. Sync query/page Search Console observations with positions 1–20 and at least 100 impressions. This is a benchmark estimate; actual visits come from GA4. If this saved run used the old SERP matching requirement, rerun it.",
  };
  if (input.includes("session-based lead conversion baseline")) return {
    title: "The existing baseline uses a different lead-rate definition", kind: "history",
    next: "Your saved baseline is preserved. It counts lead events per visit; the new conversion rate counts visits producing a lead once. The engine does not compare these different measures. A matching session-based baseline can be reviewed separately without resetting your history.",
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
    title: "Watch List defines the target terms", kind: "setup", tool: "watchlist",
    next: "All active Watch List keywords and prompts are client targets. No separate priority selection is needed. Rerun this older assessment to use the full Watch List; keyword rankings and prompt mentions/citations are evaluated separately.",
  };
  if (input.includes("no dated Watch List keyword rankings")) return {
    title: "Watch List rankings are not measured yet", kind: "coverage", tool: "watchlist",
    next: "Sync dated keyword rankings for the assessment period. All active Watch List keywords are targets; no priority flag or page mapping is required to measure their rankings.",
  };
  return { title: input, next: "Review this source requirement before using the affected diagnostic to choose work.", kind: "setup" };
}
