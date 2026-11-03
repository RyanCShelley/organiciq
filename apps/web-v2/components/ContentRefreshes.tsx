"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";

import { draftAction, refreshPageAction, setAsideAction } from "@/app/(app)/[clientSlug]/content-gaps/actions";
import { WeeklyLine } from "@/components/bi/Charts";
import { AddToCalendar, StatusChip } from "@/components/content/AddToCalendar";
import { AskModel, DEPTH, Kpi, List, SidePane, card, day, num, shortPage, td, th } from "@/components/content/parts";
import { Spinner } from "@/components/ui/Spinner";
import type { Client } from "@/lib/api";
import type { CalendarStatus, ClickWindow, Competing, ContentDepthChoice, RefreshDetail, RefreshPage, Refreshes } from "@/lib/content";
import { monthLabel } from "@/lib/focus";

const TONE: Record<string, string> = { losing: "bg-red-100 text-red-800", quiet: "bg-red-100 text-red-800", slipping: "bg-amber-100 text-amber-900", growing: "bg-green-100 text-green-800", steady: "bg-gray-100 text-gray-700", new: "bg-blue-100 text-blue-800" };

function Clicks({ w }: { w: ClickWindow }) {
  return w ? <span className="tabular-nums">{num(w.clicks)} clicks of {num(w.impressions)}</span> : <span className="text-[var(--text-tertiary)]">too little data</span>;
}

function CompetingList({ rows, here }: { rows: Competing[]; here?: string }) {
  return (
    <ul className="space-y-2 text-xs">
      {rows.map((c) => (
        <li key={c.query} className="rounded-lg border border-[var(--border)] p-2">
          <div className="font-semibold">{c.query} <span className="font-normal text-[var(--text-tertiary)]">· {num(c.impressions)} impressions</span></div>
          {c.pages.map((p) => (
            <div key={p.url} className={p.url === here ? "font-semibold" : "text-[var(--text-secondary)]"}>{shortPage(p.url)} · position {p.position} · {num(p.impressions)} impr. · {num(p.clicks)} clicks</div>
          ))}
        </li>
      ))}
    </ul>
  );
}

