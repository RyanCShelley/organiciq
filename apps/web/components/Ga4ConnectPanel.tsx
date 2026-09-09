"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { SearchableSelect } from "@/components/SearchableSelect";

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
    setMessage("GA4 property saved — use Sync GA4 below to pull data.");
    router.refresh();
  }

  return (
    <div className="mt-6 rounded-xl border border-[var(--border)] bg-[var(--card)] p-4">
      <h2 className="text-lg font-medium">Google Analytics 4</h2>
      <p className="mt-1 text-sm text-[var(--muted)]">
        Same Google connection as Search Console. Pick this client&apos;s GA4 property (reconnect if
        Analytics access was not granted).
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
            onClick={loadProperties}
            className="rounded-lg border border-[var(--border)] px-4 py-2 text-sm disabled:opacity-50"
          >
            {propertyId ? "Change property" : "Load properties"}
          </button>
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
        <p className="mt-3 text-sm text-[var(--muted)]">Connected property: {propertyId}</p>
      ) : null}
      {message ? <p className="mt-3 text-sm text-[var(--muted)]">{message}</p> : null}
    </div>
  );
}
