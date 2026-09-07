"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

const SOURCES = [
  "gsc_pages",
  "gsc_queries",
  "ga4",
  "se_ranking_search",
  "se_ranking_ai",
  "se_ranking_audit",
  "unknown_test",
];

export function EnqueueJobForm({ clientId }: { clientId: string }) {
  const router = useRouter();
  const [source, setSource] = useState("gsc_pages");
  const [message, setMessage] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setPending(true);
    setMessage(null);

    const to = new Date();
    const from = new Date();
    from.setUTCDate(to.getUTCDate() - 13);

    const res = await fetch("/api/proxy/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        clientId,
        source,
        start_date: from.toISOString().slice(0, 10),
        end_date: to.toISOString().slice(0, 10),
      }),
    });

    const text = await res.text();
    setPending(false);
    if (!res.ok) {
      setMessage(text || "Failed to enqueue");
      return;
    }
    setMessage("Job enqueued");
    router.refresh();
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-wrap items-end gap-3">
      <label className="flex flex-col gap-1 text-xs text-[var(--muted)]">
        Source
        <select
          className="rounded-lg border border-[var(--border)] bg-[#0b1220] px-3 py-2 text-sm text-white"
          value={source}
          onChange={(e) => setSource(e.target.value)}
        >
          {SOURCES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </label>
      <button
        type="submit"
        disabled={pending}
        className="btn btn-primary disabled:opacity-50"
      >
        {pending ? "Enqueueing…" : "Enqueue sync job"}
      </button>
      {message ? <p className="text-sm text-[var(--muted)]">{message}</p> : null}
    </form>
  );
}
