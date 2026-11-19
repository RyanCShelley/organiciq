"use client";

import Link from "next/link";
import { useState, useTransition } from "react";

import { logVisibilityCheckAction } from "@/app/(app)/[clientSlug]/search-visibility/actions";

export type VisibilityCheckFields = {
  nextCheckDate: string;
  searchNotes: string;
  llmNotes: string;
  nextSteps: string;
};

export function formatVisibilityCheckNotes(fields: VisibilityCheckFields): string {
  const parts: string[] = [];
  if (fields.nextCheckDate.trim()) parts.push(`Next check: ${fields.nextCheckDate.trim()}`);
  if (fields.searchNotes.trim()) parts.push(`Search visibility:\n${fields.searchNotes.trim()}`);
  if (fields.llmNotes.trim()) parts.push(`LLM visibility:\n${fields.llmNotes.trim()}`);
  if (fields.nextSteps.trim()) parts.push(`Next steps:\n${fields.nextSteps.trim()}`);
  return parts.join("\n\n");
}

export function parseVisibilityCheckNotes(raw: string | null | undefined): VisibilityCheckFields {
  const empty: VisibilityCheckFields = { nextCheckDate: "", searchNotes: "", llmNotes: "", nextSteps: "" };
  if (!raw) return empty;
  const text = raw.trim();
  const nextMatch = text.match(/^Next check:\s*(\d{4}-\d{2}-\d{2})/m);
  const nextCheckDate = nextMatch ? nextMatch[1] : "";

  const extractSection = (label: string, stopLabels: string[]) => {
    const startRe = new RegExp(`^${label}:\\s*\\n?`, "m");
    const m = startRe.exec(text);
    if (!m) return "";
    const rest = text.slice(m.index + m[0].length);
    let endIdx = rest.length;
    for (const stop of stopLabels) {
      const sRe = new RegExp(`\\n\\n${stop}:`, "m");
      const sm = sRe.exec(rest);
      if (sm && sm.index < endIdx) endIdx = sm.index;
    }
    return rest.slice(0, endIdx).trim();
  };

  const searchNotes = extractSection("Search visibility", ["LLM visibility", "Next steps"]);
  const llmNotes = extractSection("LLM visibility", ["Next steps"]);
  const nextSteps = extractSection("Next steps", []);

  if (!searchNotes && !llmNotes && !nextSteps && !nextCheckDate) {
    return { ...empty, searchNotes: text };
  }
  return { nextCheckDate, searchNotes, llmNotes, nextSteps };
}

