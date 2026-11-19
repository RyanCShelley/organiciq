"use client";

import Link from "next/link";
import { useState } from "react";

import { parseVisibilityCheckNotes, VisibilityCheckDrawer } from "@/components/VisibilityCheckDrawer";
import type { Client } from "@/lib/api";

export type VisibilityLogEntry = {
  id: string;
  date: string;
  type: string;
  description: string;
  notes: string | null;
};

const formatDate = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });

function daysBetween(fromIso: string, toIso: string): number {
  const a = new Date(`${fromIso}T00:00:00`).getTime();
  const b = new Date(`${toIso}T00:00:00`).getTime();
  return Math.round((b - a) / 86400000);
}

export function VisibilityLogs({
  client,
  initialEntries,
  error,
}: {
  client: Client;
  initialEntries: VisibilityLogEntry[];
  error: string | null;
}) {
  const [entries, setEntries] = useState<VisibilityLogEntry[]>(initialEntries);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const today = new Date().toISOString().slice(0, 10);
  const latest = entries[0] ?? null;
  const latestParsed = latest ? parseVisibilityCheckNotes(latest.notes) : null;
  const nextDue = latestParsed?.nextCheckDate || null;
  const daysUntilDue = nextDue ? daysBetween(today, nextDue) : null;

  return (
    <section className="max-w-5xl space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="font-[var(--font-heading)] text-2xl font-bold text-[#0a0c0f]">Visibility logs</h1>
          <p className="mt-1 text-sm text-[#4a5560]">
            Keep track of when you last reviewed Search and LLM visibility, what you saw, and when the next check is due.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setDrawerOpen(true)}
          className="cursor-pointer rounded-full bg-[#223540] px-4 py-2 text-xs font-semibold text-white hover:bg-[#00a99d]"
        >
          + Log visibility check
        </button>
      </header>

      {error ? (
        <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">
          {error}
        </p>
      ) : null}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="rounded-xl border border-[#ececec] bg-white p-4">
          <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">Last check</div>
          <div className="mt-1.5 font-[var(--font-heading)] text-2xl font-bold text-[#0a0c0f]">
            {latest ? formatDate(latest.date) : "—"}
          </div>
          <div className="mt-1 text-xs text-[#4a5560]">
            {latest
              ? `${Math.max(0, daysBetween(latest.date, today))} days ago`
              : "No visibility checks logged yet"}
          </div>
        </div>

        <div className="rounded-xl border border-[#ececec] bg-white p-4">
          <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">Next check due</div>
          <div className="mt-1.5 font-[var(--font-heading)] text-2xl font-bold text-[#0a0c0f]">
            {nextDue ? formatDate(nextDue) : "Not scheduled"}
          </div>
          <div className="mt-1 text-xs text-[#4a5560]">
            {daysUntilDue == null
              ? "Set a next check date when logging"
              : daysUntilDue < 0
                ? `${Math.abs(daysUntilDue)} days overdue`
                : daysUntilDue === 0
                  ? "Due today"
                  : `In ${daysUntilDue} days`}
          </div>
        </div>

        <div className="rounded-xl border border-[#ececec] bg-white p-4">
          <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">Checks logged</div>
          <div className="mt-1.5 font-[var(--font-heading)] text-2xl font-bold text-[#0a0c0f] tabular-nums">
            {entries.length}
          </div>
          <div className="mt-1 flex items-center gap-3 text-xs">
            <Link href={`/${client.slug}/search-visibility`} className="font-semibold text-[#00857b] hover:underline">
              Search visibility →
            </Link>
            <Link href={`/${client.slug}/llm`} className="font-semibold text-[#00857b] hover:underline">
              LLM visibility →
            </Link>
          </div>
        </div>
      </div>

      {entries.length === 0 ? (
        <div className="rounded-xl border border-[#ececec] bg-white p-8 text-center">
          <div className="font-[var(--font-heading)] text-base font-bold text-[#0a0c0f]">
            No visibility checks logged yet
          </div>
          <p className="mt-1 text-sm text-[#4a5560]">
            Click <strong>+ Log visibility check</strong> after reviewing Search and LLM visibility to record observations and schedule the next check.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {entries.map((entry) => {
            const parsed = parseVisibilityCheckNotes(entry.notes);
            return (
              <article key={entry.id} className="rounded-xl border border-[#ececec] bg-white p-5">
                <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-[#f1f2f3] pb-3">
                  <div>
                    <div className="text-xs font-semibold text-[#00857b]">{formatDate(entry.date)}</div>
                    <h2 className="mt-0.5 font-[var(--font-heading)] text-lg font-bold text-[#0a0c0f]">
                      {entry.description}
                    </h2>
                  </div>
                  {parsed.nextCheckDate ? (
                    <span className="rounded-full bg-[#e6f7f5] px-3 py-1 text-xs font-semibold text-[#00665f]">
                      Next check: {formatDate(parsed.nextCheckDate)}
                    </span>
                  ) : null}
                </div>

                <div className="mt-3 grid grid-cols-1 gap-4 md:grid-cols-3">
                  <div>
                    <div className="text-[11px] font-bold uppercase tracking-[0.1em] text-[#7a838c]">
                      Search visibility
                    </div>
                    <p className="mt-1 whitespace-pre-line text-sm text-[#171a22]">
                      {parsed.searchNotes || <span className="text-[#909a9f]">No search notes recorded.</span>}
                    </p>
                  </div>
                  <div>
                    <div className="text-[11px] font-bold uppercase tracking-[0.1em] text-[#7a838c]">
                      LLM visibility
                    </div>
                    <p className="mt-1 whitespace-pre-line text-sm text-[#171a22]">
                      {parsed.llmNotes || <span className="text-[#909a9f]">No LLM notes recorded.</span>}
                    </p>
                  </div>
                  <div>
                    <div className="text-[11px] font-bold uppercase tracking-[0.1em] text-[#7a838c]">
                      Next steps / projection
                    </div>
                    <p className="mt-1 whitespace-pre-line text-sm text-[#171a22]">
                      {parsed.nextSteps || <span className="text-[#909a9f]">No follow-up notes recorded.</span>}
                    </p>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}

      <VisibilityCheckDrawer
        open={drawerOpen}
        clientId={client.id}
        clientSlug={client.slug}
        onClose={() => setDrawerOpen(false)}
        onSaved={(saved) => {
          setEntries((prev) => [
            {
              id: saved.id,
              date: saved.date,
              type: "visibility_check",
              description: saved.description,
              notes: saved.notes,
            },
            ...prev,
          ]);
        }}
      />
    </section>
  );
}
