"use client";

import { useState, useTransition } from "react";

import {
  previewBaselineResetAction,
  resetBaselinesAction,
  type BaselineResetPreview,
} from "@/app/(app)/baseline-actions";
import { Alert } from "@/components/ui/Alert";
import { Input } from "@/components/ui/Input";

const CONFIRMATION = "RESET";

function download(name: string, data: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

/**
 * Clear every client's baseline and goals so each can be re-baselined.
 *
 * Irreversible, so it shows what would go first, wants the word typed, and downloads
 * a copy of everything it removed the moment it finishes.
 */
export function ResetBaselinesPanel() {
  const [pending, startTransition] = useTransition();
  const [preview, setPreview] = useState<BaselineResetPreview | null>(null);
  const [typed, setTyped] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  function check() {
    setError(null);
    setMessage(null);
    startTransition(async () => {
      const result = await previewBaselineResetAction();
      if (!result.ok) return setError(result.error);
      setPreview(result.preview);
    });
  }

  function run() {
    setError(null);
    startTransition(async () => {
      const result = await resetBaselinesAction(typed);
      if (!result.ok) return setError(result.error);
      download(`baselines-removed-${new Date().toISOString().slice(0, 10)}.json`, result.done.removed);
      setMessage(
        `Cleared ${result.done.reset_clients} client${result.done.reset_clients === 1 ? "" : "s"} ` +
          `and ${result.done.versions_deleted} locked version${result.done.versions_deleted === 1 ? "" : "s"}. ` +
          "A copy of what was removed was downloaded.",
      );
      setPreview(null);
      setTyped("");
    });
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-[var(--text-secondary)]">
        Clears every client&apos;s locked baselines, baseline numbers, frozen projection, monthly lead goal and goal
        corrections, so each can be baselined again from version 1. Lead conversions and everything else on the client
        are kept. It cannot be undone.
      </p>
      <button type="button" className="btn btn-secondary" disabled={pending} onClick={check}>
        {pending && !preview ? "Checking…" : "Check what would be cleared"}
      </button>

      {error ? <Alert variant="danger">{error}</Alert> : null}
      {message ? <Alert variant="success">{message}</Alert> : null}

      {preview ? (
        preview.clients.length === 0 ? (
          <p className="text-sm text-[var(--text-secondary)]">Nothing to clear: no client has a baseline or goal.</p>
        ) : (
          <div className="space-y-3">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[520px] border-collapse text-sm">
                <thead>
                  <tr className="border-b border-[var(--border)] text-left text-xs text-[var(--text-tertiary)]">
                    <th className="py-1.5 pr-2 font-semibold">Client</th>
                    <th className="py-1.5 pr-2 font-semibold">Locked versions</th>
                    <th className="py-1.5 pr-2 font-semibold">Baseline as of</th>
                    <th className="py-1.5 pr-2 font-semibold">Monthly lead goal</th>
                    <th className="py-1.5 font-semibold">Goal corrections</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.clients.map((row) => (
                    <tr key={row.client_id} className="border-b border-[var(--border)]">
                      <td className="py-1.5 pr-2">{row.client_name}</td>
                      <td className="py-1.5 pr-2">{row.versions}</td>
                      <td className="py-1.5 pr-2">{row.baseline_as_of ?? "—"}</td>
                      <td className="py-1.5 pr-2">{row.monthly_lead_goal ?? "—"}</td>
                      <td className="py-1.5">{row.goal_corrections}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex flex-wrap items-end gap-3">
              <label className="flex flex-col gap-1 text-xs text-[var(--text-secondary)]">
                Type {CONFIRMATION} to confirm
                <Input value={typed} onChange={(event) => setTyped(event.target.value)} className="w-40" />
              </label>
              <button
                type="button"
                className="btn btn-primary"
                disabled={pending || typed !== CONFIRMATION}
                onClick={run}
              >
                {pending ? "Resetting…" : `Reset ${preview.totals.clients} client${preview.totals.clients === 1 ? "" : "s"}`}
              </button>
            </div>
          </div>
        )
      ) : null}
    </div>
  );
}
