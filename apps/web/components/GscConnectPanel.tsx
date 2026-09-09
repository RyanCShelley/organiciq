"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { SearchableSelect } from "@/components/SearchableSelect";

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

  const siteOptions = useMemo(
    () => sites.map((s) => ({ value: s.site_url, label: s.site_url })),
    [sites],
  );

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
    setMessage("Property saved — use Sync 90 days below to pull data.");
    router.refresh();
  }

  return (
    <div className="mt-6 rounded-xl border border-[var(--border)] bg-[var(--card)] p-4">
      <h2 className="text-lg font-medium">Google Search Console</h2>
      <p className="mt-1 text-sm text-[var(--muted)]">
        Connect Google once for the workspace, then pick this client&apos;s Search Console property.
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
          <button
            type="button"
            disabled={pending}
            onClick={loadSites}
            className="rounded-lg border border-[var(--border)] px-4 py-2 text-sm disabled:opacity-50"
          >
            {propertyId ? "Change property" : "Load properties"}
          </button>
        ) : null}
      </div>

      {sites.length > 0 ? (
        <div className="mt-4 flex flex-wrap items-end gap-3">
          <SearchableSelect
            label="GSC property"
            options={siteOptions}
            value={selected}
            onChange={setSelected}
            searchPlaceholder="Search sites…"
          />
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
        <p className="mt-3 text-sm text-[var(--muted)]">Connected property: {propertyId}</p>
      ) : null}
      {message ? <p className="mt-3 text-sm text-[var(--muted)]">{message}</p> : null}
    </div>
  );
}
