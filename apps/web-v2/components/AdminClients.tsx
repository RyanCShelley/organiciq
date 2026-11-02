"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";

import { deleteClientAction, deletePreviewAction, pullStatusAction, startPullAction } from "@/app/(app)/admin/actions";
import type { AdminClient, DeletePreview, PullSource, PullStatus } from "@/lib/admin";

const day = (iso: string | null) =>
  iso ? new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" }) : "none";
const num = (n: number) => n.toLocaleString();

function Chip({ on, children }: { on: boolean; children: React.ReactNode }) {
  return (
    <span className={`whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-semibold ${on ? "bg-green-100 text-green-800" : "bg-[var(--bg)] text-[var(--text-tertiary)]"}`}>
      {children}
    </span>
  );
}

function DeletePanel({ client, onDone, onCancel }: { client: AdminClient; onDone: (message: string) => void; onCancel: () => void }) {
  const [preview, setPreview] = useState<DeletePreview | null>(null);
  const [typed, setTyped] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();

  useEffect(() => {
    let live = true;
    deletePreviewAction(client.id).then((r) => {
      if (!live) return;
      if (r.ok) setPreview(r.value);
      else setError(r.error);
    });
    return () => {
      live = false;
    };
  }, [client.id]);

  const remove = () =>
    start(async () => {
      setError(null);
      const r = await deleteClientAction(client.id, typed);
      if (r.ok) onDone(`${r.value.deleted} was deleted (${num(r.value.rows)} rows).`);
      else setError(r.error);
    });

  return (
    <div className="mt-3 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-900">
      <p className="font-semibold">Delete {client.name} for good?</p>
      {preview ? (
        <ul className="mt-2 list-disc space-y-0.5 pl-5">
          <li>{num(preview.synced_rows)} rows of synced data (Search Console, GA4, SE Ranking, crawl, Bing)</li>
          <li>{num(preview.setup_rows)} set-up rows: baselines, conversions, the watchlist, tasks and AI visibility runs</li>
          <li>{preview.integrations} connection{preview.integrations === 1 ? "" : "s"}, {preview.team_access} team access entr{preview.team_access === 1 ? "y" : "ies"}, {preview.annotations} annotation{preview.annotations === 1 ? "" : "s"}</li>
        </ul>
      ) : error ? null : (
        <p className="mt-2">Counting what would be removed…</p>
      )}
      <p className="mt-2">This cannot be undone, and it removes the client from the live tool too. Type <strong>{client.name}</strong> to confirm.</p>
      <input
        value={typed}
        onChange={(e) => setTyped(e.target.value)}
        aria-label="Type the client's name to confirm"
        className="mt-2 w-full max-w-sm rounded-lg border border-red-300 bg-white px-3 py-2 text-sm"
      />
      {error ? <p role="alert" className="mt-2 font-semibold">{error}</p> : null}
      <div className="mt-3 flex gap-2">
        <button type="button" onClick={remove} disabled={pending || typed !== client.name} className="rounded-lg bg-red-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40">
          {pending ? "Deleting…" : "Delete forever"}
        </button>
        <button type="button" onClick={onCancel} disabled={pending} className="rounded-lg border border-red-300 bg-white px-4 py-2 text-sm font-semibold">
          Cancel
        </button>
      </div>
    </div>
  );
}

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
const range = (a: string, b: string) => (a === b ? day(a) : `${new Date(`${a}T00:00:00`).toLocaleDateString("en-US", { month: "short", year: "numeric" })} to ${new Date(`${b}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}`);

function PullPanel({ client, onClose }: { client: AdminClient; onClose: () => void }) {
  const [status, setStatus] = useState<PullStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();

  useEffect(() => {
    let live = true;
    const load = async () => {
      const r = await pullStatusAction(client.id);
      if (!live) return;
      if (r.ok) setStatus(r.value);
      else setError(r.error);
    };
    load();
    const timer = setInterval(load, 5000);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, [client.id]);

  const begin = () =>
    start(async () => {
      setError(null);
      const r = await startPullAction(client.id);
      if (r.ok) setStatus(r.value);
      else setError(r.error);
    });

  const pct = status && status.jobs_total ? Math.round((status.jobs_done / status.jobs_total) * 100) : 0;
  const left = status ? span(status.seconds_left) : null;
  return (
    <div className="mt-3 rounded-lg border border-[var(--border)] bg-[var(--bg)] p-4 text-sm">
      <div className="flex items-center justify-between gap-3">
        <p className="font-semibold">Pull data for {client.name}</p>
        <button type="button" onClick={onClose} className="text-xs font-semibold text-[var(--text-secondary)] hover:underline">Close</button>
      </div>
      {status ? (
        <>
          <p className="mt-2">
            {status.running
              ? `${status.jobs_done} of ${status.jobs_total} sources done${left ? `, ${left} left` : ", time left unknown until this install has finished a pull"}.`
              : status.finished
                ? `Finished: all ${status.jobs_total} sources are in.`
                : status.failed.length
                  ? `Stopped: ${status.failed.join(", ")} failed.`
                  : status.jobs_done > 0
                    ? `Not pulling now. ${status.jobs_done} of ${status.jobs_total} sources are in from the last pull.`
                    : "Nothing is pulling. Pulling starts from the sources connected in Settings."}
            {status.running && status.jobs_ahead > 0 ? ` ${status.jobs_ahead} job${status.jobs_ahead === 1 ? "" : "s"} for other clients are ahead in the queue.` : ""}
          </p>
          {status.running || status.finished ? (
            <div className="mt-2 h-2 overflow-hidden rounded-full bg-[var(--border)]" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
              <div className="h-full bg-[var(--brand-teal)]" style={{ width: `${pct}%` }} />
            </div>
          ) : null}
          <ul className="mt-3 divide-y divide-[var(--border)] rounded-lg border border-[var(--border)] bg-white">
            {status.sources.map((s) => (
              <li key={s.source} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5 px-3 py-2">
                <div>
                  <span className="font-semibold">{s.label}</span>
                  <span className="ml-2 text-xs text-[var(--text-tertiary)]">{s.reach.startsWith("today") ? s.reach : `${s.reach}: ${range(s.from, s.to)}`}</span>
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
            {status.sources.length === 0 ? <li className="px-3 py-2 text-[var(--text-tertiary)]">No data source is connected yet.</li> : null}
          </ul>
        </>
      ) : error ? null : (
        <p className="mt-2">Loading…</p>
      )}
      {error ? <p role="alert" className="mt-2 font-semibold text-red-700">{error}</p> : null}
      <div className="mt-3">
        <button
          type="button"
          onClick={begin}
          disabled={pending || !status || status.running || status.sources.length === 0}
          className="rounded-lg bg-[var(--brand-teal)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-40"
        >
          {pending ? "Starting…" : status?.running ? "Pulling…" : status?.finished || status?.failed.length ? "Pull again" : "Pull data"}
        </button>
      </div>
    </div>
  );
}

export function AdminClients({ clients }: { clients: AdminClient[] }) {
  const router = useRouter();
  const [deleting, setDeleting] = useState<string | null>(null);
  const [pulling, setPulling] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const shown = clients.filter((c) => !filter || c.name.toLowerCase().includes(filter.toLowerCase()) || c.domain.toLowerCase().includes(filter.toLowerCase()));

  return (
    <div className="space-y-4">
      {message ? <p className="rounded-lg bg-green-50 p-3 text-sm text-green-800">{message}</p> : null}
      <input
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        placeholder="Find a client"
        aria-label="Find a client"
        className="w-full max-w-xs rounded-lg border border-[var(--border)] bg-white px-3 py-2 text-sm"
      />
      <ul className="divide-y divide-[var(--border)] rounded-xl border border-[var(--border)] bg-[var(--surface)]">
        {shown.map((c) => (
          <li key={c.id} className="p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="font-semibold">{c.name}</div>
                <div className="text-xs text-[var(--text-secondary)]">
                  {c.domain} · {c.tier ?? "no plan"}
                  {c.status ? ` · ${c.status}` : ""}
                  {c.business_model ? ` · ${c.business_model.replace("_", " ")}` : ""}
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  <Chip on={c.integrations > 0}>Google {c.integrations > 0 ? "connected" : "not connected"}</Chip>
                  <Chip on={c.bing}>Bing</Chip>
                  <Chip on={c.watchlist_keywords > 0}>{c.watchlist_keywords > 0 ? `Watchlist ${c.watchlist_keywords}` : "No watchlist"}</Chip>
                  <Chip on={c.has_baseline}>{c.has_baseline ? "Baseline" : "No baseline"}</Chip>
                  <Chip on={c.team > 0}>{c.team} on the team</Chip>
                </div>
                <div className="mt-1 text-xs text-[var(--text-tertiary)]">
                  Search Console through {day(c.gsc_through)} · GA4 through {day(c.ga4_through)}
                </div>
              </div>
              <div className="flex items-center gap-3 text-sm">
                <button type="button" onClick={() => setPulling(pulling === c.id ? null : c.id)} className="font-semibold text-[var(--brand-teal)] hover:underline">
                  Pull data
                </button>
                <Link href={`/${c.slug}/settings`} className="font-semibold text-[var(--brand-teal)] hover:underline">Settings</Link>
                <Link href={`/${c.slug}/review`} className="font-semibold text-[var(--brand-teal)] hover:underline">Open</Link>
                <button
                  type="button"
                  onClick={() => {
                    setMessage(null);
                    setDeleting(deleting === c.id ? null : c.id);
                  }}
                  className="font-semibold text-red-700 hover:underline"
                >
                  Delete
                </button>
              </div>
            </div>
            {pulling === c.id ? <PullPanel client={c} onClose={() => setPulling(null)} /> : null}
            {deleting === c.id ? (
              <DeletePanel
                client={c}
                onCancel={() => setDeleting(null)}
                onDone={(m) => {
                  setDeleting(null);
                  setMessage(m);
                  router.refresh();
                }}
              />
            ) : null}
          </li>
        ))}
        {shown.length === 0 ? <li className="p-4 text-sm text-[var(--text-tertiary)]">No client matches.</li> : null}
      </ul>
    </div>
  );
}
