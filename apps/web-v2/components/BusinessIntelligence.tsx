"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";

import { addChangeAction, removeChangeAction } from "@/app/(app)/[clientSlug]/bi/actions";
import { Spinner } from "@/components/ui/Spinner";
import { CoverageDonut, TrendChart } from "@/components/bi/Charts";
import type { Client } from "@/lib/api";
import { presets, type Bi, type BiChange, type BiKeyword } from "@/lib/bi";

const num = (n: number | null | undefined) => (n == null ? "–" : n.toLocaleString());
const pct = (n: number | null | undefined) => (n == null ? "–" : `${n.toFixed(1)}%`);
const shortPage = (url: string) => url.replace(/^https?:\/\/[^/]+/, "") || "/";
const day = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
const TYPE_LABEL: Record<string, string> = {
  growth_action: "Growth action",
  content_published: "Content published",
  content_updated: "Content updated",
  technical_change: "Technical change",
  website_change: "Website change",
  conversion_change: "Conversion change",
  campaign_change: "Campaign change",
  algorithm_event: "Algorithm update",
  manual_note: "Note",
};

/** Time on site, as a person says it. */
function duration(seconds: number | null | undefined) {
  if (seconds == null) return "–";
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return m > 0 ? `${m}m ${String(s).padStart(2, "0")}s` : `${s}s`;
}

function Delta({ now, before }: { now: number; before: number }) {
  if (!before) return <span className="text-xs text-[var(--text-tertiary)]">no earlier figure</span>;
  const change = ((now - before) / before) * 100;
  const flat = Math.abs(change) < 1;
  return (
    <span className={`text-xs font-semibold ${flat ? "text-[var(--text-secondary)]" : change > 0 ? "text-green-700" : "text-red-700"}`}>
      {flat ? "flat" : `${change > 0 ? "▲" : "▼"} ${Math.abs(change).toFixed(0)}%`}
    </span>
  );
}

/** Percentage-point change, for rates. */
function Points({ now, before }: { now: number | null; before: number | null }) {
  if (now == null || before == null) return <span className="text-xs text-[var(--text-tertiary)]">no earlier figure</span>;
  const d = now - before;
  const flat = Math.abs(d) < 0.05;
  return (
    <span className={`text-xs font-semibold ${flat ? "text-[var(--text-secondary)]" : d > 0 ? "text-green-700" : "text-red-700"}`}>
      {flat ? "flat" : `${d > 0 ? "+" : "−"}${Math.abs(d).toFixed(1)} pp`} <span className="font-normal text-[var(--text-secondary)]">vs before</span>
    </span>
  );
}

function Kpi({ label, value, change, note }: { label: string; value: string; change?: React.ReactNode; note?: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4">
      <div className="text-xs font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">{label}</div>
      <div className="mt-1 text-3xl font-bold tabular-nums">{value}</div>
      {change ? <div className="mt-1">{change}</div> : null}
      {note ? <div className="mt-1 text-xs text-[var(--text-secondary)]">{note}</div> : null}
    </div>
  );
}

function Section({ n, title, sub, children }: { n: string; title: string; sub: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-lg font-bold"><span className="mr-2 text-xs font-semibold text-[var(--text-tertiary)]">{n}</span>{title}</h2>
        <p className="text-sm text-[var(--text-secondary)]">{sub}</p>
      </div>
      {children}
    </section>
  );
}

const card = "rounded-xl border border-[var(--border)] bg-[var(--surface)]";

