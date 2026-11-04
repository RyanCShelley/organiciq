import { ServiceReportingSummary } from "@/components/analytics/ServiceReportingSummary";
import { LeadRateGoal } from "./LeadRateGoal";
export type MeasurementSettingsProps = { clientId: string; slug: string; target: number | null };
export type Measurements = {
  service_reporting?: import("@/lib/dashboard").ServiceReportingData;
  version: number; start: string; end: string; prior_start: string; prior_end: string;
  sample?: boolean;
  source_note?: string;
  visibility: {
    note: string;
    monthly_trend?: { scope: string; cohort: number; declined: number; improved: number; entered_top_10: number; left_top_10: number; rows: { text: string; previous: number; current: number; previous_date: string; current_date: string }[] };
    keywords: { text: string; priority: boolean; position: number | null; observed_on?: string | null; status: string; target_url: string | null; ranking_url: string | null }[];
    prompts: { text: string; provider: string | null; mentioned: boolean | null; cited: boolean | null; observed_on: string | null }[];
  };
  traffic: { current: { total: number | null; channels: Record<string, number> }; previous: { total: number | null; channels: Record<string, number> }; source: string; ctr_reference?: { scope: string; period: string; positions: { position: number; ctr_pct: number }[] } };
  leads: { count: number | null; sessions: number | null; rate_pct: number | null; previous_rate_pct?: number | null; event_rate_pct?: number | null; lead_sessions?: number | null; session_measurement?: { sessions: number | null; status: string; reason?: string }; target_rate_pct: number | null; monthly_goal: number | null; source: string };
};
const number = (value: number | null | undefined) => value == null ? "Not measured" : value.toLocaleString("en-US", { maximumFractionDigits: 1 });
const presence = (value: boolean | null) => value === true ? "Yes" : value === false ? "No" : "Not measured";
const names: Record<string, string> = { organic_search: "Organic search", direct_unattributed: "Direct / unattributed", ai_referral: "AI referrals", referral: "Referral", paid_search: "Paid search", paid_social: "Paid social", display: "Display", cross_network: "Cross-network", other_paid: "Other paid", social: "Social", email: "Email", other: "Other" };