function addDaysIso(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

export function VisibilityCheckDrawer({
  open,
  clientId,
  clientSlug,
  defaultSummary,
  onClose,
  onSaved,
}: {
  open: boolean;
  clientId: string;
  clientSlug: string;
  defaultSummary?: string;
  onClose: () => void;
  onSaved?: (saved: { id: string; date: string; description: string; notes: string }) => void;
}) {
  const today = new Date().toISOString().slice(0, 10);
  const [date, setDate] = useState(today);
  const [nextCheckDate, setNextCheckDate] = useState(addDaysIso(today, 30));
  const [summary, setSummary] = useState(defaultSummary || `Visibility check (${today})`);
  const [searchNotes, setSearchNotes] = useState("");
  const [llmNotes, setLlmNotes] = useState("");
  const [nextSteps, setNextSteps] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [savedId, setSavedId] = useState<string | null>(null);
  const [pending, startSave] = useTransition();

  if (!open) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const trimmedSummary = summary.trim();
    if (trimmedSummary.length < 3) {
      setError("Please enter a short headline (at least 3 characters).");
      return;
    }
    const formattedNotes = formatVisibilityCheckNotes({
      nextCheckDate,
      searchNotes,
      llmNotes,
      nextSteps,
    });
    startSave(async () => {
      const res = await logVisibilityCheckAction(clientId, date, trimmedSummary, undefined, formattedNotes);
      if (res.ok) {
        setSavedId(res.id);
        onSaved?.({ id: res.id, date, description: trimmedSummary, notes: formattedNotes });
      } else {
        setError(res.error);
      }
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30" role="dialog" aria-modal="true" aria-label="Log visibility check">
      <div className="flex h-full w-full max-w-lg flex-col border-l border-[#e8e8e8] bg-white">
        <div className="flex items-start justify-between gap-4 border-b border-[#e8e8e8] px-6 py-4">
          <div>
            <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
              Search &amp; LLM visibility
            </div>
            <h2 className="mt-0.5 font-[var(--font-heading)] text-xl font-bold text-[#0a0c0f]">
              Log visibility check
            </h2>
            <p className="mt-0.5 text-xs text-[#4a5560]">
              Record what you observed across search and AI engines, and set the next check date.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close panel"
            className="cursor-pointer rounded-full border border-[#e3e6e8] px-2.5 py-1 text-xs font-semibold text-[#4a5560] hover:text-[#0a0c0f]"
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-1 flex-col justify-between overflow-y-auto px-6 py-5">
          <div className="space-y-4">
            {error ? (
              <p role="alert" className="rounded-lg bg-red-50 p-3 text-xs text-red-800">
                {error}
              </p>
            ) : null}

            {savedId ? (
              <div className="rounded-xl border border-[#c6f2ed] bg-[#e6f7f5] p-4 text-sm text-[#00665f]">
                <div className="font-bold">Visibility check saved ✓</div>
                <p className="mt-1 text-xs">
                  Added to Visibility logs and marked on the Search visibility trend chart.
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Link
                    href={`/${clientSlug}/visibility-logs`}
                    className="rounded-full bg-[#223540] px-3.5 py-1.5 text-xs font-semibold text-white hover:opacity-90"
                  >
                    Open Visibility logs →
                  </Link>
                  <button
                    type="button"
                    onClick={onClose}
                    className="cursor-pointer rounded-full border border-[#00a99d] bg-white px-3.5 py-1.5 text-xs font-semibold text-[#00665f]"
                  >
                    Done
                  </button>
                </div>
              </div>
            ) : null}

            <div className="grid grid-cols-2 gap-3">
              <label className="block">
                <span className="text-xs font-semibold text-[#223540]">Check date</span>
                <input
                  type="date"
                  required
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                  className="mt-1 w-full rounded-[10px] border border-[#e3e6e8] px-3 py-2 text-sm text-[#171a22]"
                />
              </label>

              <label className="block">
                <span className="text-xs font-semibold text-[#223540]">Next check date</span>
                <input
                  type="date"
                  value={nextCheckDate}
                  onChange={(e) => setNextCheckDate(e.target.value)}
                  className="mt-1 w-full rounded-[10px] border border-[#e3e6e8] px-3 py-2 text-sm text-[#171a22]"
                />
              </label>
            </div>

            <label className="block">
              <span className="text-xs font-semibold text-[#223540]">Summary headline</span>
              <input
                type="text"
                required
                value={summary}
                onChange={(e) => setSummary(e.target.value)}
                placeholder="e.g. Monthly visibility check — Nov 2026"
                className="mt-1 w-full rounded-[10px] border border-[#e3e6e8] px-3 py-2 text-sm text-[#171a22]"
              />
            </label>

            <label className="block">
              <span className="text-xs font-semibold text-[#223540]">Search visibility observations</span>
              <textarea
                rows={3}
                value={searchNotes}
                onChange={(e) => setSearchNotes(e.target.value)}
                placeholder="GSC & Bing ranking shifts, page-one movers, new unsung heroes..."
                className="mt-1 w-full rounded-[10px] border border-[#e3e6e8] px-3 py-2 text-sm text-[#171a22]"
              />
            </label>

            <label className="block">
              <span className="text-xs font-semibold text-[#223540]">LLM visibility observations</span>
              <textarea
                rows={3}
                value={llmNotes}
                onChange={(e) => setLlmNotes(e.target.value)}
                placeholder="ChatGPT, Claude, Gemini, Perplexity mentions & citations..."
                className="mt-1 w-full rounded-[10px] border border-[#e3e6e8] px-3 py-2 text-sm text-[#171a22]"
              />
            </label>

            <label className="block">
              <span className="text-xs font-semibold text-[#223540]">Focus for next check (projection)</span>
              <textarea
                rows={2}
                value={nextSteps}
                onChange={(e) => setNextSteps(e.target.value)}
                placeholder="What to watch or improve before the next visibility check..."
                className="mt-1 w-full rounded-[10px] border border-[#e3e6e8] px-3 py-2 text-sm text-[#171a22]"
              />
            </label>
          </div>

          <div className="mt-6 flex items-center justify-between gap-3 border-t border-[#eef0f1] pt-4">
            <Link
              href={`/${clientSlug}/visibility-logs`}
              className="text-xs font-semibold text-[#00857b] hover:underline"
            >
              View all visibility logs →
            </Link>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={onClose}
                className="cursor-pointer rounded-full border border-[#d3d7d9] bg-white px-4 py-2 text-xs font-semibold text-[#4a5560]"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={pending}
                className="cursor-pointer rounded-full bg-[#223540] px-4 py-2 text-xs font-semibold text-white hover:bg-[#00a99d] disabled:opacity-60"
              >
                {pending ? "Saving…" : "Save visibility log"}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
