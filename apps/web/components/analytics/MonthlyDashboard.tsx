"use client";
import { engagementRate, promptComparison, pointChange } from "@/lib/dashboard-comparisons";
import React, { useState, useId } from "react";
import Link from "next/link";
import type { DashboardResponse, RankingReading } from "@/lib/dashboard";
import "./MonthlyDashboard.css";
const fmt = (n: number | null | undefined, d = 0) =>
  n == null
    ? "Not measured"
    : Number(n).toLocaleString(undefined, { maximumFractionDigits: d });
const pct = (n: number | null | undefined) =>
  n == null ? "Not measured" : `${fmt(n, 2)}%`;
const delta = (a: number | null | undefined, b: number | null | undefined) =>
  a == null || b == null
    ? "No comparison"
    : b === 0
      ? a === 0
        ? "No change"
        : `${fmt(a)} added from zero`
      : `${a >= b ? "+" : ""}${fmt(((a - b) / b) * 100, 1)}%`;
const colors = ["#0b8077", "#64ad9d", "#9acac0", "#c7ded7", "#e3e9e6"];
function Change({
  a,
  b,
}: {
  a: number | null | undefined;
  b: number | null | undefined;
}) {
  return (
    <span
      className={`change ${a == null || b == null ? "neutral" : a > b ? "up" : a < b ? "down" : "neutral"}`}
    >
      {delta(a, b)}
    </span>
  );
}
function PointChange({ a, b, lowerIsBetter = false }: { a: number | null | undefined; b: number | null | undefined; lowerIsBetter?: boolean }) {
  const direction = a == null || b == null || a === b ? "neutral" : (a > b) !== lowerIsBetter ? "up" : "down";
  return <span className={`change ${direction}`}>{pointChange(a, b)}</span>;
}
function ComparisonValue({ current, previous, rate = false, decimals = 0, showChange = true, lowerIsBetter = false }: { current: number | null | undefined; previous: number | null | undefined; rate?: boolean; decimals?: number; showChange?: boolean; lowerIsBetter?: boolean }) {
  return <div className="comparison-value"><strong>{rate ? pct(current) : fmt(current, decimals)}</strong><small>Previous {rate ? pct(previous) : fmt(previous, decimals)}</small>{showChange ? rate ? <PointChange a={current} b={previous} lowerIsBetter={lowerIsBetter} /> : <Change a={current} b={previous} /> : null}</div>;
}
function Table({
  heads,
  rows,
}: {
  heads: string[];
  rows: React.ReactNode[][];
}) {
  return (
    <div className="tablewrap">
      <table>
        <thead>
          <tr>
            {heads.map((h) => (
              <th key={h}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {r.map((v, j) => (
                <td key={j}>{v}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {!rows.length && (
        <p className="note">No observations available for this period.</p>
      )}
    </div>
  );
}
function Chart({
  title,
  current,
  previous,
  dates,
  unit = "visits",
}: {
  title: string;
  current: number[];
  previous: number[];
  dates: string[];
  unit?: string;
}) {
  const gradientId = useId();
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(1, ...current, ...previous);
  const ceiling = Math.ceil(max / 5) * 5;
  const x = (i: number) =>
      52 +
      (i / Math.max(1, Math.max(current.length, previous.length) - 1)) * 360,
    y = (v: number) => 230 - (v / ceiling) * 185;
  const path = (v: number[]) =>
    v.map((n, i) => `${i ? "L" : "M"}${x(i)},${y(n)}`).join(" ");
  return (
    <article className="card">
      <div className="cardtop">
        <h3>{title}</h3>
        <div className="legend">
          <span>● Current</span>
          {previous.length > 0 && <span className="prior">● Previous</span>}
        </div>
      </div>
      <div className="chartread">
        {hover == null ? (
          <>
            <b>
              {fmt(current.length ? current.reduce((a, b) => a + b, 0) : null)}
            </b>
            <small>{unit} in daily detail</small>
          </>
        ) : (
          <>
            <b>{fmt(current[hover])}</b>
            <small>
              {dates[hover]} · previous: {fmt(previous[hover])}
            </small>
          </>
        )}
      </div>
      <svg
        className="chart"
        viewBox="0 0 440 280"
        role="img"
        aria-label={`${title}, current and previous periods`}
        onMouseLeave={() => setHover(null)}
      >
        {[0, 1, 2, 3, 4].map((i) => (
          <g key={i}>
            <line
              x1="52"
              x2="412"
              y1={y((i * ceiling) / 4)}
              y2={y((i * ceiling) / 4)}
              stroke="#e6ece9"
              strokeDasharray="3 4"
            />
            <text x="43" y={y((i * ceiling) / 4) + 4} textAnchor="end">
              {fmt((i * ceiling) / 4)}
            </text>
          </g>
        ))}
        {current.length > 1 && (
          <path
            d={`${path(current)} L${x(current.length - 1)},230 L52,230 Z`}
            fill={`url(#${gradientId})`}
          />
        )}
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop stopColor="#0b8077" stopOpacity=".18" />
            <stop offset="1" stopColor="#0b8077" stopOpacity="0" />
          </linearGradient>
        </defs>
        {previous.length > 1 && (
          <path
            d={path(previous)}
            fill="none"
            stroke="#a7b6bd"
            strokeWidth="2"
            strokeDasharray="5 5"
          />
        )}
        {current.length > 1 && (
          <path
            d={path(current)}
            fill="none"
            stroke="#0b8077"
            strokeWidth="2.5"
            strokeLinejoin="round"
          />
        )}
        {[
          0,
          Math.round((current.length - 1) * 0.25),
          Math.round((current.length - 1) * 0.5),
          Math.round((current.length - 1) * 0.75),
          current.length - 1,
        ]
          .filter((n, i, a) => n >= 0 && a.indexOf(n) === i)
          .map((i) => (
            <text key={i} x={x(i)} y="262" textAnchor="middle">
              {dates[i]?.slice(5) ?? `Day ${i + 1}`}
            </text>
          ))}
        {current.map((v, i) => (
          <rect
            key={i}
            x={x(i) - 11}
            y="30"
            width="22"
            height="205"
            fill="transparent"
            onMouseEnter={() => setHover(i)}
          >
            <title>
              {`${dates[i]}: ${v}; previous ${previous[i] ?? "not measured"}`}
            </title>
          </rect>
        ))}
        {hover != null && (
          <g pointerEvents="none">
            <line
              x1={x(hover)}
              x2={x(hover)}
              y1="30"
              y2="230"
              stroke="#7b9991"
            />
            <circle cx={x(hover)} cy={y(current[hover])} r="4" fill="#0b8077" />
          </g>
        )}
      </svg>
      {!current.length && (
        <p className="note">No daily observations available for this period.</p>
      )}
    </article>
  );
}
function Metric({
  label,
  value,
  sub,
  a,
  b,
  series = [],
  comparison,
}: {
  label: string;
  value: string;
  sub: string;
  a?: number | null;
  b?: number | null;
  series?: number[];
  comparison?: React.ReactNode;
}) {
  return (
    <article className="card metric">
      <div className="eyebrow">{label}</div>
      <div className="metricvalue">{value}</div>
      <div className="metricfoot">
        {comparison ?? <Change a={a} b={b} />}
        <span>{sub}</span>
      </div>
      {series.length > 1 && (
        <svg viewBox="0 0 220 30" className="spark" aria-hidden="true">
          <polyline
            points={series
              .map(
                (v, i) =>
                  `${(i / (series.length - 1)) * 220},${28 - (v / Math.max(1, ...series)) * 24}`,
              )
              .join(" ")}
            fill="none"
            stroke="#0b8077"
            strokeWidth="1.8"
          />
        </svg>
      )}
    </article>
  );
}
export function MonthlyDashboard({
  data: d,
  clientName = "Performance overview",
  settingsHref,
}: {
  data: DashboardResponse;
  clientName?: string;
  settingsHref: string;
}) {
  const [detail, setDetail] = useState(""),
    [pageSort, setPageSort] = useState("leads");
  const v = d.exploration?.visibility;
  const sessions =
      d.traffic.ga4_reported_sessions?.current != null
        ? d.traffic.ga4_reported_sessions
        : d.traffic.ga4_sessions,
    rate = d.conversions.session_lead_rate;
  const terms = v?.keywords ?? [];
  const validPos = (r: RankingReading | null) =>
    r && r.position > 0 && r.position <= 100 ? r.position : 101;
  const distribution = [
    terms.filter((r) => r.current && validPos(r.current) <= 3).length,
    terms.filter(
      (r) => r.current && validPos(r.current) > 3 && validPos(r.current) <= 10,
    ).length,
    terms.filter(
      (r) => r.current && validPos(r.current) > 10 && validPos(r.current) <= 20,
    ).length,
    terms.filter(
      (r) =>
        r.current && validPos(r.current) > 20 && validPos(r.current) <= 100,
    ).length,
    terms.filter((r) => r.current && validPos(r.current) > 100).length,
  ];
  const matched = terms.filter((r) => r.current && r.previous);
  const improved = matched.filter(
      (r) => validPos(r.current) < validPos(r.previous),
    ),
    declined = matched.filter(
      (r) => validPos(r.current) > validPos(r.previous),
    );
  const previous = new Map(
    d.exploration?.previous_channels?.map((r) => [r.channel, r]),
  );
  const channels = d.traffic.by_channel;
  const engagement = engagementRate(channels);
  const previousEngagement = engagementRate(d.exploration?.previous_channels);
  const promptRows = d.exploration?.prompts ?? [],
    mentionRows = promptRows.filter((r) => r.mentioned != null),
    citationRows = promptRows.filter((r) => r.cited != null);
  const previousPrompts = d.exploration?.previous_prompts ?? [];
  const mentionChange = promptComparison(promptRows, previousPrompts, "mentioned");
  const citationChange = promptComparison(promptRows, previousPrompts, "cited");
  const providers = [
    ...new Set((d.exploration?.prompts ?? []).map((r) => r.provider)),
  ].map((provider) => {
    const rows = (d.exploration?.prompts ?? []).filter(
        (r) => r.provider === provider,
      ),
      m = rows.filter((r) => r.mentioned != null),
      c = rows.filter((r) => r.cited != null);
    return [
      provider,
      `${m.filter((r) => r.mentioned).length} / ${m.length}`,
      `${c.filter((r) => r.cited).length} / ${c.length}`,
      rows.length,
    ];
  });
  const pages = [...d.traffic.top_pages].sort((a, b) =>
    pageSort === "visits"
      ? b.ga4_sessions - a.ga4_sessions
      : b.ga4_key_events - a.ga4_key_events,
  );
  const currentStart = d.effective_periods?.ga4?.current?.[0] ?? d.period.from;
  const dates = d.traffic.ga4_sessions.series.map((_, i) => {
    const day = new Date(currentStart + "T12:00:00Z");
    day.setUTCDate(day.getUTCDate() + i);
    return day.toISOString().slice(0, 10);
  });
  let offset = 0;
  const toggle = (key: string) => setDetail(detail === key ? "" : key);
  return (
    <div className="kpi-report">
      <header>
        <div>
          <div className="eyebrow">PERFORMANCE OVERVIEW</div>
          <h1>{clientName}</h1>
          <p>
            How visible are we, who is arriving, and are those visits turning
            into leads?
          </p>
        </div>
      </header>
      <div className="summarygrid">
        <Metric
          label="Visibility · top 10"
          value={
            (v?.measured ?? 0)
              ? pct((100 * (v?.top_10 ?? 0)) / (v?.measured ?? 0))
              : "Not measured"
          }
          sub={`${v?.top_10 ?? 0} of ${v?.measured ?? 0} measured terms`}
          comparison={<PointChange a={v?.matched ? 100 * v.matched_current_top_10 / v.matched : null} b={v?.matched ? 100 * v.matched_previous_top_10 / v.matched : null} />}
        />
        <Metric
          label="Traffic · site visits"
          value={fmt(sessions.current)}
          sub="Change in site visits"
          a={sessions.current}
          b={sessions.previous}
          series={d.traffic.ga4_sessions.series}
        />
        <Metric
          label="Engagement"
          value={pct(engagement)}
          sub="Channel-based engagement rate"
          comparison={<PointChange a={engagement} b={previousEngagement} />}
        />
        <Metric
          label="Visits generating a lead"
          value={fmt(d.conversions.lead_sessions?.current)}
          sub={`${pct(rate?.current)} conversion rate`}
          a={d.conversions.lead_sessions?.current}
          b={d.conversions.lead_sessions?.previous}
        />
      </div>
      <section id="visibility">
        <div className="sectiontitle">
          <div>
            <span className="step">01</span>
            <h2>Where are we showing up?</h2>
            <p>
              Search rankings and AI answers are separate measures of
              visibility.
            </p>
          </div>
          <button
            className="textbutton"
            aria-expanded={detail === "visibility"}
            onClick={() => toggle("visibility")}
          >
            {detail === "visibility" ? "Close detail" : "Explore visibility →"}
          </button>
        </div>
        <div className="twocol">
          <article className="card">
            <div className="cardtop">
              <h3>Search ranking coverage</h3>
              <span className="tag">{v?.measured ?? 0} measured terms</span>
            </div>
            <div className="distribution">
              <div className="donut">
                <svg
                  viewBox="0 0 120 120"
                  role="img"
                  aria-label="Distribution of measured keyword rankings"
                >
                  <circle
                    cx="60"
                    cy="60"
                    r="45"
                    stroke="#edf1ef"
                    strokeWidth="14"
                    fill="none"
                  />
                  {distribution.map((count, i) => {
                    const start = offset;
                    offset += (count / Math.max(1, v?.measured ?? 0)) * 100;
                    return (
                      <circle
                        key={i}
                        cx="60"
                        cy="60"
                        r="45"
                        fill="none"
                        stroke={colors[i]}
                        strokeWidth="14"
                        pathLength="100"
                        strokeDasharray={`${(count / Math.max(1, v?.measured ?? 0)) * 100} ${100 - (count / Math.max(1, v?.measured ?? 0)) * 100}`}
                        strokeDashoffset={-start}
                        transform="rotate(-90 60 60)"
                      />
                    );
                  })}
                  <text
                    x="60"
                    y="60"
                    textAnchor="middle"
                    style={{ fontSize: 20, fontWeight: 700, fill: "#243d43" }}
                  >
                    {(v?.measured ?? 0)
                      ? `${fmt((100 * (v?.top_10 ?? 0)) / (v?.measured ?? 0), 1)}%`
                      : "—"}
                  </text>
                  <text
                    x="60"
                    y="75"
                    textAnchor="middle"
                    style={{ fontSize: 7, fill: "#7a8c8e" }}
                  >
                    in the top 10
                  </text>
                </svg>
              </div>
              <ul>
                {[
                  "Top 3",
                  "Positions 4–10",
                  "Positions 11–20",
                  "Positions 21–100",
                  "Outside top 100",
                ].map((label, i) => (
                  <li key={label}>
                    <i style={{ background: colors[i] }} />
                    {label}
                    <b>{distribution[i]}</b>
                  </li>
                ))}
              </ul>
            </div>
            <p className="note">
              {(v?.matched ?? 0)
                ? `${((((v?.matched_current_top_10 ?? 0) - (v?.matched_previous_top_10 ?? 0)) * 100) / (v?.matched ?? 0)).toFixed(1)} percentage-point change in top-10 coverage across comparable terms`
                : "Previous-period coverage comparison unavailable"}
            </p>
            <div className="ministats">
              <span>
                <b>{matched.length ? improved.length : "—"}</b> improving
              </span>
              <span>
                <b>{matched.length ? declined.length : "—"}</b> declining
              </span>
              <span>
                <b>{matched.length}</b> comparable terms
              </span>
            </div>
            <p className="note">
              {(v?.tracked ?? 0) - (v?.measured ?? 0)} unmeasured terms
              excluded. Movement uses the same dated terms in both periods.
            </p>
          </article>
          <article className="card">
            <div className="cardtop">
              <h3>AI mentions & citations</h3>
              <span className="tag">
                {d.visibility.ai.prompt_count} tracked prompts
              </span>
            </div>
            <div className="aistats">
              <div>
                <b>
                  {pct(
                    mentionRows.length
                      ? (100 * mentionRows.filter((r) => r.mentioned).length) /
                          mentionRows.length
                      : null,
                  )}
                </b>
                <span>Brand mention presence</span>
                <PointChange a={mentionChange.current} b={mentionChange.previous} />
                <small className="comparison-note">{mentionChange.count} comparable prompts</small>
              </div>
              <div>
                <b>
                  {pct(
                    citationRows.length
                      ? (100 * citationRows.filter((r) => r.cited).length) /
                          citationRows.length
                      : null,
                  )}
                </b>
                <span>Citation / link presence</span>
                <PointChange a={citationChange.current} b={citationChange.previous} />
                <small className="comparison-note">{citationChange.count} comparable prompts</small>
              </div>
            </div>
            <Table
              heads={["Provider", "Mentioned", "Cited", "Checks"]}
              rows={providers}
            />
            <p className="note">
              Rates use the dated checks shown here, excluding unknown
              responses. Bot visits are not mentions or citations.
            </p>
          </article>
        </div>
        <article className="card movers">
          <h3>Keyword movement worth reviewing</h3>
          <Table
            heads={["Keyword", "Previous", "Current", "Movement"]}
            rows={[...improved, ...declined]
              .sort(
                (a, b) =>
                  Math.abs(validPos(b.current) - validPos(b.previous)) -
                  Math.abs(validPos(a.current) - validPos(a.previous)),
              )
              .slice(0, 5)
              .map((r) => [
                r.term,
                validPos(r.previous) === 101
                  ? "Outside top 100"
                  : r.previous?.position,
                validPos(r.current) === 101
                  ? "Outside top 100"
                  : r.current?.position,
                <span
                  key={r.term}
                  className={
                    validPos(r.current) < validPos(r.previous) ? "up" : "down"
                  }
                >
                  {validPos(r.current) < validPos(r.previous)
                    ? "Improved"
                    : "Declined"}
                </span>,
              ])}
          />
          {!matched.length && (
            <p className="note">
              Current rankings are available; this client has no comparable
              prior-period keyword cohort.
            </p>
          )}
        </article>
        {detail === "visibility" && (
          <article className="card detail">
            <h3>All tracked keywords</h3>
            <Table
              heads={[
                "Keyword / ranking page",
                "Previous",
                "Current",
                "Observed",
              ]}
              rows={terms.map((r) => [
                <>
                  {r.term}
                  <small className="pageurl">
                    {r.current?.ranking_url ?? "No ranking URL"}
                  </small>
                </>,
                r.previous
                  ? validPos(r.previous) === 101
                    ? "Outside top 100"
                    : fmt(r.previous?.position)
                  : "Not measured",
                r.current
                  ? validPos(r.current) === 101
                    ? "Outside top 100"
                    : fmt(r.current?.position)
                  : "Not measured",
                r.current?.observed_on ?? "—",
              ])}
            />
            <h3>Prompt observations</h3>
            <Table
              heads={["Prompt", "Provider", "Mentioned", "Cited"]}
              rows={(d.exploration?.prompts ?? []).map((r) => [
                r.prompt,
                r.provider,
                r.mentioned == null ? "Unknown" : r.mentioned ? "Yes" : "No",
                r.cited == null ? "Unknown" : r.cited ? "Yes" : "No",
              ])}
            />
          </article>
        )}
      </section>
      <section id="traffic">
        <div className="sectiontitle">
          <div>
            <span className="step">02</span>
            <h2>Where are people coming from?</h2>
            <p>See the trend, then the channels contributing to it.</p>
          </div>
          <button
            className="textbutton"
            aria-expanded={detail === "traffic"}
            onClick={() => toggle("traffic")}
          >
            {detail === "traffic" ? "Close detail" : "Explore traffic →"}
          </button>
        </div>
        <div className="twocol">
          <Chart
            title="Visits over the period"
            current={d.traffic.ga4_sessions.series}
            previous={d.exploration?.previous_sessions_series ?? []}
            dates={dates}
          />
          <article className="card">
            <h3>Traffic by channel</h3>
            <Table
              heads={["Channel", "Visits", "Previous", "Change"]}
              rows={[...channels]
                .sort((a, b) => b.sessions - a.sessions)
                .map((r) => [
                  r.label,
                  fmt(r.sessions),
                  fmt(previous.get(r.channel)?.sessions),
                  <Change
                    key={r.channel}
                    a={r.sessions}
                    b={previous.get(r.channel)?.sessions}
                  />,
                ])}
            />
          </article>
        </div>
        <p className="note">
          Charts and channel tables use daily detail; totals can differ slightly
          from exact-period site visits above. AI referrals are counted once.
        </p>
        {detail === "traffic" && (
          <article className="card detail">
            <h3>Identified AI referral sources</h3>
            <Table
              heads={["Source", "Visits", "Google channel"]}
              rows={(d.service_reporting?.ai_sources ?? []).map((r) => [
                r.source,
                fmt(r.sessions),
                r.google_channels?.join(", ") ?? "—",
              ])}
            />
            <h3>Most visited pages</h3>
            <Table
              heads={["Page", "Visits", "Views"]}
              rows={[...pages]
                .sort((a, b) => b.ga4_sessions - a.ga4_sessions)
                .slice(0, 10)
                .map((r) => [r.page, <ComparisonValue key="visits" current={r.ga4_sessions} previous={r.previous_ga4_sessions} />, <ComparisonValue key="views" current={r.ga4_views} previous={r.previous_ga4_views} />])}
            />
            <p className="note">
              Page comparisons use equal-length observed periods. Missing history is shown as unavailable.
            </p>
          </article>
        )}
      </section>
      <section id="leads">
        <div className="sectiontitle">
          <div>
            <span className="step">03</span>
            <h2>Does the traffic engage?</h2>
            <p>
              Engagement gives context. Lead-producing visits show the business
              outcome.
            </p>
          </div>
          <button
            className="textbutton"
            aria-expanded={detail === "leads"}
            onClick={() => toggle("leads")}
          >
            {detail === "leads"
              ? "Close detail"
              : "Explore engagement & leads →"}
          </button>
        </div>
        <div className="twocol">
          <Chart
            title="Lead events over the period"
            current={d.conversions.leads.series}
            previous={d.exploration?.previous_leads_series ?? []}
            dates={dates}
            unit="lead events"
          />
          <article className="card">
            <h3>From visits to leads</h3>
            <div className="funnel">
              <div>
                <span>Site visits</span>
                <ComparisonValue current={sessions.current} previous={sessions.previous} />
              </div>
              <div>
                <span>Visits generating at least one lead</span>
                <ComparisonValue current={d.conversions.lead_sessions?.current} previous={d.conversions.lead_sessions?.previous} />
              </div>
              <div className="emphasis">
                <span>Visit-based lead conversion</span>
                <ComparisonValue current={rate?.current} previous={rate?.previous} rate />
              </div>
            </div>
            <div className="ministats">
              <span>
                Target <b>{pct(d.conversions.session_rate_target_pct)}</b>
              </span>
            </div>
            <p className="note">
              {fmt(d.conversions.leads.current)} lead events across{" "}
              {fmt(d.conversions.lead_sessions?.current)} converting visits.
              Multiple events can occur in one visit.
            </p>
          </article>
        </div>
        <article className="card movers">
          <div className="cardtop">
            <h3>Pages contributing visits & lead events</h3>
            <select
              aria-label="Sort pages"
              value={pageSort}
              onChange={(e) => setPageSort(e.target.value)}
            >
              <option value="leads">Most lead events</option>
              <option value="visits">Most visits</option>
            </select>
          </div>
          <Table
            heads={["Page", "Visits", "Lead events", "Events / 100 visits"]}
            rows={pages.slice(0, detail === "leads" ? 20 : 5).map((r) => [
              <span key={r.page} className="pageurl">
                {r.page}
              </span>,
              <ComparisonValue key="visits" current={r.ga4_sessions} previous={r.previous_ga4_sessions} />,
              <ComparisonValue key="events" current={d.conversions.configured ? r.ga4_key_events : null} previous={r.previous_ga4_key_events} />,
              <ComparisonValue key="rate" current={d.conversions.configured ? r.session_key_event_rate : null} previous={r.previous_session_key_event_rate} decimals={2} showChange={false} />,
            ])}
          />
          <p className="note">
            Page rates count lead events, not unique converting visits.
            Informational pages are not automatically conversion problems.
            Page-level engagement is not available in this report.
          </p>
        </article>
        {detail === "leads" && (
          <article className="card detail">
            <h3>Engagement by channel</h3>
            <Table
              heads={["Channel", "Visits", "Engagement rate", "Bounce rate"]}
              rows={channels.map((r) => [
                r.label,
                fmt(r.sessions),
                <ComparisonValue key="engagement" current={r.bounce_rate == null ? null : 100 - r.bounce_rate} previous={previous.get(r.channel)?.bounce_rate == null ? null : 100 - previous.get(r.channel)!.bounce_rate!} rate />,
                <ComparisonValue key="bounce" current={r.bounce_rate} previous={previous.get(r.channel)?.bounce_rate} rate lowerIsBetter />,
              ])}
            />
            <p className="note">
              Summary engagement is weighted across measured channel sessions.
              Session duration and interaction details are not available here.
            </p>
            <h3>Configured lead events</h3>
            <p>{d.conversions.lead_events.join(" · ")}</p>
            <p>
              Search CTR: {pct(d.traffic.gsc_ctr.current)} · previous{" "}
              {pct(d.traffic.gsc_ctr.previous)}
            </p>
          </article>
        )}
      </section>
      <section>
        <div className="sectiontitle">
          <div>
            <span className="step">04</span>
            <h2>OrganicIQ’s impact</h2>
            <p>Service contribution and progress since we started.</p>
          </div>
        </div>
      </section>
      <article className="card service">
        <h3>Service contribution</h3>
        <Table
          heads={["Service", "Visits", "Lead events"]}
          rows={(d.service_reporting?.rows ?? []).map((r) => [
            r.label,
            <ComparisonValue key="visits" current={r.sessions.current} previous={r.sessions.previous} />,
            <ComparisonValue key="events" current={r.lead_events.current} previous={r.lead_events.previous} />,
          ])}
        />
        <p className="note">
          Part of site totals; observed traffic is not proof of agency impact.
        </p>
      </article>
      <section>
        <div className="sectiontitle">
          <div>
            <h3>Progress since we started</h3>
            <p>
              Starting baseline for quarterly review, separate from the
              previous-period comparisons above.
            </p>
          </div>
        </div>
        <article className="card">
          <div className="cardtop">
            <h3>Baseline comparison</h3>
            <Link className="textbutton" href={settingsHref}>
              Review baseline settings →
            </Link>
            <span className="tag">
              {d.baseline.period_start} – {d.baseline.period_end}
            </span>
          </div>
          <Table
            heads={["Metric", "Starting baseline", "Current period", "Change"]}
            rows={[
              [
                "Monthly visits",
                fmt(d.baseline.monthly_sessions),
                fmt(d.baseline.vs_current.sessions.current),
                <Change
                  key="sessions"
                  a={d.baseline.vs_current.sessions.current}
                  b={d.baseline.monthly_sessions}
                />,
              ],
              [
                "Monthly lead events",
                fmt(d.baseline.monthly_leads),
                fmt(d.baseline.vs_current.leads.current),
                <Change
                  key="leads"
                  a={d.baseline.vs_current.leads.current}
                  b={d.baseline.monthly_leads}
                />,
              ],
              [
                "Lead event rate · legacy baseline",
                pct(d.baseline.lead_rate),
                pct(d.baseline.vs_current.lead_rate?.current),
                <PointChange
                  key="rate"
                  a={d.baseline.vs_current.lead_rate?.current}
                  b={d.baseline.lead_rate}
                />,
              ],
            ]}
          />
          <p className="note">
            The saved baseline uses lead events per visit. It is not compared
            with the newer visit-based conversion rate.
          </p>
        </article>
      </section>
    </div>
  );
}
