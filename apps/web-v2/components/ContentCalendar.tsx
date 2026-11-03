"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState, useTransition } from "react";

import { addItemAction, peopleAction, removeItemAction, sendItemAction, updateItemAction } from "@/app/(app)/[clientSlug]/content-calendar/actions";
import { STATUS_LABEL, StatusChip } from "@/components/content/AddToCalendar";
import { Kpi, SidePane, card, day, num, shortPage, th } from "@/components/content/parts";
import { Spinner } from "@/components/ui/Spinner";
import type { Client } from "@/lib/api";
import type { CalendarData, CalendarItem, CalendarStatus, Person } from "@/lib/content";

const STATUSES: CalendarStatus[] = ["idea", "planned", "writing", "review", "published"];
const TONE: Record<CalendarStatus, string> = { idea: "bg-gray-100 text-gray-800", planned: "bg-blue-100 text-blue-800", writing: "bg-amber-100 text-amber-900", review: "bg-purple-100 text-purple-800", published: "bg-green-100 text-green-800", dropped: "bg-gray-100 text-gray-500" };
const KIND = { new_page: "New page", refresh: "Refresh" } as const;

const key = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

function ItemPane({ client, item, canEdit, teamwork, people, onChanged }: { client: Client; item: CalendarItem; canEdit: boolean; teamwork: CalendarData["teamwork"]; people: Person[]; onChanged: () => void }) {
  const [title, setTitle] = useState(item.title);
  const [status, setStatus] = useState<CalendarStatus>(item.status);
  const [due, setDue] = useState(item.due ?? "");
  const [assignee, setAssignee] = useState(item.assignee_email ?? "");
  const [notes, setNotes] = useState(item.notes ?? "");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [pending, start] = useTransition();
  useEffect(() => {
    setTitle(item.title);
    setStatus(item.status);
    setDue(item.due ?? "");
    setAssignee(item.assignee_email ?? "");
    setNotes(item.notes ?? "");
    setError(null);
    setSaved(false);
  }, [item]);
  const save = () =>
    start(async () => {
      setError(null);
      const r = await updateItemAction(client.id, item.id, { title, status, notes, assignee_email: assignee, ...(due ? { due } : { clear_due: true }) });
      if (!r.ok) setError(r.error);
      else {
        setSaved(true);
        onChanged();
      }
    });
  const send = () =>
    start(async () => {
      setError(null);
      const r = await sendItemAction(client.id, item.id);
      if (!r.ok) setError(r.error);
      else onChanged();
    });
  const remove = () =>
    start(async () => {
      if (!window.confirm("Take this off the calendar? A Teamwork task already sent is left in Teamwork.")) return;
      const r = await removeItemAction(client.id, item.id);
      if (!r.ok) setError(r.error);
      else onChanged();
    });
  const field = "mt-1 block w-full rounded-lg border border-[var(--border)] bg-white px-2 py-2 text-sm font-normal disabled:bg-[var(--bg)]";

  return (
    <div className="space-y-4 text-sm">
      <div>
        <p className="text-xs text-[var(--text-secondary)]">{KIND[item.kind]} · {item.source_area === "manual" ? "added by hand" : `from ${item.source_area === "gap" ? "a content gap" : item.source_area === "topic" ? "a missing topic" : "a content refresh"}`} · {item.created_by}</p>
        <p className="mt-1 break-all text-xs"><span className="font-semibold">{item.source_area === "topic" ? "Subject to cover:" : item.kind === "new_page" ? "Search to win:" : "Page:"}</span> {item.target}</p>
      </div>
      {!canEdit ? <p className="rounded-lg bg-[var(--bg)] p-2 text-xs">You can read the calendar. Admins and content managers change it.</p> : null}
      <label className="block text-xs font-semibold">Title<input value={title} disabled={!canEdit} onChange={(e) => setTitle(e.target.value)} className={field} /></label>
      <div className="flex flex-wrap gap-3">
        <label className="text-xs font-semibold">Status
          <select value={status} disabled={!canEdit} onChange={(e) => setStatus(e.target.value as CalendarStatus)} className={field}>{STATUSES.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}</select>
        </label>
        <label className="text-xs font-semibold">Due<input type="date" value={due} disabled={!canEdit} onChange={(e) => setDue(e.target.value)} className={field} /></label>
        <label className="min-w-[12rem] flex-1 text-xs font-semibold">Assigned to
          <select value={assignee} disabled={!canEdit} onChange={(e) => setAssignee(e.target.value)} className={field}>
            <option value="">Unassigned</option>
            {assignee && !people.some((p) => p.email === assignee) ? <option value={assignee}>{assignee}</option> : null}
            {people.map((p) => <option key={p.email} value={p.email}>{p.name ?? p.email}</option>)}
          </select>
        </label>
      </div>
      <label className="block text-xs font-semibold">Notes for whoever does the work
        <textarea value={notes} disabled={!canEdit} onChange={(e) => setNotes(e.target.value)} rows={12} className={`${field} font-mono text-xs`} />
      </label>
      {error ? <p role="alert" className="font-semibold text-red-700">{error}</p> : null}
      {canEdit ? (
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" onClick={save} disabled={pending} className="rounded-lg bg-[var(--brand-dark)] px-4 py-2 text-xs font-semibold text-white disabled:opacity-50">{pending ? <><Spinner />Saving…</> : "Save"}</button>
          {saved ? <span className="text-xs font-semibold text-green-700">Saved</span> : null}
          <button type="button" onClick={remove} disabled={pending} className="ml-auto rounded-lg border border-[var(--border)] bg-white px-3 py-2 text-xs font-semibold text-red-700 disabled:opacity-50">Remove</button>
        </div>
      ) : null}
      <div className="space-y-2 rounded-lg border border-[var(--border)] p-3">
        <h3 className="font-bold">Teamwork</h3>
        {item.teamwork_task_id ? (
          <p className="text-xs">Sent as a task. <a href={item.teamwork_task_url ?? "#"} target="_blank" rel="noreferrer" className="font-semibold underline">Open in Teamwork</a></p>
        ) : !teamwork.configured ? (
          <p className="text-xs text-[var(--text-tertiary)]">Teamwork is not set up on this install.</p>
        ) : !teamwork.tasklist_id ? (
          <p className="text-xs text-[var(--text-tertiary)]">This client has no Teamwork tasklist yet. Choose one in Settings → Connections.</p>
        ) : canEdit ? (
          <>
            <p className="text-xs text-[var(--text-tertiary)]">Creates one task on the client&apos;s tasklist with the title, due date, assignee and notes. Save changes first: the task is built from what is saved.</p>
            <button type="button" onClick={send} disabled={pending} className="rounded-lg border border-[var(--border)] bg-white px-4 py-2 text-xs font-semibold disabled:opacity-50">Send to Teamwork</button>
          </>
        ) : (
          <p className="text-xs text-[var(--text-tertiary)]">Not sent yet.</p>
        )}
      </div>
    </div>
  );
}

