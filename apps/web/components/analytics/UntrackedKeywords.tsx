"use client";

import { Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { DataTable } from "@/components/analytics/DataTable";
import { Alert } from "@/components/ui/Alert";

export type UntrackedKeyword = {
  keyword: string;
  position: number | null;
  volume: number | null;
  difficulty: number | null;
  traffic: number | null;
  ranking_url: string | null;
  serp_features: string[];
};

export type UntrackedPayload = {
  fetched_at: string | null;
  domain_keywords: number;
  tracked_keywords: number;
  untracked_total: number;
  items: UntrackedKeyword[];
};

/** Matches the API's own cost note; shown before anyone spends it. */
const CREDITS_PER_RUN = 100;

function formatNum(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "—";
  return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(1);
}

function formatFetched(iso: string | null): string | null {
  if (!iso) return null;
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

/** How long to keep watching a queued run before giving up on it. */
const POLL_INTERVAL_MS = 4000;
const POLL_TIMEOUT_MS = 5 * 60 * 1000;

const ACTIVE_STATUSES = new Set([
  "queued",
  "fetching",
  "staging",
  "normalizing",
  "validating",
]);

export function UntrackedKeywords({
  clientId,
  data,
  loadError = null,
}: {
  clientId: string;
  data: UntrackedPayload;
  /** Read failed — distinct from "nothing fetched yet". */
  loadError?: string | null;
}) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [watching, setWatching] = useState(false);
  const startedAt = useRef<number | null>(null);

  const fetchedAt = formatFetched(data.fetched_at);

  /**
   * Watch the queue rather than telling people to refresh. "Refresh in a
   * moment" gave no way to tell a still-running job from a failed one from a
   * genuinely empty result — all three looked like the untouched panel.
   */
  const checkJob = useCallback(async () => {
    const res = await fetch(`/api/proxy/jobs?clientId=${encodeURIComponent(clientId)}`);
    if (!res.ok) return;
    const jobs: Array<{ source: string; status: string; error_message: string | null }> =
      await res.json();
    const latest = jobs.find((job) => job.source === "se_ranking_domain_keywords");
    if (!latest) return;

    if (ACTIVE_STATUSES.has(latest.status)) return;

    setWatching(false);
    startedAt.current = null;
    if (latest.status === "failed") {
      setMessage(null);
      setError(latest.error_message || "The lookup failed. Check Sync jobs for details.");
      return;
    }
    setError(null);
    setMessage("Lookup finished.");
    router.refresh();
  }, [clientId, router]);

  useEffect(() => {
    if (!watching) return;
    const timer = setInterval(() => {
      if (startedAt.current && Date.now() - startedAt.current > POLL_TIMEOUT_MS) {
        setWatching(false);
        startedAt.current = null;
        setMessage(null);
        setError("Still running after 5 minutes — check Sync jobs.");
        return;
      }
      void checkJob();
    }, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [watching, checkJob]);

  async function run() {
    setError(null);
    setMessage(null);
    setPending(true);

    const today = new Date().toISOString().slice(0, 10);
    const res = await fetch("/api/proxy/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        clientId,
        source: "se_ranking_domain_keywords",
        start_date: today,
        end_date: today,
      }),
    });

    setPending(false);
    if (!res.ok) {
      setError((await res.text()) || "Failed to queue the lookup");
      return;
    }
    setMessage("Queued — watching for results…");
    startedAt.current = Date.now();
    setWatching(true);
  }

  return (
    <div className="card mt-4 p-[var(--card-padding)]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="font-[family-name:var(--font-display)] text-[15px] font-extrabold text-[var(--text-primary)]">
            Untracked keywords
          </h3>
          <p className="mt-1 text-[12.5px] text-[var(--text-tertiary)]">
            {fetchedAt ? (
              <>
                {data.untracked_total.toLocaleString()} of{" "}
                {data.domain_keywords.toLocaleString()} ranking keywords aren&rsquo;t on the
                watch list · last checked {fetchedAt}
              </>
            ) : (
              <>
                Finds keywords the domain already ranks for that aren&rsquo;t tracked. Costs{" "}
                {CREDITS_PER_RUN} SE Ranking credits per run, so it only runs when you ask.
              </>
            )}
          </p>
        </div>
        <button
          type="button"
          className="btn btn-secondary shrink-0 gap-2"
          onClick={run}
          disabled={pending || watching}
          title={`Uses ${CREDITS_PER_RUN} SE Ranking credits`}
        >
          <Search className="h-3.5 w-3.5" aria-hidden />
          {pending
            ? "Queueing…"
            : watching
              ? "Running…"
              : fetchedAt
                ? "Re-run"
                : "Find untracked keywords"}
        </button>
      </div>

      {loadError ? (
        <Alert variant="danger" className="mt-3">
          Could not load untracked keywords: {loadError}
        </Alert>
      ) : null}
      {error ? (
        <Alert variant="danger" className="mt-3">
          {error}
        </Alert>
      ) : null}
      {message ? (
        <Alert variant="success" className="mt-3">
          {message}
        </Alert>
      ) : null}

      {data.items.length > 0 ? (
        <div className="mt-3">
          <DataTable
            columns={[
              {
                key: "keyword",
                header: "Keyword",
                render: (row) => (
                  <span className="block max-w-[22rem] truncate" title={row.keyword}>
                    {row.keyword}
                  </span>
                ),
              },
              {
                key: "volume",
                header: "Volume",
                align: "right",
                render: (row) => formatNum(row.volume),
              },
              {
                key: "position",
                header: "Position",
                align: "right",
                render: (row) => formatNum(row.position),
              },
              {
                key: "difficulty",
                header: "Difficulty",
                align: "right",
                render: (row) => formatNum(row.difficulty),
              },
              {
                key: "traffic",
                header: "Traffic",
                align: "right",
                render: (row) => formatNum(row.traffic),
              },
              {
                key: "ranking_url",
                header: "Ranking URL",
                render: (row) =>
                  row.ranking_url ? (
                    <span
                      className="block max-w-[18rem] truncate font-[family-name:var(--font-mono)] text-xs text-[var(--text-tertiary)]"
                      title={row.ranking_url}
                    >
                      {row.ranking_url}
                    </span>
                  ) : (
                    <span className="text-[var(--text-tertiary)]">—</span>
                  ),
              },
            ]}
            rows={data.items}
            getRowKey={(row) => row.keyword}
          />
          {data.untracked_total > data.items.length ? (
            <p className="mt-2 text-xs text-[var(--text-tertiary)]">
              Showing the top {data.items.length.toLocaleString()} by volume of{" "}
              {data.untracked_total.toLocaleString()}.
            </p>
          ) : null}
        </div>
      ) : fetchedAt ? (
        <Alert variant="info" className="mt-3">
          Every keyword the domain ranks for is already on the watch list.
        </Alert>
      ) : null}
    </div>
  );
}
