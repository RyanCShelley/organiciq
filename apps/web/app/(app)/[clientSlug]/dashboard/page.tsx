import Link from "next/link";

import { DataTable } from "@/components/analytics/DataTable";
import { MetricCard } from "@/components/analytics/MetricCard";
import { Sparkline } from "@/components/analytics/Sparkline";
import { Alert } from "@/components/ui/Alert";
import { Card } from "@/components/ui/Card";
import { SectionHeader, SubsectionTitle } from "@/components/ui/SectionHeader";
import { apiFetch } from "@/lib/api";
import { requireAccountClient } from "@/lib/account-routes.server";
import { clientHref } from "@/lib/client-path";
import { resolveDateRange } from "@/lib/context";
import {
  normalizeDashboardResponse,
  type DashboardBaseline,
  type DashboardResponse,
} from "@/lib/dashboard";
import { comparisonLabelFor, parseCompareMode, type CompareMode } from "@/lib/date-range";

function formatNum(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "—";
  return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(2);
}

function leadGoalLabel(periodDays: number | null): string {
  if (periodDays === null) return "Lead Goal";
  if (periodDays >= 28 && periodDays <= 31) return "Monthly Lead Goal";
  return `Lead Goal (${periodDays} days)`;
}

/** Headline for the baseline hero, driven by how many core metrics beat the snapshot. */
function baselineHeadline(baseline: DashboardBaseline): string {
  const deltas = [
    baseline.vs_current.sessions.change_pct,
    baseline.vs_current.leads.change_pct,
    baseline.vs_current.lead_rate.change_pct,
  ];
  const measured = deltas.filter((value): value is number => value !== null);
  if (measured.length === 0) {
    return "Not enough data yet to compare against the frozen kickoff snapshot.";
  }
  const ahead = measured.filter((value) => value > 0).length;
  if (ahead === measured.length) {
    return "Every core metric is ahead of the frozen kickoff snapshot.";
  }
  if (ahead === 0) {
    return "No core metric is ahead of the frozen kickoff snapshot yet.";
  }
  return `${ahead} of ${measured.length} core metrics are ahead of the frozen kickoff snapshot.`;
}

/** Provenance line: when the snapshot was frozen and which window it is compared against. */
function baselineSnapshotLine(baseline: DashboardBaseline): string | null {
  const parts: string[] = [];
  if (baseline.as_of) parts.push(`Snapshot as of ${baseline.as_of}`);
  if (baseline.source) parts.push(baseline.source);
  if (baseline.tier_name) parts.push(baseline.tier_name);

  const window = baseline.current_window;
  const period = window
    ? `period ${window.from}\u2192${window.to}${window.days ? ` (${window.days}d \u2192 monthly)` : ""}`
    : null;

  if (parts.length === 0) return period;
  const prefix = parts.join(" \u00b7 ");
  return period ? `${prefix} \u2014 ${period}` : prefix;
}

function channelBarColor(label: string): string {
  const key = label.toLowerCase();
  if (key.includes("organic")) return "var(--brand-teal)";
  if (key.includes("ai")) return "var(--brand-lime)";
  if (key.includes("direct")) return "var(--brand-dark-3)";
  return "#9aa3ab";
}

