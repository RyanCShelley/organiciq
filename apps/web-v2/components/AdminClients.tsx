"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";

import { deleteClientAction, deletePreviewAction } from "@/app/(app)/admin/actions";
import type { AdminClient, DeletePreview } from "@/lib/admin";

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

export function AdminClients({ clients }: { clients: AdminClient[] }) {
  const router = useRouter();
  const [deleting, setDeleting] = useState<string | null>(null);
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
                <Link href={`/${c.slug}/settings/connections`} className="font-semibold text-[var(--brand-teal)] hover:underline">Connect &amp; pull</Link>
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
