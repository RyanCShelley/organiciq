"use client";

import { Spinner } from "@/components/ui/Spinner";
import type { ContentDepthChoice } from "@/lib/content";

export const card = "rounded-xl border border-[var(--border)] bg-[var(--surface)]";
export const th = "px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-[var(--text-tertiary)]";
export const td = "px-3 py-2 tabular-nums";
export const num = (n: number | null | undefined) => (n == null ? "–" : n.toLocaleString());
export const shortPage = (url: string) => url.replace(/^https?:\/\/[^/]+/, "") || "/";
export const day = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
export const DEPTH: Record<ContentDepthChoice, string> = { quick: "Quick (Sonnet 5.5)", deep: "Deep dive (Opus 5.5)", deepest: "Deepest (Fable 5.1)" };

export function Kpi({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className={`${card} p-4`}>
      <div className="text-xs font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">{label}</div>
      <div className="mt-1 text-3xl font-bold tabular-nums">{value}</div>
      {note ? <div className="mt-1 text-xs text-[var(--text-secondary)]">{note}</div> : null}
    </div>
  );
}

/** The depth choice and the button that asks the model, shared by the brief, the refresh plan and the topic finder. */
export function AskModel({ ready, depth, onDepth, busy, again, label, onRun }: { ready: boolean; depth: ContentDepthChoice; onDepth: (d: ContentDepthChoice) => void; busy: boolean; again: boolean; label: string; onRun: () => void }) {
  if (!ready) return <p className="rounded-lg bg-amber-50 p-2 text-xs text-amber-900">The model needs the Anthropic key on the API service.</p>;
  return (
    <div className="flex flex-wrap items-end gap-2">
      <label className="text-xs font-semibold">
        How deep
        <select value={depth} onChange={(e) => onDepth(e.target.value as ContentDepthChoice)} className="mt-1 block rounded-lg border border-[var(--border)] bg-white px-2 py-2 text-sm font-normal">
          {(Object.keys(DEPTH) as ContentDepthChoice[]).map((k) => <option key={k} value={k}>{DEPTH[k]}</option>)}
        </select>
      </label>
      <button type="button" onClick={onRun} disabled={busy} className="rounded-lg bg-[var(--brand-dark)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
        {busy ? <><Spinner />Writing…</> : again ? "Write again" : label}
      </button>
    </div>
  );
}

export function List({ title, items }: { title: string; items?: string[] }) {
  if (!items || items.length === 0) return null;
  return (
    <div>
      <div className="text-xs font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">{title}</div>
      <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm">{items.map((x, i) => <li key={i}>{x}</li>)}</ul>
    </div>
  );
}

export function SidePane({ open, label, onClose, children }: { open: boolean; label: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <aside aria-label={label} aria-hidden={!open} className={`fixed right-0 top-0 z-30 flex h-full w-full max-w-2xl flex-col border-l border-[var(--border)] bg-[var(--surface)] shadow-xl transition-transform duration-200 ${open ? "translate-x-0" : "pointer-events-none translate-x-full"}`}>
      <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-3">
        <h2 className="font-bold">{label}</h2>
        <button type="button" onClick={onClose} className="rounded-lg border border-[var(--border)] bg-white px-3 py-1 text-sm font-semibold">Close</button>
      </div>
      <div className="flex-1 overflow-y-auto p-5">{children}</div>
    </aside>
  );
}
