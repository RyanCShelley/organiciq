import type { BranchTest } from "./monthly-record";

export function metricExplanation(test: BranchTest): { calculation: string; source: string; limitation: string } {
  const e = test.evidence ?? {};
  const pct = test.value == null ? "unknown" : `${Math.round(test.value)}%`;
  if (test.id === "V1") return {
    calculation: e.priority_keywords != null && e.in_top_10 != null
      ? `${e.in_top_10} terms in the top 10 ÷ ${e.priority_keywords} measured priority terms × 100 = ${pct}`
      : "Top-10 priority terms ÷ measured priority terms × 100. This saved run has no underlying counts; rerun to record them.",
    source: "Confirmed priority keyword targets joined to tracked keyword positions.",
    limitation: "This describes the measured priority subset, not every keyword or AI prompt. A small or incomplete watchlist limits the conclusion.",
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
    source: e.benchmark ? `Desktop US query/page Search Console observations matched to a dated AI Overview SERP snapshot. ${e.matched_impressions} of ${e.total_query_impressions} query impressions match (${Number(e.coverage_pct ?? 0).toFixed(1)}% coverage).` : "Search Console clicks and impressions versus a reference CTR curve.",
    limitation: "A benchmark diagnostic, not measured missed traffic or a forecast. GA4 sessions measure visits. Query intent, device and SERP features affect CTR; a desktop AI Overview curve is a separate scenario, not a universal expectation.",
  };
  if (test.id === "L1") return {
    calculation: e.formula_version === 2
      ? `Actual lead event rate ${e.lead_rate_pct ?? "unknown"}% compared with target ${e.target_rate_pct ?? "not configured"}%. Rate = configured lead events ÷ sessions × 100.`
      : "This saved run used lead-count goal pace. It predates the conversion-rate target and should not be read as a conversion rate.",
    source: "Configured GA4 lead events and GA4 sessions, all channels over the same period.",
    limitation: "Lead events may include repeated submissions. Use unique/qualified leads only when a deduplicated source is available. The target rate is explicitly configured, not inferred from a lead-count goal.",
  };
  return { calculation: test.display ?? `${test.metric_label}: ${pct}`, source: "Saved assessment test.", limitation: test.missing ?? "Read this test against its threshold and the source coverage for this run." };
}
