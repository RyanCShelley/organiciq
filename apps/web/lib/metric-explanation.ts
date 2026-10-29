import type { BranchTest } from "./monthly-record";

export function metricExplanation(test: BranchTest): { calculation: string; source: string; limitation: string } {
  const e = test.evidence ?? {};
  const pct = test.value == null ? "unknown" : `${Math.round(test.value)}%`;
  if (test.id === "V1") return {
    calculation: e.priority_keywords != null && e.in_top_10 != null
      ? `${e.in_top_10} terms in the top 10 ÷ ${e.priority_keywords} measured ${e.scope === "watchlist" ? "Watch List" : "priority"} terms × 100 = ${pct}`
      : "Top-10 priority terms ÷ measured priority terms × 100. This saved run has no underlying counts; rerun to record them.",
    source: e.scope === "watchlist" ? "Active Watch List keywords joined to dated ranking observations as of the assessment date." : "Legacy priority keyword targets joined to tracked positions in this saved run. Rerun to use the full Watch List.",
    limitation: "All active Watch List keywords define the target set for new assessments. Unmeasured terms stay unknown; prompt mentions and citations are measured separately. Older runs may use the former priority subset.",
  };
  if (test.id === "V2" && e.source === "matched_monthly_keyword_history") return {
    calculation: `${e.declined} terms losing at least 3 positions ÷ ${e.cohort} terms observed in both months × 100 = ${pct}`,
    source: "Dated keyword rankings for a matched cohort across the assessment month and preceding calendar month.",
    limitation: "At least five paired terms are needed for this diagnostic. The 30% threshold is an engine review rule, not proof of a business constraint. New or unmeasured terms are excluded; see individual movements and impression trends too.",
  };
  if (test.id === "T1") return {
    calculation: e.formula_version !== 2
      ? "Superseded calculation in this saved run. Rerun the assessment to use the bounded CTR benchmark gap."
      : e.estimated_missed_clicks != null && e.actual_clicks != null
        ? `${e.estimated_missed_clicks} estimated shortfall ÷ (${e.estimated_missed_clicks} shortfall + ${e.actual_clicks} earned clicks) × 100 = ${pct}`
        : "Estimated shortfall ÷ (shortfall + earned clicks) × 100. Underlying counts unavailable.",
    source: e.application === "all_terms_reference" ? `All-device, all-market query/page Search Console observations using the supplied industry curve as a common reference. ${e.matched_impressions} of ${e.total_query_impressions} impressions have supported positions (1–20). No observed AI Overview is required.` : e.benchmark ? `Desktop US query/page Search Console observations matched to a dated AI Overview SERP snapshot. ${e.matched_impressions} of ${e.total_query_impressions} query impressions match (${Number(e.coverage_pct ?? 0).toFixed(1)}% coverage).` : "Search Console clicks and impressions versus a reference CTR curve.",
    limitation: "A benchmark diagnostic, not measured missed traffic or a forecast. GA4 sessions measure visits. Query intent, device and SERP features affect CTR; the supplied desktop study is applied as your planning reference across terms, not a measured expectation for each device, market or SERP.",
  };
  if (test.id === "L1") return {
    calculation: e.formula_version === 3
      ? `Visit-based lead conversion rate ${e.lead_rate_pct ?? "unknown"}% compared with target ${e.target_rate_pct ?? "not configured"}%. Visits with at least one configured lead event ÷ matching visits × 100.`
      : e.formula_version === 2
      ? `Actual lead event rate ${e.lead_rate_pct ?? "unknown"}% compared with target ${e.target_rate_pct ?? "not configured"}%. Rate = configured lead events ÷ sessions × 100.`
      : "This saved run used lead-count goal pace. It predates the conversion-rate target and should not be read as a conversion rate.",
    source: "Configured GA4 lead events and GA4 sessions, all channels over the same period.",
    limitation: e.formula_version === 3 ? "Each visit counts once, even with several lead events. This is not a count of unique people or qualified leads. Session-based targets are configured separately from legacy event-rate targets." : "This saved event-based calculation may include repeated submissions. Re-run to use visit-based conversion and its separate target.",
  };
  return { calculation: test.display ?? `${test.metric_label}: ${pct}`, source: "Saved assessment test.", limitation: test.missing ?? "Read this test against its threshold and the source coverage for this run." };
}
