"use client";

import { useEffect, useRef, useState, useTransition } from "react";

import { pullStatusAction, startPullAction } from "@/app/(app)/admin/actions";
import type { PullSource, PullStatus } from "@/lib/admin";

const num = (n: number) => n.toLocaleString();
const day = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
const month = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", year: "numeric" });

const span = (secs: number | null) => {
  if (secs == null) return null;
  if (secs < 90) return "about a minute";
  const m = Math.round(secs / 60);
  return m < 90 ? `about ${m} minutes` : `about ${(m / 60).toFixed(1)} hours`;
};

const STATE: Record<PullSource["state"], { text: string; cls: string }> = {
  not_started: { text: "Not pulled yet", cls: "text-[var(--text-tertiary)]" },
  queued: { text: "Waiting", cls: "text-[var(--text-secondary)]" },
  running: { text: "Pulling", cls: "text-blue-700" },
  done: { text: "Done", cls: "text-green-700" },
  partial: { text: "Done, with gaps", cls: "text-amber-700" },
  failed: { text: "Failed", cls: "text-red-700" },
};

const reach = (s: PullSource) => (s.reach.startsWith("today") || s.from === s.to ? s.reach : `${s.reach}, ${month(s.from)} to ${day(s.to)}`);

/** Pull every connected source for one client, and show where the pull stands. Admin only. */
export function PullPanel({ clientId }: { clientId: string }) {
  const [status, setStatus] = useState<PullStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const live = useRef(true);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = async () => {
    const r = await pullStatusAction(clientId);
    if (!live.current) return;
    if (r.ok) {
      setError(null);
      setStatus(r.value);
      watch(r.value);
    } else setError(r.error);
  };
  // Check again every 5 seconds, but only while something is pulling.
  const watch = (s: PullStatus) => {
    if (timer.current) clearTimeout(timer.current);
    if (s.running && live.current) timer.current = setTimeout(load, 5000);
  };

  useEffect(() => {
    live.current = true;
    load();
    return () => {
      live.current = false;
      if (timer.current) clearTimeout(timer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId]);

  const begin = () =>
    start(async () => {
      setError(null);
      const r = await startPullAction(clientId);
      if (r.ok) {
        setStatus(r.value);
        watch(r.value);
      } else setError(r.error);
    });

  const pct = status && status.jobs_total ? Math.round((status.jobs_done / status.jobs_total) * 100) : 0;
  const left = status ? span(status.seconds_left) : null;
  const headline = !status
    ? "Loading…"
    : status.running
      ? `${status.jobs_done} of ${status.jobs_total} sources done${left ? `, ${left} left` : ". Time left shows after this install has finished one pull"}.`
      : status.finished
        ? `Finished. All ${status.jobs_total} sources are in.`
        : status.failed.length
          ? `Stopped. ${status.failed.join(", ")} failed.`
          : status.jobs_done > 0
            ? `Not pulling now. ${status.jobs_done} of ${status.jobs_total} sources are in from the last pull.`
            : status.sources.length
              ? "Nothing pulled yet. Pull data fetches every source below."
              : "Choose a site or property for at least one source below, then pull.";

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold">Pull data</h2>
          <p className="mt-0.5 text-sm text-[var(--text-secondary)]">
            {headline}
            {status?.running && status.jobs_ahead > 0 ? ` ${status.jobs_ahead} job${status.jobs_ahead === 1 ? "" : "s"} for other clients are ahead in the queue.` : ""}
          </p>
        </div>
        <button
          type="button"
          onClick={begin}
          disabled={pending || !status || status.running || status.sources.length === 0}
          className="rounded-lg bg-[var(--brand-teal)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-40"
        >
          {pending ? "Starting…" : status?.running ? "Pulling…" : status?.finished || status?.failed.length ? "Pull again" : "Pull data"}
        </button>
      </div>
      {status && (status.running || status.finished) ? (
        <div className="mt-3 h-2 overflow-hidden rounded-full bg-[var(--border)]" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
          <div className="h-full bg-[var(--brand-teal)] transition-all" style={{ width: `${pct}%` }} />
        </div>
      ) : null}
      {status && status.sources.length ? (
        <ul className="mt-3 divide-y divide-[var(--border)] rounded-lg border border-[var(--border)] bg-white text-sm">
          {status.sources.map((s) => (
            <li key={s.source} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5 px-3 py-2">
              <div>
                <span className="font-semibold">{s.label}</span>
                <span className="ml-2 text-xs text-[var(--text-tertiary)]">{reach(s)}</span>
              </div>
              <div className="text-xs">
                <span className={`font-semibold ${STATE[s.state].cls}`}>{STATE[s.state].text}</span>
                {s.state === "running" && s.stage ? ` · ${s.stage}` : ""}
                {s.seconds_left != null && (s.state === "running" || s.state === "queued") ? ` · ${span(s.seconds_left)} left` : ""}
                {s.rows != null && (s.state === "done" || s.state === "partial") ? ` · ${num(s.rows)} rows` : ""}
                {s.error ? <div className="mt-0.5 text-red-700">{s.error}</div> : null}
              </div>
            </li>
          ))}
        </ul>
      ) : null}
      {error ? <p role="alert" className="mt-2 text-sm font-semibold text-red-700">{error}</p> : null}
    </div>
  );
}