/** The tables on screen as a CSV, to open in a spreadsheet. */
function toCsv(data: Bi, noEvents: boolean) {
  const q = (v: string | number | null) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const rows: (string | number | null)[][] = [
    ["Channels", data.from, data.to],
    ["Channel", "Visits", "Visits before", "Engaged %", "Avg seconds", "Key actions", "Conversion %"],
    ...data.channels.map((c) => [c.label, c.sessions, c.sessions_before, c.engagement_rate, c.avg_seconds, noEvents ? null : c.conversions, noEvents ? null : c.conversion_rate]),
    [],
    ["Landing pages"],
    ["Page", "Visits", "Engaged %", "Avg seconds", "Key actions", "Conversion %"],
    ...data.pages.map((p) => [p.url, p.sessions, p.engagement_rate, p.avg_seconds, noEvents ? null : p.conversions, noEvents ? null : p.conversion_rate]),
    [],
    ["Keywords", data.keywords.from, data.keywords.to],
    ["Keyword", "Searches per month", "Start position", "End position", "AI prompt", "Platforms citing", "Platforms naming"],
    ...data.keywords.keywords.map((k) => [k.keyword, k.volume, k.start, k.end, k.prompt, k.ai?.cited ?? null, k.ai?.mentioned ?? null]),
  ];
  return rows.map((r) => r.map(q).join(",")).join("\n");
}

const th = "px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-[var(--text-tertiary)]";
const td = "px-3 py-2 tabular-nums";

/** How the AI platforms answered the term's paired prompt: one chip per platform, and the count against the run before. */
function AiVisibility({ k }: { k: BiKeyword }) {
  if (!k.prompt) return <span className="text-xs text-[var(--text-tertiary)]">{k.in_watchlist ? "no prompt paired" : "not on the watchlist"}</span>;
  if (!k.ai) return <span className="text-xs text-[var(--text-tertiary)]">not asked in the latest run</span>;
  const { ai } = k;
  const was = ai.previous_cited == null ? null : `${ai.previous_cited} cited, ${ai.previous_mentioned} named`;
  return (
    <div className="space-y-1">
      <div className="flex flex-wrap gap-1">
        {Object.entries(ai.by_platform).map(([platform, v]) => (
          <span
            key={platform}
            title={`${platform}: ${v.cited ? "cites the site" : v.named ? "names the brand" : "does not name the brand"}`}
            className={`rounded px-1.5 py-0.5 text-[0.7rem] font-semibold ${v.cited ? "bg-green-100 text-green-800" : v.named ? "bg-teal-50 text-teal-800" : "bg-[var(--bg)] text-[var(--text-tertiary)]"}`}
          >
            {platform} {v.cited ? "cited" : v.named ? "named" : "–"}
          </span>
        ))}
      </div>
      <div className="text-xs text-[var(--text-secondary)]">
        {ai.cited} cited, {ai.mentioned} named of {ai.platforms}
        {was ? <span className="text-[var(--text-tertiary)]"> · before: {was}</span> : null}
      </div>
    </div>
  );
}

function KeywordRow({ k }: { k: BiKeyword }) {
  const style = k.state === "up" || k.state === "new" ? "text-green-700" : k.state === "down" || k.state === "lost" ? "text-red-700" : "text-[var(--text-secondary)]";
  const text =
    k.state === "new" ? "now ranking" : k.state === "lost" ? "dropped out" : k.change == null ? "–" : k.state === "steady" ? "steady" : `${k.change > 0 ? "▲" : "▼"} ${Math.abs(k.change)}`;
  return (
    <tr className="border-t border-[var(--border)] align-top">
      <td className="px-3 py-2 font-medium">{k.keyword}</td>
      <td className={td}>{num(k.volume)}</td>
      <td className={td}>{k.start ?? "–"}</td>
      <td className={td}>{k.end ?? "–"}</td>
      <td className={`${td} font-semibold ${style}`}>{text}</td>
      <td className="max-w-xs px-3 py-2 text-xs text-[var(--text-secondary)]" title={k.prompt ?? undefined}>{k.prompt ?? "–"}</td>
      <td className="px-3 py-2"><AiVisibility k={k} /></td>
    </tr>
  );
}

