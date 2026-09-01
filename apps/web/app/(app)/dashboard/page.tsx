import Link from "next/link";

import { apiFetch } from "@/lib/api";
import { resolveClientId, resolveDateRange } from "@/lib/context";
import { normalizeDashboardResponse, type DashboardResponse } from "@/lib/dashboard";
import {
  DashboardMetricCard,
  DashboardSection,
  FreshnessBanner,
} from "@/components/DashboardMetrics";

function formatNum(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "—";
  return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(2);
}

function leadGoalLabel(periodDays: number | null): string {
  if (periodDays === null) return "Lead Goal";
  if (periodDays >= 28 && periodDays <= 31) return "Monthly Lead Goal";
  return `Lead Goal (${periodDays} days)`;
}

export default async function DashboardPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const clientId = await resolveClientId(params);
  const { from, to } = await resolveDateRange(params);

  let data: DashboardResponse | null = null;
  let error: string | null = null;

  if (!clientId) {
    error = "Select a client to view the dashboard.";
  } else {
    try {
      data = normalizeDashboardResponse(
        await apiFetch<DashboardResponse>(
          `/dashboard?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
          { clientId },
        ),
      );
    } catch (e) {
      error = e instanceof Error ? e.message : "Failed to load dashboard";
    }
  }

  return (
    <section>
      <h1 className="text-2xl font-semibold">Dashboard</h1>
      <p className="mt-1 text-sm text-[var(--muted)]">
        Conversions → Visibility → Traffic from validated facts only ({from} to {to}).
      </p>

      {error ? (
        <p className="mt-4 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-100">
          {error}
        </p>
      ) : null}

      {data ? (
        <>
          <FreshnessBanner rows={data.freshness} />

          <DashboardSection
            title="Conversions"
            description="Lead events from GA4 conversion definitions. Lead rate uses GA4 sessions."
          >
            {!data.conversions.configured ? (
              <p className="rounded-lg border border-[var(--border)] px-3 py-2 text-sm text-[var(--muted)]">
                No lead conversion definitions configured. Add them in{" "}
                <Link
                  href={clientId ? `/clients/${clientId}/conversions` : "/clients"}
                  className="underline"
                >
                  Clients → workspace → Conversions
                </Link>{" "}
                to populate leads and lead rate.
              </p>
            ) : null}
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <DashboardMetricCard label="Leads" metric={data.conversions.leads} />
              <DashboardMetricCard label="Lead Rate" metric={data.conversions.lead_rate} unit="pct" />
              {data.conversions.period_lead_goal ? (
                <div className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-4">
                  <div className="text-sm text-[var(--muted)]">
                    {leadGoalLabel(data.conversions.goal_period_days)}
                  </div>
                  <div className="mt-2 text-2xl font-semibold">
                    {data.conversions.period_lead_goal.toLocaleString()}
                  </div>
                  {data.conversions.monthly_lead_goal &&
                  data.conversions.goal_period_days !== null &&
                  (data.conversions.goal_period_days < 28 ||
                    data.conversions.goal_period_days > 31) ? (
                    <div className="mt-1 text-xs text-[var(--muted)]">
                      Based on {data.conversions.monthly_lead_goal.toLocaleString()}/month
                    </div>
                  ) : null}
                  <div className="mt-2 text-xs text-[var(--muted)]">
                    Progress {formatNum(data.conversions.goal_progress_pct)}%
                  </div>
                </div>
              ) : null}
            </div>
            {data.conversions.leads_by_channel.length > 0 ? (
              <div className="mt-4 overflow-x-auto rounded-xl border border-[var(--border)]">
                <table className="min-w-full text-left text-sm">
                  <thead className="bg-white/5 text-[var(--muted)]">
                    <tr>
                      <th className="px-4 py-3 font-medium">Channel</th>
                      <th className="px-4 py-3 font-medium">Leads</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.conversions.leads_by_channel.map((row) => (
                      <tr key={row.channel} className="border-t border-[var(--border)]">
                        <td className="px-4 py-3">{row.label}</td>
                        <td className="px-4 py-3">{row.leads}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </DashboardSection>

          <DashboardSection
            title="Visibility"
            description="Search and AI visibility are reported separately — no combined score."
          >
            <h3 className="text-sm font-medium text-[var(--muted)]">Search</h3>
            <div className="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <DashboardMetricCard
                label="Search Visibility"
                metric={data.visibility.search.search_visibility}
                unit="visibility"
                hint={
                  data.visibility.search.search_visibility_source === "site_summary"
                    ? "SE Ranking site summary — same 0–1 scale as their project overview (e.g. 0.1)."
                    : data.visibility.search.search_visibility_source === "keyword_avg"
                      ? "Average tracked keyword visibility from SE Ranking (0–1 scale)."
                      : "Run Sync Search in the client workspace to populate."
                }
              />
              <DashboardMetricCard
                label="Search SOV"
                metric={data.visibility.search.search_sov}
                unit="pct"
                hint={
                  data.visibility.search.search_sov.current !== null
                    ? "Share of voice from site + competitor visibility facts."
                    : "Requires competitor visibility from SE Ranking (not returned for current sync)."
                }
              />
              <DashboardMetricCard
                label="GSC Impressions"
                metric={data.visibility.search.gsc_impressions}
              />
              <DashboardMetricCard
                label="Average Position"
                metric={data.visibility.search.average_position}
                unit="position"
                invertChange
                hint={`Source: ${data.visibility.search.average_position_source.replaceAll("_", " ")}`}
              />
            </div>
            {Object.values(data.visibility.search.keyword_distribution).some((v) => v > 0) ? (
              <div className="mt-4 grid gap-3 sm:grid-cols-5">
                {(
                  [
                    ["Top 3", data.visibility.search.keyword_distribution.top_3],
                    ["Top 10", data.visibility.search.keyword_distribution.top_10],
                    ["Top 20", data.visibility.search.keyword_distribution.top_20],
                    ["Beyond 20", data.visibility.search.keyword_distribution.beyond_20],
                    ["Not ranking", data.visibility.search.keyword_distribution.not_ranking],
                  ] as const
                ).map(([label, count]) => (
                  <div
                    key={label}
                    className="rounded-lg border border-[var(--border)] px-3 py-2 text-sm"
                  >
                    <div className="text-[var(--muted)]">{label}</div>
                    <div className="mt-1 text-lg font-semibold">{count}</div>
                  </div>
                ))}
              </div>
            ) : null}

            <h3 className="mt-6 text-sm font-medium text-[var(--muted)]">AI</h3>
            <p className="mt-1 text-xs text-[var(--muted)]">
              From your SE Ranking AIRT tracked prompts — same presence metrics as the Rankings report.
            </p>
            <div className="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <DashboardMetricCard
                label="Answers with your mention"
                metric={data.visibility.ai.mention_presence}
                unit="pct"
                hint="Share of tracked prompts where your brand is mentioned in the AI answer."
              />
              <DashboardMetricCard
                label="Answers with your link"
                metric={data.visibility.ai.link_presence}
                unit="pct"
                hint="Share of tracked prompts where your domain is cited with a link."
              />
              <DashboardMetricCard
                label="Mention in Top 3"
                metric={data.visibility.ai.mention_top3_presence}
                unit="pct"
                hint="Share of tracked prompts where your brand mention appears in the top 3 positions."
              />
              <DashboardMetricCard
                label="Link in Top 3"
                metric={data.visibility.ai.link_top3_presence}
                unit="pct"
                hint="Share of tracked prompts where your domain link appears in the top 3 positions."
              />
            </div>
            {data.visibility.ai.prompt_count !== null ? (
              <p className="mt-3 text-sm text-[var(--muted)]">
                {data.visibility.ai.prompt_count} tracked prompts in SE Ranking.
              </p>
            ) : (
              <p className="mt-3 text-sm text-[var(--muted)]">
                Run Sync AI to pull AIRT presence stats from SE Ranking.
              </p>
            )}
          </DashboardSection>

          <DashboardSection title="Traffic" description="GSC clicks and GA4 sessions/views by channel.">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <DashboardMetricCard label="GSC Clicks" metric={data.traffic.gsc_clicks} />
              <DashboardMetricCard label="GSC CTR" metric={data.traffic.gsc_ctr} unit="pct" />
              <DashboardMetricCard label="GA4 Sessions" metric={data.traffic.ga4_sessions} />
              <DashboardMetricCard label="GA4 Views" metric={data.traffic.ga4_views} />
            </div>

            {data.traffic.by_channel.length > 0 ? (
              <>
                <h3 className="mt-6 text-sm font-medium text-[var(--muted)]">Traffic by Channel</h3>
                <div className="mt-3 overflow-x-auto rounded-xl border border-[var(--border)]">
                  <table className="min-w-full text-left text-sm">
                    <thead className="bg-white/5 text-[var(--muted)]">
                      <tr>
                        <th className="px-4 py-3 font-medium">Channel</th>
                        <th className="px-4 py-3 font-medium">Sessions</th>
                        <th className="px-4 py-3 font-medium">Views</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.traffic.by_channel.map((row) => (
                        <tr key={row.channel} className="border-t border-[var(--border)]">
                          <td className="px-4 py-3">{row.label}</td>
                          <td className="px-4 py-3">{formatNum(row.sessions)}</td>
                          <td className="px-4 py-3">{formatNum(row.views)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            ) : null}

            {data.traffic.top_pages.length > 0 ? (
              <>
                <h3 className="mt-6 text-sm font-medium text-[var(--muted)]">Top Pages</h3>
                <div className="mt-3 overflow-x-auto rounded-xl border border-[var(--border)]">
                  <table className="min-w-full text-left text-sm">
                    <thead className="bg-white/5 text-[var(--muted)]">
                      <tr>
                        <th className="px-4 py-3 font-medium">Page</th>
                        <th className="px-4 py-3 font-medium">GSC Impr.</th>
                        <th className="px-4 py-3 font-medium">GSC Clicks</th>
                        <th className="px-4 py-3 font-medium">GA4 Sessions</th>
                        <th className="px-4 py-3 font-medium">GA4 Views</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.traffic.top_pages.map((row) => (
                        <tr key={row.page} className="border-t border-[var(--border)]">
                          <td className="max-w-xs truncate px-4 py-3" title={row.page}>
                            {row.page}
                          </td>
                          <td className="px-4 py-3">{formatNum(row.gsc_impressions)}</td>
                          <td className="px-4 py-3">{formatNum(row.gsc_clicks)}</td>
                          <td className="px-4 py-3">{formatNum(row.ga4_sessions)}</td>
                          <td className="px-4 py-3">{formatNum(row.ga4_views)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            ) : null}
          </DashboardSection>

          <div className="mt-8 overflow-x-auto rounded-xl border border-[var(--border)]">
            <h3 className="border-b border-[var(--border)] px-4 py-3 text-sm font-medium">
              Data Freshness
            </h3>
            <table className="min-w-full text-left text-sm">
              <thead className="bg-white/5 text-[var(--muted)]">
                <tr>
                  <th className="px-4 py-3 font-medium">Source</th>
                  <th className="px-4 py-3 font-medium">Fact Through</th>
                  <th className="px-4 py-3 font-medium">Validation</th>
                </tr>
              </thead>
              <tbody>
                {data.freshness.map((row) => (
                  <tr key={row.source} className="border-t border-[var(--border)]">
                    <td className="px-4 py-3">{row.source.replaceAll("_", " ")}</td>
                    <td className="px-4 py-3 text-[var(--muted)]">{row.fact_through ?? "—"}</td>
                    <td className="px-4 py-3 text-[var(--muted)]">{row.validation ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}
    </section>
  );
}
