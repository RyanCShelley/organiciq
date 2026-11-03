"use client";

import { useRouter } from "next/navigation";
import { Fragment, useEffect, useMemo, useState } from "react";

import { termDetailAction } from "@/app/(app)/[clientSlug]/search-visibility/actions";
import { Spark, WeeklyLine } from "@/components/bi/Charts";
import { Spinner } from "@/components/ui/Spinner";
import type { Client } from "@/lib/api";
import { presets } from "@/lib/bi";
import type { Sv, SvDetail, SvTerm } from "@/lib/search-visibility";

const num = (n: number | null | undefined) => (n == null ? "–" : n.toLocaleString());
const pos = (n: number | null | undefined) => (n == null ? "–" : n.toFixed(1));
const shortPage = (url: string) => url.replace(/^https?:\/\/[^/]+/, "") || "/";
const day = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
const th = "px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-[var(--text-tertiary)]";
const td = "px-3 py-2 tabular-nums";
const card = "rounded-xl border border-[var(--border)] bg-[var(--surface)]";

const BANDS: { key: string; label: string; color: string }[] = [
  { key: "top3", label: "Top 3", color: "#0f766e" },
  { key: "top10", label: "4–10", color: "#2a9d8f" },
  { key: "top20", label: "11–20", color: "#7fc8bd" },
  { key: "beyond", label: "21+", color: "#bfe3dd" },
  { key: "none", label: "Not showing", color: "#e5e7eb" },
];

/** A change in a count or a figure where bigger is better. */
function Delta({ now, before, lowerIsBetter = false }: { now: number | null; before: number | null; lowerIsBetter?: boolean }) {
  if (now == null || before == null || before === 0) return <span className="text-xs text-[var(--text-tertiary)]">no earlier figure</span>;
  const d = now - before;
  if (Math.abs(d) < 0.05) return <span className="text-xs font-semibold text-[var(--text-secondary)]">flat</span>;
  const good = lowerIsBetter ? d < 0 : d > 0;
  return <span className={`text-xs font-semibold ${good ? "text-green-700" : "text-red-700"}`}>{d > 0 ? "▲" : "▼"} {Math.abs(d) >= 10 ? Math.abs(d).toFixed(0) : Math.abs(d).toFixed(1)} <span className="font-normal text-[var(--text-secondary)]">vs before ({num(before)})</span></span>;
}

function Kpi({ label, value, change, note }: { label: string; value: string; change?: React.ReactNode; note?: string }) {
  return (
    <div className={`${card} p-4`}>
      <div className="text-xs font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">{label}</div>
      <div className="mt-1 text-3xl font-bold tabular-nums">{value}</div>
      {change ? <div className="mt-1">{change}</div> : null}
      {note ? <div className="mt-1 text-xs text-[var(--text-secondary)]">{note}</div> : null}
    </div>
  );
}

function Move({ t }: { t: SvTerm }) {
  if (t.move == null) return <span className="text-[var(--text-tertiary)]">–</span>;
  if (Math.abs(t.move) < 0.5) return <span className="text-[var(--text-secondary)]">steady</span>;
  return <span className={`font-semibold ${t.move > 0 ? "text-green-700" : "text-red-700"}`}>{t.move > 0 ? "▲" : "▼"} {Math.abs(t.move)}</span>;
}

