"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { syncJobWindow } from "@/lib/dates";

type Site = { site_url: string; permission_level?: string };

export function GscConnectPanel({
  clientId,
  connected,
  propertyId,
}: {
  clientId: string;
  connected: boolean;
  propertyId: string | null;
}) {
  const router = useRouter();
  const [sites, setSites] = useState<Site[]>([]);
  const [selected, setSelected] = useState(propertyId ?? "");
  const [message, setMessage] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function connectGoogle() {
    setPending(true);
    setMessage(null);
    const res = await fetch(`/api/proxy/oauth/google/start?clientId=${encodeURIComponent(clientId)}`);
    const data = await res.json();
    setPending(false);
    if (!res.ok) {
      setMessage(data.detail || "Failed to start OAuth");
      return;
    }
    window.location.href = data.authorization_url;
  }

  async function loadSites() {
    setPending(true);
    setMessage(null);
    const res = await fetch(`/api/proxy/gsc/sites?clientId=${encodeURIComponent(clientId)}`);
    const data = await res.json();
    setPending(false);
    if (!res.ok) {
      setMessage(typeof data.detail === "string" ? data.detail : "Failed to list sites");
      return;
    }
    setSites(data);
  }

  async function saveProperty() {
    if (!selected) return;
    setPending(true);
    setMessage(null);
    const res = await fetch(`/api/proxy/gsc/property`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ clientId, site_url: selected }),
    });
    const text = await res.text();
    setPending(false);
    if (!res.ok) {
      setMessage(text || "Failed to save property");
      return;
    }
    setMessage("Property saved");
    router.refresh();
  }

  async function syncDays(days: number) {
    setPending(true);
    setMessage(null);
    const window = syncJobWindow(days);

    for (const source of ["gsc_pages", "gsc_queries"]) {
      const res = await fetch("/api/proxy/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ clientId, source, ...window }),
      });
      if (!res.ok) {
        setPending(false);
        setMessage(await res.text());
        return;
      }
    }
    setPending(false);
    setMessage(`Enqueued gsc_pages + gsc_queries (${days} days)`);
    router.refresh();
  }

  return (
    <div className="mt-6 rounded-xl border border-[var(--border)] bg-[var(--card)] p-4">
      <h2 className="text-lg font-medium">Google Search Console</h2>
      <p className="mt-1 text-sm text-[var(--muted)]">
        Connect Google for Search Console and Analytics, select a property, then sync 14 or 90 days.
      </p>

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          disabled={pending}
          onClick={connectGoogle}
          className="btn btn-primary btn-sm disabled:opacity-50"
        >
          {connected ? "Reconnect Google" : "Connect Google"}
        </button>
        {connected ? (
          <>
            <button
              type="button"
              disabled={pending}
              onClick={loadSites}
              className="rounded-lg border border-[var(--border)] px-4 py-2 text-sm disabled:opacity-50"
            >
              Load properties
            </button>
            <button
              type="button"
              disabled={pending || !propertyId}
              onClick={() => syncDays(14)}
              className="rounded-lg border border-[var(--border)] px-4 py-2 text-sm disabled:opacity-50"
            >
              Sync GSC 14 days
            </button>
            <button
              type="button"
              disabled={pending || !propertyId}
              onClick={() => syncDays(90)}
              className="rounded-lg border border-[var(--border)] px-4 py-2 text-sm disabled:opacity-50"
            >
              Sync GSC 90 days
            </button>
          </>
        ) : null}
      </div>

      {sites.length > 0 ? (
        <div className="mt-4 flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs text-[var(--muted)]">
            GSC property
            <select
              className="min-w-[320px] rounded-lg border border-[var(--border)] bg-[#0b1220] px-3 py-2 text-sm text-white"
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
            >
              <option value="">Select…</option>
              {sites.map((s) => (
                <option key={s.site_url} value={s.site_url}>
                  {s.site_url}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            disabled={pending || !selected}
            onClick={saveProperty}
            className="btn btn-primary btn-sm disabled:opacity-50"
          >
            Save property
          </button>
        </div>
      ) : null}

      {propertyId ? (
        <p className="mt-3 text-sm text-[var(--muted)]">Selected property: {propertyId}</p>
      ) : null}
      {message ? <p className="mt-3 text-sm text-[var(--muted)]">{message}</p> : null}
    </div>
  );
}
