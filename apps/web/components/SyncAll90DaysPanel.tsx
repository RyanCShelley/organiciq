"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { syncJobWindow } from "@/lib/dates";

type SyncSource =
  | "gsc_pages"
  | "gsc_queries"
  | "ga4"
  | "se_ranking_search"
  | "se_ranking_ai"
  | "se_ranking_audit";

async function enqueueJob(
  clientId: string,
  source: SyncSource,
  window: { start_date: string; end_date: string },
): Promise<string | null> {
  const res = await fetch("/api/proxy/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ clientId, source, ...window }),
  });
  if (!res.ok) {
    return (await res.text()) || `Failed to enqueue ${source}`;
  }
  return null;
}

export function SyncAll90DaysPanel({
  clientId,
  hasGscProperty,
  hasGa4Property,
  hasSerankingProject,
}: {
  clientId: string;
  hasGscProperty: boolean;
  hasGa4Property: boolean;
  hasSerankingProject: boolean;
}) {
  const router = useRouter();
  const [message, setMessage] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const canSync = hasGscProperty || hasGa4Property || hasSerankingProject;
  const mapped: string[] = [];
  if (hasGscProperty) mapped.push("GSC");
  if (hasGa4Property) mapped.push("GA4");
  if (hasSerankingProject) mapped.push("SE Ranking");

  async function syncAll90Days() {
    setPending(true);
    setMessage(null);
    const window = syncJobWindow(90);
    const sources: SyncSource[] = [];

    if (hasGscProperty) {
      sources.push("gsc_pages", "gsc_queries");
    }
    if (hasGa4Property) {
      sources.push("ga4");
    }
    if (hasSerankingProject) {
      sources.push("se_ranking_search", "se_ranking_ai", "se_ranking_audit");
    }

    const enqueued: string[] = [];
    for (const source of sources) {
      const error = await enqueueJob(clientId, source, window);
      if (error) {
        setPending(false);
        setMessage(`${error}${enqueued.length ? ` (enqueued: ${enqueued.join(", ")})` : ""}`);
        return;
      }
      enqueued.push(source);
    }

    setPending(false);
    setMessage(
      enqueued.length
        ? `Sync started for ${enqueued.length} jobs (${window.start_date} → ${window.end_date}). Watch Platform → Sync jobs for progress.`
        : "No mapped integrations to sync.",
    );
    router.refresh();
  }

  return (
    <div className="mt-6 rounded-xl border border-[var(--accent)]/40 bg-[var(--accent)]/5 p-4">
      <h2 className="text-lg font-medium">Sync data</h2>
      <p className="mt-1 text-sm text-[var(--muted)]">
        Pull the last <strong>90 days</strong> for every mapped source on this client
        {mapped.length ? ` (${mapped.join(", ")})` : ""}. Use this for the first backfill or a full
        refresh. After that, the platform auto-syncs the last few days every morning.
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          disabled={pending || !canSync}
          onClick={syncAll90Days}
          className="btn btn-primary disabled:opacity-50"
        >
          {pending ? "Starting sync…" : "Sync 90 days"}
        </button>
      </div>
      {!canSync ? (
        <p className="mt-3 text-sm text-[var(--muted)]">
          Map at least one GSC, GA4, or SE Ranking property above before syncing.
        </p>
      ) : null}
      {message ? <p className="mt-3 text-sm text-[var(--muted)]">{message}</p> : null}
    </div>
  );
}