export default async function DashboardPage({
  params,
  searchParams,
}: {
  params: Promise<{ clientSlug: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { clientSlug } = await params;
  const query = await searchParams;
  const selectedClient = await requireAccountClient(clientSlug, "dashboard");
  const clientId = selectedClient.id;
  const { from, to } = await resolveDateRange(query);
  const compare: CompareMode = parseCompareMode(query.compare);
  const comparisonLabel = comparisonLabelFor(compare);
  // Compare: none — show the raw value and sparkline, no delta pill.
  const showComparison = compare !== "none";
  const clientPath = clientHref(selectedClient.slug);
  const conversionsPath = clientHref(selectedClient.slug, "conversions");

  let data: DashboardResponse | null = null;
  let error: string | null = null;

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

  const baselineConfigured = Boolean(data?.baseline.configured);
  const snapshotLine =
    data && baselineConfigured ? baselineSnapshotLine(data.baseline) : null;

  return (
    <section>
      {error ? <Alert variant="danger">{error}</Alert> : null}

      {data ? (
        <div className="space-y-[30px]">
          <section className="baseline-hero">
            <div className="flex flex-wrap items-start justify-between gap-5">
              <div className="min-w-0">
                <div className="text-[10.5px] font-bold uppercase tracking-[0.14em] text-[var(--brand-lime)]">
                  Baseline
                </div>
                {baselineConfigured ? (
                  <h2 className="mt-2.5 max-w-[24ch] text-pretty font-[family-name:var(--font-display)] text-[27px] font-black leading-[1.15] tracking-[-0.02em] text-white">
                    {baselineHeadline(data.baseline)}
                  </h2>
                ) : null}
                <p className="mt-2.5 max-w-[62ch] text-[13.5px] leading-relaxed text-[var(--brand-on-dark)]">
                  Selected period scaled to monthly vs the frozen kickoff /
                  calculator snapshot.
                </p>
              </div>
              {clientId ? (
                <Link
                  href={clientPath}
                  className="shrink-0 rounded-[10px] border-[1.5px] border-white/35 bg-transparent px-[15px] py-[9px] text-[12.5px] font-semibold text-white transition-colors duration-[120ms] hover:bg-white/10"
                >
                  Edit baseline
                </Link>
              ) : null}
            </div>

            {snapshotLine ? (
              <p className="mt-4 font-[family-name:var(--font-mono)] text-[11.5px] text-[var(--brand-on-dark-muted)]">
                {snapshotLine}
              </p>
            ) : null}

            {!baselineConfigured ? (
              <Alert variant="info" className="mt-4">
                No baseline snapshot yet. Set monthly sessions, leads, and lead
                rate in{" "}
                <Link href={clientPath} className="font-medium underline">
                  Client settings
                </Link>
                .
              </Alert>
            ) : (
              <div className="metric-grid mt-[18px]">
                <MetricCard
                  tone="glass"
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
                  tone="glass"
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
                  tone="glass"
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
            )}
          </section>

          <section>
            <SectionHeader
              accent
              title="Conversions"
              description="Lead events and lead rate from GA4 conversion definitions."
              actions={
                clientId ? (
                  <Link
                    href={conversionsPath}
                    className="text-[12.5px] font-semibold text-[var(--brand-teal)] transition-colors hover:text-[var(--brand-lime)]"
                  >
                    Conversion settings
                  </Link>
                ) : null
              }
            />

            {!data.conversions.configured ? (
              <Alert variant="info">
                No lead conversion definitions configured. Add them in{" "}
                <Link
                  href={conversionsPath}
                  className="font-medium text-[var(--brand-teal-hover)] underline"
                >
                  Clients → Conversions
                </Link>
                .
              </Alert>
            ) : null}

            <div className="metric-grid">
              <MetricCard
                label="Leads"
                metric={
                  compare === "baseline" && baselineConfigured
                    ? data.baseline.vs_current.leads
                    : data.conversions.leads
                }
                comparisonLabel={comparisonLabel}
                showComparison={showComparison}
              />
              <MetricCard
                label="Lead Rate"
                metric={
                  compare === "baseline" && baselineConfigured
                    ? data.baseline.vs_current.lead_rate
                    : data.conversions.lead_rate
                }
                unit="pct"
                comparisonLabel={comparisonLabel}
                showComparison={showComparison}
              />
              {data.conversions.period_lead_goal ? (
                <Card className="flex h-full flex-col p-[18px_20px]">
                  <div className="text-[12.5px] font-semibold text-[var(--text-secondary)]">
                    {leadGoalLabel(data.conversions.goal_period_days)}
                  </div>
                  <div className="mt-2.5 flex items-end justify-between gap-3.5">
                    <div className="font-[family-name:var(--font-display)] text-[32px] font-black leading-none tracking-[-0.02em]">
                      {data.conversions.period_lead_goal.toLocaleString()}
                    </div>
                    <Sparkline
                      values={data.conversions.leads_series}
                      width={86}
                      height={30}
                    />
                  </div>
                  {data.conversions.monthly_lead_goal &&
                  data.conversions.goal_period_days !== null &&
                  (data.conversions.goal_period_days < 28 ||
                    data.conversions.goal_period_days > 31) ? (
                    <div className="mt-1 text-xs text-[var(--text-tertiary)]">
                      Based on{" "}
                      {data.conversions.monthly_lead_goal.toLocaleString()}
                      /month
                    </div>
                  ) : null}
                  <div className="mt-auto pt-2.5 text-xs text-[var(--text-secondary)]">
                    Progress{" "}
                    <span className="font-medium text-[var(--text-primary)]">
                      {formatNum(data.conversions.goal_progress_pct)}%
                    </span>
                  </div>
                  <div className="progress-track mt-2 h-[7px] overflow-hidden rounded-full">
                    <div
                      className="progress-fill h-full rounded-full"
                      style={{
                        width: `${Math.min(100, Math.max(0, data.conversions.goal_progress_pct ?? 0))}%`,
                      }}
                    />
                  </div>
                </Card>
              ) : null}
            </div>

            {data.conversions.leads_by_channel.length > 0 ? (
              <div className="mt-3.5">
                <DataTable
                  columns={[
                    {
                      key: "channel",
                      header: "Channel",
                      render: (row) => {
                        const max = Math.max(
                          ...data.conversions.leads_by_channel.map(
                            (item) => item.leads,
                          ),
                          1,
                        );
                        const pct = `${Math.round((row.leads / max) * 100)}%`;
                        return (
                          <span className="flex flex-col gap-1.5">
                            <span>{row.label}</span>
                            <span className="h-[5px] max-w-[340px] overflow-hidden rounded-full bg-[#F1F2F3]">
                              <span
                                className="block h-full rounded-full"
                                style={{
                                  width: pct,
                                  background: channelBarColor(row.label),
                                }}
                              />
                            </span>
                          </span>
                        );
                      },
                    },
                    {
                      key: "leads",
                      header: "Leads",
                      align: "right",
                      render: (row) => (
                        <span className="font-[family-name:var(--font-display)] font-extrabold">
                          {row.leads.toLocaleString()}
                        </span>
                      ),
                    },
                  ]}
                  rows={data.conversions.leads_by_channel}
                  getRowKey={(row) => row.channel}
                />
              </div>
            ) : null}
          </section>

          <section>
            <SectionHeader
              accent
              title="Visibility"
              description="Search and AI visibility reported separately."
            />

            <div className="space-y-3.5">
              <div className="card p-[18px_20px]">
                <SubsectionTitle>Search</SubsectionTitle>
                <div className="metric-grid mt-3.5">
                  <MetricCard
                    label="Search Visibility"
                    metric={data.visibility.search.search_visibility}
                    unit="visibility"
                    size="compact"
                    comparisonLabel={comparisonLabel}
                    showComparison={showComparison}
                    hint={
                      data.visibility.search.search_visibility_source ===
                      "site_summary"
                        ? "SE Ranking site summary"
                        : data.visibility.search.search_visibility_source ===
                            "keyword_avg"
                          ? "Average tracked keyword visibility"
                          : "Run Sync Search to populate"
                    }
                  />
                  <MetricCard
                    label="Search SOV"
                    metric={data.visibility.search.search_sov}
                    unit="pct"
                    size="compact"
                    comparisonLabel={comparisonLabel}
                    showComparison={showComparison}
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
                    comparisonLabel={comparisonLabel}
                    showComparison={showComparison}
                  />
                  <MetricCard
                    label="Average Position"
                    metric={data.visibility.search.average_position}
                    unit="position"
                    invertChange
                    size="compact"
                    comparisonLabel={comparisonLabel}
                    showComparison={showComparison}
                    hint={`Source: ${data.visibility.search.average_position_source.replaceAll("_", " ")}`}
                  />
                </div>
              </div>

              <div className="rounded-[12px] border border-[var(--border-ai)] bg-[var(--surface-ai)] p-[18px_20px]">
                <div className="flex items-center gap-2">
                  <span
                    className="inline-block h-[3px] w-[22px] rounded-sm"
                    style={{ background: "var(--gradient-brand)" }}
                    aria-hidden
                  />
                  <span className="text-[10.5px] font-bold uppercase tracking-[0.14em] text-[var(--brand-teal-deep)]">
                    AI
                  </span>
                </div>
                <div className="metric-grid mt-3.5">
                  <MetricCard
                    label="Answers with your mention"
                    metric={data.visibility.ai.mention_presence}
                    unit="pct"
                    size="compact"
                    comparisonLabel={comparisonLabel}
                    showComparison={showComparison}
                  />
                  <MetricCard
                    label="Answers with your link"
                    metric={data.visibility.ai.link_presence}
                    unit="pct"
                    size="compact"
                    comparisonLabel={comparisonLabel}
                    showComparison={showComparison}
                  />
                  <MetricCard
                    label="Mention in Top 3"
                    metric={data.visibility.ai.mention_top3_presence}
                    unit="pct"
                    size="compact"
                    comparisonLabel={comparisonLabel}
                    showComparison={showComparison}
                  />
                  <MetricCard
                    label="Link in Top 3"
                    metric={data.visibility.ai.link_top3_presence}
                    unit="pct"
                    size="compact"
                    comparisonLabel={comparisonLabel}
                    showComparison={showComparison}
                  />
                </div>
                <p className="mt-3 text-xs text-[var(--text-tertiary)]">
                  {data.visibility.ai.prompt_count !== null
                    ? `${data.visibility.ai.prompt_count} tracked prompts in SE Ranking.`
                    : "Run Sync AI to pull AIRT presence stats."}
                </p>
              </div>
            </div>
          </section>

          <section>
            <SectionHeader
              accent
              title="Traffic"
              description="GSC clicks and GA4 sessions / views."
            />

            <div className="metric-grid">
              <MetricCard
                label="GSC Clicks"
                metric={data.traffic.gsc_clicks}
                comparisonLabel={comparisonLabel}
                showComparison={showComparison}
              />
              <MetricCard
                label="GSC CTR"
                metric={data.traffic.gsc_ctr}
                unit="pct"
                comparisonLabel={comparisonLabel}
                showComparison={showComparison}
              />
              <MetricCard
                label="GA4 Sessions"
                metric={
                  compare === "baseline" && baselineConfigured
                    ? data.baseline.vs_current.sessions
                    : data.traffic.ga4_sessions
                }
                comparisonLabel={comparisonLabel}
                showComparison={showComparison}
              />
              <MetricCard
                label="GA4 Views"
                metric={data.traffic.ga4_views}
                comparisonLabel={comparisonLabel}
                showComparison={showComparison}
              />
            </div>

            {data.traffic.by_channel.length > 0 ? (
              <div className="mt-3.5">
                <h3 className="mb-2 font-[family-name:var(--font-display)] text-[15px] font-extrabold text-[var(--text-primary)]">
                  Traffic by Channel
                </h3>
                <DataTable
                  columns={[
                    {
                      key: "channel",
                      header: "Channel",
                      render: (row) => {
                        const max = Math.max(
                          ...data.traffic.by_channel.map(
                            (item) => item.sessions ?? 0,
                          ),
                          1,
                        );
                        const pct = `${Math.round(((row.sessions ?? 0) / max) * 100)}%`;
                        return (
                          <span className="flex flex-col gap-1.5">
                            <span>{row.label}</span>
                            <span className="h-[5px] max-w-[340px] overflow-hidden rounded-full bg-[#F1F2F3]">
                              <span
                                className="block h-full rounded-full"
                                style={{
                                  width: pct,
                                  background: channelBarColor(row.label),
                                }}
                              />
                            </span>
                          </span>
                        );
                      },
                    },
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
                    {
                      key: "conversions",
                      header: "Conversions",
                      align: "right",
                      render: (row) => (
                        <span className="rounded-full bg-[var(--success-soft)] px-2 py-0.5 text-[11.5px] font-bold text-[var(--success)]">
                          {row.conversions.toLocaleString()}
                        </span>
                      ),
                    },
                    {
                      key: "bounce_rate",
                      header: "Bounce rate",
                      align: "right",
                      render: (row) =>
                        row.bounce_rate == null
                          ? "—"
                          : `${row.bounce_rate.toFixed(1)}%`,
                    },
                  ]}
                  rows={data.traffic.by_channel}
                  getRowKey={(row) => row.channel}
                />
              </div>
            ) : null}

            {data.traffic.top_pages.length > 0 ? (
              <div className="mt-3.5">
                <h3 className="mb-2 font-[family-name:var(--font-display)] text-[15px] font-extrabold text-[var(--text-primary)]">
                  Top Pages
                </h3>
                <DataTable
                  columns={[
                    {
                      key: "page",
                      header: "Page",
                      render: (row) => (
                        <span
                          className="block max-w-xs truncate font-[family-name:var(--font-mono)] text-xs text-[var(--text-secondary)]"
                          title={row.page}
                        >
                          {row.page}
                        </span>
                      ),
                    },
                    {
                      key: "gsc_impressions",
                      header: "GSC impr.",
                      align: "right",
                      render: (row) => formatNum(row.gsc_impressions),
                    },
                    {
                      key: "gsc_clicks",
                      header: "GSC clicks",
                      align: "right",
                      render: (row) => formatNum(row.gsc_clicks),
                    },
                    {
                      key: "ga4_sessions",
                      header: "GA4 sessions",
                      align: "right",
                      render: (row) => formatNum(row.ga4_sessions),
                    },
                    {
                      key: "ga4_views",
                      header: "GA4 views",
                      align: "right",
                      render: (row) => formatNum(row.ga4_views),
                    },
                  ]}
                  rows={data.traffic.top_pages}
                  getRowKey={(row) => row.page}
                />
                <p className="mt-2 text-xs text-[var(--text-tertiary)]">
                  Ranked by GSC clicks · {data.traffic.top_pages.length} URLs
                  shown
                </p>
              </div>
            ) : null}
          </section>
        </div>
      ) : null}
    </section>
  );
}
