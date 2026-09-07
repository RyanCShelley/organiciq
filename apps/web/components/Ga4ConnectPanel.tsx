"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { syncJobWindow } from "@/lib/dates";

type Ga4Property = {
  property_id: string;
  display_name: string;
  account_name?: string;
};

export function Ga4ConnectPanel({
  clientId,
  connected,
  propertyId,
}: {
  clientId: string;
  connected: boolean;
  propertyId: string | null;
}) {
  const router = useRouter();
  const [properties, setProperties] = useState<Ga4Property[]>([]);
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

  async function loadProperties() {
    setPending(true);
    setMessage(null);
    const res = await fetch(`/api/proxy/ga4/properties?clientId=${encodeURIComponent(clientId)}`);
    const data = await res.json();
    setPending(false);
    if (!res.ok) {
      setMessage(typeof data.detail === "string" ? data.detail : "Failed to list GA4 properties");
      return;
    }
    setProperties(data);
  }

  async function saveProperty() {
    if (!selected) return;
    setPending(true);
    setMessage(null);
    const res = await fetch(`/api/proxy/ga4/property`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ clientId, property_id: selected }),
    });
    const text = await res.text();
    setPending(false);
    if (!res.ok) {
      setMessage(text || "Failed to save property");
      return;
    }
    setMessage("GA4 property saved");
    router.refresh();
  }

  async function syncDays(days: number) {
    setPending(true);
    setMessage(null);
    const res = await fetch("/api/proxy/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        clientId,
        source: "ga4",
        ...syncJobWindow(days),
      }),
    });
    if (!res.ok) {
      setPending(false);
      setMessage(await res.text());
      return;
    }
    setPending(false);
    setMessage(`Enqueued ga4 (${days} days)`);
    router.refresh();
  }

  return (
    <div className="mt-6 rounded-xl border border-[var(--border)] bg-[var(--card)] p-4">
      <h2 className="text-lg font-medium">Google Analytics 4</h2>
      <p className="mt-1 text-sm text-[var(--muted)]">
        Same Google Data OAuth as Search Console. Reconnect if Analytics was not granted, then pick a
        property and sync 14 or 90 days.
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
              onClick={loadProperties}
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
              Sync GA4 14 days
            </button>
            <button
              type="button"
              disabled={pending || !propertyId}
              onClick={() => syncDays(90)}
              className="rounded-lg border border-[var(--border)] px-4 py-2 text-sm disabled:opacity-50"
            >
              Sync GA4 90 days
            </button>
          </>
        ) : null}
      </div>

      {properties.length > 0 ? (
        <div className="mt-4 flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs text-[var(--muted)]">
            GA4 property
            <select
              className="min-w-[320px] rounded-lg border border-[var(--border)] bg-[#0b1220] px-3 py-2 text-sm text-white"
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
            >
              <option value="">Select…</option>
              {properties.map((p) => (
                <option key={p.property_id} value={p.property_id}>
                  {p.account_name ? `${p.account_name} / ` : ""}
                  {p.display_name} ({p.property_id})
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
