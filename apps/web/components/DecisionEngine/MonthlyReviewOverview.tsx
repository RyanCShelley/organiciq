import type { MonthlyRecord } from "@/lib/monthly-record";
import { BRANCH_LABEL, formatDay } from "@/lib/monthly-record";
import { visibilitySummary } from "@/lib/visibility-summary";
import "./MonthlyFlow.css";

const tone = (value: number | null | undefined) =>
  value == null || value === 0 ? "steady" : value > 0 ? "positive" : "negative";
const fmt = (n: number | null | undefined, rate = false) =>
  n == null ? "Not measured" : rate ? `${n.toFixed(2)}%` : n.toLocaleString();
function Comparison({
  current,
  previous,
  rate = false,
}: {
  current: number | null | undefined;
  previous: number | null | undefined;
  rate?: boolean;
}) {
  const max = Math.max(current ?? 0, previous ?? 0);
  return (
    <div className="comparisonbars">
      {[
        ["Previous", previous],
        ["Current", current],
      ].map(([label, value]) => (
        <div key={String(label)}>
          <span>{label}</span>
          <div className="bartrack">
            <div
              className={`bar ${label === "Current" ? "current" : "previous"}`}
              style={{
                width:
                  typeof value === "number" && max > 0
                    ? `${(value / max) * 100}%`
                    : "0%",
              }}
            />
          </div>
          <b>{fmt(value as number | null, rate)}</b>
        </div>
      ))}
    </div>
  );
}
export function MonthlyReviewOverview({
  record,
  targetRate,
  suggestedFocus,
  suggestedReason,
  capacity,
}: {
  record: MonthlyRecord;
  targetRate: number | null;
  suggestedFocus: string;
  suggestedReason?: string | null;
  capacity?: number;
}) {
  const d = record.measurements;
  const keywords = d?.visibility.keywords ?? [];
  const measured = keywords.filter((k) => k.status !== "not_measured");
  const top = measured.filter(
    (k) => k.position != null && k.position > 0 && k.position <= 10,
  ).length;
  const pct = measured.length ? (top / measured.length) * 100 : null;
  const trend = d?.visibility.monthly_trend;
  const visits = d?.traffic.current.total,
    priorVisits = d?.traffic.previous.total;
  const rate = d?.leads.rate_pct,
    priorRate = d?.leads.previous_rate_pct;
  const visitChange =
    visits != null && priorVisits != null && priorVisits > 0
      ? ((visits - priorVisits) / priorVisits) * 100
      : null;
  const rateChange =
    rate != null && priorRate != null ? rate - priorRate : null;
  return (
    <section
      className="monthlyflow overview rounded-xl border border-[var(--border)] bg-[var(--surface)]"
      aria-labelledby="month-overview"
    >
      <div className="flex flex-wrap justify-between gap-3">
        <h2 id="month-overview" className="text-xl font-bold">
          1. What changed this month?
        </h2>
        <p className="text-sm text-[var(--text-secondary)]">
          {d
            ? `${formatDay(d.start)}–${formatDay(d.end)} · compared with ${formatDay(d.prior_start)}–${formatDay(d.prior_end)}`
            : "Saved assessment"}
          {d?.sample ? " · Synthetic sample" : ""}
        </p>
      </div>
      <div className="visualmetrics">
        <article className="visualmetric">
          <p className="metriclabel">Top-10 keyword coverage</p>
          <div className="visibilityhero">
            <div
              className="rankring"
              style={{
                background: `conic-gradient(#087c75 ${pct ?? 0}%, #e5ecee 0)`,
              }}
            >
              <div>
                <strong>{pct == null ? "—" : `${pct.toFixed(0)}%`}</strong>
                <small>in the top 10</small>
              </div>
            </div>
            <div className="rankcount">
              <strong>
                {measured.length ? (
                  <>
                    {top} <span>of {measured.length}</span>
                  </>
                ) : (
                  "Not measured"
                )}
              </strong>
              <p>measured tracked terms</p>
            </div>
          </div>
          {trend && trend.cohort > 0 ? (
            <>
              <span
                className={`movement ${tone(trend.entered_top_10 - trend.left_top_10)}`}
              >
                {trend.entered_top_10} entered · {trend.left_top_10} left the
                top 10
              </span>
              <p className="metricfoot">
                Compared across {trend.cohort} of the same terms in both months.
                Net {trend.entered_top_10 - trend.left_top_10 > 0 ? "+" : ""}
                {trend.entered_top_10 - trend.left_top_10} terms.
              </p>
            </>
          ) : (
            <p className="metricfoot">No comparable prior ranking cohort.</p>
          )}
          <p className="metricfoot">{visibilitySummary(keywords).note}</p>
        </article>
        <article className="visualmetric">
          <p className="metriclabel">Site visits</p>
          <div className="metricbig">{fmt(visits)}</div>
          <span className={`movement ${tone(visitChange)}`}>
            {visitChange == null
              ? "No comparable prior period"
              : `${visitChange > 0 ? "+" : ""}${visitChange.toFixed(1)}%`}
          </span>
          {visits != null && priorVisits != null && (
            <span className="metricdelta">
              {visits - priorVisits > 0 ? "+" : ""}
              {fmt(visits - priorVisits)} visits
            </span>
          )}
          <Comparison current={visits} previous={priorVisits} />
          <p className="metricfoot">GA4 sessions · all channels</p>
        </article>
        <article className="visualmetric">
          <p className="metriclabel">Lead conversion rate</p>
          <div className="metricbig">{fmt(rate, true)}</div>
          <span className={`movement ${tone(rateChange)}`}>
            {rateChange == null
              ? "No comparable prior rate"
              : `${rateChange > 0 ? "+" : ""}${rateChange.toFixed(2)} percentage points`}
          </span>
          <Comparison current={rate} previous={priorRate} rate />
          <p className="metricfoot">
            Visits generating at least one lead.{" "}
            {targetRate == null
              ? "Target rate awaits review."
              : `Target: ${targetRate}%.`}{" "}
            {d?.leads.count == null
              ? ""
              : `${fmt(d.leads.count)} lead events, including repeats.`}
          </p>
        </article>
      </div>
      <div className="direction">
        <div>
          <p className="directioneyebrow">ENGINE’S SUGGESTED DIRECTION</p>
          <h3>{BRANCH_LABEL[suggestedFocus] ?? "Review available evidence"}</h3>
          <p>
            {suggestedReason ??
              (record.override
                ? "Review the linked page findings and observed changes below before choosing this month’s focus."
                : record.reason_text)}
          </p>
          <p className="muted">
            Choose the growth actions supported by specific page findings below.
          </p>
        </div>
        <aside>
          <p>
            <strong>{capacity ?? record.action_slots}</strong> growth action
            allowance
          </p>
          <p>
            Assessment confidence: <strong>{record.confidence}</strong>
          </p>
          {record.confidence_reasons?.map((r) => (
            <p className="metricfoot" key={r.code}>
              {r.text}
            </p>
          ))}
        </aside>
      </div>
    </section>
  );
}