function PagePane({ client, page, month, ready, canEdit, onCalendar, onRefresh, onChanged }: { client: Client; page: RefreshPage; month: string; ready: boolean; canEdit: boolean; onCalendar?: CalendarStatus; onRefresh: () => void; onChanged: () => void }) {
  const [d, setD] = useState<RefreshDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [depth, setDepth] = useState<ContentDepthChoice>("quick");
  const [pending, start] = useTransition();
  const load = () => refreshPageAction(client.id, page.url, month).then((r) => (r.ok ? setD(r.value) : setError(r.error)));
  useEffect(() => {
    setD(null);
    setError(null);
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client.id, page.url, month]);
  const plan = d?.plan;
  const running = plan?.status === "running";
  useEffect(() => {
    if (!running) return;
    const t = setInterval(load, 2500);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running]);
  const write = () =>
    start(async () => {
      setError(null);
      const r = await draftAction(client.id, "refresh", page.url, depth, month);
      if (!r.ok) setError(r.error);
      else await load();
    });
  const setAside = () =>
    start(async () => {
      const r = await setAsideAction(client.id, "refresh", page.url, page.ignored);
      if (!r.ok) setError(r.error);
      else onChanged();
    });
  const s = d?.depth?.signals;

  return (
    <div className="space-y-4 text-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="break-all font-semibold">{page.url}</p>
          <p className="text-xs text-[var(--text-secondary)]"><span className={`mr-2 rounded px-1.5 py-0.5 font-semibold ${TONE[page.label]}`}>{page.status}</span>{page.title ?? "no title found"}</p>
        </div>
        <button type="button" onClick={setAside} disabled={pending} className="rounded-lg border border-[var(--border)] bg-white px-3 py-1 text-xs font-semibold disabled:opacity-50">{page.ignored ? "Restore" : "Ignore"}</button>
      </div>
      {error ? <p role="alert" className="font-semibold text-red-700">{error}</p> : null}
      {page.reasons.length ? <ul className="list-disc space-y-0.5 rounded-lg bg-[var(--bg)] p-3 pl-7 text-xs">{page.reasons.map((r) => <li key={r}>{r}</li>)}</ul> : null}
      <AddToCalendar client={client} canEdit={canEdit} status={onCalendar} kind="refresh" title={`Refresh ${page.title ?? shortPage(page.url)}`} target={page.url} sourceArea="refresh" sourceKey={page.url} onAdded={onRefresh} />
      {page.watch.length ? (
        <div className="rounded-lg border border-[var(--border)] p-3">
          <h3 className="font-bold">Watchlist terms on this page</h3>
          <ul className="mt-1 space-y-0.5 text-xs">{page.watch.map((w) => <li key={w.term}><span className="font-semibold">{w.term}</span> · position {w.position}{w.change ? ` (${w.change > 0 ? "+" : ""}${w.change})` : ""}{w.volume != null ? ` · ${num(w.volume)} searches a month` : ""} · <span className={w.slipping ? "font-semibold text-red-700" : "text-[var(--text-secondary)]"}>{w.slipping ? "slipping" : "within reach of page one"}</span></li>)}</ul>
        </div>
      ) : null}
      {!d && !error ? <p className="text-[var(--text-secondary)]"><Spinner />Reading the page…</p> : null}
      {d ? (
        <>
          <div>
            <h3 className="font-bold">Organic sessions by month</h3>
            <WeeklyLine label="Organic sessions by month" periodLabel="Month of" spanDays={28} points={d.sessions.map((m) => ({ week: `${m.month}-01`, value: m.sessions }))} />
          </div>

          <div>
            <h3 className="font-bold">Searches that lost clicks</h3>
            <p className="text-xs text-[var(--text-tertiary)]">The last three months against the three before.</p>
            {d.lost.length === 0 ? <p className="mt-1 text-xs text-[var(--text-secondary)]">No search lost enough clicks to list.</p> : (
              <div className="mt-1 overflow-x-auto">
                <table className="w-full text-xs">
                  <thead><tr><th className={th}>Search</th><th className={th}>Clicks</th><th className={th}>Impressions</th><th className={th}>Position</th><th className={th}>Lost</th></tr></thead>
                  <tbody>
                    {d.lost.map((l) => (
                      <tr key={l.query} className="border-t border-[var(--border)]">
                        <td className="px-3 py-2 font-medium">{l.query}</td>
                        <td className={td}>{num(l.clicks.previous)} → {num(l.clicks.current)}</td>
                        <td className={td}>{num(l.impressions.previous)} → {num(l.impressions.current)}</td>
                        <td className={td}>{l.position.previous} → {l.position.current ?? "not shown"}</td>
                        <td className={`${td} font-semibold text-red-700`}>{l.clicks_lost > 0 ? `−${num(l.clicks_lost)} clicks` : `−${num(l.impressions.previous - l.impressions.current)} impr.`}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {d.competing.length ? (
            <div>
              <h3 className="font-bold">Pages shown for the same searches</h3>
              <p className="text-xs text-[var(--text-tertiary)]">When two pages answer one search, Google picks between them. Update the stronger page, or merge the two.</p>
              <div className="mt-1"><CompetingList rows={d.competing} here={d.url} /></div>
            </div>
          ) : null}

          <div>
            <h3 className="font-bold">How much it says</h3>
            {d.depth && s ? (
              <div className="mt-1 text-xs">
                <p><span className="text-2xl font-bold tabular-nums">{d.depth.score}</span> of 100 · {d.depth.score < 30 ? "thin or generic" : d.depth.score < 60 ? "some substance" : "rich"}</p>
                <p className="mt-1 text-[var(--text-secondary)]">
                  {s.word_count ?? 0} words · {s.stats_hits ?? 0} figures, percentages or years · {s.dates_present ?? 0} dated claims · {s.list_items ?? 0} list items · {s.table_present ? "a table" : "no table"} · {s.quotes ?? 0} quotes{s.citation_marker ? " · cites sources" : ""}
                </p>
              </div>
            ) : <p className="text-xs text-[var(--text-secondary)]">{d.read.note ?? "The page could not be read."}</p>}
          </div>

          <div>
            <h3 className="font-bold">Changes to this page</h3>
            {d.changes.length === 0 ? (
              <p className="text-xs text-[var(--text-secondary)]">No shipped task or change-log note is recorded for this page. When you update it, add a note in OrganicIQ insights&apos;s change log, and the before and after clicks appear here.</p>
            ) : (
              <ul className="mt-2 space-y-2 text-xs">
                {d.changes.map((c, i) => (
                  <li key={i} className="rounded-lg border border-[var(--border)] p-2">
                    <div><span className="font-semibold">{day(c.date)}</span> · {c.kind}: {c.text}</div>
                    <div className="mt-1 text-[var(--text-secondary)]">28 days before: <Clicks w={c.before} /></div>
                    <div className="text-[var(--text-secondary)]">28 days after: {c.measured_on ? <span className="text-[var(--text-tertiary)]">measured on {day(c.measured_on)}</span> : <Clicks w={c.after} />}</div>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="space-y-2 rounded-lg border border-[var(--border)] p-3">
            <h3 className="font-bold">Refresh plan</h3>
            <p className="text-xs text-[var(--text-tertiary)]">The model reads the page, the searches it lost and the pages it competes with, and says what to keep, add, change and cut. A draft: nothing is sent anywhere and it uses no page allowance.</p>
            <AskModel ready={ready} depth={depth} onDepth={setDepth} busy={pending || running} again={plan?.status === "done"} label="Write a refresh plan" onRun={write} />
            {plan?.status === "failed" ? <p role="alert" className="text-xs font-semibold text-red-700">{plan.error}</p> : null}
            {plan?.status === "done" ? (
              <div className="space-y-3 pt-1">
                {plan.diagnosis ? <p><strong>Why it lost ground:</strong> {plan.diagnosis}</p> : null}
                <List title="Keep" items={plan.keep} />
                {plan.add?.length ? <List title="Add" items={plan.add.map((a) => `${a.section} — wins back: ${a.why}`)} /> : null}
                {plan.change?.length ? <List title="Change" items={plan.change.map((a) => `${a.what} — ${a.why}`)} /> : null}
                <List title="Cut" items={plan.remove} />
                {plan.merge_with ? <p className="rounded-lg bg-amber-50 p-2 text-xs text-amber-900">The model suggests merging this page into {plan.merge_with}.</p> : null}
                <p className="text-xs text-[var(--text-tertiary)]">{plan.target_words ? `About ${num(plan.target_words)} words. ` : ""}{DEPTH[plan.depth]} · ${plan.cost_usd.toFixed(2)}{plan.page_read === false ? " · the page could not be read, so this comes from the data only" : ""}</p>
              </div>
            ) : null}
          </div>
        </>
      ) : null}
    </div>
  );
}

export function ContentRefreshes({ client, month, months, q, ignored, data, error }: { client: Client; month: string; months: string[]; q: string; ignored: boolean; data: Refreshes | null; error: string | null }) {
  const router = useRouter();
  const [search, setSearch] = useState(q);
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);
  const go = (m = month, query = q, showIgnored = ignored) => {
    const params = new URLSearchParams({ month: m });
    if (query) params.set("q", query);
    if (showIgnored) params.set("ignored", "1");
    router.push(`/${client.slug}/content-refreshes?${params}`);
  };
  const page = data?.pages.find((p) => p.url === open) ?? null;
  const c = data?.counts;

  return (
    <section className="max-w-6xl space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Content refreshes</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">Pages worth updating, ranked by the organic sessions at stake. A page is judged against the whole site&apos;s own change, so a dip everyone had does not count.</p>
      </header>

      <div className="flex flex-wrap items-end gap-3 text-sm">
        <label className="text-xs font-semibold">
          Month
          <select value={month} onChange={(e) => go(e.target.value)} className="mt-1 block rounded-lg border border-[var(--border)] bg-white px-2 py-2 text-sm font-normal">
            {months.map((m) => <option key={m} value={m}>{monthLabel(m)}</option>)}
          </select>
        </label>
        <span className="pb-2 text-xs text-[var(--text-tertiary)]">The last three months, against the same three a year earlier.</span>
      </div>

      {error ? <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p> : null}

      {data && c ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <Kpi label="Pages to refresh" value={num(c.pages)} note={c.pages === 0 ? "Clean" : `${num(c.losing)} losing traffic, ${num(c.quiet)} gone quiet, ${num(c.slipping)} slipping`} />
            <Kpi label="Sessions at stake" value={num(c.at_stake)} note="a month, against what the site's own trend says these pages should have" />
            <Kpi label="Stale" value={num(c.stale)} note="not updated in 18 months, and still earning" />
            <Kpi label="Thin" value={num(c.thin)} note="under 300 words, and still earning" />
            <Kpi label="Watchlist slipping" value={num(c.watch)} note="pages where a tracked term fell three or more places" />
          </div>
          {data.has_last_year ? (
            <p className="-mt-3 text-xs text-[var(--text-secondary)]">The whole site: {num(data.site.three_months.current)} organic sessions in these three months{data.site.three_months.change_pct != null ? `, ${data.site.three_months.change_pct > 0 ? "+" : ""}${data.site.three_months.change_pct}% on last year` : ""}.</p>
          ) : null}

          <form className="flex flex-wrap items-center gap-2 text-sm" onSubmit={(e) => { e.preventDefault(); go(month, search.trim()); }} role="search">
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Find a page: part of its address or its title" aria-label="Find a page" className="min-w-[20rem] flex-1 rounded-lg border border-[var(--border)] bg-white px-3 py-2" />
            <button type="submit" className="rounded-lg border border-[var(--border)] bg-white px-4 py-2 font-semibold">Find</button>
            {q ? <button type="button" onClick={() => { setSearch(""); go(month, ""); }} className="text-xs font-semibold underline">Clear</button> : null}
            <button type="button" onClick={() => go(month, q, !ignored)} className="ml-auto text-xs font-semibold underline">{ignored ? "Back to the pages" : `Show ignored (${data.ignored_total})`}</button>
          </form>

          <section className={card}>
            <h2 className="px-5 pt-4 text-lg font-bold">{ignored ? "Ignored pages" : q ? `Pages matching “${q}”` : "Pages to refresh, most at stake first"}</h2>
            <p className="px-5 text-xs text-[var(--text-tertiary)]">Open a page to see the searches it lost, the pages it competes with, how much it says, and to have the model plan the refresh.</p>
            <div className="overflow-x-auto">
              <table className="mt-2 w-full text-sm">
                <thead><tr><th className={th}>Page</th><th className={th}>Status</th><th className={th}>Sessions, 3 months</th><th className={th}>Last year</th><th className={th}>At stake</th><th className={th}>Why</th><th className={th}>Calendar</th></tr></thead>
                <tbody>
                  {data.pages.map((p) => (
                    <tr key={p.url} className="cursor-pointer border-t border-[var(--border)] align-top hover:bg-[var(--bg)]" onClick={() => setOpen(p.url)}>
                      <td className="max-w-sm px-3 py-2"><div className="break-all font-semibold">{shortPage(p.url)}</div><div className="truncate text-xs text-[var(--text-tertiary)]" title={p.title ?? undefined}>{p.title ?? "no title found"}</div></td>
                      <td className="px-3 py-2"><span className={`rounded px-1.5 py-0.5 text-xs font-semibold ${TONE[p.label]}`}>{p.status}</span></td>
                      <td className={td}>{num(p.three_months.current)}</td>
                      <td className={td}>{num(p.three_months.last_year)}{p.three_months.change_pct != null ? <span className={`ml-1 text-xs ${p.three_months.change_pct < 0 ? "text-red-700" : "text-green-700"}`}>{p.three_months.change_pct > 0 ? "+" : ""}{p.three_months.change_pct}%</span> : null}</td>
                      <td className={`${td} font-semibold ${p.at_stake ? "text-red-700" : ""}`}>{p.at_stake ? `−${num(p.at_stake)}` : "–"}</td>
                      <td className="max-w-xs px-3 py-2 text-xs text-[var(--text-secondary)]">{p.reasons.slice(0, 2).join(" ")}</td>
                      <td className="px-3 py-2"><StatusChip status={data.calendar[p.url]} /></td>
                    </tr>
                  ))}
                  {data.pages.length === 0 ? <tr><td colSpan={7} className={`px-5 py-4 font-semibold ${q || ignored ? "text-[var(--text-secondary)]" : "text-green-700"}`}>{ignored ? "Nothing is ignored." : q ? `No page with traffic matches “${q}”.` : "Clean: no page needs a refresh this month."}</td></tr> : null}
                </tbody>
              </table>
            </div>
            {data.pages_total > data.pages.length ? <p className="px-5 pb-3 text-xs text-[var(--text-tertiary)]">The first {data.pages.length} of {data.pages_total}. Find a page to see the rest.</p> : null}
          </section>

          {!ignored && !q ? (
            <section className={`${card} p-5`}>
              <h2 className="text-lg font-bold">Pages competing for the same search</h2>
              <p className="text-xs text-[var(--text-tertiary)]">Searches two or more pages are shown for in the top 30 over 90 days. One may be taking the other&apos;s place, or they may be one page. Brand searches are left out.</p>
              <div className="mt-3">{data.competing.length ? <CompetingList rows={data.competing.slice(0, 12)} /> : <p className="text-sm font-semibold text-green-700">Clean: no search is split between pages.</p>}</div>
            </section>
          ) : null}
          <ul className="list-disc space-y-1 pl-5 text-xs text-[var(--text-tertiary)]">{data.notes.map((n) => <li key={n}>{n}</li>)}</ul>
        </>
      ) : null}

      <SidePane open={!!page} label="Page" onClose={() => setOpen(null)}>
        {page ? <PagePane client={client} page={page} month={month} ready={data?.model_ready ?? false} canEdit={data?.can_edit ?? false} onCalendar={data?.calendar[page.url]} onRefresh={() => router.refresh()} onChanged={() => { setOpen(null); router.refresh(); }} /> : null}
      </SidePane>
    </section>
  );
}
