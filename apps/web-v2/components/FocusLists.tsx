"use client";

import { useState } from "react";

import type { LeadsCandidates, TrafficCandidates } from "@/lib/engine";

const num = (n: number | null | undefined, digits = 0) =>
  n == null ? "–" : n.toLocaleString(undefined, { maximumFractionDigits: digits });
const shortPage = (url: string) => url.replace(/^https?:\/\/[^/]+/, "") || "/";

function Change({ value }: { value: number | null }) {
  if (value == null) return <span className="text-[var(--text-tertiary)]">–</span>;
  const up = value > 0;
  return (
    <span className={`text-xs font-semibold ${Math.abs(value) < 1 ? "text-[var(--text-secondary)]" : up ? "text-green-700" : "text-red-700"}`}>
      {Math.abs(value) < 1 ? "flat" : `${up ? "▲" : "▼"} ${Math.abs(value).toFixed(0)}%`}
    </span>
  );
}

function PickBar({
  picked,
  max,
  diagnosing,
  onDiagnose,
  onClear,
}: {
  picked: string[];
  max: number;
  diagnosing: boolean;
  onDiagnose: () => void;
  onClear: () => void;
}) {
  return (
    <div className="mt-4 flex flex-wrap items-center gap-3 text-sm">
      <button
        type="button"
        disabled={diagnosing || picked.length === 0}
        onClick={onDiagnose}
        className="rounded-lg bg-[var(--brand-dark)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
      >
        {diagnosing ? "Reading the pages…" : `Diagnose ${picked.length || ""} selected`.replace("  ", " ")}
      </button>
      <span className="text-xs text-[var(--text-secondary)]">
        Tick up to {max} pages. Each is read live from the client&apos;s site, with what is worth checking on it.
      </span>
      {picked.length > 0 ? (
        <button type="button" onClick={onClear} className="text-xs text-[var(--text-secondary)] hover:underline">
          Clear
        </button>
      ) : null}
    </div>
  );
}

const MAX_PICKS = 5;

