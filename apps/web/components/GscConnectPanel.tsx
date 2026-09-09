"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { SearchableSelect } from "@/components/SearchableSelect";

type Site = { site_url: string; permission_level?: string };

export function GscConnectPanel({
  clientId,
  connected,
  propertyId,
  secondarySiteUrls = [],
}: {
  clientId: string;
  connected: boolean;
  propertyId: string | null;
  secondarySiteUrls?: string[];
}) {
  const router = useRouter();
  const [sites, setSites] = useState<Site[]>([]);
  const [selectedPrimary, setSelectedPrimary] = useState(propertyId ?? "");
  const [selectedSecondary, setSelectedSecondary] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const attached = useMemo(() => {
    const values = new Set<string>();
    if (propertyId) values.add(propertyId);
    for (const url of secondarySiteUrls) values.add(url);
    return values;
  }, [propertyId, secondarySiteUrls]);

  const primaryOptions = useMemo(
    () => sites.map((s) => ({ value: s.site_url, label: s.site_url })),
    [sites],
  );

  const secondaryOptions = useMemo(
    () =>
      sites
        .filter((s) => !attached.has(s.site_url) || s.site_url === selectedSecondary)
        .map((s) => ({ value: s.site_url, label: s.site_url })),
    [sites, attached, selectedSecondary],
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

  async function saveProperty(role: "primary" | "secondary", siteUrl: string) {
    if (!siteUrl) return;
    setPending(true);
    setMessage(null);
    const res = await fetch(`/api/proxy/gsc/property`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ clientId, site_url: siteUrl, role }),
    });
    const text = await res.text();
    setPending(false);
    if (!res.ok) {
      setMessage(text || "Failed to save property");
      return;
    }
    setMessage(
      role === "primary"
        ? "Primary property saved — use Sync 90 days below to pull data."
        : "Secondary property saved — re-run Sync 90 days to pull historical data.",
    );
    if (role === "secondary") setSelectedSecondary("");
    router.refresh();
  }

  async function removeProperty(siteUrl: string) {
    setPending(true);
    setMessage(null);
    const res = await fetch(`/api/proxy/gsc/property`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ clientId, site_url: siteUrl }),
    });
    const text = await res.text();
    setPending(false);
    if (!res.ok) {
      setMessage(text || "Failed to remove property");
      return;
    }
    setMessage("Property removed.");
    router.refresh();
  }

  return (
    <div className="mt-6 rounded-xl border border-[var(--border)] bg-[var(--card)] p-4">
      <h2 className="text-lg font-medium">Google Search Console</h2>
      <p className="mt-1 text-sm text-[var(--muted)]">
        Connect Google once for the workspace, then pick a primary Search Console property. Add a
        secondary property for an old domain — history is rewritten onto this client&apos;s domain,
        and the primary wins when both report the same day or page.
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
            {propertyId ? "Load / change properties" : "Load properties"}
          </button>
        ) : null}
      </div>

      {sites.length > 0 ? (
        <div className="mt-4 space-y-4">
          <div className="flex flex-wrap items-end gap-3">
            <SearchableSelect
              label="Primary GSC property"
              options={primaryOptions}
              value={selectedPrimary}
              onChange={setSelectedPrimary}
              searchPlaceholder="Search sites…"
            />
            <button
              type="button"
              disabled={pending || !selectedPrimary}
              onClick={() => saveProperty("primary", selectedPrimary)}
              className="btn btn-primary btn-sm disabled:opacity-50"
            >
              Save primary
            </button>
          </div>

          {propertyId ? (
            <div className="flex flex-wrap items-end gap-3">
              <SearchableSelect
                label="Add secondary GSC property"
                options={secondaryOptions}
                value={selectedSecondary}
                onChange={setSelectedSecondary}
                searchPlaceholder="Search old domain…"
              />
              <button
                type="button"
                disabled={pending || !selectedSecondary}
                onClick={() => saveProperty("secondary", selectedSecondary)}
                className="btn btn-primary btn-sm disabled:opacity-50"
              >
                Add secondary
              </button>
            </div>
          ) : null}
        </div>
      ) : null}

      {propertyId ? (
        <div className="mt-4 space-y-2 text-sm">
          <p className="text-[var(--muted)]">
            Primary: <span className="text-[var(--text-primary)]">{propertyId}</span>
          </p>
          {secondarySiteUrls.length > 0 ? (
            <ul className="space-y-1">
              {secondarySiteUrls.map((url) => (
                <li key={url} className="flex flex-wrap items-center gap-2 text-[var(--muted)]">
                  <span>
                    Secondary: <span className="text-[var(--text-primary)]">{url}</span>
                  </span>
                  <button
                    type="button"
                    disabled={pending}
                    onClick={() => removeProperty(url)}
                    className="rounded border border-[var(--border)] px-2 py-0.5 text-xs disabled:opacity-50"
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-[var(--muted)]">No secondary properties yet.</p>
          )}
        </div>
      ) : null}
      {message ? <p className="mt-3 text-sm text-[var(--muted)]">{message}</p> : null}
    </div>
  );
}
