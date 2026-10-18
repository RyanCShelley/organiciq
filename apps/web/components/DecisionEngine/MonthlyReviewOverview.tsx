import type { MonthlyRecord } from "@/lib/monthly-record";
import { visibilitySummary } from "@/lib/visibility-summary";
import { BRANCH_LABEL } from "@/lib/monthly-record";

export function MonthlyReviewOverview({ record, targetRate, suggestedFocus }: { record: MonthlyRecord; targetRate: number | null; suggestedFocus: string }) {
  const data = record.measurements;
  const visibility = visibilitySummary(data?.visibility.keywords);
  const visits = data?.traffic.current.total;
  const previous = data?.traffic.previous.total;
  const change = visits != null && previous ? (visits - previous) / previous * 100 : null;
  const rate = data?.leads.rate_pct;
  return <section className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6" aria-labelledby="month-overview">
    <div className="flex flex-wrap items-center justify-between gap-2"><h2 id="month-overview" className="text-lg font-bold">Last month at a glance</h2>{data?.sample && <span className="text-xs text-[var(--text-secondary)]">Synthetic sample account</span>}</div>
    <div className="mt-5 grid gap-5 sm:grid-cols-3">
      <div><p className="text-sm text-[var(--text-secondary)]">Visibility</p><p className="mt-1 text-2xl font-bold">{visibility.value}</p><p className="mt-1 text-sm">{visibility.label}</p>{data?.visibility.monthly_trend && data.visibility.monthly_trend.cohort > 0 && <p className="mt-1 text-xs text-[var(--text-secondary)]">Monthly matched terms: {data.visibility.monthly_trend.entered_top_10} entered the top 10 · {data.visibility.monthly_trend.left_top_10} left</p>}{visibility.note && <p className="mt-1 text-xs text-[var(--text-secondary)]">{visibility.note}</p>}</div>
      <div><p className="text-sm text-[var(--text-secondary)]">Site visits</p><p className="mt-1 text-2xl font-bold">{visits == null ? "Not measured" : visits.toLocaleString()}</p><p className="mt-1 text-sm">{change == null ? "No comparable prior period" : `${Math.abs(change).toFixed(1)}% ${change < 0 ? "lower" : "higher"} than the previous period`}</p><p className="mt-1 text-xs text-[var(--text-secondary)]">GA4 sessions · all channels</p></div>
      <div><p className="text-sm text-[var(--text-secondary)]">Lead conversion rate</p><p className="mt-1 text-2xl font-bold">{rate == null ? "Not measured" : `${rate.toFixed(2)}%`}</p><p className="mt-1 text-sm">{targetRate == null ? "Set a target rate to judge performance" : `Target ${targetRate}%${rate == null ? "" : rate >= targetRate ? " · on target" : " · below target"}`}</p><p className="mt-1 text-xs text-[var(--text-secondary)]">{data?.leads.count == null ? "Lead events not measured" : `${data.leads.count.toLocaleString()} lead events`} · each converting visit counts once</p></div>
    </div>
    <div className="mt-5 border-t border-[var(--border)] pt-4"><p className="text-sm"><strong>Engine’s suggested focus:</strong> {BRANCH_LABEL[suggestedFocus] ?? "Review the available evidence"}</p><p className="mt-1 text-sm text-[var(--text-secondary)]">Use this as the starting point for your client review. Choose the focus and work below.</p>{record.data_gaps.length > 0 && <p className="mt-2 text-sm">{record.data_gaps.length} data gaps limit this assessment. Details are available in the evidence.</p>}</div>
  </section>;
}
