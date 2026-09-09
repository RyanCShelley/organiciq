"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { SearchableSelect } from "@/components/SearchableSelect";
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

  const propertyOptions = useMemo(
    () =>
      properties.map((p) => ({
        value: p.property_id,
        label: `${p.account_name ? `${p.account_name} / ` : ""}${p.display_name} (${p.property_id})`,
      })),
    [properties],
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
        Google is shared across clients — connect once, then pick this client&apos;s GA4 property and
        sync. Reconnect if Analytics access was not granted.
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
          <SearchableSelect
            label="GA4 property"
            options={propertyOptions}
            value={selected}
            onChange={setSelected}
            searchPlaceholder="Search properties…"
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
        <p className="mt-3 text-sm text-[var(--muted)]">Selected property: {propertyId}</p>
      ) : null}
      {message ? <p className="mt-3 text-sm text-[var(--muted)]">{message}</p> : null}
    </div>
  );
}
