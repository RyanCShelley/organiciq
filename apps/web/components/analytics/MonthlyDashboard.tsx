"use client";

import Link from "next/link";
import { useState } from "react";
import type { DashboardResponse } from "@/lib/dashboard";
import { ProgressPanel } from "./ProgressPanel";
import { Sparkline } from "./Sparkline";

const number = (value: number | null | undefined) =>
  value == null
    ? "Not measured"
    : value.toLocaleString(undefined, { maximumFractionDigits: 2 });
const position = (value?: number | null) =>
  value == null
    ? "Not measured"
    : value <= 0 || value > 100
      ? "Outside top 100"
      : number(value);
const yes = (value: boolean | null) =>
  value == null ? "Unknown" : value ? "Yes" : "No";
const panel =
  "rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5";
const muted = "text-sm text-[var(--text-secondary)]";
function change(
  now: number | null | undefined,
  before: number | null | undefined,
) {
  if (now == null || before == null) return "No comparable previous period";
  if (!before) return now ? `${number(now)} added from zero` : "Unchanged";
  const delta = ((now - before) / before) * 100;
  return `${Math.abs(delta).toFixed(1)}% ${delta < 0 ? "lower" : delta > 0 ? "higher" : "change"} vs previous period`;
}
function Table({
  heads,
  rows,
}: {
  heads: string[];
  rows: React.ReactNode[][];
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr>
            {heads.map((h) => (
              <th
                key={h}
                className="border-b border-[var(--border)] py-3 pr-4 font-medium text-[var(--text-secondary)]"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {r.map((c, j) => (
                <td
                  key={j}
                  className="border-b border-[var(--border)] py-3 pr-4 align-top break-words"
                >
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {!rows.length && (
        <p className={muted + " py-4"}>
          No dated observations available for this period.
        </p>
      )}
    </div>
  );
}
function Trend({
  current,
  previous,
  label,
}: {
  current: number[];
  previous: number[];
  label: string;
}) {
  if (current.length < 2)
    return (
      <p className={muted + " py-8"}>
        Not enough dated observations to draw this trend.
      </p>
    );
  const maximum = Math.max(1, ...current, ...previous),
    width = 640,
    height = 180;
  const path = (values: number[]) =>
    values
      .map(
        (value, i) =>
          `${i ? "L" : "M"}${40 + (i / Math.max(1, Math.max(current.length, previous.length) - 1)) * 580},${150 - (value / maximum) * 130}`,
      )
      .join(" ");
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="my-5 w-full"
      role="img"
      aria-label={label}
    >
      <title>{label}</title>
      <line x1="40" x2="620" y1="150" y2="150" stroke="var(--border)" />
      {previous.length > 1 && (
        <path
          d={path(previous)}
          fill="none"
          stroke="var(--text-secondary)"
          strokeWidth="2"
          strokeDasharray="5 4"
        />
      )}
      <path
        d={path(current)}
        fill="none"
        stroke="var(--brand-teal)"
        strokeWidth="2.5"
      />
      <g fill="var(--text-secondary)" fontSize="12">
        <text x="0" y="25">
          {number(maximum)}
        </text>
        <text x="20" y="153">
          0
        </text>
        <text x="40" y="175">
          Day 1
        </text>
        <text x="620" y="175" textAnchor="end">
          Day {Math.max(current.length, previous.length)}
        </text>
      </g>
    </svg>
  );
}
export function MonthlyDashboard({
  data,
  engineHref,
  settingsHref,
}: {
  data: DashboardResponse;
  engineHref: string;
  settingsHref: string;
}) {
  const [explore, setExplore] = useState<string | null>(null);
  const [metric, setMetric] = useState("visibility");
  const details = data.exploration,
    visibility = details?.visibility;
  const sessions =
    data.traffic.ga4_reported_sessions?.current != null
      ? data.traffic.ga4_reported_sessions
      : data.traffic.ga4_sessions;
  const previousChannels = new Map(
    details?.previous_channels?.map((row) => [row.channel, row]),
  );
  const channelKeys = [
    ...new Set([
      ...data.traffic.by_channel.map((row) => row.channel),
      ...previousChannels.keys(),
    ]),
  ];
  const currentChannels = new Map(
    data.traffic.by_channel.map((row) => [row.channel, row]),
  );
  const toggle = (key: string) => setExplore(explore === key ? null : key);
  const ga4 = data.effective_periods?.ga4;
  const rankingPeriod = data.effective_periods?.rankings;
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold">Visibility, traffic & leads</h2>
          <p className={muted}>
            {data.period.from} – {data.period.to} · Whole site
          </p>
          {ga4?.current && ga4.current[1] !== data.period.to && (
            <p className={muted} role="status">
              Visits and leads cover {ga4.current.join(" – ")}; the comparison
              uses the same number of days.
            </p>
          )}
        </div>
        <Link className="btn btn-primary" href={engineHref}>
          Review this month →
        </Link>
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        <section className={panel}>
          <h3>Visibility</h3>
          <p className="mt-2 text-3xl font-bold">
            {visibility?.measured
              ? `${visibility.top_10} / ${visibility.measured}`
              : "Not measured"}
          </p>
          <p className={muted}>Measured tracked keywords in the top 10</p>
          <p className={muted}>
            {visibility
              ? `${visibility.measured} of ${visibility.tracked} tracked terms measured`
              : "Dated keyword detail unavailable"}
          </p>
          <div className="my-5">
            <p className={muted}>AI brand mentions · separate measure</p>
            <strong>
              {number(data.visibility.ai.mention_presence.current)}
              {data.visibility.ai.mention_presence.current != null ? "%" : ""}
            </strong>
            <p className={muted}>
              {number(data.visibility.ai.prompt_count)} tracked prompts
            </p>
          </div>
          <button
            className="text-sm text-[var(--brand-teal)] underline"
            aria-expanded={explore === "visibility"}
            onClick={() => toggle("visibility")}
          >
            Explore visibility
          </button>
        </section>
        <section className={panel}>
          <h3>Traffic</h3>
          <p className="mt-2 text-3xl font-bold">{number(sessions?.current)}</p>
          <p className={muted}>Site visits · GA4 sessions</p>
          <p className={muted}>
            {change(sessions?.current, sessions?.previous)}
          </p>
          <Sparkline
            values={data.traffic.ga4_sessions.series}
            width={200}
            height={65}
            className="my-4 max-w-full"
          />
          <button
            className="text-sm text-[var(--brand-teal)] underline"
            aria-expanded={explore === "traffic"}
            onClick={() => toggle("traffic")}
          >
            Explore traffic
          </button>
        </section>
        <section className={panel}>
          <h3>Leads</h3>
          <p className="mt-2 text-3xl font-bold">
            {number(data.conversions.leads.current)}
          </p>
          <p className={muted}>Configured lead events</p>
          <p className={muted}>
            {change(
              data.conversions.leads.current,
              data.conversions.leads.previous,
            )}
          </p>
          <Sparkline
            values={data.conversions.leads.series}
            width={200}
            height={65}
            className="my-4 max-w-full"
          />
          <p className={muted}>
            Visit-based conversion:{" "}
            {number(data.conversions.session_lead_rate?.current)}
            {data.conversions.session_lead_rate?.current != null ? "%" : ""}
          </p>
          <button
            className="mt-2 text-sm text-[var(--brand-teal)] underline"
            aria-expanded={explore === "leads"}
            onClick={() => toggle("leads")}
          >
            Explore leads & conversion
          </button>
        </section>
      </div>
      {explore && (
        <section className={panel} aria-live="polite">
          <div className="flex justify-between gap-4">
            <h3 className="font-semibold">
              {explore === "visibility"
                ? "What is ranking—and where the brand is mentioned"
                : explore === "traffic"
                  ? "Which traffic is growing—and which is falling"
                  : "Which pages produce lead events"}
            </h3>
            <button
              className="text-sm underline"
              onClick={() => setExplore(null)}
            >
              Close breakdown
            </button>
          </div>
          {explore === "visibility" && (
            <div className="mt-4 space-y-5">
              <Table
                heads={[
                  "Tracked term / ranking page",
                  "Previous → current position",
                  "Observed",
                ]}
                rows={(visibility?.keywords ?? []).map((row) => [
                  <span key={row.term}>
                    {row.term}
                    <span className="block break-all text-xs text-[var(--text-secondary)]">
                      {row.current?.ranking_url ?? "Ranking page unavailable"}
                    </span>
                  </span>,
                  `${position(row.previous?.position)} → ${position(row.current?.position)}`,
                  row.current?.observed_on ?? "Not measured",
                ])}
              />
              <h4 className="font-semibold">AI prompt observations</h4>
              <Table
                heads={[
                  "Prompt",
                  "Provider / date",
                  "Brand mentioned",
                  "Brand cited",
                ]}
                rows={(details?.prompts ?? []).map((row) => [
                  row.prompt,
                  `${row.provider} · ${row.observed_on}`,
                  yes(row.mentioned),
                  yes(row.cited),
                ])}
              />
              <p className={muted}>
                Mentions and citations are separate observations. Missing
                provider or period data is unknown.
              </p>
            </div>
          )}
          {explore === "traffic" && (
            <div className="mt-4 space-y-3">
              <p className={muted}>
                GA4 observed channel traffic. Detailed channel totals can differ
                slightly from exact-period site visits. Inclusion in a service
                does not prove agency attribution.
              </p>
              <Table
                heads={[
                  "Channel",
                  "Previous visits",
                  "Current visits",
                  "Change",
                ]}
                rows={channelKeys.map((key) => {
                  const row = currentChannels.get(key);
                  const before =
                    details?.previous_channels == null
                      ? null
                      : (previousChannels.get(key)?.sessions ?? 0);
                  const now = row?.sessions ?? 0;
                  return [
                    row?.label ?? previousChannels.get(key)?.label ?? key,
                    number(before),
                    number(now),
                    change(now, before),
                  ];
                })}
              />
              <h4 className="font-semibold">Identifiable AI sources</h4>
              <Table
                heads={["Source", "Visits", "Google channel"]}
                rows={(data.service_reporting?.ai_sources ?? []).map((row) => [
                  row.source,
                  number(row.sessions),
                  row.google_channels.join(", "),
                ])}
              />
              <p className={muted}>
                AI referrals are included once in channel totals. Direct visits
                without a recorded source remain unattributed.
              </p>
            </div>
          )}
          {explore === "leads" && (
            <div className="mt-4 space-y-3">
              <p>
                {number(data.conversions.session_measurement?.lead_sessions)}{" "}
                visits produced a lead /{" "}
                {number(data.conversions.session_measurement?.sessions)} visits.
                Each converting visit counts once.
              </p>
              <p className={muted}>
                Site visit-based rate:{" "}
                {data.conversions.session_lead_rate?.current == null
                  ? "Not measured"
                  : `${number(data.conversions.session_lead_rate.current)}%`}{" "}
                · Previous:{" "}
                {data.conversions.session_lead_rate?.previous == null
                  ? "Not measured"
                  : `${number(data.conversions.session_lead_rate.previous)}%`}
                . Lead events per 100 visits:{" "}
                {number(data.conversions.lead_rate.current)}.
              </p>
              <Table
                heads={["Page", "Visits", "Lead events", "Events / 100 visits"]}
                rows={
                  ga4?.current
                    ? data.traffic.top_pages.map((row) => [
                        row.page,
                        number(row.ga4_sessions),
                        data.conversions.configured
                          ? number(row.ga4_key_events)
                          : "Lead events not configured",
                        data.conversions.configured
                          ? number(row.session_key_event_rate)
                          : "Not measured",
                      ])
                    : []
                }
              />
              <p className={muted}>
                Page-level data measures lead events, not unique converting
                visits. Low rates on informational pages are not automatically
                conversion problems; consider intent and sample size. This is a
                ranked page sample, not every page.
              </p>
              <Link className="text-sm underline" href={settingsHref}>
                Review lead definitions and target
              </Link>
            </div>
          )}
        </section>
      )}
      <section className={panel}>
        <h3 className="font-semibold">Performance over the period</h3>
        <div className="my-3 flex flex-wrap gap-2">
          {[
            ["visibility", "Visibility"],
            ["traffic", "Visits"],
            ["leads", "Lead events"],
            ["conversion", "Lead conversion"],
          ].map(([key, label]) => (
            <button
              key={key}
              className={`btn ${metric === key ? "btn-primary" : "btn-ghost"}`}
              aria-pressed={metric === key}
              onClick={() => setMetric(key)}
            >
              {label}
            </button>
          ))}
        </div>
        {metric === "visibility" ? (
          <div className="space-y-3 py-4">
            {visibility?.matched ? (
              <>
                <p className="text-2xl font-semibold">
                  {visibility.matched_previous_top_10} / {visibility.matched} →{" "}
                  {visibility.matched_current_top_10} / {visibility.matched}
                </p>
                <p className={muted}>
                  Same measured keywords in the top 10 ·{" "}
                  {(
                    (100 *
                      (visibility.matched_current_top_10 -
                        visibility.matched_previous_top_10)) /
                    visibility.matched
                  ).toFixed(1)}{" "}
                  percentage-point change
                </p>
                <div className="space-y-3">
                  {[
                    ["Previous", visibility.matched_previous_top_10],
                    ["Current", visibility.matched_current_top_10],
                  ].map(([label, value]) => (
                    <div key={label} className="flex items-center gap-3">
                      <span className="w-20 text-sm">{label}</span>
                      <div className="h-3 flex-1 bg-[var(--surface-muted)]">
                        <div
                          className="h-3 bg-[var(--brand-teal)]"
                          style={{
                            width: `${(Number(value) / visibility.matched) * 100}%`,
                          }}
                        />
                      </div>
                      <span>{number(Number(value))}</span>
                    </div>
                  ))}
                </div>
                <p className={muted}>
                  Previous:{" "}
                  {rankingPeriod?.previous?.join(" – ") ?? "Unavailable"} ·
                  Current:{" "}
                  {rankingPeriod?.current?.join(" – ") ?? "Unavailable"}.
                  Endpoint observations; no daily ranking history is inferred.
                </p>
              </>
            ) : (
              <p className={muted}>
                No comparable keyword cohort in both periods. Current visibility
                remains available above.
              </p>
            )}
          </div>
        ) : metric === "conversion" ? (
          <div className="space-y-3 py-5">
            <p className="text-2xl font-semibold">
              {data.conversions.session_lead_rate?.previous == null
                ? "Not measured"
                : `${number(data.conversions.session_lead_rate.previous)}%`}{" "}
              →{" "}
              {data.conversions.session_lead_rate?.current == null
                ? "Not measured"
                : `${number(data.conversions.session_lead_rate.current)}%`}
            </p>
            <p className={muted}>
              Previous → current · Visits with at least one configured lead
              event ÷ matching visits. These are exact-period rates; daily
              unique converting-visit history is not available.
            </p>
          </div>
        ) : (
          <>
            <Trend
              current={
                metric === "traffic"
                  ? data.traffic.ga4_sessions.series
                  : data.conversions.leads.series
              }
              previous={
                (metric === "traffic"
                  ? details?.previous_sessions_series
                  : details?.previous_leads_series) ?? []
              }
              label={`Daily ${metric === "traffic" ? "visits" : "lead events"}, current and previous periods`}
            />
            <p className={muted}>
              Daily {metric === "traffic" ? "detailed visits" : "lead events"} ·
              Solid: {ga4?.current?.join(" – ") ?? "unavailable"} · Dashed:{" "}
              {ga4?.previous?.join(" – ") ?? "unavailable"}. Visits in detailed
              daily reports can differ slightly from exact-period headline
              totals.
            </p>
          </>
        )}
      </section>
      <section className={panel}>
        <h3 className="font-semibold">Service contribution</h3>
        <p className={muted}>
          Part of the whole-site totals; observed traffic is not proof of agency
          impact.
        </p>
        <Table
          heads={["Service", "Visits", "Lead events"]}
          rows={(data.service_reporting?.rows ?? []).map((row) => [
            row.label,
            number(row.sessions.current),
            number(row.lead_events.current),
          ])}
        />
      </section>
      <details className={panel}>
        <summary className="cursor-pointer font-semibold">
          Quarterly progress · starting baseline
        </summary>
        <div className="mt-5">
          <ProgressPanel baseline={data.baseline} editHref={settingsHref} />
        </div>
      </details>
      <details className={panel}>
        <summary className="cursor-pointer font-semibold">
          Sources, freshness & reporting scope
        </summary>
        <p className={muted + " mt-3"}>{data.service_reporting?.note}</p>
        <Table
          heads={["Source", "Facts through", "Validation"]}
          rows={data.freshness.map((row) => [
            row.source,
            row.fact_through ?? "Unavailable",
            row.validation ?? "Unknown",
          ])}
        />
        {data.search_console_sources?.combined_history && (
          <p className={muted}>
            Combined Search Console history · configured properties shown
            separately below.
          </p>
        )}
        <Table
          heads={["Search Console property", "Clicks", "Impressions"]}
          rows={(data.search_console_sources?.properties ?? []).map((row) => [
            row.property,
            number(row.clicks),
            number(row.impressions),
          ])}
        />
      </details>
    </div>
  );
}
