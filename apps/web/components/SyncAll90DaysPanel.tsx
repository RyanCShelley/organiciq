"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import type { SyncJob } from "@/lib/api";
import { syncJobWindow } from "@/lib/dates";

type SyncSource =
  | "gsc_pages"
  | "gsc_queries"
  | "ga4"
  | "se_ranking_search"
  | "se_ranking_ai"
  | "se_ranking_audit";

const ACTIVE_STATUSES = new Set([
  "queued",
  "fetching",
  "staging",
  "normalizing",
  "validating",
]);

const SOURCE_LABELS: Record<SyncSource, string> = {
  gsc_pages: "GSC pages",
  gsc_queries: "GSC queries",
  ga4: "GA4",
  se_ranking_search: "SE Ranking search",
  se_ranking_ai: "SE Ranking AI",
  se_ranking_audit: "SE Ranking audit",
};

type SourceProgress = {
  source: SyncSource;
  status: string | null;
  error: string | null;
};

function isOverlapError(text: string): boolean {
  return /active sync job already exists/i.test(text);
}

function parseErrorDetail(text: string): string {
  try {
    const body = JSON.parse(text) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // fall through
  }
  return text;
}

async function enqueueJob(
  clientId: string,
  source: SyncSource,
  window: { start_date: string; end_date: string },
): Promise<"created" | "already_active" | string> {
  const res = await fetch("/api/proxy/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ clientId, source, ...window }),
  });
  if (res.ok) return "created";
  const text = await res.text();
  if (res.status === 409 || isOverlapError(text)) return "already_active";
  return parseErrorDetail(text) || `Failed to enqueue ${source}`;
}

async function fetchJobs(clientId: string): Promise<SyncJob[]> {
  const res = await fetch(`/api/proxy/jobs?clientId=${encodeURIComponent(clientId)}`, {
    cache: "no-store",
  });
  if (!res.ok) return [];
  const data = (await res.json()) as unknown;
  return Array.isArray(data) ? (data as SyncJob[]) : [];
}

function latestBySource(jobs: SyncJob[], sources: SyncSource[]): SourceProgress[] {
  return sources.map((source) => {
    const match = jobs.find((job) => job.source === source);
    return {
      source,
      status: match?.status ?? null,
      error: match?.error_message ?? null,
    };
  });
}

function hasActiveJobs(rows: SourceProgress[]): boolean {
  return rows.some((row) => row.status != null && ACTIVE_STATUSES.has(row.status));
}

function completedCount(rows: SourceProgress[]): number {
  return rows.filter((row) => row.status != null && !ACTIVE_STATUSES.has(row.status)).length;
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
  const [tracking, setTracking] = useState(false);
  const [progressRows, setProgressRows] = useState<SourceProgress[]>([]);
  const trackingRef = useRef(false);
  const wasActiveRef = useRef(false);

  useEffect(() => {
    trackingRef.current = tracking;
  }, [tracking]);

  const canSync = hasGscProperty || hasGa4Property || hasSerankingProject;
  const mapped: string[] = [];
  if (hasGscProperty) mapped.push("GSC");
  if (hasGa4Property) mapped.push("GA4");
  if (hasSerankingProject) mapped.push("SE Ranking");

  const trackedSources = useMemo(() => {
    const sources: SyncSource[] = [];
    if (hasGscProperty) sources.push("gsc_pages", "gsc_queries");
    if (hasGa4Property) sources.push("ga4");
    if (hasSerankingProject) {
      sources.push("se_ranking_search", "se_ranking_ai", "se_ranking_audit");
    }
    return sources;
  }, [hasGscProperty, hasGa4Property, hasSerankingProject]);

  useEffect(() => {
    if (!trackedSources.length) return;

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    async function poll() {
      const jobs = await fetchJobs(clientId);
      if (cancelled) return;

      const rows = latestBySource(jobs, trackedSources);
      const active = hasActiveJobs(rows);

      if (active || trackingRef.current) {
        setProgressRows(rows);
      }

      if (active) {
        wasActiveRef.current = true;
        if (!trackingRef.current) {
          setTracking(true);
          setMessage(null);
        }
      } else if (trackingRef.current && wasActiveRef.current) {
        wasActiveRef.current = false;
        setTracking(false);
        const failed = rows.filter((row) => row.status === "failed");
        setMessage(
          failed.length
            ? `Sync finished with ${failed.length} failed job${failed.length === 1 ? "" : "s"}.`
            : "Sync finished.",
        );
        router.refresh();
      }

      timer = setTimeout(poll, active || trackingRef.current ? 2500 : 10000);
    }

    void poll();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [clientId, trackedSources, router]);

  async function syncAll90Days() {
    setPending(true);
    setMessage(null);
    const window = syncJobWindow(90);
    if (!trackedSources.length) {
      setPending(false);
      setMessage("No mapped integrations to sync.");
      return;
    }

    for (const source of trackedSources) {
      const result = await enqueueJob(clientId, source, window);
      if (result !== "created" && result !== "already_active") {
        setPending(false);
        setTracking(true);
        wasActiveRef.current = true;
        setMessage(result);
        return;
      }
    }

    setPending(false);
    setTracking(true);
    wasActiveRef.current = true;
    setMessage(null);
    router.refresh();
  }

  const total = progressRows.length || trackedSources.length;
  const done = completedCount(progressRows);
  const active = hasActiveJobs(progressRows);
  const showProgress = tracking || active;
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  const current =
    progressRows.find((row) => row.status != null && ACTIVE_STATUSES.has(row.status)) ?? null;

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
          disabled={pending || !canSync || active}
          onClick={syncAll90Days}
          className="btn btn-primary disabled:opacity-50"
        >
          {pending ? "Starting sync…" : active ? "Sync in progress…" : "Sync 90 days"}
        </button>
      </div>
      {!canSync ? (
        <p className="mt-3 text-sm text-[var(--muted)]">
          Map at least one GSC, GA4, or SE Ranking property above before syncing.
        </p>
      ) : null}

      {showProgress ? (
        <div className="mt-4 space-y-2">
          <div className="flex items-center justify-between gap-3 text-sm">
            <span className="text-[var(--text-secondary)]">
              {active
                ? current
                  ? `Syncing ${SOURCE_LABELS[current.source]} (${current.status})`
                  : "Sync in progress"
                : "Finishing sync…"}
            </span>
            <span className="tabular-nums text-[var(--text-tertiary)]">
              {done}/{total} · {pct}%
            </span>
          </div>
          <div className="progress-track h-2 overflow-hidden rounded-full">
            <div
              className="progress-fill h-full rounded-full transition-[width] duration-500"
              style={{ width: `${pct}%` }}
            />
          </div>
          <ul className="space-y-1 text-xs text-[var(--text-tertiary)]">
            {(progressRows.length
              ? progressRows
              : trackedSources.map((source) => ({
                  source,
                  status: null as string | null,
                  error: null as string | null,
                }))
            ).map((row) => (
              <li key={row.source} className="flex items-center justify-between gap-2">
                <span>{SOURCE_LABELS[row.source]}</span>
                <span className="tabular-nums">
                  {row.status ? row.status.replaceAll("_", " ") : "waiting"}
                  {row.status === "failed" && row.error ? ` — ${row.error}` : ""}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {message ? <p className="mt-3 text-sm text-[var(--muted)]">{message}</p> : null}
    </div>
  );
}