export function TrafficList({
  data,
  collapsed,
  diagnosing,
  onDiagnose,
  onScope,
  buckets,
  onShow,
}: {
  data: TrafficCandidates;
  collapsed: boolean;
  diagnosing: boolean;
  onDiagnose: (pages: string[]) => void;
  onScope: (bucketId: string) => void;
  buckets: { id: string; name: string }[];
  onShow: () => void;
}) {
  const [picked, setPicked] = useState<string[]>([]);
  const toggle = (key: string) => setPicked((c) => (c.includes(key) ? c.filter((k) => k !== key) : [...c, key]));
  const [sortBy, setSortBy] = useState<"month" | "year">("month");
  const [shown, setShown] = useState(25);
  const dropped = [...data.dropped_pages].sort((a, b) =>
    sortBy === "month" ? b.lost_month - a.lost_month || b.lost_year - a.lost_year : b.lost_year - a.lost_year || b.lost_month - a.lost_month,
  );

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold">Traffic candidates</h2>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            {collapsed
              ? `${picked.length} selected · ${data.counts.strong} strong, ${data.counts.possible} possible.`
              : `Organic sessions that fell, judged against the site's own trend. ${data.windows.three_months[0]} to ${data.windows.three_months[1]}, against the same months a year earlier.`}
          </p>
        </div>
        {collapsed ? (
          <button type="button" onClick={onShow} className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm font-semibold">
            Show the candidates
          </button>
        ) : (
          <label className="text-sm">
            <span className="font-semibold">Scope</span>
            <select
              value={data.bucket?.id ?? "site"}
              onChange={(e) => onScope(e.target.value)}
              className="ml-2 rounded-lg border border-[var(--border)] bg-white px-3 py-1.5 text-sm"
            >
              <option value="site">Whole site</option>
              {buckets.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {!collapsed ? (
        <>
          <p className="mt-3 text-sm text-[var(--text-secondary)]">
            The whole site: {num(data.site.three_months.current)} organic sessions in the last three months
            {data.site.has_last_year ? (
              <>
                , <Change value={data.site.three_months.change_pct} /> on the same months last year ({num(data.site.three_months.last_year)}).
              </>
            ) : (
              ". There is no data from last year, so the slow-bleed test cannot run."
            )}{" "}
            Last month: {num(data.site.sessions.current)}, <Change value={data.site.sessions.change_pct} /> on the month before.
          </p>
          <p className="mt-1 text-xs text-[var(--text-tertiary)]">
            Sudden: {data.thresholds.sudden}. Slow bleed: {data.thresholds.slow_bleed}.
          </p>

          <PickBar picked={picked} max={MAX_PICKS} diagnosing={diagnosing} onDiagnose={() => onDiagnose(picked)} onClear={() => setPicked([])} />

          <div className="mt-5 flex flex-wrap items-end justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold">Pages that dropped</h3>
              <p className="text-xs text-[var(--text-tertiary)]">
                Every page that lost 5+ organic sessions a month, whatever the tests say: {data.dropped_total} in {data.scope}.
              </p>
            </div>
            <label className="text-sm">
              <span className="font-semibold">Biggest drop</span>
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as "month" | "year")}
                className="ml-2 rounded-lg border border-[var(--border)] bg-white px-3 py-1.5 text-sm"
              >
                <option value="month">Last month vs the month before</option>
                <option value="year">Last 3 months vs last year</option>
              </select>
            </label>
          </div>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full min-w-[40rem] text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-[var(--text-tertiary)]">
                <tr>
                  <th className="w-6 py-1 pr-2" />
                  <th className="py-1 pr-3 font-medium">Page</th>
                  <th className="px-3 py-1 text-right font-medium">Last month</th>
                  <th className="px-3 py-1 text-right font-medium">3 months vs last year</th>
                  <th className="px-3 py-1 text-right font-medium">Lost a month</th>
                  <th className="py-1 pl-3 font-medium">Flag</th>
                </tr>
              </thead>
              <tbody>
                {dropped.slice(0, shown).map((d) => (
                  <tr key={d.page} className="border-t border-[var(--border)] align-top">
                    <td className="py-2 pr-2">
                      <input
                        type="checkbox"
                        checked={picked.includes(d.page)}
                        disabled={picked.length >= MAX_PICKS && !picked.includes(d.page)}
                        onChange={() => toggle(d.page)}
                        aria-label={`Diagnose ${shortPage(d.page)}`}
                      />
                    </td>
                    <td className="min-w-[10rem] break-all py-2 pr-3 font-medium">{shortPage(d.page)}</td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {num(d.sessions.current)} <Change value={d.sessions.change_pct} />
                      <div className="text-xs text-[var(--text-tertiary)]">was {num(d.sessions.previous)}</div>
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {num(d.three_months.current)} <Change value={d.three_months.change_pct} />
                      <div className="text-xs text-[var(--text-tertiary)]">was {num(d.three_months.last_year)}</div>
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      <span className="font-semibold">{num(sortBy === "month" ? d.lost_month : d.lost_year)}</span>
                      <div className="text-xs text-[var(--text-tertiary)]">{sortBy === "month" ? "vs month before" : "vs last year, per month"}</div>
                    </td>
                    <td className="py-2 pl-3 text-xs">
                      {d.flag ? (
                        <span className="rounded bg-red-50 px-2 py-0.5 font-semibold text-red-800">
                          {d.flag === "sudden" ? "sudden drop" : d.flag === "slow_bleed" ? "slow bleed" : "sudden + slow"}
                        </span>
                      ) : (
                        <span className="text-[var(--text-tertiary)]">under the test thresholds</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {dropped.length === 0 ? <p className="py-4 text-sm text-[var(--text-tertiary)]">No page lost 5+ sessions a month in this scope.</p> : null}
            {dropped.length > shown ? (
              <button type="button" onClick={() => setShown((n) => n + 25)} className="mt-2 text-sm font-semibold underline">
                Show 25 more ({dropped.length - shown} left)
              </button>
            ) : null}
          </div>

          <h3 className="mt-6 text-sm font-semibold">Ranked against the site's trend</h3>

          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[40rem] text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-[var(--text-tertiary)]">
                <tr>
                  <th className="w-6 py-1 pr-2" />
                  <th className="py-1 pr-3 font-medium">What</th>
                  <th className="px-3 py-1 text-right font-medium">Last month</th>
                  <th className="px-3 py-1 text-right font-medium">3 months vs last year</th>
                  <th className="px-3 py-1 text-right font-medium">Sessions at stake</th>
                  <th className="py-1 pl-3 font-medium">Strength</th>
                </tr>
              </thead>
              <tbody>
                {data.candidates.map((c) => (
                  <tr key={`${c.level}|${c.key}`} className="border-t border-[var(--border)] align-top">
                    <td className="py-2 pr-2">
                      {c.level === "page" ? (
                        <input
                          type="checkbox"
                          checked={picked.includes(c.key)}
                          disabled={picked.length >= MAX_PICKS && !picked.includes(c.key)}
                          onChange={() => toggle(c.key)}
                          aria-label={`Diagnose ${shortPage(c.key)}`}
                        />
                      ) : null}
                    </td>
                    <td className="min-w-[10rem] py-2 pr-3">
                      <div className="font-medium">{c.level === "page" ? shortPage(c.key) : c.label}</div>
                      <div className="mt-0.5 text-xs text-[var(--text-tertiary)]">
                        {c.level === "site" ? "whole site" : c.level === "bucket" ? "bucket, all its pages together" : "page"}
                      </div>
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {num(c.sessions.current)} <Change value={c.sessions.change_pct} />
                      <div className="text-xs text-[var(--text-tertiary)]">was {num(c.sessions.previous)}</div>
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {num(c.three_months.current)} <Change value={c.three_months.change_pct} />
                      <div className="text-xs text-[var(--text-tertiary)]">was {num(c.three_months.last_year)}</div>
                    </td>
                    <td className="px-3 py-2 text-right font-semibold tabular-nums">{c.at_stake > 0 ? num(c.at_stake) : "–"}</td>
                    <td className="py-2 pl-3">
                      <span
                        className={`whitespace-nowrap rounded px-2 py-0.5 text-xs font-semibold ${
                          c.strength === "strong" ? "bg-red-50 text-red-800" : "bg-[var(--bg)] text-[var(--text-secondary)]"
                        }`}
                      >
                        {c.flag === "sudden" ? "sudden drop" : c.flag === "slow_bleed" ? "slow bleed" : c.flag === "both" ? "sudden + slow" : "possible"}
                      </span>
                      {c.reason ? <div className="mt-0.5 max-w-[14rem] text-xs text-[var(--text-tertiary)]">{c.reason}</div> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {data.candidates.length === 0 ? <p className="py-4 text-sm text-[var(--text-tertiary)]">Nothing to list for this scope.</p> : null}
          </div>
          <ul className="mt-3 space-y-1 text-xs text-[var(--text-tertiary)]">
            {data.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </>
      ) : null}
    </div>
  );
}

export function LeadsList({
  data,
  collapsed,
  diagnosing,
  onDiagnose,
  onScope,
  buckets,
  onShow,
  settingsHref,
}: {
  data: LeadsCandidates;
  collapsed: boolean;
  diagnosing: boolean;
  onDiagnose: (pages: string[]) => void;
  onScope: (bucketId: string) => void;
  buckets: { id: string; name: string }[];
  onShow: () => void;
  settingsHref: string;
}) {
  const [picked, setPicked] = useState<string[]>([]);
  const toggle = (key: string) => setPicked((c) => (c.includes(key) ? c.filter((k) => k !== key) : [...c, key]));
  const noun = data.noun.plural;

  if (data.needs === "conversions") {
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-900">
        <h2 className="font-semibold">Leads needs conversions defined first</h2>
        <p className="mt-1">
          This list ranks pages by the {noun} they miss, so it needs to know which GA4 events count as one. Set them in{" "}
          <a href={settingsHref} className="font-semibold underline">
            Settings → Conversions &amp; goals
          </a>
          .
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold">{noun.charAt(0).toUpperCase() + noun.slice(1)} candidates</h2>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            {collapsed
              ? `${picked.length} selected · ${data.counts.strong} strong, ${data.counts.possible} possible.`
              : `Pages whose organic visitors convert or engage less than this site's own norm. ${data.window.from} to ${data.window.to}. Counting: ${data.conversion_events.join(", ")}.`}
          </p>
        </div>
        {collapsed ? (
          <button type="button" onClick={onShow} className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm font-semibold">
            Show the candidates
          </button>
        ) : (
          <label className="text-sm">
            <span className="font-semibold">Scope</span>
            <select
              value={data.bucket?.id ?? "site"}
              onChange={(e) => onScope(e.target.value)}
              className="ml-2 rounded-lg border border-[var(--border)] bg-white px-3 py-1.5 text-sm"
            >
              <option value="site">Whole site</option>
              {buckets.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {!collapsed && data.site ? (
        <>
          <p className="mt-3 text-sm text-[var(--text-secondary)]">
            The site&apos;s own norm, from {data.site.qualifying_pages} pages with 50+ organic sessions: {data.site.median_conversion_rate ?? "–"}% convert and{" "}
            {data.site.median_engagement_rate ?? "–"}% engage. A page is compared with these, not with an outside benchmark.
          </p>
          {data.candidates.length === 0 ? (
            <p className="mt-4 rounded-lg bg-[var(--bg)] p-3 text-sm text-[var(--text-secondary)]">
              No page in this scope has 50+ organic sessions over the three months, so none can be compared.
            </p>
          ) : (
            <>
              <PickBar picked={picked} max={MAX_PICKS} diagnosing={diagnosing} onDiagnose={() => onDiagnose(picked)} onClear={() => setPicked([])} />
              <div className="mt-4 overflow-x-auto">
                <table className="w-full min-w-[40rem] text-left text-sm">
                  <thead className="text-xs uppercase tracking-wide text-[var(--text-tertiary)]">
                    <tr>
                      <th className="w-6 py-1 pr-2" />
                      <th className="py-1 pr-3 font-medium">Page</th>
                      <th className="px-3 py-1 text-right font-medium">Sessions</th>
                      <th className="px-3 py-1 text-right font-medium">{data.noun.plural}</th>
                      <th className="px-3 py-1 text-right font-medium">Engagement</th>
                      <th className="px-3 py-1 text-right font-medium">Missed {data.noun.plural}</th>
                      <th className="py-1 pl-3 font-medium">Strength</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.candidates.map((c) => (
                      <tr key={c.page} className="border-t border-[var(--border)] align-top">
                        <td className="py-2 pr-2">
                          <input
                            type="checkbox"
                            checked={picked.includes(c.page)}
                            disabled={picked.length >= MAX_PICKS && !picked.includes(c.page)}
                            onChange={() => toggle(c.page)}
                            aria-label={`Diagnose ${shortPage(c.page)}`}
                          />
                        </td>
                        <td className="min-w-[10rem] py-2 pr-3 font-medium" title={c.page}>
                          {shortPage(c.page)}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums">{num(c.sessions)}</td>
                        <td className="px-3 py-2 text-right tabular-nums">
                          {num(c.conversions)}
                          <div className={`text-xs ${c.worst_conversion ? "text-red-700" : "text-[var(--text-tertiary)]"}`}>{c.conversion_rate}%</div>
                        </td>
                        <td className={`px-3 py-2 text-right tabular-nums ${c.worst_engagement ? "text-red-700" : ""}`}>{c.engagement_rate}%</td>
                        <td className="px-3 py-2 text-right font-semibold tabular-nums">{c.missed_conversions > 0 ? `+${num(c.missed_conversions, 1)}` : "–"}</td>
                        <td className="py-2 pl-3">
                          <span
                            className={`whitespace-nowrap rounded px-2 py-0.5 text-xs font-semibold ${
                              c.strength === "strong" ? "bg-red-50 text-red-800" : "bg-[var(--bg)] text-[var(--text-secondary)]"
                            }`}
                          >
                            {c.strength}
                          </span>
                          {c.reason ? <div className="mt-0.5 max-w-[14rem] text-xs text-[var(--text-tertiary)]">{c.reason}</div> : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
          <ul className="mt-3 space-y-1 text-xs text-[var(--text-tertiary)]">
            {data.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </>
      ) : null}
    </div>
  );
}