function NewItem({ client, people, onAdded }: { client: Client; people: Person[]; onAdded: () => void }) {
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<"new_page" | "refresh">("new_page");
  const [title, setTitle] = useState("");
  const [target, setTarget] = useState("");
  const [due, setDue] = useState("");
  const [assignee, setAssignee] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const add = () =>
    start(async () => {
      setError(null);
      const r = await addItemAction(client.id, { kind, title, target, source_area: "manual", due: due || null, assignee_email: assignee || null });
      if (!r.ok) setError(r.error);
      else {
        setOpen(false);
        setTitle("");
        setTarget("");
        setDue("");
        setAssignee("");
        onAdded();
      }
    });
  const field = "mt-1 block w-full rounded-lg border border-[var(--border)] bg-white px-2 py-2 text-sm font-normal";
  if (!open) return <button type="button" onClick={() => setOpen(true)} className="rounded-lg bg-[var(--brand-dark)] px-4 py-2 text-sm font-semibold text-white">Add an item</button>;
  return (
    <div className={`${card} space-y-2 p-4`}>
      <div className="flex flex-wrap gap-3">
        <label className="text-xs font-semibold">Type
          <select value={kind} onChange={(e) => setKind(e.target.value as "new_page" | "refresh")} className={field}><option value="new_page">New page</option><option value="refresh">Refresh a page</option></select>
        </label>
        <label className="min-w-[14rem] flex-1 text-xs font-semibold">Title<input value={title} onChange={(e) => setTitle(e.target.value)} className={field} /></label>
        <label className="min-w-[14rem] flex-1 text-xs font-semibold">{kind === "new_page" ? "Search to win" : "Page address"}<input value={target} onChange={(e) => setTarget(e.target.value)} className={field} /></label>
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-xs font-semibold">Due<input type="date" value={due} onChange={(e) => setDue(e.target.value)} className={field} /></label>
        <label className="min-w-[12rem] text-xs font-semibold">Assigned to
          <select value={assignee} onChange={(e) => setAssignee(e.target.value)} className={field}><option value="">Unassigned</option>{people.map((p) => <option key={p.email} value={p.email}>{p.name ?? p.email}</option>)}</select>
        </label>
        <button type="button" onClick={add} disabled={pending || !title.trim() || !target.trim()} className="rounded-lg bg-[var(--brand-dark)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{pending ? "Adding…" : "Add"}</button>
        <button type="button" onClick={() => setOpen(false)} className="text-xs font-semibold underline">Cancel</button>
      </div>
      {error ? <p role="alert" className="text-xs font-semibold text-red-700">{error}</p> : null}
    </div>
  );
}

