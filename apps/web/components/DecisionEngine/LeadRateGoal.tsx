"use client";
import { useState, useTransition } from "react";
import { saveLeadRateGoalAction } from "@/app/(app)/[clientSlug]/decision-engine/actions";

export function LeadRateGoal({ initial, actual, clientId, slug, expanded = false }: { expanded?: boolean; initial: number | null; actual: number | null; clientId: string; slug: string }) {
  const [target, setTarget] = useState(initial);
  const [input, setInput] = useState(initial?.toString() ?? "");
  const [message, setMessage] = useState("");
  const [pending, startTransition] = useTransition();
  return <div className="mt-3 rounded-md bg-[var(--surface-muted)] p-3 text-sm">
    <p className="font-semibold">Current target conversion rate: {target == null ? "Not configured" : `${target}%`}</p>
    <p className="mt-1">{actual == null || target == null ? "A measured rate and a target rate are needed to judge performance." : `${actual.toFixed(2)}% actual versus ${target}% target · ${(actual / target * 100).toFixed(0)}% of rate goal (${actual >= target ? "at or above target" : "below target"}).`}</p>
    <details className="mt-2" open={expanded || undefined}><summary className="cursor-pointer">Set target conversion rate</summary>
      <form className="mt-2 flex flex-wrap items-end gap-2" onSubmit={event => {
        event.preventDefault(); startTransition(async () => {
          const value = input.trim() ? Number(input) : null;
          const result = await saveLeadRateGoalAction(clientId, slug, value);
          if (result.ok) { setTarget(value); setMessage("Target saved for this client. Future assessments use this rate; saved assessment history is preserved."); }
          else setMessage(result.error);
        });
      }}>
        <label>Target lead conversion rate (%)<input className="ml-2 w-24 rounded border border-[var(--border)] bg-[var(--surface)] p-2" type="number" min="0.01" max="100" step="0.01" value={input} onChange={e => setInput(e.target.value)} placeholder="e.g. 3" /></label>
        <button className="rounded border border-[var(--border)] px-3 py-2 disabled:opacity-50" disabled={pending}>Save rate target</button>
      </form>
      <p className="mt-2 text-xs">Blank clears the target. The rate counts each visit with a configured lead outcome once. Legacy event-based targets and baselines stay separate.</p>
    </details>
    {message && <p role="status" className="mt-2">{message}</p>}
  </div>;
}
