"use client";

import { useState } from "react";

import type { LeadsCandidates, TrafficCandidates } from "@/lib/engine";
import { Spinner } from "@/components/ui/Spinner";

const num = (n: number | null | undefined, digits = 0) =>
  n == null ? "–" : n.toLocaleString(undefined, { maximumFractionDigits: digits });
const shortPage = (url: string) => url.replace(/^https?:\/\/[^/]+/, "") || "/";

function Change({ value }: { value: number | null }) {
  if (value == null) return <span className="text-[#7a838c]">–</span>;
  const up = value > 0;
  return (
    <span
      className={`text-xs font-semibold ${
        Math.abs(value) < 1
          ? "text-[#7a838c]"
          : up
            ? "text-[#00857b]"
            : "text-[oklch(0.48_0.17_25)]"
      }`}
    >
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
        className="cursor-pointer rounded-full bg-[#223540] px-4 py-2 text-[13px] font-semibold text-white transition-colors hover:bg-[#00a99d] disabled:cursor-not-allowed disabled:opacity-50"
      >
        {diagnosing ? (
          <>
            <Spinner />
            Reading the pages…
          </>
        ) : (
          `Diagnose ${picked.length || ""} selected`.replace("  ", " ")
        )}
      </button>
      <span className="text-xs text-[#4a5560]">
        Select up to {max} pages. Each is read live from the client&apos;s site, with page-type checks and history.
      </span>
      {picked.length > 0 ? (
        <button
          type="button"
          onClick={onClear}
          className="cursor-pointer rounded-full border border-[#e3e6e8] bg-white px-3 py-1 text-xs font-semibold text-[#4a5560] hover:text-[#0a0c0f]"
        >
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
    <div className="rounded-xl border border-[#ececec] bg-white p-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">Focus candidates</div>
          <h2 className="mt-0.5 font-[var(--font-heading)] text-lg font-bold text-[#0a0c0f]">Traffic candidates</h2>
          <p className="mt-1 text-[13px] text-[#4a5560]">
            {collapsed
              ? `${picked.length} selected · ${data.counts.strong} strong, ${data.counts.possible} possible.`
              : `Organic sessions that fell, judged against the site's own trend. ${data.windows.three_months[0]} to ${data.windows.three_months[1]}, against the same months a year earlier.`}
          </p>
        </div>
        {collapsed ? (
          <button
            type="button"
            onClick={onShow}
            className="cursor-pointer rounded-full border border-[#d3d7d9] bg-white px-3.5 py-1.5 text-xs font-semibold text-[#223540] hover:border-[#00a99d] hover:bg-[#e6f7f5]"
          >
            Show the candidates
          </button>
        ) : (
          <label className="text-xs font-semibold text-[#171a22]">
            Scope
            <select
              value={data.bucket?.id ?? "site"}
              onChange={(e) => onScope(e.target.value)}
              className="ml-2 rounded-[10px] border border-[#e3e6e8] bg-white px-3 py-1.5 text-sm font-normal text-[#171a22]"
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
          <p className="mt-3 text-sm text-[#4a5560]">
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
          <p className="mt-1 text-xs text-[#7a838c]">
            Sudden: {data.thresholds.sudden}. Slow bleed: {data.thresholds.slow_bleed}.
          </p>

          <PickBar picked={picked} max={MAX_PICKS} diagnosing={diagnosing} onDiagnose={() => onDiagnose(picked)} onClear={() => setPicked([])} />

          <div className="mt-5 flex flex-wrap items-end justify-between gap-3">
            <div>
              <h3 className="font-[var(--font-heading)] text-base font-bold text-[#0a0c0f]">Pages that dropped</h3>
              <p className="text-xs text-[#7a838c]">
                Every page that lost 5+ organic sessions a month, whatever the tests say: {data.dropped_total} in {data.scope}.
              </p>
            </div>
            <label className="text-xs font-semibold text-[#171a22]">
              Biggest drop
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as "month" | "year")}
                className="ml-2 rounded-[10px] border border-[#e3e6e8] bg-white px-3 py-1.5 text-sm font-normal text-[#171a22]"
              >
                <option value="month">Last month vs the month before</option>
                <option value="year">Last 3 months vs last year</option>
              </select>
            </label>
          </div>
          <div className="mt-2 overflow-x-auto rounded-[10px] border border-[#ececec]">
            <table className="w-full min-w-[40rem] text-left text-sm">
              <thead className="bg-[#fbfbfb] text-[10px] font-bold uppercase tracking-[0.1em] text-[#909a9f]">
                <tr>
                  <th className="w-6 px-3 py-2" />
                  <th className="py-2 pr-3 font-bold">Page</th>
                  <th className="px-3 py-2 text-right font-bold">Last month</th>
                  <th className="px-3 py-2 text-right font-bold">3 months vs last year</th>
                  <th className="px-3 py-2 text-right font-bold">Lost a month</th>
                  <th className="px-3 py-2 font-bold">Flag</th>
                </tr>
              </thead>
              <tbody>
                {dropped.slice(0, shown).map((d) => {
                  const selected = picked.includes(d.page);
                  return (
                    <tr
                      key={d.page}
                      className={`border-t border-[#f1f2f3] align-top ${selected ? "bg-[#eef8f7]" : "bg-white hover:bg-[#f8f8f8]"}`}
                    >
                      <td className="px-3 py-2.5">
                        <input
                          type="checkbox"
                          checked={selected}
                          disabled={picked.length >= MAX_PICKS && !selected}
                          onChange={() => toggle(d.page)}
                          aria-label={`Diagnose ${shortPage(d.page)}`}
                        />
                      </td>
                      <td className="min-w-[10rem] break-all py-2.5 pr-3 font-medium text-[#0a0c0f]">{shortPage(d.page)}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums text-[#171a22]">
                        {num(d.sessions.current)} <Change value={d.sessions.change_pct} />
                        <div className="text-xs text-[#7a838c]">was {num(d.sessions.previous)}</div>
                      </td>
                      <td className="px-3 py-2.5 text-right tabular-nums text-[#171a22]">
                        {num(d.three_months.current)} <Change value={d.three_months.change_pct} />
                        <div className="text-xs text-[#7a838c]">was {num(d.three_months.last_year)}</div>
                      </td>
                      <td className="px-3 py-2.5 text-right tabular-nums">
                        <span className="font-semibold text-[#0a0c0f]">{num(sortBy === "month" ? d.lost_month : d.lost_year)}</span>
                        <div className="text-xs text-[#7a838c]">{sortBy === "month" ? "vs month before" : "vs last year, per month"}</div>
                      </td>
                      <td className="px-3 py-2.5 text-xs">
                        {d.flag ? (
                          <span className="rounded-full bg-[oklch(0.965_0.025_25)] px-2.5 py-0.5 text-[11px] font-semibold text-[oklch(0.48_0.17_25)]">
                            {d.flag === "sudden" ? "sudden drop" : d.flag === "slow_bleed" ? "slow bleed" : "sudden + slow"}
                          </span>
                        ) : (
                          <span className="text-[#7a838c]">under the test thresholds</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {dropped.length === 0 ? <p className="px-4 py-4 text-sm text-[#7a838c]">No page lost 5+ sessions a month in this scope.</p> : null}
          </div>
          {dropped.length > shown ? (
            <button type="button" onClick={() => setShown((n) => n + 25)} className="mt-2 cursor-pointer text-xs font-semibold text-[#00857b] hover:underline">
              Show 25 more ({dropped.length - shown} left)
            </button>
          ) : null}

          <h3 className="mt-6 font-[var(--font-heading)] text-base font-bold text-[#0a0c0f]">Ranked against the site&apos;s trend</h3>

          <div className="mt-2 overflow-x-auto rounded-[10px] border border-[#ececec]">
            <table className="w-full min-w-[40rem] text-left text-sm">
              <thead className="bg-[#fbfbfb] text-[10px] font-bold uppercase tracking-[0.1em] text-[#909a9f]">
                <tr>
                  <th className="w-6 px-3 py-2" />
                  <th className="py-2 pr-3 font-bold">What</th>
                  <th className="px-3 py-2 text-right font-bold">Last month</th>
                  <th className="px-3 py-2 text-right font-bold">3 months vs last year</th>
                  <th className="px-3 py-2 text-right font-bold">Sessions at stake</th>
                  <th className="px-3 py-2 font-bold">Strength</th>
                </tr>
              </thead>
              <tbody>
                {data.candidates.map((c) => {
                  const selected = c.level === "page" && picked.includes(c.key);
                  return (
                    <tr
                      key={`${c.level}|${c.key}`}
                      className={`border-t border-[#f1f2f3] align-top ${selected ? "bg-[#eef8f7]" : "bg-white hover:bg-[#f8f8f8]"}`}
                    >
                      <td className="px-3 py-2.5">
                        {c.level === "page" ? (
                          <input
                            type="checkbox"
                            checked={selected}
                            disabled={picked.length >= MAX_PICKS && !selected}
                            onChange={() => toggle(c.key)}
                            aria-label={`Diagnose ${shortPage(c.key)}`}
                          />
                        ) : null}
                      </td>
                      <td className="min-w-[10rem] py-2.5 pr-3">
                        <div className="font-medium text-[#0a0c0f]">{c.level === "page" ? shortPage(c.key) : c.label}</div>
                        <div className="mt-0.5 text-xs text-[#7a838c]">
                          {c.level === "site" ? "whole site" : c.level === "bucket" ? "bucket, all its pages together" : "page"}
                        </div>
                      </td>
                      <td className="px-3 py-2.5 text-right tabular-nums text-[#171a22]">
                        {num(c.sessions.current)} <Change value={c.sessions.change_pct} />
                        <div className="text-xs text-[#7a838c]">was {num(c.sessions.previous)}</div>
                      </td>
                      <td className="px-3 py-2.5 text-right tabular-nums text-[#171a22]">
                        {num(c.three_months.current)} <Change value={c.three_months.change_pct} />
                        <div className="text-xs text-[#7a838c]">was {num(c.three_months.last_year)}</div>
                      </td>
                      <td className="px-3 py-2.5 text-right font-semibold tabular-nums text-[#0a0c0f]">{c.at_stake > 0 ? num(c.at_stake) : "–"}</td>
                      <td className="px-3 py-2.5">
                        <span
                          className={`whitespace-nowrap rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${
                            c.strength === "strong"
                              ? "bg-[oklch(0.965_0.025_25)] text-[oklch(0.48_0.17_25)]"
                              : "bg-[#f1f3f4] text-[#4a5560]"
                          }`}
                        >
                          {c.flag === "sudden" ? "sudden drop" : c.flag === "slow_bleed" ? "slow bleed" : c.flag === "both" ? "sudden + slow" : "possible"}
                        </span>
                        {c.reason ? <div className="mt-0.5 max-w-[14rem] text-xs text-[#7a838c]">{c.reason}</div> : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {data.candidates.length === 0 ? <p className="px-4 py-4 text-sm text-[#7a838c]">Nothing to list for this scope.</p> : null}
          </div>
          <ul className="mt-3 space-y-1 text-xs text-[#7a838c]">
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
  const [sortBy, setSortBy] = useState<"missed" | "sessions" | "rate">("missed");
  const [shown, setShown] = useState(25);
  const everyPage = [...(data.all_pages ?? [])].sort((a, b) =>
    sortBy === "sessions" ? b.sessions - a.sessions : sortBy === "rate" ? a.conversion_rate - b.conversion_rate || b.sessions - a.sessions : b.missed_conversions - a.missed_conversions || b.sessions - a.sessions,
  );

  if (data.needs === "conversions") {
    return (
      <div className="rounded-xl border border-dashed border-[oklch(0.88_0.08_85)] bg-white p-5 text-sm text-[#4a5560]">
        <h2 className="font-[var(--font-heading)] font-bold text-[oklch(0.42_0.1_65)]">Leads needs conversions defined first</h2>
        <p className="mt-1">
          This list ranks pages by the {noun} they miss, so it needs to know which GA4 events count as one. Set them in{" "}
          <a href={settingsHref} className="font-semibold text-[#00857b] underline">
            Settings → Conversions &amp; goals
          </a>
          .
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-[#ececec] bg-white p-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">Focus candidates</div>
          <h2 className="mt-0.5 font-[var(--font-heading)] text-lg font-bold text-[#0a0c0f]">
            {noun.charAt(0).toUpperCase() + noun.slice(1)} candidates
          </h2>
          <p className="mt-1 text-[13px] text-[#4a5560]">
            {collapsed
              ? `${picked.length} selected · ${data.counts.strong} strong, ${data.counts.possible} possible.`
              : `Pages whose organic visitors convert or engage less than this site's own norm. ${data.window.from} to ${data.window.to}. Counting: ${data.conversion_events.join(", ")}.`}
          </p>
        </div>
        {collapsed ? (
          <button
            type="button"
            onClick={onShow}
            className="cursor-pointer rounded-full border border-[#d3d7d9] bg-white px-3.5 py-1.5 text-xs font-semibold text-[#223540] hover:border-[#00a99d] hover:bg-[#e6f7f5]"
          >
            Show the candidates
          </button>
        ) : (
          <label className="text-xs font-semibold text-[#171a22]">
            Scope
            <select
              value={data.bucket?.id ?? "site"}
              onChange={(e) => onScope(e.target.value)}
              className="ml-2 rounded-[10px] border border-[#e3e6e8] bg-white px-3 py-1.5 text-sm font-normal text-[#171a22]"
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
          <p className="mt-3 text-sm text-[#4a5560]">
            The site&apos;s own norm, from {data.site.qualifying_pages} pages with 50+ organic sessions: {data.site.median_conversion_rate ?? "–"}% convert and{" "}
            {data.site.median_engagement_rate ?? "–"}% engage. A page is compared with these, not with an outside benchmark.
          </p>
          {data.candidates.length === 0 ? (
            <p className="mt-4 rounded-[10px] border border-dashed border-[#d3d7d9] bg-[#f8f8f8] p-3 text-sm text-[#4a5560]">
              No page in this scope has 50+ organic sessions over the three months, so none can be compared.
            </p>
          ) : (
            <>
              <PickBar picked={picked} max={MAX_PICKS} diagnosing={diagnosing} onDiagnose={() => onDiagnose(picked)} onClear={() => setPicked([])} />
              <div className="mt-4 overflow-x-auto rounded-[10px] border border-[#ececec]">
                <table className="w-full min-w-[40rem] text-left text-sm">
                  <thead className="bg-[#fbfbfb] text-[10px] font-bold uppercase tracking-[0.1em] text-[#909a9f]">
                    <tr>
                      <th className="w-6 px-3 py-2" />
                      <th className="py-2 pr-3 font-bold">Page</th>
                      <th className="px-3 py-2 text-right font-bold">Sessions</th>
                      <th className="px-3 py-2 text-right font-bold">{data.noun.plural}</th>
                      <th className="px-3 py-2 text-right font-bold">Engagement</th>
                      <th className="px-3 py-2 text-right font-bold">Missed {data.noun.plural}</th>
                      <th className="px-3 py-2 font-bold">Strength</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.candidates.map((c) => {
                      const selected = picked.includes(c.page);
                      return (
                        <tr
                          key={c.page}
                          className={`border-t border-[#f1f2f3] align-top ${selected ? "bg-[#eef8f7]" : "bg-white hover:bg-[#f8f8f8]"}`}
                        >
                          <td className="px-3 py-2.5">
                            <input
                              type="checkbox"
                              checked={selected}
                              disabled={picked.length >= MAX_PICKS && !selected}
                              onChange={() => toggle(c.page)}
                              aria-label={`Diagnose ${shortPage(c.page)}`}
                            />
                          </td>
                          <td className="min-w-[10rem] py-2.5 pr-3 font-medium text-[#0a0c0f]" title={c.page}>
                            {shortPage(c.page)}
                          </td>
                          <td className="px-3 py-2.5 text-right tabular-nums text-[#171a22]">{num(c.sessions)}</td>
                          <td className="px-3 py-2.5 text-right tabular-nums text-[#171a22]">
                            {num(c.conversions)}
                            <div className={`text-xs ${c.worst_conversion ? "text-[oklch(0.48_0.17_25)]" : "text-[#7a838c]"}`}>{c.conversion_rate}%</div>
                          </td>
                          <td className={`px-3 py-2.5 text-right tabular-nums ${c.worst_engagement ? "text-[oklch(0.48_0.17_25)]" : "text-[#171a22]"}`}>{c.engagement_rate}%</td>
                          <td className="px-3 py-2.5 text-right font-semibold tabular-nums text-[#0a0c0f]">{c.missed_conversions > 0 ? `+${num(c.missed_conversions, 1)}` : "–"}</td>
                          <td className="px-3 py-2.5">
                            <span
                              className={`whitespace-nowrap rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${
                                c.strength === "strong"
                                  ? "bg-[oklch(0.965_0.025_25)] text-[oklch(0.48_0.17_25)]"
                                  : "bg-[#f1f3f4] text-[#4a5560]"
                              }`}
                            >
                              {c.strength}
                            </span>
                            {c.reason ? <div className="mt-0.5 max-w-[14rem] text-xs text-[#7a838c]">{c.reason}</div> : null}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </>
          )}
          <div className="mt-6 flex flex-wrap items-end justify-between gap-3">
            <div>
              <h3 className="font-[var(--font-heading)] text-base font-bold text-[#0a0c0f]">Every page with organic visits</h3>
              <p className="text-xs text-[#7a838c]">
                {data.all_pages_total ?? 0} pages with 10+ organic sessions in {data.scope}, including ones too small to be compared with the site&apos;s norm.
              </p>
            </div>
            <label className="text-xs font-semibold text-[#171a22]">
              Sort by
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as "missed" | "sessions" | "rate")}
                className="ml-2 rounded-[10px] border border-[#e3e6e8] bg-white px-3 py-1.5 text-sm font-normal text-[#171a22]"
              >
                <option value="missed">Most missed {noun}</option>
                <option value="sessions">Most sessions</option>
                <option value="rate">Lowest conversion rate</option>
              </select>
            </label>
          </div>
          <div className="mt-2 overflow-x-auto rounded-[10px] border border-[#ececec]">
            <table className="w-full min-w-[40rem] text-left text-sm">
              <thead className="bg-[#fbfbfb] text-[10px] font-bold uppercase tracking-[0.1em] text-[#909a9f]">
                <tr>
                  <th className="w-6 px-3 py-2" />
                  <th className="py-2 pr-3 font-bold">Page</th>
                  <th className="px-3 py-2 text-right font-bold">Sessions</th>
                  <th className="px-3 py-2 text-right font-bold">{noun}</th>
                  <th className="px-3 py-2 text-right font-bold">Engagement</th>
                  <th className="px-3 py-2 text-right font-bold">Missed {noun}</th>
                  <th className="px-3 py-2 font-bold">Compared</th>
                </tr>
              </thead>
              <tbody>
                {everyPage.slice(0, shown).map((p) => {
                  const selected = picked.includes(p.page);
                  return (
                    <tr
                      key={p.page}
                      className={`border-t border-[#f1f2f3] align-top ${selected ? "bg-[#eef8f7]" : "bg-white hover:bg-[#f8f8f8]"}`}
                    >
                      <td className="px-3 py-2.5">
                        <input
                          type="checkbox"
                          checked={selected}
                          disabled={picked.length >= MAX_PICKS && !selected}
                          onChange={() => toggle(p.page)}
                          aria-label={`Diagnose ${shortPage(p.page)}`}
                        />
                      </td>
                      <td className="min-w-[10rem] break-all py-2.5 pr-3 font-medium text-[#0a0c0f]" title={p.page}>
                        {shortPage(p.page)}
                      </td>
                      <td className="px-3 py-2.5 text-right tabular-nums text-[#171a22]">{num(p.sessions)}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums text-[#171a22]">
                        {num(p.conversions)}
                        <div className="text-xs text-[#7a838c]">{p.conversion_rate}%</div>
                      </td>
                      <td className="px-3 py-2.5 text-right tabular-nums text-[#171a22]">{p.engagement_rate}%</td>
                      <td className="px-3 py-2.5 text-right font-semibold tabular-nums text-[#0a0c0f]">{p.missed_conversions > 0 ? `+${num(p.missed_conversions, 1)}` : "–"}</td>
                      <td className="px-3 py-2.5 text-xs text-[#7a838c]">{p.compared ? "yes" : "no, under 50 sessions"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {everyPage.length > shown ? (
            <button type="button" onClick={() => setShown((n) => n + 25)} className="mt-2 cursor-pointer text-xs font-semibold text-[#00857b] hover:underline">
              Show 25 more ({everyPage.length - shown} left)
            </button>
          ) : null}
          <ul className="mt-3 space-y-1 text-xs text-[#7a838c]">
            {data.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </>
      ) : null}
    </div>
  );
}
