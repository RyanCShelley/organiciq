"use client";

import Link from "next/link";
import { useEffect, useState, useTransition } from "react";

import { addItemAction, peopleAction } from "@/app/(app)/[clientSlug]/content-calendar/actions";
import { Spinner } from "@/components/ui/Spinner";
import type { Client } from "@/lib/api";
import type { CalendarStatus, Person } from "@/lib/content";

export const STATUS_LABEL: Record<CalendarStatus, string> = { idea: "Idea", planned: "Planned", writing: "Writing", review: "In review", published: "Published", dropped: "Dropped" };

/** Puts a gap or a page on the content calendar. Admins and content managers add; everyone else sees where it stands. */
export function AddToCalendar({ client, canEdit, status, kind, title, target, sourceArea, sourceKey, onAdded }: {
  client: Client;
  canEdit: boolean;
  status?: CalendarStatus;
  kind: "new_page" | "refresh";
  title: string;
  target: string;
  sourceArea: "gap" | "refresh";
  sourceKey: string;
  onAdded: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [people, setPeople] = useState<Person[]>([]);
  const [due, setDue] = useState("");
  const [assignee, setAssignee] = useState("");
  const [name, setName] = useState(title);
  const [added, setAdded] = useState<CalendarStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();
  useEffect(() => {
    setOpen(false);
    setAdded(null);
    setName(title);
    setError(null);
  }, [sourceKey, title]);
  useEffect(() => {
    if (open && people.length === 0) void peopleAction(client.id).then((r) => r.ok && setPeople(r.value));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);
  const where = added ?? status;
  const add = () =>
    start(async () => {
      setError(null);
      const r = await addItemAction(client.id, { kind, title: name.trim() || title, target, source_area: sourceArea, source_key: sourceKey, due: due || null, assignee_email: assignee || null });
      if (!r.ok) setError(r.error);
      else {
        setAdded(r.value.status);
        setOpen(false);
        onAdded();
      }
    });

  return (
    <div className="space-y-2 rounded-lg border border-[var(--border)] p-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-bold">Content calendar</h3>
        {where ? (
          <span className="text-xs">On the calendar · <strong>{STATUS_LABEL[where]}</strong> · <Link href={`/${client.slug}/content-calendar`} className="font-semibold underline">Open calendar</Link></span>
        ) : canEdit ? (
          <button type="button" onClick={() => setOpen(!open)} className="rounded-lg bg-[var(--brand-dark)] px-3 py-1.5 text-xs font-semibold text-white">{open ? "Cancel" : "Add to calendar"}</button>
        ) : (
          <span className="text-xs text-[var(--text-tertiary)]">Only admins and content managers add to the calendar.</span>
        )}
      </div>
      {open && !where ? (
        <div className="space-y-2">
          <label className="block text-xs font-semibold">
            Title
            <input value={name} onChange={(e) => setName(e.target.value)} className="mt-1 block w-full rounded-lg border border-[var(--border)] bg-white px-2 py-2 text-sm font-normal" />
          </label>
          <div className="flex flex-wrap gap-3">
            <label className="text-xs font-semibold">
              Due
              <input type="date" value={due} onChange={(e) => setDue(e.target.value)} className="mt-1 block rounded-lg border border-[var(--border)] bg-white px-2 py-2 text-sm font-normal" />
            </label>
            <label className="min-w-[12rem] flex-1 text-xs font-semibold">
              Assigned to
              <select value={assignee} onChange={(e) => setAssignee(e.target.value)} className="mt-1 block w-full rounded-lg border border-[var(--border)] bg-white px-2 py-2 text-sm font-normal">
                <option value="">Unassigned</option>
                {people.map((p) => <option key={p.email} value={p.email}>{p.name ?? p.email}</option>)}
              </select>
            </label>
          </div>
          <p className="text-xs text-[var(--text-tertiary)]">{kind === "new_page" ? "The brief is copied in if the model has written one." : "The refresh plan is copied in if the model has written one."} Nothing is sent to Teamwork until you press send on the calendar.</p>
          <button type="button" onClick={add} disabled={pending} className="rounded-lg bg-[var(--brand-dark)] px-4 py-2 text-xs font-semibold text-white disabled:opacity-50">{pending ? <><Spinner />Adding…</> : "Add"}</button>
        </div>
      ) : null}
      {error ? <p role="alert" className="text-xs font-semibold text-red-700">{error}</p> : null}
    </div>
  );
}

export function StatusChip({ status }: { status?: CalendarStatus }) {
  if (!status) return <span className="text-xs text-[var(--text-tertiary)]">–</span>;
  const tone = status === "published" ? "bg-green-100 text-green-800" : status === "idea" ? "bg-gray-100 text-gray-700" : "bg-blue-100 text-blue-800";
  return <span className={`rounded px-1.5 py-0.5 text-xs font-semibold ${tone}`}>{STATUS_LABEL[status]}</span>;
}
