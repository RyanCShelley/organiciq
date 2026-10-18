import type { ServiceReportingData, ServiceReportingMetric } from "@/lib/dashboard";

const number = (value: number | null) => value == null ? "—" : value.toLocaleString("en-US", { maximumFractionDigits: 0 });
function Value({ metric }: { metric: ServiceReportingMetric }) {
  return <><span>{number(metric.current)}</span>{metric.change_pct != null && <span className="ml-2 text-xs text-[var(--text-secondary)]">{metric.change_pct > 0 ? "+" : ""}{metric.change_pct.toFixed(1)}% vs previous</span>}</>;
}

export function ServiceReportingSummary({ data }: { data?: ServiceReportingData }) {
  if (!data || data.status === "not_configured") return null;
  const rows = [...data.rows];
  if (rows.length > 1 && data.combined) rows.push(data.combined);
  if (data.outside_services && ((data.outside_services.sessions.current ?? 0) > 0 || (data.outside_services.lead_events.current ?? 0) > 0)) rows.push(data.outside_services);
  return <section className="card p-5" aria-label="Service contribution">
    <h3 className="font-semibold">Service contribution</h3>
    <p className="mt-1 text-sm text-[var(--text-secondary)]">Site totals include all channels. These rows show the services you manage.</p>
    {data.status !== "measured" ? <p className="mt-3 text-sm">Refresh GA4 data for this period to measure service contribution. Missing channel coverage is not zero performance.</p> : <>
      <div className="mt-3 overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr><th className="py-2 pr-4">Service</th><th className="py-2 pr-4">Visits</th><th className="py-2">Lead events</th></tr></thead><tbody>
        {rows.map(row => <tr key={row.key} className="border-t border-[var(--border)]"><th className="py-3 pr-4 font-medium">{row.label}</th><td className="py-3 pr-4"><Value metric={row.sessions} /></td><td className="py-3"><Value metric={row.lead_events} /></td></tr>)}
      </tbody></table></div>
      {data.ai_referrals && data.rows.some(row => row.key === "organiciq") && <p className="mt-3 text-sm">AI referrals included in OrganicIQ: <strong>{number(data.ai_referrals.sessions.current)} visits</strong> · {number(data.ai_referrals.lead_events.current)} lead events.</p>}
      {!!data.ai_sources?.length && <details className="mt-2 text-sm"><summary className="cursor-pointer">AI sources and Google’s classification</summary><ul className="mt-2 space-y-1">{data.ai_sources.map(row => <li key={row.source}>{row.source}: {number(row.sessions)} visits · {number(row.lead_events)} lead events. Google channel: {row.google_channels.join(", ") || "Not supplied"}.</li>)}</ul></details>}
      <p className="mt-2 text-xs text-[var(--text-secondary)]">Visits use GA4’s detailed channel report and can differ slightly from site totals. Lead events include repeats. Direct and referral inclusion does not prove agency attribution. Visits with no recorded AI source remain unattributed. Existing baselines and targets remain whole-site.</p>
    </>}
  </section>;
}