function Movers({ title, rows, tone }: { title: string; rows: SvTerm[]; tone: "up" | "down" }) {
  return (
    <div className={`${card} p-5`}>
      <h3 className="text-sm font-semibold">{title}</h3>
      {rows.length === 0 ? (
        <p className="mt-3 text-sm text-[var(--text-secondary)]">None moved by half a position or more.</p>
      ) : (
        <ul className="mt-2 divide-y divide-[var(--border)] text-sm">
          {rows.map((r) => (
            <li key={r.key} className="flex items-center justify-between gap-3 py-2">
              <span className="min-w-0 truncate font-medium">{r.term}</span>
              <span className="whitespace-nowrap tabular-nums text-xs text-[var(--text-secondary)]">
                {pos(r.google.position_before ?? r.ser.position_start)} → {pos(r.google.position ?? r.ser.position)}{" "}
                <span className={`font-semibold ${tone === "up" ? "text-green-700" : "text-red-700"}`}>{tone === "up" ? "▲" : "▼"} {Math.abs(r.move ?? 0)}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Detail({ clientId, term, from, to }: { clientId: string; term: string; from: string; to: string }) {
  const [state, setState] = useState<{ detail?: SvDetail; error?: string } | null>(null);
  useEffect(() => {
    let live = true;
    termDetailAction(clientId, term, from, to).then((r) => live && setState(r.ok ? { detail: r.detail } : { error: r.error }));
    return () => {
      live = false;
    };
  }, [clientId, term, from, to]);
  if (state === null) return <p className="p-4 text-sm text-[var(--text-secondary)]"><Spinner />Reading the term…</p>;
  if (state.error || !state.detail) return <p role="alert" className="p-4 text-sm font-semibold text-red-700">{state.error}</p>;
  const d = state.detail;
  return (
    <div className="grid gap-4 p-4 text-sm lg:grid-cols-3">
      <div>
        <h4 className="text-xs font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">Pages that show for it</h4>
        {d.pages.length === 0 ? <p className="mt-2 text-[var(--text-secondary)]">No page showed for it in Search Console.</p> : (
          <ul className="mt-2 space-y-1">
            {d.pages.map((p) => (
              <li key={p.url} className="flex justify-between gap-2"><span className="min-w-0 break-all font-medium">{shortPage(p.url)}</span><span className="whitespace-nowrap tabular-nums text-xs text-[var(--text-secondary)]">{num(p.impressions)} imp · pos {pos(p.position)}</span></li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <h4 className="text-xs font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">Competitors ranking for it</h4>
        {d.competitors.length === 0 ? <p className="mt-2 text-[var(--text-secondary)]">No competitor rankings read for this term. Competitors are chosen in settings and read monthly.</p> : (
          <ul className="mt-2 space-y-1">
            {d.competitors.map((c) => <li key={c.domain} className="flex justify-between gap-2"><span className="font-medium">{c.domain}</span><span className="tabular-nums text-xs text-[var(--text-secondary)]">position {pos(c.position)}</span></li>)}
          </ul>
        )}
        {d.competitors_read_on ? <p className="mt-1 text-xs text-[var(--text-tertiary)]">Read on {day(d.competitors_read_on)}</p> : null}
      </div>
      <div>
        <h4 className="text-xs font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">What else is on the results page</h4>
        {d.serp ? (
          <>
            <ul className="mt-2 flex flex-wrap gap-1.5">{d.serp.features.map((f) => <li key={f} className="rounded bg-[var(--bg)] px-2 py-0.5 text-xs font-semibold">{f.replace(/_/g, " ")}</li>)}</ul>
            <p className="mt-1 text-xs text-[var(--text-tertiary)]">Read on {day(d.serp.pulled_on)}</p>
          </>
        ) : <p className="mt-2 text-[var(--text-secondary)]">Results-page features have not been read for this term.</p>}
      </div>
    </div>
  );
}

type Filter = "all" | "page1" | "disagree" | "none";

export function SearchVisibility({ client, from, to, bucket, data, error }: { client: Client; from: string; to: string; bucket: string; data: Sv | null; error: string | null }) {
  const router = useRouter();
  const [custom, setCustom] = useState({ from, to });
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const go = (f: string, t: string, b = bucket) => {
    const q = new URLSearchParams({ from: f, to: t });
    if (b) q.set("bucket", b);
    router.push(`/${client.slug}/search-visibility?${q}`);
  };
  const ranges = presets();
  const active = ranges.find((r) => r.from === from && r.to === to)?.key ?? "custom";

  const shown = useMemo(() => {
    if (!data) return [];
    return data.terms.filter((t) => {
      if (query && !t.term.toLowerCase().includes(query.toLowerCase())) return false;
      if (filter === "page1") return t.band === "top3" || t.band === "top10";
      if (filter === "disagree") return t.disagree != null;
      if (filter === "none") return t.band === "none";
      return true;
    });
  }, [data, filter, query]);
  const disagreeing = data?.terms.filter((t) => t.disagree).length ?? 0;
  const maxBand = data ? Math.max(1, ...BANDS.map((b) => Math.max(data.distribution.now[b.key] ?? 0, data.distribution.before[b.key] ?? 0))) : 1;

  return (
    <section className="max-w-6xl space-y-8">
      <header>
        <h1 className="text-2xl font-bold">Search visibility</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          Where the watchlist&apos;s terms show in Google, Bing and SE Ranking, whether the three agree, and what moved. Compared with the same number of days before.
        </p>
      </header>

      <div className="flex flex-wrap items-end gap-2 text-sm">
        {ranges.map((r) => (
          <button key={r.key} type="button" onClick={() => go(r.from, r.to)} className={`rounded-lg border px-3 py-1.5 font-semibold ${active === r.key ? "border-[var(--brand-teal)] bg-[var(--brand-teal)] text-white" : "border-[var(--border)] bg-white"}`}>{r.label}</button>
        ))}
        <label className="text-xs font-semibold">From<input type="date" value={custom.from} onChange={(e) => setCustom({ ...custom, from: e.target.value })} className="mt-1 block rounded-lg border border-[var(--border)] bg-white px-2 py-1.5 text-sm" /></label>
        <label className="text-xs font-semibold">To<input type="date" value={custom.to} onChange={(e) => setCustom({ ...custom, to: e.target.value })} className="mt-1 block rounded-lg border border-[var(--border)] bg-white px-2 py-1.5 text-sm" /></label>
        <button type="button" onClick={() => go(custom.from, custom.to)} disabled={!custom.from || !custom.to || custom.to < custom.from} className="rounded-lg border border-[var(--border)] bg-white px-3 py-1.5 font-semibold disabled:opacity-50">Apply</button>
        {data && data.buckets.length > 0 ? (
          <label className="text-xs font-semibold">
            Bucket
            <select value={bucket} onChange={(e) => go(from, to, e.target.value)} className="mt-1 block rounded-lg border border-[var(--border)] bg-white px-2 py-1.5 text-sm font-normal">
              <option value="">All buckets</option>
              {data.buckets.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
          </label>
        ) : null}
        <span className="pb-2 text-xs text-[var(--text-tertiary)]">{day(from)} to {day(to)}</span>
      </div>

      {error ? <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p> : null}

      {data && data.terms_total === 0 ? (
        <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">The watchlist has no terms{bucket ? " in this bucket" : ""}. Add them in the Watchlist.</p>
      ) : null}

      {data && data.terms_total > 0 ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Kpi label="Terms showing" value={`${data.now.showing} of ${data.terms_total}`} change={<Delta now={data.now.showing} before={data.before.showing} />} note="watchlist terms with any impression in Google" />
            <Kpi label="On page one" value={num(data.now.page_one)} change={<Delta now={data.now.page_one} before={data.before.page_one} />} note="average position 10 or better, with 10+ impressions" />
            <Kpi label="Average position" value={pos(data.now.position)} change={<Delta now={data.now.position} before={data.before.position} lowerIsBetter />} note="weighted by impressions" />
            <Kpi label="Clicks from these terms" value={num(data.now.clicks)} change={<Delta now={data.now.clicks} before={data.before.clicks} />} note={`${num(data.now.impressions)} impressions`} />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <div className={`${card} p-5`}>
              <h3 className="text-sm font-semibold">Clicks per week</h3>
              <div className="mt-2"><WeeklyLine label="Weekly clicks from watchlist terms" points={data.series.map((s) => ({ week: s.week, value: s.clicks }))} bands={data.updates.map((u) => ({ begin: u.begin, end: u.end, title: u.title }))} /></div>
            </div>
            <div className={`${card} p-5`}>
              <h3 className="text-sm font-semibold">Average position per week <span className="font-normal text-[var(--text-tertiary)]">(higher on the chart is better)</span></h3>
              <div className="mt-2"><WeeklyLine invert label="Weekly average position of watchlist terms" format={(n) => n.toFixed(1)} points={data.series.map((s) => ({ week: s.week, value: s.position }))} bands={data.updates.map((u) => ({ begin: u.begin, end: u.end, title: u.title }))} /></div>
            </div>
          </div>
          {data.updates.length > 0 ? (
            <ul className="-mt-4 space-y-1 text-xs text-[var(--text-secondary)]">
              {data.updates.map((u) => (
                <li key={u.id}>
                  <strong>{u.title}</strong>, {day(u.begin)}{u.end ? ` to ${day(u.end)}` : ", still rolling out"}.{" "}
                  {u.url ? <a href={u.url} target="_blank" rel="noreferrer" className="underline">Google&apos;s note</a> : null}
                </li>
              ))}
            </ul>
          ) : <p className="-mt-4 text-xs text-[var(--text-tertiary)]">No Google ranking update was announced in this range.</p>}

          <div className="grid gap-4 lg:grid-cols-[2fr_1fr_1fr]">
            <div className={`${card} p-5`}>
              <h3 className="text-sm font-semibold">Where the terms sit</h3>
              <p className="text-xs text-[var(--text-tertiary)]">Number of terms by position in Google, this period (solid) and before (light).</p>
              <ul className="mt-3 space-y-2">
                {BANDS.map((b) => (
                  <li key={b.key} className="flex items-center gap-3 text-sm">
                    <span className="w-24 text-[var(--text-secondary)]">{b.label}</span>
                    <span className="flex-1 space-y-1">
                      <span className="block h-3 rounded-sm" style={{ width: `${((data.distribution.now[b.key] ?? 0) / maxBand) * 100}%`, background: b.color, minWidth: (data.distribution.now[b.key] ?? 0) ? 4 : 0 }} />
                      <span className="block h-2 rounded-sm opacity-40" style={{ width: `${((data.distribution.before[b.key] ?? 0) / maxBand) * 100}%`, background: b.color, minWidth: (data.distribution.before[b.key] ?? 0) ? 4 : 0 }} />
                    </span>
                    <span className="w-16 text-right tabular-nums font-semibold">{data.distribution.now[b.key] ?? 0} <span className="font-normal text-[var(--text-tertiary)]">/ {data.distribution.before[b.key] ?? 0}</span></span>
                  </li>
                ))}
              </ul>
            </div>
            <Movers title="Winners" rows={data.winners} tone="up" />
            <Movers title="Losers" rows={data.losers} tone="down" />
          </div>

          <section className={card}>
            <div className="flex flex-wrap items-center justify-between gap-3 px-5 pt-4">
              <h2 className="text-lg font-bold">Every term, source by source</h2>
              <div className="flex flex-wrap items-center gap-2 text-sm">
                {([["all", "All"], ["page1", "Page one"], ["disagree", `Sources disagree (${disagreeing})`], ["none", "Not showing"]] as [Filter, string][]).map(([k, label]) => (
                  <button key={k} type="button" onClick={() => setFilter(k)} className={`rounded-full border px-3 py-1 text-xs font-semibold ${filter === k ? "border-[var(--brand-teal)] bg-[var(--brand-teal)] text-white" : "border-[var(--border)] bg-white"}`}>{label}</button>
                ))}
                <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Find a term" aria-label="Find a term" className="rounded-lg border border-[var(--border)] bg-white px-3 py-1 text-sm" />
              </div>
            </div>
            <p className="px-5 text-xs text-[var(--text-tertiary)]">
              Google and Bing positions are averages weighted by impressions, shown only with 10 or more. SE Ranking is its latest check{data.sources.ser_to ? ` (${day(data.sources.ser_to)}; ${data.sources.ser_tracked} terms tracked)` : " (nothing in this range)"}. A flag means two sources are 5 or more positions apart: the term is worth a look, not a mistake in either.
            </p>
            <div className="overflow-x-auto">
              <table className="mt-2 w-full text-sm">
                <thead>
                  <tr>
                    <th className={th}>Term</th>
                    <th className={th}>Google</th>
                    <th className={th}>Impr.</th>
                    <th className={th}>Clicks</th>
                    <th className={th}>Bing</th>
                    <th className={th}>SE Ranking</th>
                    <th className={th}>Move</th>
                    <th className={th}>Trend</th>
                  </tr>
                </thead>
                <tbody>
                  {shown.map((t) => (
                    <Fragment key={t.key}>
                      <tr className={`cursor-pointer border-t border-[var(--border)] hover:bg-[var(--bg)] ${open === t.key ? "bg-[var(--bg)]" : ""}`} onClick={() => setOpen(open === t.key ? null : t.key)}>
                        <td className="px-3 py-2">
                          <div className="font-medium">{t.term}</div>
                          <div className="text-xs text-[var(--text-tertiary)]">{t.bucket}{t.volume ? ` · ${num(t.volume)} searches/mo` : ""}</div>
                          {t.disagree ? <div className="text-xs font-semibold text-amber-800">⚠ {t.disagree}</div> : null}
                        </td>
                        <td className={`${td} font-semibold`}>{pos(t.google.position)}</td>
                        <td className={td}>{num(t.google.impressions)}</td>
                        <td className={td}>{num(t.google.clicks)}</td>
                        <td className={td}>{pos(t.bing.position)}</td>
                        <td className={td}>{t.ser.tracked ? pos(t.ser.position) : <span className="text-xs text-[var(--text-tertiary)]">not tracked</span>}</td>
                        <td className={td}><Move t={t} /></td>
                        <td className={td}><Spark values={t.trend} /></td>
                      </tr>
                      {open === t.key ? (
                        <tr className="border-t border-[var(--border)] bg-[var(--bg)]"><td colSpan={8}><Detail clientId={client.id} term={t.term} from={from} to={to} /></td></tr>
                      ) : null}
                    </Fragment>
                  ))}
                  {shown.length === 0 ? <tr><td colSpan={8} className="px-5 py-4 text-[var(--text-secondary)]">No term matches.</td></tr> : null}
                </tbody>
              </table>
            </div>
          </section>
        </>
      ) : null}
    </section>
  );
}
