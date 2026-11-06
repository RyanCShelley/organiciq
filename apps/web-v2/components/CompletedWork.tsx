"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { addNoteAction, editEntryAction, removeEntryAction } from "@/app/(app)/[clientSlug]/annotations/actions";
import { Kpi, card, num, shortPage } from "@/components/content/parts";
import type { Client } from "@/lib/api";
import type { Changes, Completed, Entry } from "@/lib/annotations";

const RESULT: Record<Entry["result"], { label: string; cls: string }> = {
  improved: { label: "Improved", cls: "text-green-800" },
  no_meaningful_change: { label: "No clear change", cls: "text-[var(--text-secondary)]" },
  declined: { label: "Declined", cls: "text-red-800" },
  not_enough_data: { label: "Not enough data", cls: "text-amber-800" },
  not_yet_measured: { label: "Measuring", cls: "text-[var(--text-secondary)]" },
};
const day = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
const pct = (v: number | null | undefined) => (v == null ? null : `${v > 0 ? "+" : ""}${Math.round(v)}%`);

function Numbers({ e }: { e: Entry }) {
  const rows: [string, keyof Changes, "sessions" | "leads" | "clicks" | "impressions"][] = [["Visits", "sessions_change_pct", "sessions"], ["Leads", "leads_change_pct", "leads"], ["Clicks", "clicks_change_pct", "clicks"], ["Impressions", "impressions_change_pct", "impressions"]];
  const shown = rows.filter(([, k]) => e.changes[k] != null);
  if (!shown.length) return <span className="text-xs text-[var(--text-tertiary)]">{e.waiting ?? (e.measure_to ? `Measured over ${day(e.measure_from!)} to ${day(e.measure_to)}` : "Not measured")}</span>;
  return (
    <ul className="text-xs">
      {shown.map(([label, k, m]) => (
        <li key={label} className="tabular-nums">{label}: {num(e.baseline[m])} → {num(e.after[m])} <span className="font-semibold">({pct(e.changes[k])})</span></li>
      ))}
    </ul>
  );
}

function Row({ client, e }: { client: Client; e: Entry }) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [notes, setNotes] = useState(e.notes ?? "");
  const [error, setError] = useState<string | null>(null);
  const save = (patch: { notes?: string; result?: Entry["result"] }) =>
    start(async () => { const r = await editEntryAction(client.id, e.id, patch); if (r.ok) { setError(null); router.refresh(); } else setError(r.error); });
  const remove = () => start(async () => { const r = await removeEntryAction(client.id, e.id); if (r.ok) router.refresh(); else setError(r.error); });
  return (
    <li className="space-y-2 py-4 text-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div className="min-w-0 flex-1">
          <span className="mr-2 rounded-full bg-[var(--bg)] px-2 py-0.5 text-xs font-semibold">{e.type_label}</span>
          <span className="font-semibold">{e.description}</span>
        </div>
        <span className="text-xs text-[var(--text-tertiary)]">{day(e.date)}</span>
      </div>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1 text-xs text-[var(--text-secondary)]">
          {e.page ? <div className="break-all">{shortPage(e.page)}</div> : null}
          <div>{e.how}{e.from_plan ? <> · <Link href={`/${client.slug}/engine`} className="text-[var(--brand-teal)] hover:underline">See the plan</Link></> : null}</div>
        </div>
        <Numbers e={e} />
        <label className="text-xs font-semibold">
          Result
          <select value={e.result} disabled={pending} onChange={(ev) => save({ result: ev.target.value as Entry["result"] })} className={`ml-2 rounded-lg border border-[var(--border)] bg-white px-2 py-1 font-semibold ${RESULT[e.result].cls}`}>
            {(Object.keys(RESULT) as Entry["result"][]).map((k) => <option key={k} value={k}>{RESULT[k].label}</option>)}
          </select>
        </label>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <input value={notes} onChange={(ev) => setNotes(ev.target.value)} onBlur={() => notes !== (e.notes ?? "") && save({ notes })} placeholder="Add a note" aria-label="Note" className="min-w-[16rem] flex-1 rounded-lg border border-[var(--border)] bg-white px-3 py-1.5 text-xs" />
        {!e.from_plan ? <button type="button" onClick={remove} disabled={pending} className="text-xs font-semibold text-red-700 underline">Remove</button> : null}
      </div>
      {error ? <p role="alert" className="text-xs text-red-800">{error}</p> : null}
    </li>
  );
}

export function CompletedWork({ client, data, error, page }: { client: Client; data: Completed | null; error: string | null; page: string | null }) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [text, setText] = useState("");
  const [notePage, setNotePage] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const add = () =>
    start(async () => { const r = await addNoteAction(client.id, date, text, notePage); if (r.ok) { setText(""); setNotePage(""); setFormError(null); router.refresh(); } else setFormError(r.error); });
  return (
    <section className="max-w-5xl space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Completed work</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">Everything marked done on the plan, and anything noted by hand, with what happened to the page&apos;s visits, leads and clicks in the 28 days after compared with the 28 before. A change in the numbers is not proof the work caused it.</p>
      </header>
      {error ? <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p> : null}
      {data ? (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            <Kpi label="Entries" value={num(data.counts.total)} />
            <Kpi label="Marked done on the plan" value={num(data.counts.from_plan)} />
            <Kpi label="Improved" value={num(data.counts.improved)} note="by the numbers or by your say" />
          </div>
          {page ? <p className="text-sm">Showing only <span className="font-semibold">{shortPage(page)}</span>. <Link href={`/${client.slug}/annotations`} className="font-semibold text-[var(--brand-teal)] hover:underline">Show everything</Link></p> : null}
          <section className={`${card} px-5`}>
            {data.entries.length === 0 ? <p className="py-4 text-sm text-[var(--text-secondary)]">Nothing yet. Mark a part of the plan done and it appears here.</p> : <ul className="divide-y divide-[var(--border)]">{data.entries.map((e) => <Row key={e.id} client={client} e={e} />)}</ul>}
          </section>
          <section className={`${card} space-y-3 p-5`}>
            <h2 className="text-lg font-bold">Add a note</h2>
            <p className="text-xs text-[var(--text-secondary)]">For a change made outside the plan: a new form, a redesign, a campaign, a search update.</p>
            <div className="flex flex-wrap items-end gap-2 text-sm">
              <label className="text-xs font-semibold">Date<input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="mt-1 block rounded-lg border border-[var(--border)] bg-white px-3 py-2 text-sm font-normal" /></label>
              <label className="min-w-[16rem] flex-1 text-xs font-semibold">What changed<input value={text} onChange={(e) => setText(e.target.value)} className="mt-1 block w-full rounded-lg border border-[var(--border)] bg-white px-3 py-2 text-sm font-normal" /></label>
              <label className="min-w-[12rem] text-xs font-semibold">Page (optional)<input value={notePage} onChange={(e) => setNotePage(e.target.value)} placeholder="Full address" className="mt-1 block w-full rounded-lg border border-[var(--border)] bg-white px-3 py-2 text-sm font-normal" /></label>
              <button type="button" onClick={add} disabled={pending || text.trim().length < 3} className="rounded-lg bg-[var(--brand-dark)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Add</button>
            </div>
            {formError ? <p role="alert" className="text-xs text-red-800">{formError}</p> : null}
          </section>
        </>
      ) : null}
    </section>
  );
}
