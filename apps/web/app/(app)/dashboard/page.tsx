import Link from "next/link";

import { DataTable } from "@/components/analytics/DataTable";
import { MetricCard } from "@/components/analytics/MetricCard";
import { StatusBadge } from "@/components/analytics/StatusBadge";
import { Alert } from "@/components/ui/Alert";
import { Card } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/PageHeader";
import { SectionHeader, SubsectionTitle } from "@/components/ui/SectionHeader";
import { apiFetch } from "@/lib/api";
import { resolveClientId, resolveDateRange } from "@/lib/context";
import { normalizeDashboardResponse, type DashboardResponse } from "@/lib/dashboard";

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
      <PageHeader
        title="Dashboard"
        description="Conversions → Visibility → Traffic from validated facts only."
      />

      {error ? <Alert variant="danger">{error}</Alert> : null}

      {data ? (
        <div className="space-y-[var(--section-gap)]">
          <section className="workspace-section">
            <SectionHeader
              title="Baseline"
              description="Current period scaled to monthly vs the frozen kickoff / calculator snapshot."
              actions={
                clientId ? (
                  <Link href={`/clients/${clientId}`} className="btn btn-ghost btn-sm">
                    Edit baseline
                  </Link>
                ) : null
              }
            />
            <div className="workspace-panel space-y-3">
              {!data.baseline.configured ? (
                <Alert variant="info">
                  No baseline snapshot yet. Set monthly sessions, leads, and lead rate in{" "}
                  <Link
                    href={clientId ? `/clients/${clientId}` : "/clients"}
                    className="font-medium text-[var(--brand-teal-hover)] underline"
                  >
                    Client settings
                  </Link>{" "}
                  (from the growth calculator when you have it).
                </Alert>
              ) : (
                <>
                  <p className="text-xs text-[var(--text-secondary)]">
                    Snapshot
                    {data.baseline.as_of ? ` as of ${data.baseline.as_of}` : ""}
                    {data.baseline.source ? ` · ${data.baseline.source}` : ""}
                    {data.baseline.notes ? ` — ${data.baseline.notes}` : ""}
                  </p>
                  <div className="metric-grid sm:grid-cols-3">
                    <MetricCard
                      label="Monthly sessions vs baseline"
                      metric={data.baseline.vs_current.sessions}
                      comparisonLabel="vs baseline"
                      hint={
                        data.baseline.monthly_sessions != null
                          ? `Baseline ${data.baseline.monthly_sessions.toLocaleString()}/mo`
                          : undefined
                      }
                    />
                    <MetricCard
                      label="Monthly leads vs baseline"
                      metric={data.baseline.vs_current.leads}
                      comparisonLabel="vs baseline"
                      hint={
                        data.baseline.monthly_leads != null
                          ? `Baseline ${data.baseline.monthly_leads.toLocaleString()}/mo`
                          : undefined
                      }
                    />
                    <MetricCard
                      label="Lead rate vs baseline"
                      metric={data.baseline.vs_current.lead_rate}
                      unit="pct"
                      comparisonLabel="vs baseline"
                      hint={
                        data.baseline.lead_rate != null
                          ? `Baseline ${formatNum(data.baseline.lead_rate)}%`
                          : undefined
                      }
                    />
                  </div>
                </>
              )}
            </div>
          </section>

          <section className="workspace-section">
            <SectionHeader
              title="Conversions"
              description="Lead events and lead rate from GA4 conversion definitions."
              actions={
                clientId ? (
                  <Link
                    href={`/clients/${clientId}/conversions`}
                    className="btn btn-ghost btn-sm"
                  >
                    Conversion settings
                  </Link>
                ) : null
              }
            />

            <div className="workspace-panel space-y-3">
              {!data.conversions.configured ? (
                <Alert variant="info">
                  No lead conversion definitions configured. Add them in{" "}
                  <Link
                    href={clientId ? `/clients/${clientId}/conversions` : "/clients"}
                    className="font-medium text-[var(--brand-teal-hover)] underline"
                  >
                    Clients → Conversions
                  </Link>
                  .
                </Alert>
              ) : null}

              <div className="metric-grid sm:grid-cols-2 lg:grid-cols-3">
                <MetricCard label="Leads" metric={data.conversions.leads} />
                <MetricCard label="Lead Rate" metric={data.conversions.lead_rate} unit="pct" />
                {data.conversions.period_lead_goal ? (
                  <Card className="flex h-full flex-col p-[var(--card-padding)]">
                    <div className="text-xs font-medium text-[var(--text-secondary)]">
                      {leadGoalLabel(data.conversions.goal_period_days)}
                    </div>
                    <div className="mt-1 font-[family-name:var(--font-display)] text-xl font-bold tracking-tight">
                      {data.conversions.period_lead_goal.toLocaleString()}
                    </div>
                    {data.conversions.monthly_lead_goal &&
                    data.conversions.goal_period_days !== null &&
                    (data.conversions.goal_period_days < 28 ||
                      data.conversions.goal_period_days > 31) ? (
                      <div className="mt-0.5 text-xs text-[var(--text-tertiary)]">
                        Based on {data.conversions.monthly_lead_goal.toLocaleString()}/month
                      </div>
                    ) : null}
                    <div className="mt-auto pt-2 text-xs text-[var(--text-secondary)]">
                      Progress{" "}
                      <span className="font-medium text-[var(--text-primary)]">
                        {formatNum(data.conversions.goal_progress_pct)}%
                      </span>
                    </div>
                  </Card>
                ) : null}
              </div>

              {data.conversions.leads_by_channel.length > 0 ? (
                <DataTable
                  columns={[
                    { key: "channel", header: "Channel", render: (row) => row.label },
                    {
                      key: "leads",
                      header: "Leads",
                      align: "right",
                      render: (row) => row.leads.toLocaleString(),
                    },
                  ]}
                  rows={data.conversions.leads_by_channel}
                  getRowKey={(row) => row.channel}
                />
              ) : null}
            </div>
          </section>

          <section className="workspace-section">
            <SectionHeader
              title="Visibility"
              description="Search and AI visibility reported separately."
            />

            <div className="workspace-panel space-y-4">
              <div>
                <SubsectionTitle>Search</SubsectionTitle>
                <div className="metric-grid mt-2 sm:grid-cols-2 lg:grid-cols-4">
                  <MetricCard
                    label="Search Visibility"
                    metric={data.visibility.search.search_visibility}
                    unit="visibility"
                    size="compact"
                    hint={
                      data.visibility.search.search_visibility_source === "site_summary"
                        ? "SE Ranking site summary"
                        : data.visibility.search.search_visibility_source === "keyword_avg"
                          ? "Average tracked keyword visibility"
                          : "Run Sync Search to populate"
                    }
                  />
                  <MetricCard
                    label="Search SOV"
                    metric={data.visibility.search.search_sov}
                    unit="pct"
                    size="compact"
                    hint={
                      data.visibility.search.search_sov.current !== null
                        ? "Share of voice from visibility facts"
                        : "Requires competitor visibility data"
                    }
                  />
                  <MetricCard
                    label="GSC Impressions"
                    metric={data.visibility.search.gsc_impressions}
                    size="compact"
                  />
                  <MetricCard
                    label="Average Position"
                    metric={data.visibility.search.average_position}
                    unit="position"
                    invertChange
                    size="compact"
                    hint={`Source: ${data.visibility.search.average_position_source.replaceAll("_", " ")}`}
                  />
                </div>

                {Object.values(data.visibility.search.keyword_distribution).some((v) => v > 0) ? (
                  <div className="mt-3 grid gap-2 sm:grid-cols-5">
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
                        className="rounded-[var(--radius-md)] border border-[var(--border)] px-2.5 py-2"
                      >
                        <div className="text-[0.625rem] font-medium text-[var(--text-tertiary)]">
                          {label}
                        </div>
                        <div className="mt-0.5 font-[family-name:var(--font-display)] text-base font-bold">
                          {count}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>

              <div>
                <SubsectionTitle>AI</SubsectionTitle>
                <div className="metric-grid mt-2 sm:grid-cols-2 lg:grid-cols-4">
                  <MetricCard
                    label="Answers with your mention"
                    metric={data.visibility.ai.mention_presence}
                    unit="pct"
                    size="compact"
                  />
                  <MetricCard
                    label="Answers with your link"
                    metric={data.visibility.ai.link_presence}
                    unit="pct"
                    size="compact"
                  />
                  <MetricCard
                    label="Mention in Top 3"
                    metric={data.visibility.ai.mention_top3_presence}
                    unit="pct"
                    size="compact"
                  />
                  <MetricCard
                    label="Link in Top 3"
                    metric={data.visibility.ai.link_top3_presence}
                    unit="pct"
                    size="compact"
                  />
                </div>
                <p className="mt-2 text-xs text-[var(--text-tertiary)]">
                  {data.visibility.ai.prompt_count !== null
                    ? `${data.visibility.ai.prompt_count} tracked prompts in SE Ranking.`
                    : "Run Sync AI to pull AIRT presence stats."}
                </p>
              </div>
            </div>
          </section>

          <section className="workspace-section">
            <SectionHeader title="Traffic" description="GSC clicks and GA4 sessions/views." />

            <div className="workspace-panel space-y-4">
              <div className="metric-grid sm:grid-cols-2 lg:grid-cols-4">
                <MetricCard label="GSC Clicks" metric={data.traffic.gsc_clicks} size="compact" />
                <MetricCard label="GSC CTR" metric={data.traffic.gsc_ctr} unit="pct" size="compact" />
                <MetricCard label="GA4 Sessions" metric={data.traffic.ga4_sessions} size="compact" />
                <MetricCard label="GA4 Views" metric={data.traffic.ga4_views} size="compact" />
              </div>

              {data.traffic.by_channel.length > 0 ? (
                <div>
                  <SubsectionTitle className="mb-2">Traffic by Channel</SubsectionTitle>
                  <DataTable
                    columns={[
                      { key: "channel", header: "Channel", render: (row) => row.label },
                      {
                        key: "sessions",
                        header: "Sessions",
                        align: "right",
                        render: (row) => formatNum(row.sessions),
                      },
                      {
                        key: "views",
                        header: "Views",
                        align: "right",
                        render: (row) => formatNum(row.views),
                      },
                    ]}
                    rows={data.traffic.by_channel}
                    getRowKey={(row) => row.channel}
                  />
                </div>
              ) : null}

              {data.traffic.top_pages.length > 0 ? (
                <div>
                  <SubsectionTitle className="mb-2">Top Pages</SubsectionTitle>
                  <DataTable
                    columns={[
                      {
                        key: "page",
                        header: "Page",
                        render: (row) => (
                          <span className="block max-w-xs truncate" title={row.page}>
                            {row.page}
                          </span>
                        ),
                      },
                      {
                        key: "gsc_impressions",
                        header: "GSC Impr.",
                        align: "right",
                        render: (row) => formatNum(row.gsc_impressions),
                      },
                      {
                        key: "gsc_clicks",
                        header: "GSC Clicks",
                        align: "right",
                        render: (row) => formatNum(row.gsc_clicks),
                      },
                      {
                        key: "ga4_sessions",
                        header: "GA4 Sessions",
                        align: "right",
                        render: (row) => formatNum(row.ga4_sessions),
                      },
                      {
                        key: "ga4_views",
                        header: "GA4 Views",
                        align: "right",
                        render: (row) => formatNum(row.ga4_views),
                      },
                    ]}
                    rows={data.traffic.top_pages}
                    getRowKey={(row) => row.page}
                  />
                </div>
              ) : null}
            </div>
          </section>

          <section className="workspace-section">
            <SectionHeader title="Data Freshness" description="Validated fact coverage by source." />
            <DataTable
              columns={[
                {
                  key: "source",
                  header: "Source",
                  render: (row) => row.source.replaceAll("_", " "),
                },
                {
                  key: "fact_through",
                  header: "Fact Through",
                  render: (row) => (
                    <span className="text-[var(--text-secondary)]">{row.fact_through ?? "—"}</span>
                  ),
                },
                {
                  key: "validation",
                  header: "Validation",
                  render: (row) => (
                    <span className="text-[var(--text-secondary)]">{row.validation ?? "—"}</span>
                  ),
                },
                {
                  key: "available",
                  header: "Status",
                  render: (row) => <StatusBadge available={row.available} />,
                },
              ]}
              rows={data.freshness}
              getRowKey={(row) => row.source}
            />
          </section>
        </div>
      ) : null}
    </section>
  );
}