export function MeasurementSummary({ data, settings }: { data?: Measurements; settings?: MeasurementSettingsProps }) {
  if (!data) return <p className="mt-5 rounded-md bg-[var(--surface-muted)] p-4 text-sm">This saved assessment predates the revised measurements. Run a new assessment to capture individual term visibility, all-channel visits and lead rates. The old percentages are not summary scores.</p>;
  const { visibility, traffic, leads } = data;
  const channels = [...new Set(["organic_search", "direct_unattributed", "ai_referral", ...Object.keys(traffic.current.channels), ...Object.keys(traffic.previous.channels)])];
  return <div className="mt-5 space-y-5">
    <ServiceReportingSummary data={data.service_reporting} />
    <p className="text-sm text-[var(--text-secondary)]">Measured period: {data.start}–{data.end}. Traffic comparison: {data.prior_start}–{data.prior_end}.{data.sample && <strong> Synthetic sample data for this preview.</strong>}</p>
    {data.source_note && <p className="text-xs text-[var(--text-secondary)]">{data.source_note}</p>}
    <section className="rounded-lg border border-[var(--border)] p-4">
      <h3 className="font-semibold">Visibility · individual keywords and prompts</h3>
      <p className="mt-1 text-sm">Showing up for a keyword and being mentioned or cited in an AI answer are separate observations.</p>
      {visibility.keywords.length ? <div className="mt-3 overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr><th className="p-2">Keyword</th><th className="p-2">Position</th><th className="p-2">Observed</th><th className="p-2">Actual ranking page</th></tr></thead><tbody>{visibility.keywords.map((term, i) => <tr key={i} className="border-t border-[var(--border)]"><td className="p-2">{term.text}{term.priority ? " · priority" : ""}</td><td className="p-2">{term.status === "not_in_top_100" ? "Not in top 100" : number(term.position)}</td><td className="p-2">{term.observed_on || "Not measured"}</td><td className="break-all p-2">{term.ranking_url || "Not measured"}</td></tr>)}</tbody></table></div> : <p className="mt-2 text-sm">No tracked keywords available.</p>}
      <details className="mt-3 text-sm"><summary className="cursor-pointer">AI prompt observations ({visibility.prompts.length})</summary>{visibility.prompts.length ? visibility.prompts.map((prompt, i) => <p className="mt-2" key={i}>{prompt.text} · {prompt.provider || "Provider unspecified"} · Mentioned: {presence(prompt.mentioned)} · Cited: {presence(prompt.cited)} · {prompt.observed_on || "No observation date"}</p>) : <p className="mt-2">No measured prompt observations.</p>}</details>
      {visibility.monthly_trend && visibility.monthly_trend.cohort > 0 && <details className="mt-3 text-sm"><summary className="cursor-pointer">Monthly keyword movement · {visibility.monthly_trend.cohort} matched {visibility.monthly_trend.scope} terms</summary>
        <p className="mt-2">{visibility.monthly_trend.improved} improved and {visibility.monthly_trend.declined} declined by at least 3 positions. {visibility.monthly_trend.entered_top_10} entered the top 10; {visibility.monthly_trend.left_top_10} left it. Both months use the same terms; unmeasured terms are excluded, never treated as zero.</p>
        <ul className="mt-2 space-y-1">{visibility.monthly_trend.rows.map((row, index) => <li key={index}>{row.text}: {row.previous === 101 ? "Outside top 100" : row.previous} → {row.current === 101 ? "Outside top 100" : row.current} · {row.previous_date} → {row.current_date}</li>)}</ul>
      </details>}
      <p className="mt-3 text-xs text-[var(--text-secondary)]">{visibility.note}</p>
    </section>
    <section className="rounded-lg border border-[var(--border)] p-4">
      <h3 className="font-semibold">Traffic · {number(traffic.current.total)} site visits</h3>
      <p className="mt-1 text-sm">GA4 sessions, all channels. Search clicks and benchmark CTR estimates are separate diagnostics.</p>
      <table className="mt-3 w-full text-left text-sm"><thead><tr><th className="p-2">Channel</th><th className="p-2">Current visits</th><th className="p-2">Previous visits</th></tr></thead><tbody>{["all", ...channels].map(channel => <tr key={channel} className="border-t border-[var(--border)]"><td className="p-2">{channel === "all" ? "All channels (total)" : names[channel] || channel}</td><td className="p-2">{number(channel === "all" ? traffic.current.total : traffic.current.channels[channel])}</td><td className="p-2">{number(channel === "all" ? traffic.previous.total : traffic.previous.channels[channel])}</td></tr>)}</tbody></table>
      <p className="mt-3 text-xs text-[var(--text-secondary)]">{traffic.source} Channel rows are parts of the total; do not add the total to them.</p>
      {traffic.ctr_reference && <details className="mt-3 text-sm"><summary className="cursor-pointer">CTR reference · supplied industry averages</summary>
        <p className="mt-2">{traffic.ctr_reference.scope} · {traffic.ctr_reference.period}</p>
        <p className="mt-2">The supplied industry curve is the baseline reference for all terms, across devices and markets; no observed AI Overview is required. Positions 1–20 are supported. It does not measure visits, prove missed clicks, or establish AI Overview presence for every keyword.</p>
        <table className="mt-2 text-left"><thead><tr><th className="px-3 py-1">Position</th><th className="px-3 py-1">Industry CTR</th></tr></thead><tbody>{traffic.ctr_reference.positions.map(row => <tr key={row.position}><td className="px-3 py-1">{row.position}</td><td className="px-3 py-1">{row.ctr_pct}%</td></tr>)}</tbody></table>
      </details>}
    </section>
    <section className="rounded-lg border border-[var(--border)] p-4">
      <h3 className="font-semibold">Leads · {leads.rate_pct == null ? "Rate not measured" : `${leads.rate_pct.toFixed(2)}% lead conversion rate`}</h3>
      <p className="mt-2 text-sm">{number(leads.count)} lead events, including repeats. {number(leads.lead_sessions)} visits produced a lead ÷ {number(leads.session_measurement?.sessions)} matching GA4 visits × 100.</p>
      {leads.session_measurement?.reason && <p className="mt-2 text-sm">{leads.session_measurement.reason}</p>}
      <p className="mt-2 text-xs text-[var(--text-secondary)]">Legacy event rate: {leads.event_rate_pct == null ? "Not measured" : `${leads.event_rate_pct.toFixed(2)} lead events per 100 visits`}. Existing event-based baseline history is retained separately.</p>
      {settings ? <LeadRateGoal initial={settings.target} actual={leads.rate_pct} clientId={settings.clientId} slug={settings.slug} /> : <p className="mt-2 text-sm">Assessment target rate: {leads.target_rate_pct == null ? "Not configured" : `${number(leads.target_rate_pct)}%`}</p>}
      <p className="mt-2 text-sm">Monthly lead-count goal: {number(leads.monthly_goal)}. A count goal is separate from a conversion-rate target.</p>
      <p className="mt-3 text-xs text-[var(--text-secondary)]">{leads.source}</p>
    </section>
  </div>;
}