export function ContentCalendar({ client, data, error }: { client: Client; data: CalendarData | null; error: string | null }) {
  const router = useRouter();
  const [view, setView] = useState<"month" | "list">("month");
  const [cursor, setCursor] = useState(() => { const n = new Date(); return new Date(n.getFullYear(), n.getMonth(), 1); });
  const [filter, setFilter] = useState<CalendarStatus | "all">("all");
  const [open, setOpen] = useState<string | null>(null);
  const [people, setPeople] = useState<Person[]>([]);
  useEffect(() => {
    void peopleAction(client.id).then((r) => r.ok && setPeople(r.value));
  }, [client.id]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const items = useMemo(() => (data?.items ?? []).filter((i) => filter === "all" || i.status === filter), [data, filter]);
  const item = data?.items.find((i) => i.id === open) ?? null;
  const canEdit = data?.can_edit ?? false;
  const refresh = () => { setOpen(null); router.refresh(); };

  const first = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
  const start = new Date(first); start.setDate(1 - ((first.getDay() + 6) % 7)); // weeks start on Monday
  const cells = Array.from({ length: 42 }, (_, i) => { const d = new Date(start); d.setDate(start.getDate() + i); return d; });
  const byDay = new Map<string, CalendarItem[]>();
  for (const i of items) if (i.due) byDay.set(i.due, [...(byDay.get(i.due) ?? []), i]);
  const undated = items.filter((i) => !i.due);
  const today = key(new Date());
  const counts = data?.counts ?? {};
  const overdue = (data?.items ?? []).filter((i) => i.due && i.due < today && i.status !== "published").length;

  const chip = (i: CalendarItem) => (
    <button key={i.id} type="button" onClick={() => setOpen(i.id)} title={`${KIND[i.kind]}: ${i.title}`} className={`block w-full truncate rounded px-1.5 py-0.5 text-left text-[0.7rem] font-semibold ${TONE[i.status]}`}>
      {i.kind === "refresh" ? "↻ " : ""}{i.title}
    </button>
  );

  return (
    <section className="max-w-6xl space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Content calendar</h1>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">Pages to write and pages to refresh, planned and sent to Teamwork. Add them from Content gaps and Content refreshes.</p>
        </div>
        {canEdit ? <NewItem client={client} people={people} onAdded={() => router.refresh()} /> : null}
      </header>

      {error ? <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p> : null}
      {data && !canEdit ? <p className="rounded-lg bg-[var(--bg)] p-3 text-xs">You can read the calendar. Admins and content managers add and change items.</p> : null}

      {data ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Kpi label="On the calendar" value={num(STATUSES.reduce((n, s) => n + (counts[s] ?? 0), 0))} note={`${num(counts.idea ?? 0)} ideas, ${num(counts.planned ?? 0)} planned`} />
            <Kpi label="In progress" value={num((counts.writing ?? 0) + (counts.review ?? 0))} note={`${num(counts.writing ?? 0)} writing, ${num(counts.review ?? 0)} in review`} />
            <Kpi label="Published" value={num(counts.published ?? 0)} note="done" />
            <Kpi label="Overdue" value={num(overdue)} note={overdue === 0 ? "Clean" : "past their due date and not published"} />
          </div>

          <div className="flex flex-wrap items-center gap-2 text-sm">
            <div role="tablist" aria-label="View" className="flex overflow-hidden rounded-lg border border-[var(--border)]">
              {(["month", "list"] as const).map((v) => <button key={v} role="tab" aria-selected={view === v} type="button" onClick={() => setView(v)} className={`px-4 py-2 font-semibold ${view === v ? "bg-[var(--brand-dark)] text-white" : "bg-white"}`}>{v === "month" ? "Month" : "List"}</button>)}
            </div>
            <label className="text-xs font-semibold">Status{" "}
              <select value={filter} onChange={(e) => setFilter(e.target.value as CalendarStatus | "all")} className="ml-1 rounded-lg border border-[var(--border)] bg-white px-2 py-2 text-sm font-normal">
                <option value="all">All</option>{STATUSES.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
              </select>
            </label>
            {view === "month" ? (
              <div className="ml-auto flex items-center gap-2">
                <button type="button" aria-label="Previous month" onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() - 1, 1))} className="rounded-lg border border-[var(--border)] bg-white px-3 py-2 font-semibold">‹</button>
                <span className="min-w-[9rem] text-center font-bold">{cursor.toLocaleDateString("en-US", { month: "long", year: "numeric" })}</span>
                <button type="button" aria-label="Next month" onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1))} className="rounded-lg border border-[var(--border)] bg-white px-3 py-2 font-semibold">›</button>
              </div>
            ) : null}
          </div>

          {data.items.length === 0 ? (
            <section className={`${card} p-5 text-sm`}><p className="font-semibold">Nothing is planned yet.</p><p className="mt-1 text-[var(--text-secondary)]">Open a gap or a page to refresh and press Add to calendar{canEdit ? ", or add an item by hand" : ""}.</p></section>
          ) : view === "month" ? (
            <section className={`${card} overflow-x-auto`}>
              <div className="grid min-w-[44rem] grid-cols-7 text-xs">
                {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => <div key={d} className={th}>{d}</div>)}
                {cells.map((d) => {
                  const k = key(d);
                  const inMonth = d.getMonth() === cursor.getMonth();
                  return (
                    <div key={k} className={`min-h-24 space-y-1 border-t border-[var(--border)] p-1.5 ${inMonth ? "" : "bg-[var(--bg)] text-[var(--text-tertiary)]"} ${k === today ? "ring-1 ring-inset ring-[var(--brand-dark)]" : ""}`}>
                      <div className="font-semibold tabular-nums">{d.getDate()}</div>
                      {(byDay.get(k) ?? []).map(chip)}
                    </div>
                  );
                })}
              </div>
            </section>
          ) : (
            <section className={card}>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr><th className={th}>Item</th><th className={th}>Type</th><th className={th}>Status</th><th className={th}>Due</th><th className={th}>Assigned</th><th className={th}>Teamwork</th></tr></thead>
                  <tbody>
                    {items.map((i) => (
                      <tr key={i.id} className="cursor-pointer border-t border-[var(--border)] align-top hover:bg-[var(--bg)]" onClick={() => setOpen(i.id)}>
                        <td className="max-w-sm px-3 py-2"><div className="font-semibold">{i.title}</div><div className="break-all text-xs text-[var(--text-tertiary)]">{i.kind === "refresh" ? shortPage(i.target) : i.target}</div></td>
                        <td className="px-3 py-2 text-xs">{KIND[i.kind]}</td>
                        <td className="px-3 py-2"><StatusChip status={i.status} /></td>
                        <td className={`px-3 py-2 tabular-nums ${i.due && i.due < today && i.status !== "published" ? "font-semibold text-red-700" : ""}`}>{i.due ? day(i.due) : "–"}</td>
                        <td className="px-3 py-2 text-xs">{i.assignee_email ?? "–"}</td>
                        <td className="px-3 py-2 text-xs">{i.teamwork_task_id ? "Sent" : "–"}</td>
                      </tr>
                    ))}
                    {items.length === 0 ? <tr><td colSpan={6} className="px-5 py-4 text-[var(--text-secondary)]">Nothing has that status.</td></tr> : null}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {view === "month" && undated.length ? (
            <section className={`${card} p-4`}>
              <h2 className="font-bold">No date yet</h2>
              <div className="mt-2 flex flex-wrap gap-2">{undated.map((i) => <div key={i.id} className="w-56">{chip(i)}</div>)}</div>
            </section>
          ) : null}
        </>
      ) : null}

      <SidePane open={!!item} label={item?.title ?? "Item"} onClose={() => setOpen(null)}>
        {item && data ? <ItemPane client={client} item={item} canEdit={canEdit} teamwork={data.teamwork} people={people} onChanged={refresh} /> : null}
      </SidePane>
    </section>
  );
}