function ChangeLog({ clientId, slug, from, to, changes }: { clientId: string; slug: string; from: string; to: string; changes: BiChange[] }) {
  const router = useRouter();
  const [date, setDate] = useState(to);
  const [text, setText] = useState("");
  const [page, setPage] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const add = () =>
    start(async () => {
      setError(null);
      const r = await addChangeAction(clientId, slug, date, text, page);
      if (r.ok) {
        setText("");
        setPage("");
        router.refresh();
      } else setError(r.error);
    });
  const remove = (id: string) =>
    start(async () => {
      const r = await removeChangeAction(clientId, slug, id);
      if (r.ok) router.refresh();
      else setError(r.error);
    });
  const input = "rounded-lg border border-[var(--border)] bg-white px-3 py-2 text-sm";
  return (
    <section className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
      <h3 className="text-sm font-semibold">Change log</h3>
      <p className="mt-1 text-xs text-[var(--text-tertiary)]">
        What changed on the site or in the work, so a movement in the numbers above can be tied to something. Shipping a task adds its entry here; add anything else by hand.
      </p>
      <div className="mt-3 flex flex-wrap items-end gap-2">
        <label className="text-xs font-semibold">
          Date
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className={`mt-1 block ${input}`} />
        </label>
        <label className="min-w-[16rem] flex-1 text-xs font-semibold">
          What changed
          <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Moved the SPF collection to a new template" className={`mt-1 block w-full ${input}`} />
        </label>
        <label className="min-w-[10rem] text-xs font-semibold">
          Page (optional)
          <input value={page} onChange={(e) => setPage(e.target.value)} placeholder="/collections/spf" className={`mt-1 block w-full ${input}`} />
        </label>
        <button type="button" onClick={add} disabled={pending || text.trim().length < 3 || !date} className="rounded-lg bg-[var(--brand-dark)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
          {pending ? <><Spinner />Saving…</> : "Add"}
        </button>
      </div>
      {error ? <p role="alert" className="mt-2 text-sm font-semibold text-red-700">{error}</p> : null}
      {changes.length === 0 ? (
        <p className="mt-4 text-sm text-[var(--text-secondary)]">Nothing logged between {day(from)} and {day(to)}.</p>
      ) : (
        <ul className="mt-4 divide-y divide-[var(--border)] text-sm">
          {changes.map((c) => (
            <li key={c.id} className="flex flex-wrap items-start gap-3 py-2">
              <span className="w-28 shrink-0 text-xs tabular-nums text-[var(--text-secondary)]">{day(c.date)}</span>
              <span className="w-36 shrink-0 text-xs font-semibold">{TYPE_LABEL[c.type] ?? c.type}</span>
              <span className="min-w-0 flex-1">
                {c.description}
                {c.page ? <span className="ml-2 text-xs text-[var(--text-tertiary)]">{shortPage(c.page)}</span> : null}
              </span>
              {!c.from_task ? (
                <button type="button" onClick={() => remove(c.id)} disabled={pending} className="text-xs font-semibold text-red-700 underline disabled:opacity-50">
                  Remove
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function BusinessIntelligence({ client, from, to, channel, data, error }: { client: Client; from: string; to: string; channel: string; data: Bi | null; error: string | null }) {
  const router = useRouter();
  const [custom, setCustom] = useState({ from, to });
  const go = (f: string, t: string, c = channel) => {
    const q = new URLSearchParams({ from: f, to: t });
    if (c) q.set("channel", c);
    router.push(`/${client.slug}/bi?${q}`);
  };
  const ranges = presets();
  const active = ranges.find((r) => r.from === from && r.to === to)?.key ?? "custom";
  const noEvents = data != null && data.key_events.length === 0;
  const download = () => {
    if (!data) return;
    const url = URL.createObjectURL(new Blob([toCsv(data, noEvents)], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `business-intelligence-${client.slug}-${from}-to-${to}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const cov = data?.keywords.coverage;
  const top10 = (b: { top3: number; top10: number }, n: number) => (n > 0 ? ((b.top3 + b.top10) / n) * 100 : null);
  const marks = data?.changes.map((c) => ({ date: c.date, text: c.description })) ?? [];
  const t = data?.totals, tb = data?.totals_before;
  const moved = data?.keywords.keywords ?? [];
  const improved = moved.filter((k) => k.state === "up" || k.state === "new").length;
  const declined = moved.filter((k) => k.state === "down" || k.state === "lost").length;

  return (
    <section className="max-w-6xl space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">OrganicIQ insights</h1>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">How visible are we, who is arriving, and do those visits stay and act? Compared with the same number of days before.</p>
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={download} disabled={!data} className="rounded-lg bg-[var(--brand-dark)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Export data</button>
        </div>
      </header>

      <div className="flex flex-wrap items-end gap-2 text-sm">
        {ranges.map((r) => (
          <button key={r.key} type="button" onClick={() => go(r.from, r.to)} className={`rounded-lg border px-3 py-1.5 font-semibold ${active === r.key ? "border-[var(--brand-teal)] bg-[var(--brand-teal)] text-white" : "border-[var(--border)] bg-white"}`}>
            {r.label}
          </button>
        ))}
        <label className="text-xs font-semibold">From<input type="date" value={custom.from} onChange={(e) => setCustom({ ...custom, from: e.target.value })} className="mt-1 block rounded-lg border border-[var(--border)] bg-white px-2 py-1.5 text-sm" /></label>
        <label className="text-xs font-semibold">To<input type="date" value={custom.to} onChange={(e) => setCustom({ ...custom, to: e.target.value })} className="mt-1 block rounded-lg border border-[var(--border)] bg-white px-2 py-1.5 text-sm" /></label>
        <button type="button" onClick={() => go(custom.from, custom.to)} disabled={!custom.from || !custom.to || custom.to < custom.from} className="rounded-lg border border-[var(--border)] bg-white px-3 py-1.5 font-semibold disabled:opacity-50">Apply</button>
        <span className="pb-2 text-xs text-[var(--text-tertiary)]">{day(from)} to {day(to)}</span>
      </div>

      {error ? <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p> : null}

      {data && t && tb ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Kpi
              label="Visibility: top 10"
              value={cov ? pct(top10(cov.end, cov.tracked)) : "–"}
              change={cov ? <Points now={top10(cov.end, cov.tracked)} before={top10(cov.start, cov.tracked)} /> : undefined}
              note={cov ? `${cov.end.top3 + cov.end.top10} of ${cov.tracked} tracked keywords` : "the rank tracker has no check in this range"}
            />
            <Kpi label="Traffic: site visits" value={num(t.sessions)} change={<Delta now={t.sessions} before={tb.sessions} />} note={`${num(tb.sessions)} before`} />
            <Kpi
              label="Engagement"
              value={pct(t.engagement_rate)}
              change={<Points now={t.engagement_rate} before={tb.engagement_rate} />}
              note={data.has_engagement_time ? `${duration(t.avg_seconds)} engaged time per visit` : "time on site: pull Google Analytics again"}
            />
            <Kpi
              label="Visits with a key action"
              value={noEvents ? "–" : pct(t.conversion_rate)}
              change={noEvents ? undefined : <Points now={t.conversion_rate} before={tb.conversion_rate} />}
              note={noEvents ? "none chosen yet" : `${num(t.conversions)} key actions (${num(tb.conversions)} before)`}
            />
          </div>

          {noEvents ? (
            <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
              No key actions are chosen for this client, so conversions show as a dash. Choose them in{" "}
              <Link href={`/${client.slug}/settings/conversions`} className="font-semibold underline">Settings → Conversions</Link>.
            </p>
          ) : (
            <p className="-mt-4 text-xs text-[var(--text-tertiary)]">Key actions counted: {data.key_events.map((e) => e.name).join(", ")}.</p>
          )}

          <Section n="01" title="Where are we showing up?" sub="Search rankings and AI answers are separate measures of visibility.">
            <div className="grid gap-4 lg:grid-cols-2">
              <div className={`${card} p-5`}>
                <h3 className="text-sm font-semibold">Search ranking coverage</h3>
                {cov ? (
                  <>
                    <div className="mt-3"><CoverageDonut bands={cov.end} tracked={cov.tracked} /></div>
                    <p className="mt-3 text-xs text-[var(--text-secondary)]">
                      <strong>{improved}</strong> improving, <strong>{declined}</strong> declining, of {cov.tracked} tracked keywords. Positions on {data.keywords.to ? day(data.keywords.to) : ""}; a keyword not found in the top 100 counts as outside.
                    </p>
                  </>
                ) : (
                  <p className="mt-3 text-sm text-[var(--text-secondary)]">The rank tracker has no check inside this range.</p>
                )}
              </div>
              <div className={`${card} p-5`}>
                <h3 className="text-sm font-semibold">AI mentions and citations</h3>
                {data.ai ? (
                  <>
                    <div className="mt-3 flex flex-wrap gap-8">
                      <div>
                        <div className="text-3xl font-bold tabular-nums">{pct(data.ai.mention_rate)}</div>
                        <div className="text-xs text-[var(--text-secondary)]">answers that name the brand</div>
                        <Points now={data.ai.mention_rate} before={data.ai.mention_rate_before} />
                      </div>
                      <div>
                        <div className="text-3xl font-bold tabular-nums">{pct(data.ai.cited_rate)}</div>
                        <div className="text-xs text-[var(--text-secondary)]">answers that cite the site</div>
                        <Points now={data.ai.cited_rate} before={data.ai.cited_rate_before} />
                      </div>
                    </div>
                    <table className="mt-4 w-full text-sm">
                      <thead><tr><th className={th}>Platform</th><th className={th}>Named</th><th className={th}>Cited</th><th className={th}>Checks</th></tr></thead>
                      <tbody>
                        {data.ai.platforms.map((p) => (
                          <tr key={p.platform} className="border-t border-[var(--border)]">
                            <td className="px-3 py-2 font-medium">{p.platform}</td>
                            <td className={td}>{p.mentioned}</td>
                            <td className={td}>{p.cited}</td>
                            <td className={td}>{p.checks}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <p className="mt-2 text-xs text-[var(--text-tertiary)]">From the run on {day(data.ai.date)}{data.ai.date_before ? `, against the run on ${day(data.ai.date_before)}` : ""}. Questions that name the brand are left out.</p>
                  </>
                ) : (
                  <p className="mt-3 text-sm text-[var(--text-secondary)]">No LLM visibility run has finished by {day(to)}.</p>
                )}
              </div>
            </div>

            {data.keywords.keywords.length > 0 ? (
              <div className={card}>
                <h3 className="px-5 pt-4 text-sm font-semibold">Keyword movement and AI visibility</h3>
                <p className="px-5 text-xs text-[var(--text-tertiary)]">Positions on {data.keywords.from ? day(data.keywords.from) : ""} and {data.keywords.to ? day(data.keywords.to) : ""}, the first and last days the rank tracker checked in this range. A dash means not ranking. The AI columns show how the platforms answered the prompt paired with the term, in the latest run up to the end of the range.</p>
                <div className="overflow-x-auto">
                  <table className="mt-2 w-full text-sm">
                    <thead><tr><th className={th}>Keyword</th><th className={th}>Searches / month</th><th className={th}>Start</th><th className={th}>End</th><th className={th}>Movement</th><th className={th}>AI prompt</th><th className={th}>AI visibility</th></tr></thead>
                    <tbody>{data.keywords.keywords.map((k) => <KeywordRow key={k.keyword} k={k} />)}</tbody>
                  </table>
                </div>
              </div>
            ) : null}
          </Section>

          <Section n="02" title="Where are people coming from?" sub="The trend first, then the channels behind it.">
            <div className="grid gap-4 lg:grid-cols-[3fr_2fr]">
              <div className={`${card} p-5`}>
                <h3 className="text-sm font-semibold">Visits over the period</h3>
                <div className="text-3xl font-bold tabular-nums">{num(t.sessions)} <span className="text-sm font-normal text-[var(--text-secondary)]">visits in daily detail</span></div>
                <div className="mt-2"><TrendChart label="Visits per day, this period against the one before" data={data.daily.map((d) => ({ date: d.date, now: d.sessions, before: d.sessions_before }))} marks={marks} /></div>
              </div>
              <div className={card}>
                <h3 className="px-5 pt-4 text-sm font-semibold">Traffic by channel</h3>
                <p className="px-5 text-xs text-[var(--text-tertiary)]">Choose one to filter the pages below.</p>
                <table className="mt-2 w-full text-sm">
                  <thead><tr><th className={th}>Channel</th><th className={th}>Visits</th><th className={th}>Before</th><th className={th}>Change</th></tr></thead>
                  <tbody>
                    {data.channels.map((c) => (
                      <tr key={c.channel} className={`border-t border-[var(--border)] ${channel === c.channel ? "bg-[var(--bg)]" : ""}`}>
                        <td className="px-3 py-2">
                          <button type="button" onClick={() => go(from, to, channel === c.channel ? "" : c.channel)} className="text-left font-semibold underline-offset-2 hover:underline">{c.label}</button>
                        </td>
                        <td className={td}>{num(c.sessions)}</td>
                        <td className={`${td} text-[var(--text-secondary)]`}>{num(c.sessions_before)}</td>
                        <td className={td}><Delta now={c.sessions} before={c.sessions_before} /></td>
                      </tr>
                    ))}
                    {data.channels.length === 0 ? <tr><td colSpan={4} className="px-5 py-4 text-[var(--text-secondary)]">No Google Analytics data in this range.</td></tr> : null}
                  </tbody>
                </table>
              </div>
            </div>
          </Section>

          <Section n="03" title="Does the traffic engage?" sub="Engagement gives context; visits that take a key action show the business outcome.">
            <div className="grid gap-4 lg:grid-cols-[3fr_2fr]">
              <div className={`${card} p-5`}>
                <h3 className="text-sm font-semibold">Key actions over the period</h3>
                {noEvents ? (
                  <p className="mt-3 text-sm text-[var(--text-secondary)]">Choose key actions in Settings → Conversions to see them here.</p>
                ) : (
                  <>
                    <div className="text-3xl font-bold tabular-nums">{num(t.conversions)} <span className="text-sm font-normal text-[var(--text-secondary)]">key actions in daily detail</span></div>
                    <div className="mt-2"><TrendChart label="Key actions per day, this period against the one before" data={data.daily.map((d) => ({ date: d.date, now: d.conversions, before: d.conversions_before }))} marks={marks} /></div>
                  </>
                )}
              </div>
              <div className={`${card} p-5`}>
                <h3 className="text-sm font-semibold">From visits to key actions</h3>
                <ol className="mt-3 space-y-2 text-sm">
                  <li className="rounded-lg bg-[var(--bg)] p-3"><div className="flex justify-between"><span>Site visits</span><span className="font-bold tabular-nums">{num(t.sessions)}</span></div><div className="text-xs text-[var(--text-secondary)]">{num(tb.sessions)} before</div></li>
                  <li className="rounded-lg bg-[var(--bg)] p-3"><div className="flex justify-between"><span>Engaged visits</span><span className="font-bold tabular-nums">{num(t.engaged)}</span></div><div className="text-xs text-[var(--text-secondary)]">{pct(t.engagement_rate)} of visits stayed 10 seconds, viewed 2 pages, or took a key action</div></li>
                  <li className="rounded-lg bg-[var(--bg)] p-3"><div className="flex justify-between"><span>Key actions</span><span className="font-bold tabular-nums">{noEvents ? "–" : num(t.conversions)}</span></div><div className="text-xs text-[var(--text-secondary)]">{noEvents ? "none chosen yet" : `${pct(t.conversion_rate)} of visits`}</div></li>
                </ol>
                <p className="mt-3 text-xs text-[var(--text-tertiary)]">{data.has_engagement_time ? `On average a visit holds attention for ${duration(t.avg_seconds)}.` : "Engaged time per visit appears once Google Analytics has been pulled again."}</p>
              </div>
            </div>

            <div className={card}>
              <h3 className="px-5 pt-4 text-sm font-semibold">Engagement by channel</h3>
              <div className="overflow-x-auto">
                <table className="mt-2 w-full text-sm">
                  <thead><tr><th className={th}>Channel</th><th className={th}>Visits</th><th className={th}>Engaged</th><th className={th}>Time per visit</th><th className={th}>Key actions</th><th className={th}>Rate</th></tr></thead>
                  <tbody>
                    {data.channels.map((c) => (
                      <tr key={c.channel} className="border-t border-[var(--border)]">
                        <td className="px-3 py-2 font-medium">{c.label}</td>
                        <td className={td}>{num(c.sessions)}</td>
                        <td className={td}>{pct(c.engagement_rate)}</td>
                        <td className={td}>{duration(c.avg_seconds)}</td>
                        <td className={td}>{noEvents ? "–" : num(c.conversions)}</td>
                        <td className={td}>{noEvents ? "–" : pct(c.conversion_rate)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className={card}>
              <div className="flex flex-wrap items-center justify-between gap-2 px-5 pt-4">
                <h3 className="text-sm font-semibold">Pages contributing visits and key actions{channel ? `: ${data.channels.find((c) => c.channel === channel)?.label ?? channel}` : ""}</h3>
                <select value={channel} onChange={(e) => go(from, to, e.target.value)} aria-label="Channel" className="rounded-lg border border-[var(--border)] bg-white px-2 py-1 text-sm">
                  <option value="">All channels</option>
                  {data.channels.map((c) => <option key={c.channel} value={c.channel}>{c.label}</option>)}
                </select>
              </div>
              <p className="px-5 text-xs text-[var(--text-tertiary)]">The 25 busiest pages people arrive on. Time is engaged time per visit; pages with the least time are where visits leave soonest.</p>
              <div className="overflow-x-auto">
                <table className="mt-2 w-full text-sm">
                  <thead><tr><th className={th}>Page</th><th className={th}>Visits</th><th className={th}>Engaged</th><th className={th}>Time per visit</th><th className={th}>Key actions</th><th className={th}>Per 100 visits</th></tr></thead>
                  <tbody>
                    {data.pages.map((p) => (
                      <tr key={p.url} className="border-t border-[var(--border)]">
                        <td className="max-w-md break-all px-3 py-2 font-medium" title={p.url}>{shortPage(p.url)}</td>
                        <td className={td}>{num(p.sessions)}</td>
                        <td className={td}>{pct(p.engagement_rate)}</td>
                        <td className={td}>{duration(p.avg_seconds)}</td>
                        <td className={td}>{noEvents ? "–" : num(p.conversions)}</td>
                        <td className={td}>{noEvents || p.conversion_rate == null ? "–" : p.conversion_rate.toFixed(1)}</td>
                      </tr>
                    ))}
                    {data.pages.length === 0 ? <tr><td colSpan={6} className="px-5 py-4 text-[var(--text-secondary)]">No pages for this range.</td></tr> : null}
                  </tbody>
                </table>
              </div>
            </div>
          </Section>

          <Section n="04" title="What changed?" sub="Work shipped and changes made to the site, so a movement above can be tied to something. Marked on the charts.">
            <ChangeLog clientId={client.id} slug={client.slug} from={from} to={to} changes={data.changes} />
          </Section>
        </>
      ) : null}
    </section>
  );
}
