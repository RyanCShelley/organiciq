"use client";

import { RefreshCw } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { Alert } from "@/components/ui/Alert";

/**
 * Run a site crawl on demand.
 *
 * Crawls are scheduled weekly and staggered, so without this the only way to
 * refresh a client after changing its domain or declaring a sitemap was to wait
 * for its slot to come round.
 */

const POLL_INTERVAL_MS = 5000;
/** A 478-page site took about three and a half minutes; leave generous room. */
const POLL_TIMEOUT_MS = 20 * 60 * 1000;

const ACTIVE_STATUSES = new Set([
  "queued",
  "fetching",
  "staging",
  "normalizing",
  "validating",
]);

export function RunCrawlButton({ clientId }: { clientId: string }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [watching, setWatching] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const startedAt = useRef<number | null>(null);

  const checkJob = useCallback(async () => {
    const res = await fetch(`/api/proxy/jobs?clientId=${encodeURIComponent(clientId)}`);
    if (!res.ok) return;
    const jobs: Array<{ source: string; status: string; error_message: string | null }> =
      await res.json();
    const latest = jobs.find((job) => job.source === "site_crawl");
    if (!latest || ACTIVE_STATUSES.has(latest.status)) return;

    setWatching(false);
    startedAt.current = null;
    if (latest.status === "failed") {
      setMessage(null);
      setError(latest.error_message || "The crawl failed. Check Sync jobs for details.");
      return;
    }
    setError(null);
    // The job's own note says how many pages, how much schema, and what
    // happened with the sitemap — which is exactly what someone re-running a
    // crawl wants to know.
    setMessage(latest.error_message || "Crawl finished.");
    router.refresh();
  }, [clientId, router]);

  useEffect(() => {
    if (!watching) return;
    const timer = setInterval(() => {
      if (startedAt.current && Date.now() - startedAt.current > POLL_TIMEOUT_MS) {
        setWatching(false);
        startedAt.current = null;
        setMessage(null);
        setError("Still running after 20 minutes — check Sync jobs.");
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
        source: "site_crawl",
        start_date: today,
        end_date: today,
      }),
    });

    setPending(false);
    if (!res.ok) {
      setError((await res.text()) || "Failed to queue the crawl");
      return;
    }
    setMessage("Crawling — this takes a few minutes on a large site.");
    startedAt.current = Date.now();
    setWatching(true);
  }

  return (
    <div className="flex flex-col items-end gap-2">
      <button
        type="button"
        className="btn btn-secondary gap-2"
        onClick={run}
        disabled={pending || watching}
      >
        <RefreshCw
          className={`h-3.5 w-3.5 ${watching ? "animate-spin" : ""}`}
          aria-hidden
        />
        {pending ? "Queueing…" : watching ? "Crawling…" : "Run crawl"}
      </button>

      {error ? (
        <Alert variant="danger" className="max-w-[34rem]">
          {error}
        </Alert>
      ) : null}
      {message ? (
        <Alert variant={watching ? "info" : "success"} className="max-w-[34rem]">
          {message}
        </Alert>
      ) : null}
    </div>
  );
}
