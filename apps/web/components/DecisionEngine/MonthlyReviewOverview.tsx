import type { MonthlyRecord } from "@/lib/monthly-record";
import { BRANCH_LABEL } from "@/lib/monthly-record";

export function MonthlyReviewOverview({ record, targetRate, suggestedFocus }: { record: MonthlyRecord; targetRate: number | null; suggestedFocus: string }) {
  const data = record.measurements;
  const terms = data?.visibility.keywords.filter(term => term.priority) ?? [];
  const measured = terms.filter(term => term.status !== "not_measured");
  const topTen = measured.filter(term => term.position != null && term.position <= 10).length;
  const visits = data?.traffic.current.total;
  const previous = data?.traffic.previous.total;
  const change = visits != null && previous ? (visits - previous) / previous * 100 : null;
  const rate = data?.leads.rate_pct;
  return <section className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6" aria-labelledby="month-overview">
    <div className="flex flex-wrap items-center justify-between gap-2"><h2 id="month-overview" className="text-lg font-bold">Last month at a glance</h2>{data?.sample && <span className="text-xs text-[var(--text-secondary)]">Synthetic sample account</span>}</div>
    <div className="mt-5 grid gap-5 sm:grid-cols-3">
      <div><p className="text-sm text-[var(--text-secondary)]">Visibility</p><p className="mt-1 text-2xl font-bold">{measured.length ? `${topTen} of ${measured.length}` : "Not measured"}</p><p className="mt-1 text-sm">Measured priority keywords in the top 10</p>{terms.length > measured.length && <p className="mt-1 text-xs text-[var(--text-secondary)]">{terms.length - measured.length} priority terms still unmeasured</p>}</div>
      <div><p className="text-sm text-[var(--text-secondary)]">Site visits</p><p className="mt-1 text-2xl font-bold">{visits == null ? "Not measured" : visits.toLocaleString()}</p><p className="mt-1 text-sm">{change == null ? "No comparable prior period" : `${Math.abs(change).toFixed(1)}% ${change < 0 ? "lower" : "higher"} than the previous period`}</p><p className="mt-1 text-xs text-[var(--text-secondary)]">GA4 sessions · all channels</p></div>
      <div><p className="text-sm text-[var(--text-secondary)]">Lead conversion rate</p><p className="mt-1 text-2xl font-bold">{rate == null ? "Not measured" : `${rate.toFixed(1)}%`}</p><p className="mt-1 text-sm">{targetRate == null ? "Set a target rate to judge performance" : `Target ${targetRate}%${rate == null ? "" : rate >= targetRate ? " · on target" : " · below target"}`}</p><p className="mt-1 text-xs text-[var(--text-secondary)]">Configured lead events per visit</p></div>
    </div>
    <div className="mt-5 border-t border-[var(--border)] pt-4"><p className="text-sm"><strong>Engine’s suggested focus:</strong> {BRANCH_LABEL[suggestedFocus] ?? "Review the available evidence"}</p><p className="mt-1 text-sm text-[var(--text-secondary)]">Use this as the starting point for your client review. Choose the focus and work below.</p>{record.data_gaps.length > 0 && <p className="mt-2 text-sm">{record.data_gaps.length} data gaps limit this assessment. Details are available in the evidence.</p>}</div>
  </section>;
}
